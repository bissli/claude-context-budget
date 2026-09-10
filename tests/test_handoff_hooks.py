"""Tests for the handoff PreToolUse gate and the handoff Stop hook."""

import io
import json
import pathlib
import sys

from scripts import handoff_gate, handoff_stop, hq

_SLUG = 'demo-slug'
_NOW = '2026-09-09T12:00:00'
_SPEC_TEXT = '# Spec\n\n## Scope\n\nOne.\nTwo.\n\n## Risks\n\nThree.\n'
_SPEC_SPAN = 'lines 3-7'
_LEDGER_HEADER = '\t'.join(hq.LEDGER_FIELDS)
_MANIFEST_HEADER = '\t'.join(hq.MANIFEST_FIELDS)
_REPO = pathlib.Path(__file__).resolve().parents[1]


def _row(path: str, **overrides: str) -> dict:
    """Build one ledger row with live/always defaults.

    Parameters
    ----------
    path : str
        Value for the ``path`` field, stored as the ledger stores it.
    **overrides : str
        Field values replacing the defaults, keyed by ledger field name.

    Returns
    -------
    dict
        A row carrying every field in ``hq.LEDGER_FIELDS``.
    """
    row = {
        'cycle': '1', 'ts': _NOW, 'path': path, 'base': 'folder',
        'kind': 'spec', 'status': 'live', 'read_before': 'always',
        'successor': '-', 'where': 'Scope', 'sha12': '-', 'lines': '10',
        'reason': '-', 'label': '-',
        }
    row.update(overrides)
    return row


def _handoff_root(tmp_path: pathlib.Path, slug: str = _SLUG) -> tuple:
    """Create a project root holding one handoff folder and its ledger.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Pytest temporary directory; the root is placed at ``tmp_path/proj``.
    slug : str, default _SLUG
        Handoff folder name under ``working/``.

    Returns
    -------
    tuple[pathlib.Path, pathlib.Path]
        The project root and the handoff folder.

    Notes
    -----
    - SPEC.md is the only gated row: NOTES.md is read_before=mention and
      OLD.md is superseded, so a filter that drops either test breaks.
    """
    root = pathlib.Path(tmp_path) / 'proj'
    folder = root / 'working' / slug
    folder.mkdir(parents=True, exist_ok=True)
    (root / 'src').mkdir(exist_ok=True)
    (root / 'src' / 'app.py').write_text('x = 1\n', encoding='utf-8')
    (folder / 'SPEC.md').write_text(_SPEC_TEXT, encoding='utf-8')
    (folder / 'NOTES.md').write_text('# Notes\n\n## Scope\n\nOne.\n',
                                     encoding='utf-8')
    (folder / 'OLD.md').write_text('# Old\n\n## Scope\n\nOne.\n',
                                   encoding='utf-8')
    (folder / 'HANDOFF.md').write_text('# Handoff\n\n## Task\n\nWork.\n',
                                       encoding='utf-8')
    ledger = folder / 'ledger.tsv'
    for row in (_row('SPEC.md'),
                _row('NOTES.md', read_before='mention'),
                _row('OLD.md', status='superseded')):
        hq._append_tsv(ledger, hq.LEDGER_FIELDS, row, _LEDGER_HEADER)
    return root, folder


def _bash(command: str) -> dict:
    """Return one transcript line holding a Bash tool call.
    """
    return {'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Bash', 'input': {'command': command}}]}}


def _read(file_path: str) -> dict:
    """Return one transcript line holding a Read tool call.
    """
    return {'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Read',
         'input': {'file_path': file_path}}]}}


def _transcript(path: pathlib.Path, entries: list) -> pathlib.Path:
    """Write a JSONL transcript and return its path.
    """
    path.write_text('\n'.join(json.dumps(e) for e in entries) + '\n',
                    encoding='utf-8')
    return path


