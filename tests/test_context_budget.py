"""Tests for the context-budget Stop hook."""

import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, '..', 'scripts')
sys.path.insert(0, SCRIPTS)

SPEC = importlib.util.spec_from_file_location(
    'context_budget', os.path.join(SCRIPTS, 'context_budget.py'))
cb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cb)

import budget  # noqa: E402  (path must be set before this import resolves)
import statusline as sl  # noqa: E402  (same)


def test_every_model_is_held_to_the_same_cost_per_turn():
    """Verify targets are derived from price, not set per model by hand.

    Mutation: hard-coding a token target per model, which is how a 2x
    model ends up with the same room as opus and quietly costs double.
    Oracle: differential - at a slow growth rate, where the compaction
    cycle floor does not bind, each tier's derived target must reproduce
    the declared dollar budget when run back through the cost formula.
    """
    assert budget.model_tier('claude-fable-5') == 'fable'
    assert budget.model_tier('claude-opus-5') == 'opus'
    slow = 1_200
    for tier in ('fable', 'opus'):
        target = budget.target_tokens(tier, slow)
        assert abs(budget.cost_per_turn(target, tier)
                   - budget.COST_PER_TURN_TARGET) < 0.02
    assert (budget.target_tokens('fable', slow)
            < budget.target_tokens('opus', slow))


def test_a_cheap_model_is_left_alone(monkeypatch, capsys, tmp_path):
    """Verify a Sonnet or Haiku session raises no warning at all.

    Mutation: model_tier falling back to 'opus' for an unlisted model,
    which is what makes a plugin nag about a session whose whole cost is
    a few cents and train the user to ignore it.
    Oracle: a spy on stdout - the same 600K transcript prints on opus and
    prints nothing on sonnet.
    """
    monkeypatch.setattr(cb, 'STATE_DIR', str(tmp_path / 'state'))
    assert budget.model_tier('claude-sonnet-5') is None
    assert budget.model_tier('claude-haiku-4-5') is None

    def run(model, session):
        path = tmp_path / f'{session}.jsonl'
        path.write_text(json.dumps({
            'type': 'assistant',
            'message': {
                'id': 'm1', 'role': 'assistant', 'model': model,
                'usage': {'cache_read_input_tokens': 600_000,
                          'cache_creation_input_tokens': 0, 'input_tokens': 0},
                },
            }))
        payload = {'session_id': session, 'transcript_path': str(path)}
        monkeypatch.setattr(sys, 'stdin', _Stdin(json.dumps(payload)))
        cb.main()
        return capsys.readouterr().out.strip()

    assert run('claude-opus-5', 'a')
    assert run('claude-sonnet-5', 'b') == ''


def test_the_over_band_holds_the_dollar_limit_and_the_order():
    """Verify over-budget means the dollar limit and never undercuts the
    target.

    Mutation: restoring over = target * (limit / target ratio), which on
    a fast-growing fable session moves "overpriced" from $2.20 to $5 a
    turn because the cycle floor inflates the target it scales; or
    dropping the max() clamp, which puts the loudest band below the
    budget one.
    Oracle: the declared dollar limit run back through the cost formula
    where cost decides, and the target itself where the cycle floor has
    passed the limit.
    """
    for tier in budget.PRICE_PER_MTOK:
        over = budget.over_budget_tokens(tier, 1_900)
        assert abs(budget.cost_per_turn(over, tier)
                   - budget.COST_PER_TURN_LIMIT) < 0.02
        for per_call in (1_200, 1_900, 2_500, 6_300, 10_000):
            assert (budget.over_budget_tokens(tier, per_call)
                    >= budget.target_tokens(tier, per_call))
    assert (budget.over_budget_tokens('fable', 6_300)
            == budget.target_tokens('fable', 6_300))


def test_a_floor_inflated_target_is_announced_at_its_real_cost():
    """Verify the loudest band fires at a floor-dominated target, in
    dollars.

    Mutation: scaling the over band with the inflated target (the
    shipped defect), which lets a fable session reading 6K tokens a call
    march to $5 a turn before the overpriced warning fires.
    Oracle: hand-computed - at 6,300 tokens a call fable's cycle floor
    is 123,000 + 44 * 6,300 = 400,200, past the $2.20 point at 250,000,
    so at 400,200 the band is 2 and the message prices the turn at
    $3.52, 2.3x the $1.54 target.
    """
    per_call = 6_300
    target = budget.target_tokens('fable', per_call)
    assert target == 400_200
    band, message = cb.compose(target, 'fable', per_call)
    assert band == 2
    assert '$3.52' in message
    assert '2.3x' in message


