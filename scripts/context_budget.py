#!/usr/bin/env python3
"""Stop hook that warns while there is still room to hand off and compact.

Claude Code resends the whole conversation on every API call, so even a
fully cached turn still bills the entire context at the cache-read rate.
Cost tracks the area under the context curve, and the only lever a user
has is where the session gets compacted.

Compacting is not instant. It takes a turn to write a handoff, a turn to
read it back, and a turn to run ``/compact``. So this hook does not warn
at a fixed token count. It warns when the room left before the budget has
shrunk to what those turns will consume, measured at the rate this
session is actually growing. A session reading large files fills up
several times faster than a conversation and is warned much earlier in
absolute tokens.

The budget itself is set in dollars per turn and converted to a token
target per model in :mod:`budget`, so an expensive model is held to a
proportionally shorter session rather than the same one.

Notes
-----
- Bands fire on ENTRY only. A Stop hook runs every turn, so repeating a
  band already reached would be noise. The highest band announced is kept
  in a per-session state file and rearmed when the context drops.
- Growth is measured from the context series itself, not by counting
  turns. Transcripts interleave real user prompts with injected system
  reminders, tool results, and hook output, and no reliable rule
  separates them; the context series has no such ambiguity.
- A subagent carries its own short-lived context and never compacts, so
  the hook exits silently when ``agent_id`` is present.
"""

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import budget  # noqa: E402  (path must be set before this import resolves)

# Calls to average growth over. Long enough to survive one quiet stretch,
# short enough to react when a session starts reading large files.
GROWTH_WINDOW_CALLS = 60

STATE_DIR = os.path.expanduser('~/.claude/cache/context-budget')

OSC_NOTIFY = '\x1b]9;{}\x07'