def _payload(root: pathlib.Path, transcript: pathlib.Path, session: str,
             tool_name: str, tool_input: dict) -> dict:
    """Build a PreToolUse payload of the shape Claude Code sends.

    Parameters
    ----------
    root : pathlib.Path
        Directory the tool call runs in, sent as ``cwd``.
    transcript : pathlib.Path
        Path to the session transcript.
    session : str
        Session id, which names the state and receipt files.
    tool_name : str
        Tool being called, e.g. ``Bash`` or ``Edit``.
    tool_input : dict
        The tool's own input block.

    Returns
    -------
    dict
        A payload ready to hand to the gate over stdin.
    """
    return {
        'hook_event_name': 'PreToolUse', 'cwd': str(root),
        'session_id': session, 'transcript_path': str(transcript),
        'tool_name': tool_name, 'tool_input': tool_input,
        }


def _run(monkeypatch, capsys, module, payload):
    """Drive a hook's main() over one payload and return its stdout.
    """
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    module.main()
    return capsys.readouterr().out.strip()


def _context(out: str) -> str:
    """Return the additionalContext text from a gate's stdout.
    """
    return json.loads(out)['hookSpecificOutput']['additionalContext']


def test_gate_ignores_stderr_only_redirects():
    """Verify bash_writes() reads only real writes as writes.

    Mutation: testing the raw command for '>' without stripping stderr
    redirections, quoted spans, and heredoc bodies - which makes every
    `cmd 2>&1` a write and fires the gate on read-only commands.
    Oracle: hand-classified command list, each side of the boundary.
    """
    quiet = [
        'cmd 2>&1',
        'cmd >/dev/null 2>&1',
        'cmd 2>/dev/null',
        'echo ">" | grep x',
        "echo 'a > b'",
        "cat <<'EOF'\n> not a redirect\nEOF",
        'sed -n 1,20p file',
        'grep -n x file',
        'python3 scripts/hq.py stamp demo-slug SPEC.md > out.txt',
        ]
    loud = [
        'cmd > out.txt',
        'cmd >> log',
        'cmd &> both.txt',
        'sed -i s/a/b/ f',
        'sed -ni 1,2p f',
        'sed --in-place s/a/b/ f',
        'tee f',
        'git add .',
        'git commit -m x',
        ]
    assert [c for c in quiet if handoff_gate.bash_writes(c)] == []
    assert [c for c in loud if not handoff_gate.bash_writes(c)] == []


def test_gate_fires_on_a_heredoc_and_a_redirect_write(monkeypatch, capsys,
                                                      tmp_path):
    """Verify an armed session with an unread gated path is reported.

    Mutation: dropping the read_before/status filter, or naming the row
    without its span, so the message cannot be acted on.
    Oracle: hand-computed - SPEC.md's 'Scope' heading spans lines 3-7 of
    the fixture, and NOTES.md and OLD.md must not appear.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _payload(root, tr, 'S1', 'Bash',
                       {'command': "cat > x.py <<'EOF'\nprint(1)\nEOF"})
    out = _run(monkeypatch, capsys, handoff_gate, payload)
    text = _context(out)
    assert json.loads(out)['hookSpecificOutput'] == {
        'hookEventName': 'PreToolUse', 'permissionDecision': 'allow',
        'additionalContext': text,
        }
    assert text == (
        f'handoff gate: {_SLUG}: 1 gated path(s) not read this session'
        f' - SPEC.md ({_SPEC_SPAN}); read each or run:'
        f' hq.py read {_SLUG} SPEC.md')


def test_gate_counts_only_read_shaped_evidence(monkeypatch, capsys, tmp_path):
    """Verify only a read verb or the Read tool clears a gated path.

    Mutation: counting any mention of the path in the transcript, so an
    `ls` or a `wc -l` reads as having read the file.
    Oracle: a spy on stdout - the same write payload reports under ls,
    wc, and stamp, and is silent under cat, sed -n, and Read.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    spec = folder / 'SPEC.md'
    armed = [_bash(f'python3 scripts/hq.py open {_SLUG}')]

    def run(session, extra):
        tr = _transcript(tmp_path / f'{session}.jsonl', armed + extra)
        payload = _payload(root, tr, session, 'Edit',
                           {'file_path': 'src/app.py'})
        return _run(monkeypatch, capsys, handoff_gate, payload)

    assert 'SPEC.md' in run('m1', [
        _bash(f'ls working/{_SLUG}/SPEC.md'),
        _bash(f'wc -l working/{_SLUG}/SPEC.md'),
        _bash(f'python3 scripts/hq.py stamp {_SLUG} SPEC.md'),
        ])
    assert run('m2', [_bash(f'cat working/{_SLUG}/SPEC.md')]) == ''
    assert run('m3', [_bash(f'sed -n 1,20p {spec}')]) == ''
    assert run('m4', [_read(str(spec))]) == ''