def test_the_countdown_rounds_up_so_it_never_sticks():
    """Verify turns-left counts by ceiling, not floor-with-a-floor.

    Mutation: restoring max(1, int(...)), which shows "in 1" from 1.9
    turns of room all the way to the threshold - two turns reading the
    same - and overstates sub-turn room as a full turn.
    Oracle: hand-computed at 1,900 tokens a call on opus - 23,408 tokens
    of room to the 274,760 handoff point is 1.4 turns, which must read
    "handoff in 2", and 50,000 to the 350,000 target is 2.99 turns,
    "About 3".
    """
    line = re.sub(r'\x1b\[[0-9;]*m', '', sl.render({
        'session_id': 'none',
        'model': {'id': 'claude-opus-5', 'display_name': 'Opus 5'},
        'workspace': {'current_dir': '/x/proj'},
        'context_window': {'total_input_tokens': 251_352},
        }))
    assert 'handoff in 2' in line
    _, message = cb.compose(300_000, 'opus', 1_900)
    assert 'About 3 turns' in message


def test_growth_ignores_context_dropped_by_compaction():
    """Verify a compaction drop restarts the growth run, not flattens it.

    Mutation: dropping the `run = []` reset in growth_per_call, so the
    window spans the compaction.
    Oracle: hand-computed. The post-compaction run climbs 20K over five
    steps, so growth is 5,000; spanning the drop would give (60-100)/9,
    which is negative and would silently fall back.
    """
    series = [100_000, 120_000, 140_000, 160_000, 180_000,
              60_000, 65_000, 70_000, 75_000, 80_000]
    assert cb.growth_per_call(series) == 5_000


def test_growth_falls_back_on_a_short_series():
    """Verify a young session uses the documented fallback, not zero.

    Mutation: returning 0 or the raw difference when fewer than five
    calls exist, which would make the reserve collapse and the warning
    fire on the session's first turn.
    Oracle: the module's own declared fallback constant.
    """
    assert cb.growth_per_call([50_000, 60_000]) == budget.FALLBACK_GROWTH_PER_CALL
    assert cb.growth_per_call([]) == budget.FALLBACK_GROWTH_PER_CALL


def test_reserve_holds_a_floor_for_a_slow_session():
    """Verify a barely-growing session still gets room to hand off.

    Mutation: dropping the MIN_RESERVE_TOKENS floor, so a session growing
    100 tokens a call reserves ~4K and the warning arrives with no room
    left to write anything.
    Oracle: hand-computed - 3 turns * 8.8 calls * 100 * 1.5 = 3,960,
    which is below the floor and must be lifted to it.
    """
    assert budget.reserve_tokens(350_000, 100) == budget.MIN_RESERVE_TOKENS


def test_reserve_is_capped_so_it_cannot_swallow_the_session():
    """Verify a fast-growing session cannot reserve the whole budget.

    Mutation: removing the MAX_RESERVE_FRACTION ceiling, so a session
    adding 20K a call reserves 792K against a 350K target and warns on
    turn one, every session, forever.
    Oracle: hand-computed - the cap is half of 350,000.
    """
    assert budget.reserve_tokens(350_000, 20_000) == 175_000


def test_bands_fire_in_order_and_not_before_the_handoff_point():
    """Verify each band starts exactly where the arithmetic says it does.

    Mutation: a flipped comparison in compose, or the handoff band
    keyed off the target instead of target-minus-reserve, either of
    which shifts every warning by a full reserve.
    Oracle: hand-computed at 1,900 tokens/call - the reserve is
    3 * 1,900 * 8.8 * 1.5 = 75,240, clearing the 60,000 floor, so handoff
    starts at 274,760, the target at 350,000, and over-budget at 500,000.
    """
    per_call = 1_900
    assert budget.reserve_tokens(350_000, per_call) == 75_240
    assert cb.compose(274_759, 'opus', per_call)[0] == -1
    assert cb.compose(274_760, 'opus', per_call)[0] == 0
    assert cb.compose(349_999, 'opus', per_call)[0] == 0
    assert cb.compose(350_000, 'opus', per_call)[0] == 1
    assert cb.compose(499_999, 'opus', per_call)[0] == 1
    assert cb.compose(500_000, 'opus', per_call)[0] == 2