def growth_per_call(series: list[int]) -> int:
    """Estimate how many tokens each assistant call adds to the context.

    Parameters
    ----------
    series : list[int]
        Billed context of each assistant call, in order.

    Returns
    -------
    int
        Mean tokens added per call over the most recent unbroken run of
        growth, or ``budget.FALLBACK_GROWTH_PER_CALL`` when the series is
        too short to measure.

    Notes
    -----
    - The series is cut at every drop. A drop means a compaction, and
      averaging across one reads as near-zero growth, which would silence
      the warning exactly where it matters most.
    - The mean is right here rather than the median: what matters is how
      fast the context fills, and one 40K tool result fills it just as
      surely as forty small ones.
    """
    window = series[-GROWTH_WINDOW_CALLS:]
    run: list[int] = []
    for value in window:
        if run and value < run[-1]:
            run = []
        run.append(value)
    if len(run) < 5 or run[-1] <= run[0]:
        return budget.FALLBACK_GROWTH_PER_CALL
    return max(1, (run[-1] - run[0]) // (len(run) - 1))


def read_transcript(path: str) -> tuple[int, str, int]:
    """Read a transcript's current context, model, and growth rate.

    Parameters
    ----------
    path : str
        Absolute path to the session transcript, as handed to the hook.

    Returns
    -------
    tuple[int, str, int]
        Billed context of the last assistant call, that call's model id,
        and the estimated tokens added per call. Context is 0 when the
        transcript holds no usage record yet.

    Notes
    -----
    - Claude Code writes one API response as several progressive stream
      snapshots sharing a message id, with output growing across them.
      The cache counts are fixed when the request is sent, so taking the
      last snapshot is safe for context even though it understates
      output.
    """
    series: list[int] = []
    model = ''
    seen: set[str] = set()
    try:
        handle = open(path, errors='replace')
    except OSError:
        return 0, '', budget.FALLBACK_GROWTH_PER_CALL
    with handle:
        for line in handle:
            if '"usage"' not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get('message') or {}
            usage = message.get('usage')
            if not usage or message.get('role') != 'assistant':
                continue
            identifier = message.get('id') or ''
            if identifier and identifier in seen:
                continue
            if identifier:
                seen.add(identifier)
            series.append((usage.get('cache_read_input_tokens') or 0)
                          + (usage.get('cache_creation_input_tokens') or 0)
                          + (usage.get('input_tokens') or 0))
            model = message.get('model') or model
    if not series:
        return 0, model, budget.FALLBACK_GROWTH_PER_CALL
    return series[-1], model, growth_per_call(series)


def compose(context: int, tier: str, per_call: int) -> tuple[int, str]:
    """Pick the band for a context size and write its message.

    Parameters
    ----------
    context : int
        Current billed context in tokens.
    tier : str
        Price tier from ``budget.model_tier``.
    per_call : int
        Estimated tokens added per assistant call.

    Returns
    -------
    tuple[int, str]
        Band index and the message to show, or ``(-1, '')`` when the
        session still has room and nothing needs saying.
    """
    target = budget.target_tokens(tier)
    over = budget.over_budget_tokens(tier)
    handoff_at = target - budget.reserve_tokens(target, per_call)
    per_turn = per_call * budget.CALLS_PER_TURN
    cost = budget.cost_per_turn(context, tier)
    now = f'{context // 1000}K'
    goal = f'{target // 1000}K'
    rate = f'{int(per_turn) // 1000}K'

    if context >= over:
        share = cost / budget.COST_PER_TURN_TARGET
        return 2, (f'Context is {now}, well past the {goal} budget. Each turn '
                   f'costs about ${cost:.2f}, roughly {share:.1f} times what '
                   f'it would at the budget. Worth compacting before you go '
                   f'on.')
    if context >= target:
        if not budget.compaction_is_worthwhile(target, per_call):
            return 1, (f'Context is {now}, past the {goal} budget for this '
                       f'model. Compacting would land near '
                       f'{budget.POST_COMPACTION_TOKENS // 1000}K and buy back '
                       f'barely a turn, so a fresh session is the cheaper '
                       f'reset here.')
        return 1, (f'Context is {now}, just past the {goal} budget and growing '
                   f'about {rate} a turn. A good place to finish the handoff '
                   f'and compact.')
    if context >= handoff_at:
        left = max(1, int((target - context) / max(per_turn, 1)))
        turns = 'turn' if left == 1 else 'turns'
        return 0, (f'Context is {now} of a {goal} budget, growing about {rate} '
                   f'a turn. About {left} {turns} of room left, so this is a '
                   f'good moment to start the handoff.')
    return -1, ''


def load_band(state_path: str) -> int:
    """Read the highest band index already announced for a session.

    Parameters
    ----------
    state_path : str
        Path to the per-session state file.

    Returns
    -------
    int
        The stored band index, or -1 when nothing is recorded.
    """
    try:
        with open(state_path) as handle:
            return int(json.load(handle).get('band', -1))
    except (OSError, ValueError, AttributeError, TypeError):
        return -1


def store_state(state_path: str, band: int, per_call: int, target: int) -> None:
    """Record the announced band, growth rate, and target for a session.
    """
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, 'w') as handle:
            json.dump({
                'band': band,
                'growth_per_call': per_call,
                'target': target,
                }, handle)
    except OSError:
        pass


def main() -> int:
    """Announce the context band when a session first enters one.
    """
    try:
        payload: dict[str, Any] = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get('agent_id'):
        return 0
    transcript = payload.get('transcript_path') or ''
    if not transcript:
        return 0
    session = str(payload.get('session_id') or 'unknown').replace('/', '_')

    context, model, per_call = read_transcript(transcript)
    if context <= 0:
        return 0
    tier = budget.model_tier(model)
    if tier is None:
        return 0
    band, message = compose(context, tier, per_call)

    state_path = os.path.join(STATE_DIR, f'{session}.json')
    announced = load_band(state_path)
    store_state(state_path, band, per_call, budget.target_tokens(tier))
    if band <= announced or band < 0:
        return 0

    out: dict[str, str] = {'systemMessage': message}
    if band > 0:
        out['terminalSequence'] = OSC_NOTIFY.format(message)
    json.dump(out, sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())