def test_gate_credits_a_read_receipt(monkeypatch, capsys, tmp_path):
    """Verify an hq.py read receipt clears a path never read in-transcript.

    Mutation: matching the receipt line on the path alone, so a receipt
    from another handoff folder clears this one, or dropping the receipt
    check, which makes `hq.py read` no answer to the gate it names.
    Oracle: a spy on stdout - the identical payload reports with no
    receipt, reports with a receipt naming another folder, and is silent
    with the receipt naming this one.
    """
    root, folder = _handoff_root(tmp_path)
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setenv('HQ_STATE_DIR', str(state))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])

    def run(session):
        payload = _payload(root, tr, session, 'Edit',
                           {'file_path': 'src/app.py'})
        return _run(monkeypatch, capsys, handoff_gate, payload)

    assert 'SPEC.md' in run('r1')
    (state / 'hq-reads-r2.txt').write_text(f'{_NOW} other-slug SPEC.md\n',
                                           encoding='utf-8')
    assert 'SPEC.md' in run('r2')
    (state / 'hq-reads-r3.txt').write_text(f'{_NOW} {_SLUG} SPEC.md\n',
                                           encoding='utf-8')
    assert run('r3') == ''


def test_gate_arms_only_on_hq_open(monkeypatch, capsys, tmp_path):
    """Verify nothing is gated until an hq.py open names a slug.

    Mutation: arming on the presence of a handoff root, so every session
    in the repo is gated whether or not it opened a handoff.
    Oracle: a spy on stdout - a transcript reading HANDOFF.md is silent,
    the same transcript plus `hq.py open` reports, and a prefix of the
    slug resolves to the same folder.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    seen = [_read(str(folder / 'HANDOFF.md'))]

    def run(session, entries):
        tr = _transcript(tmp_path / f'{session}.jsonl', entries)
        payload = _payload(root, tr, session, 'Edit',
                           {'file_path': 'src/app.py'})
        return _run(monkeypatch, capsys, handoff_gate, payload)

    assert run('a1', seen) == ''
    assert 'SPEC.md' in run('a2', seen + [_bash(f'hq.py open {_SLUG}')])
    assert 'SPEC.md' in run('a3', seen + [_bash('hq.py open demo')])


def test_gate_exempts_hq_commands_and_folder_writes(monkeypatch, capsys,
                                                    tmp_path):
    """Verify writing the handoff itself never trips its own gate.

    Mutation: gating every write once armed, which blocks `hq.py stamp`
    and every edit of HANDOFF.md - the work the gate exists to protect.
    Oracle: a spy on stdout across four payloads in one session - the hq
    command, the folder redirect, and the HANDOFF.md edit are silent,
    and the repo write that follows still reports.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])

    def run(tool_name, tool_input):
        payload = _payload(root, tr, 'E1', tool_name, tool_input)
        return _run(monkeypatch, capsys, handoff_gate, payload)

    assert run('Bash', {
        'command': f'python3 scripts/hq.py stamp {_SLUG} notes-a.md'}) == ''
    assert run('Bash', {
        'command': f'echo x > working/{_SLUG}/notes-a.md'}) == ''
    assert run('Edit', {'file_path': str(folder / 'HANDOFF.md')}) == ''
    assert 'SPEC.md' in run('Edit', {'file_path': 'src/app.py'})