def test_handoff_warning_arrives_earlier_when_the_session_fills_faster():
    """Verify the warning point tracks growth instead of a fixed number.

    Mutation: replacing the measured per-call growth with a constant, the
    whole point of the design - a session reading large files would then
    be warned at the same token count as a chat and blow past the target
    mid-handoff.
    Oracle: differential - the same context is silent at the slow rate
    and already warning at the fast one.
    """
    slow = cb.compose(250_000, 'opus', 1_900)
    fast = cb.compose(250_000, 'opus', 6_000)
    assert slow[0] == -1
    assert fast[0] == 0


def test_message_names_the_numbers_the_reader_has_to_act_on():
    """Verify the warning text carries context, target, and turns left.

    Mutation: a message that says only "context is large", which gives
    the reader nothing to decide with.
    Oracle: the hand-computed strings for a 300K context on a 350K
    target growing 16,720 tokens a turn.
    """
    _, message = cb.compose(300_000, 'opus', 1_900)
    assert '300K' in message
    assert '350K' in message
    assert 'handoff' in message
    assert '16K a turn' in message


def test_the_warning_names_the_skill_the_plugin_ships():
    """Verify every warning band names the bundled handoff skill.

    Mutation: renaming skills/handoff/, or rewording a band so the
    warning names a command that no longer exists - band 2 included,
    since a floor-inflated target skips band 1 and band 2 is then the
    only message carrying the exit.
    Oracle: the skill's own frontmatter name on disk, matched against
    the text of all three bands.
    """
    skill = os.path.join(HERE, '..', 'skills', 'handoff', 'SKILL.md')
    with open(skill) as handle:
        front = handle.read().split('---\n', 2)[1]
    name = re.search(r'^name:\s*(\S+)', front, re.M).group(1)
    for context in (300_000, 360_000, 600_000):
        _, message = cb.compose(context, 'opus', 1_900)
        assert f'/{name} write' in message


def test_repeated_stream_snapshots_do_not_inflate_the_series(tmp_path):
    """Verify one API response counts once, however often it is written.

    Mutation: dropping the message-id dedupe in read_transcript. Claude
    Code writes a response as several progressive snapshots sharing an
    id, so counting each would treble the call count and divide the
    measured growth by three.
    Oracle: hand-built transcript - four responses climbing 10K each,
    written as ten records, must read as 10,000 per call.
    """
    path = tmp_path / 'session.jsonl'
    records = []
    for index, context in enumerate((100_000, 110_000, 120_000, 130_000,
                                     140_000, 150_000)):
        records.extend({
                'type': 'assistant',
                'message': {
                    'id': f'msg_{index}',
                    'role': 'assistant',
                    'model': 'claude-opus-5',
                    'usage': {
                        'cache_read_input_tokens': context,
                        'cache_creation_input_tokens': 0,
                        'input_tokens': 0,
                        'output_tokens': snapshot,
                        },
                    },
                } for snapshot in range(3))
    path.write_text('\n'.join(json.dumps(r) for r in records))
    context, model, per_call = cb.read_transcript(str(path))
    assert context == 150_000
    assert model == 'claude-opus-5'
    assert per_call == 10_000


def test_a_missing_or_unreadable_transcript_stays_silent(tmp_path):
    """Verify the hook never breaks a turn over its own input.

    Mutation: letting the OSError escape read_transcript. A Stop hook
    that raises turns every single turn into an error banner.
    Oracle: the documented zero-context return, which main() treats as
    nothing to say.
    """
    context, model, per_call = cb.read_transcript(str(tmp_path / 'nope.jsonl'))
    assert context == 0
    assert per_call == budget.FALLBACK_GROWTH_PER_CALL


def test_subagent_turns_are_never_announced(monkeypatch, capsys, tmp_path):
    """Verify a subagent's own context never raises a compaction warning.

    Mutation: dropping the agent_id guard in main. A subagent cannot
    compact and its context dies with it, so every delegated call would
    fire a warning the user can do nothing about.
    Oracle: a spy on stdout - the main-thread payload prints, the
    subagent payload with the identical transcript does not.
    """
    path = tmp_path / 's.jsonl'
    path.write_text(json.dumps({
        'type': 'assistant',
        'message': {
            'id': 'm1', 'role': 'assistant', 'model': 'claude-opus-5',
            'usage': {'cache_read_input_tokens': 600_000,
                      'cache_creation_input_tokens': 0, 'input_tokens': 0},
            },
        }))
    monkeypatch.setattr(cb, 'STATE_DIR', str(tmp_path / 'state'))

    payload = {'session_id': 'main-1', 'transcript_path': str(path)}
    monkeypatch.setattr(sys, 'stdin', _Stdin(json.dumps(payload)))
    cb.main()
    assert capsys.readouterr().out.strip()

    sub = {'session_id': 'sub-1', 'transcript_path': str(path),
           'agent_id': 'agent-9'}
    monkeypatch.setattr(sys, 'stdin', _Stdin(json.dumps(sub)))
    cb.main()
    assert capsys.readouterr().out.strip() == ''


def test_a_band_is_announced_once_and_rearmed_by_a_compaction(monkeypatch,
                                                              capsys,
                                                              tmp_path):
    """Verify the warning fires on entry, stays quiet, then fires again.

    Mutation: writing the state unconditionally without comparing, which
    silences everything, or never writing it, which re-warns every turn
    until the user disables the hook.
    Oracle: a spy on stdout across three runs - warn, silence, and warn
    again once a compaction has dropped the context and it climbs back.
    """
    state = tmp_path / 'state'
    monkeypatch.setattr(cb, 'STATE_DIR', str(state))
    path = tmp_path / 's.jsonl'

    def write(context):
        path.write_text(json.dumps({
            'type': 'assistant',
            'message': {
                'id': f'm{context}', 'role': 'assistant',
                'model': 'claude-opus-5',
                'usage': {'cache_read_input_tokens': context,
                          'cache_creation_input_tokens': 0, 'input_tokens': 0},
                },
            }))

    def run():
        payload = {'session_id': 'S', 'transcript_path': str(path)}
        monkeypatch.setattr(sys, 'stdin', _Stdin(json.dumps(payload)))
        cb.main()
        return capsys.readouterr().out.strip()

    write(300_000)
    assert 'handoff' in run()
    write(305_000)
    assert run() == ''
    write(120_000)
    assert run() == ''
    write(300_000)
    assert 'handoff' in run()


def test_a_growth_slowdown_does_not_rearm_an_announced_band(monkeypatch,
                                                            capsys,
                                                            tmp_path):
    """Verify a band fires once even when slowing growth lifts the
    handoff point back above the context.

    Mutation: storing the freshly computed band unconditionally, which
    lets a slowdown erase the announced-band memory - the same band
    then fires twice with no compaction between.
    Oracle: a spy on stdout across five runs - warn at 240K on steep
    growth, silence when the measured rate halves, silence again at
    280K, silence through a real compaction drop, and a warn once the
    context climbs back.
    """
    monkeypatch.setattr(cb, 'STATE_DIR', str(tmp_path / 'state'))
    path = tmp_path / 's.jsonl'
    contexts = [225_000, 228_000, 231_000, 234_000, 237_000, 240_000]

    def run():
        records = [{
            'type': 'assistant',
            'message': {
                'id': f'm{index}', 'role': 'assistant',
                'model': 'claude-opus-5',
                'usage': {'cache_read_input_tokens': value,
                          'cache_creation_input_tokens': 0,
                          'input_tokens': 0},
                },
            } for index, value in enumerate(contexts)]
        path.write_text('\n'.join(json.dumps(r) for r in records))
        payload = {'session_id': 'D', 'transcript_path': str(path)}
        monkeypatch.setattr(sys, 'stdin', _Stdin(json.dumps(payload)))
        cb.main()
        return capsys.readouterr().out.strip()

    assert 'handoff' in run()
    contexts += [240_500, 241_000, 241_500, 242_000, 242_500]
    assert run() == ''
    contexts += [250_000, 257_500, 265_000, 272_500, 280_000]
    assert run() == ''
    contexts += [120_000, 125_000, 130_000]
    assert run() == ''
    contexts += [300_000]
    assert 'handoff' in run()


def test_a_barely_growing_session_never_reads_as_zero_growth():
    """Verify the growth rate never prints as 0K a turn.

    Mutation: restoring the bare integer floor for the rate, which
    prints "growing 0K a turn" for a session measured under 114 tokens
    a call - a statement the reader can only parse as broken.
    Oracle: hand-computed - 100 tokens a call is 880 a turn, under the
    1K floor, so the message must carry "<1K a turn".
    """
    _, message = cb.compose(300_000, 'opus', 100)
    assert '<1K a turn' in message
    assert ' 0K a turn' not in message