def test_gate_scans_the_transcript_once_per_session(monkeypatch, capsys,
                                                    tmp_path):
    """Verify the scan resumes from the stored offset and never rescans.

    Mutation: dropping the offset and the persisted reads, so every call
    re-reads the whole transcript - the cost the gate must not pay on a
    hook that runs on every Bash and Edit.
    Oracle: a counting spy on scan_transcript, which must be called once
    however many writes follow, plus the deleted transcript, so a report
    on the later call can only come from stored state.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    scanned = []
    real = handoff_gate.scan_transcript

    def counted(text):
        scanned.append(text)
        return real(text)

    monkeypatch.setattr(handoff_gate, 'scan_transcript', counted)

    def run(tool_input):
        payload = _payload(root, tr, 'O1', 'Bash', tool_input)
        return _run(monkeypatch, capsys, handoff_gate, payload)

    assert run({'command': f'echo x > working/{_SLUG}/notes-a.md'}) == ''
    assert len(scanned) == 1
    assert run({'command': f'echo y > working/{_SLUG}/notes-b.md'}) == ''
    assert len(scanned) == 1
    tr.unlink()
    assert 'SPEC.md' in run({'command': 'echo x > src/app.py'})
    assert run({'command': 'echo y > src/app.py'}) == ''
    assert len(scanned) == 1


def test_gate_resumes_at_a_line_boundary(monkeypatch, capsys, tmp_path):
    """Verify a half-written transcript line is scanned whole on the next call.

    Mutation: advancing the offset to the end of the bytes read, so the
    tail of a line the host was still writing is split across two
    scans and the hq.py open it carried is never seen.
    Oracle: a spy on stdout - the same repo write is silent while the open
    line is half written and reports once the line is completed.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl', [_read(str(folder / 'HANDOFF.md'))])
    open_line = json.dumps(_bash(f'python3 scripts/hq.py open {_SLUG}'))
    cut = len(open_line) // 2
    with tr.open('a', encoding='utf-8') as handle:
        handle.write(open_line[:cut])

    def run(command):
        payload = _payload(root, tr, 'B1', 'Bash', {'command': command})
        return _run(monkeypatch, capsys, handoff_gate, payload)

    assert run('echo x > src/app.py') == ''
    with tr.open('a', encoding='utf-8') as handle:
        handle.write(open_line[cut:] + '\n')
    assert 'SPEC.md' in _context(run('echo y > src/app.py'))


def test_gate_allows_when_off_marker_present(monkeypatch, capsys, tmp_path):
    """Verify HQ_GATE=0 silences the gate on a payload that reports.

    Mutation: reading the switch as truthy, so HQ_GATE=0 turns the gate
    on and the documented way out does not work.
    Oracle: a spy on stdout - the same payload and transcript report
    with the switch unset and print nothing with HQ_GATE=0.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])

    def run(session):
        payload = _payload(root, tr, session, 'Edit',
                           {'file_path': 'src/app.py'})
        return _run(monkeypatch, capsys, handoff_gate, payload)

    assert 'SPEC.md' in run('g1')
    monkeypatch.setenv('HQ_GATE', '0')
    assert run('g2') == ''


def test_gate_deny_path_behind_env(monkeypatch, capsys, tmp_path):
    """Verify HQ_GATE_DENY=1 blocks the call with the same message.

    Mutation: emitting the deny form by default, which stops the tool
    call for every user who never asked for a hard block.
    Oracle: differential - the deny reason must equal the allow context
    from the identical payload, and the default must be allow.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])

    def run(session):
        payload = _payload(root, tr, session, 'Edit',
                           {'file_path': 'src/app.py'})
        return _run(monkeypatch, capsys, handoff_gate, payload)

    allowed = json.loads(run('d1'))['hookSpecificOutput']
    monkeypatch.setenv('HQ_GATE_DENY', '1')
    denied = json.loads(run('d2'))['hookSpecificOutput']
    assert allowed['permissionDecision'] == 'allow'
    assert denied == {
        'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
        'permissionDecisionReason': allowed['additionalContext'],
        }


def test_gate_is_silent_outside_a_handoff_root(monkeypatch, capsys, tmp_path):
    """Verify a repo with no handoff folder costs nothing and says nothing.

    Mutation: walking to the filesystem root and gating anyway, or
    writing state before the root is found - which leaves a state file
    per session for every project on the machine.
    Oracle: a spy on the state directory, which must stay empty, plus
    stdout.
    """
    state = tmp_path / 'state'
    monkeypatch.setenv('HQ_STATE_DIR', str(state))
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _payload(elsewhere, tr, 'X1', 'Bash',
                       {'command': 'echo x > out.txt'})
    assert _run(monkeypatch, capsys, handoff_gate, payload) == ''
    assert not state.exists() or list(state.iterdir()) == []