def test_the_state_file_records_the_target_the_session_was_held_to(
        monkeypatch, tmp_path):
    """Verify the stored target uses the session's measured growth.

    Mutation: dropping per_call from the store_state call, which records
    the fallback-growth target while compose warned against the measured
    one - the two figures in the state file would describe different
    sessions.
    Oracle: hand-computed - a transcript climbing 10,000 tokens a call
    puts opus's cycle floor at 123,000 + 44 * 10,000 = 563,000, past the
    350,000 cost target, and that is the figure the file must hold.
    """
    monkeypatch.setattr(cb, 'STATE_DIR', str(tmp_path / 'state'))
    path = tmp_path / 's.jsonl'
    records = [{
        'type': 'assistant',
        'message': {
            'id': f'm{index}', 'role': 'assistant',
            'model': 'claude-opus-5',
            'usage': {'cache_read_input_tokens': 100_000 + 10_000 * index,
                      'cache_creation_input_tokens': 0, 'input_tokens': 0},
            },
        } for index in range(6)]
    path.write_text('\n'.join(json.dumps(r) for r in records))
    payload = {'session_id': 'S2', 'transcript_path': str(path)}
    monkeypatch.setattr(sys, 'stdin', _Stdin(json.dumps(payload)))
    cb.main()
    with open(tmp_path / 'state' / 'S2.json') as handle:
        assert json.load(handle)['target'] == 563_000


class _Stdin:
    """Minimal stdin stand-in returning a fixed payload to json.load.
    """

    def __init__(self, text: str) -> None:
        self.text = text

    def read(self, *args: object) -> str:
        return self.text


def test_an_expensive_model_gets_a_workable_compaction_cycle():
    """Verify the target clears where a compaction lands, by real turns.

    Mutation: deriving the target from cost alone. Fable's cost-parity
    target is 175K while a compaction lands at 123K, so a fast fable
    session would be handed a cycle of under three turns - and at some
    rates a target below the point it restarts at.
    Oracle: hand-computed - at 2,500 tokens a call the cycle floor is
    123,000 + 5 * 2,500 * 8.8 = 233,000, which beats cost parity, and
    every cycle must be worth at least MIN_CYCLE_TURNS.
    """
    assert budget.target_tokens('fable', 2_500) == 233_000
    for tier in budget.PRICE_PER_MTOK:
        for per_call in (1_200, 1_900, 2_500, 4_000):
            target = budget.target_tokens(tier, per_call)
            per_turn = per_call * budget.CALLS_PER_TURN
            cycle = (target - budget.POST_COMPACTION_TOKENS) / per_turn
            assert cycle >= budget.MIN_CYCLE_TURNS - 0.01


def test_the_warning_never_lands_below_where_a_compaction_restarts():
    """Verify the handoff point stays above the post-compaction floor.

    Mutation: leaving the reserve unclamped. On an expensive model the
    reserve exceeds the gap between the target and where a compaction
    lands, putting the warning below the restart point - so it fires on
    the first turn of every cycle and the user learns to ignore it.
    Oracle: differential across rates - target minus reserve must never
    dip under POST_COMPACTION_TOKENS.
    """
    for tier in budget.PRICE_PER_MTOK:
        for per_call in (1_200, 1_900, 2_500, 4_000, 8_000):
            target = budget.target_tokens(tier, per_call)
            handoff = target - budget.reserve_tokens(target, per_call)
            assert handoff >= budget.POST_COMPACTION_TOKENS


def test_the_gauge_stays_readable_past_the_budget():
    """Verify two different over-budget sizes do not render identically.

    Mutation: keeping the bar past the budget. It clamps to full, so
    1.1x and 3x print the same glyph - and past the budget is exactly
    where the reader needs to tell them apart.
    Oracle: differential - the same session at 452K and at 700K must
    produce different text.
    """
    def line(context):
        return sl.render({
            'session_id': 'none',
            'model': {'id': 'claude-opus-5', 'display_name': 'Opus 5'},
            'workspace': {'current_dir': '/x/proj'},
            'context_window': {'total_input_tokens': context},
            })

    assert line(452_000) != line(700_000)
    assert '1.3x over' in line(452_000)
    assert '2.0x over' in line(700_000)


def test_the_decision_numbers_survive_a_narrow_pane():
    """Verify size and action lead the line, and the line stays short.

    Mutation: putting the directory or the model first, as most status
    lines do. A pane is cut from the right, so the two fields that carry
    the decision are the ones lost.
    Oracle: hand-checked - the visible line with colour stripped must
    start with the size and fit a narrow split.
    """
    visible = re.sub(r'\x1b\[[0-9;]*m', '', sl.render({
        'session_id': 'none',
        'model': {'id': 'claude-opus-5', 'display_name': 'Opus 5'},
        'workspace': {'current_dir': '/x/myproject'},
        'context_window': {'total_input_tokens': 248_000},
        }))
    assert visible.startswith('248K/350K')
    assert 'handoff in' in visible.split('$')[0]
    assert len(visible) <= 64