def test_gate_survives_a_corrupt_state_file(monkeypatch, capsys, tmp_path):
    """Verify a truncated state file does not silence the gate.

    Mutation: letting the state read raise into the fail-open catch, so
    one bad write disables the gate for the rest of the session.
    Oracle: a spy on stdout, with gate() called directly so a raise
    surfaces as an error instead of being swallowed.
    """
    root, folder = _handoff_root(tmp_path)
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setenv('HQ_STATE_DIR', str(state))
    (state / 'C1.handoff.json').write_text('{"gate": ', encoding='utf-8')
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _payload(root, tr, 'C1', 'Edit', {'file_path': 'src/app.py'})
    assert handoff_gate.gate(payload) == 0
    assert 'SPEC.md' in capsys.readouterr().out


def _finished(folder: pathlib.Path, cycle: str, sha: str) -> None:
    """Append one finished-cycle row to a handoff folder's manifest.

    Parameters
    ----------
    folder : pathlib.Path
        The handoff folder holding ``cycles/manifest.tsv``.
    cycle : str
        Cycle number the row records.
    sha : str
        HANDOFF.md digest the cycle finished on.

    Returns
    -------
    None
    """
    (folder / 'cycles').mkdir(exist_ok=True)
    row = dict.fromkeys(hq.MANIFEST_FIELDS, '-')
    row.update({'cycle': cycle, 'written': _NOW, 'handoff_sha': sha})
    hq._append_tsv(folder / 'cycles' / 'manifest.tsv', hq.MANIFEST_FIELDS,
                   row, _MANIFEST_HEADER)


def _stop_payload(root: pathlib.Path, session: str, **extra) -> dict:
    """Build a Stop payload of the shape Claude Code sends.
    """
    payload = {'hook_event_name': 'Stop', 'cwd': str(root),
               'session_id': session, 'stop_hook_active': False}
    payload.update(extra)
    return payload


def test_stop_reports_when_handoff_sha_differs_from_manifest(monkeypatch,
                                                             capsys,
                                                             tmp_path):
    """Verify a hand-edited HANDOFF.md is reported with its cycle number.

    Mutation: comparing against the first manifest row instead of the
    last, which names a stale cycle, or comparing file size rather than
    the digest, which misses an edit of equal length.
    Oracle: hand-computed - the manifest records cycle 2 on the original
    digest, and the file is rewritten to the same length.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    handoff = folder / 'HANDOFF.md'
    _finished(folder, '1', 'aaaaaaaaaaaa')
    _finished(folder, '2', hq._sha12_path(handoff))
    handoff.write_text('# Handoff\n\n## Task\n\nWonk.\n', encoding='utf-8')
    out = _run(monkeypatch, capsys, handoff_stop, _stop_payload(root, 'P1'))
    assert json.loads(out) == {'systemMessage': (
        f'handoff: working/{_SLUG}/HANDOFF.md was written by hand since'
        f' cycle 2 finished; run hq.py begin {_SLUG}, then hq.py finish'
        f' {_SLUG} --log "...", or the next open reports LEDGER BEHIND')}


def test_stop_silent_when_it_matches(monkeypatch, capsys, tmp_path):
    """Verify an untouched handoff, and a locked one, say nothing.

    Mutation: dropping the .hq.lock skip, so every turn of an open cycle
    reports the edit the agent is in the middle of making, or reading
    the first manifest row rather than the last, which reports a folder
    whose digest matches the cycle it actually finished on.
    Oracle: a spy on stdout - a manifest whose last row matches and
    whose first does not is silent, the same folder with a changed file
    and a lock is silent, and removing the lock reports.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    handoff = folder / 'HANDOFF.md'
    _finished(folder, '1', 'aaaaaaaaaaaa')
    _finished(folder, '2', hq._sha12_path(handoff))
    assert _run(monkeypatch, capsys, handoff_stop,
                _stop_payload(root, 'Q1')) == ''
    (folder / '.hq.lock').write_text(f'slug={_SLUG}\ncycle=2\n',
                                     encoding='utf-8')
    handoff.write_text('# Handoff\n\n## Task\n\nOther.\n', encoding='utf-8')
    assert _run(monkeypatch, capsys, handoff_stop,
                _stop_payload(root, 'Q2')) == ''
    (folder / '.hq.lock').unlink()
    assert 'HANDOFF.md' in _run(monkeypatch, capsys, handoff_stop,
                                _stop_payload(root, 'Q3'))


def test_stop_reports_once_per_session_with_flag_set_or_not(monkeypatch,
                                                            capsys,
                                                            tmp_path):
    """Verify one report per hand edit, and none inside a stop loop.

    Mutation: dropping the stop_hook_active guard, which re-fires inside
    the loop it is meant to end, or keying the memory on the slug alone,
    which silences every later edit of the same file.
    Oracle: a spy on stdout across four calls - report, silence, silence
    under the flag in a fresh session, and report again after a second
    edit changes the digest.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    handoff = folder / 'HANDOFF.md'
    _finished(folder, '1', hq._sha12_path(handoff))
    handoff.write_text('# Handoff\n\n## Task\n\nFirst edit.\n',
                       encoding='utf-8')
    assert 'HANDOFF.md' in _run(monkeypatch, capsys, handoff_stop,
                                _stop_payload(root, 'R1'))
    assert _run(monkeypatch, capsys, handoff_stop,
                _stop_payload(root, 'R1')) == ''
    assert _run(monkeypatch, capsys, handoff_stop,
                _stop_payload(root, 'R2', stop_hook_active=True)) == ''
    handoff.write_text('# Handoff\n\n## Task\n\nSecond edit.\n',
                       encoding='utf-8')
    assert 'HANDOFF.md' in _run(monkeypatch, capsys, handoff_stop,
                                _stop_payload(root, 'R1'))


def test_stop_keeps_the_band_message(monkeypatch, capsys, tmp_path):
    """Verify the new hooks are added beside the band hook, not over it.

    Mutation: replacing the context_budget.py Stop entry with the new
    one, or writing the band's own session state from this hook - either
    way the cost warning stops arriving.
    Oracle: hooks.json read from disk, plus a byte comparison of a
    pre-existing <session>.json across the call.
    """
    config = json.loads((_REPO / 'hooks' / 'hooks.json').read_text())
    stop = [h['command'] for entry in config['hooks']['Stop']
            for h in entry['hooks']]
    assert len(stop) == 2
    assert stop[0].endswith('scripts/context_budget.py"')
    assert stop[1].endswith('scripts/handoff_stop.py"')
    pre = config['hooks']['PreToolUse']
    assert len(pre) == 1
    assert pre[0]['matcher'] == 'Edit|Write|NotebookEdit|Bash'
    assert pre[0]['hooks'][0]['command'].endswith('scripts/handoff_gate.py"')

    root, folder = _handoff_root(tmp_path)
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setenv('HQ_STATE_DIR', str(state))
    band = state / 'B1.json'
    band.write_text('{"band": 1, "context": 300000}', encoding='utf-8')
    before = band.read_bytes()
    handoff = folder / 'HANDOFF.md'
    _finished(folder, '1', 'aaaaaaaaaaaa')
    assert 'HANDOFF.md' in _run(monkeypatch, capsys, handoff_stop,
                                _stop_payload(root, 'B1'))
    assert band.read_bytes() == before
    assert (state / 'B1.handoff.json').exists()


def test_stop_ignores_subagents(monkeypatch, capsys, tmp_path):
    """Verify a subagent's Stop never reports a hand-edited handoff.

    Mutation: dropping the agent_id guard, so every delegated agent
    repeats the same message on the same folder.
    Oracle: a spy on stdout - the main-thread payload reports and the
    identical payload carrying agent_id does not.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    _finished(folder, '1', 'aaaaaaaaaaaa')
    assert 'HANDOFF.md' in _run(monkeypatch, capsys, handoff_stop,
                                _stop_payload(root, 'T1'))
    assert _run(monkeypatch, capsys, handoff_stop,
                _stop_payload(root, 'T2', agent_id='agent-9')) == ''
