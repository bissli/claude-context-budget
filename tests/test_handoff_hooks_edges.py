"""Edge-case tests for handoff_gate.py and handoff_stop.py."""

import io
import json
import os
import pathlib
import sys
import types
from typing import Any

import pytest
from scripts import handoff_gate, handoff_stop, hq

_SLUG = 'test-proj'
_NOW = '2026-09-09T12:00:00'
_LEDGER_HEADER = '\t'.join(hq.LEDGER_FIELDS)
_MANIFEST_HEADER = '\t'.join(hq.MANIFEST_FIELDS)


def _row(path: str, **overrides: str) -> dict:
    """Build one ledger row with live/always defaults.

    Parameters
    ----------
    path : str
        Value for the ``path`` field.
    **overrides : str
        Field values replacing the defaults.

    Returns
    -------
    dict
        A row carrying every field in ``hq.LEDGER_FIELDS``.
    """
    row = {
        'cycle': '1', 'ts': _NOW, 'path': path, 'base': 'folder',
        'kind': 'spec', 'status': 'live', 'read_before': 'always',
        'successor': '-', 'where': '-', 'sha12': '-', 'lines': '10',
        'reason': '-', 'label': '-',
        }
    row.update(overrides)
    return row


def _handoff_root(
    tmp_path: pathlib.Path, slug: str = _SLUG,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Create a project root with one handoff folder and a gated ledger row.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Pytest temporary directory.
    slug : str, default _SLUG
        Handoff folder name under ``.handoff/``.

    Returns
    -------
    tuple[pathlib.Path, pathlib.Path]
        The project root and the handoff folder.
    """
    root = tmp_path / 'proj'
    folder = root / '.handoff' / slug
    folder.mkdir(parents=True, exist_ok=True)
    (root / 'src').mkdir(exist_ok=True)
    (root / 'src' / 'app.py').write_text('x = 1\n', encoding='utf-8')
    (folder / 'SPEC.md').write_text('# Spec\n\nContent.\n', encoding='utf-8')
    (folder / 'HANDOFF.md').write_text(
        '# Handoff\n\n## Task\n\nWork.\n', encoding='utf-8')
    ledger = folder / 'ledger.tsv'
    hq._append_tsv(ledger, hq.LEDGER_FIELDS, _row('SPEC.md'), _LEDGER_HEADER)
    return root, folder


def _finished(folder: pathlib.Path, cycle: int | str, sha: str) -> None:
    """Append one finished-cycle row to the manifest.

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


def _bash(command: str) -> dict:
    """Return one transcript line holding a Bash tool call.
    """
    return {'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Bash',
         'input': {'command': command}}]}}


def _transcript(path: pathlib.Path, entries: list[dict]) -> pathlib.Path:
    """Write a JSONL transcript and return its path.
    """
    path.write_text(
        '\n'.join(json.dumps(e) for e in entries) + '\n',
        encoding='utf-8')
    return path


def _gate_payload(
    root: pathlib.Path,
    transcript: pathlib.Path,
    session: str,
    tool_name: str,
    tool_input: dict,
) -> dict:
    """Build a PreToolUse payload of the shape Claude Code sends.

    Parameters
    ----------
    root : pathlib.Path
        Directory the tool call runs in, sent as ``cwd``.
    transcript : pathlib.Path
        Path to the session transcript.
    session : str
        Session id.
    tool_name : str
        Tool being called.
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


def _stop_payload(root: pathlib.Path, session: str, **extra: Any) -> dict:
    """Build a Stop payload of the shape Claude Code sends.
    """
    payload = {'hook_event_name': 'Stop', 'cwd': str(root),
               'session_id': session, 'stop_hook_active': False}
    payload.update(extra)
    return payload


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    module: types.ModuleType,
    payload: dict,
) -> str:
    """Drive a hook's main() over one payload and return its stdout.
    """
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    module.main()
    return capsys.readouterr().out.strip()


# --- The Stop hook and an unreadable file ---


def test_stop_silent_on_unreadable_handoff(monkeypatch, capsys, tmp_path):
    """Verify an unreadable HANDOFF.md is not reported as a hand edit.

    Mutation: treating the '-' sha from _sha12_path on OSError as a real
    digest mismatch, which fires a false alarm on any chmod-000 file.
    Oracle: stdout must be empty; the only evidence is an OSError, not a
    hash difference between the file's content and the recorded digest.
    """
    if os.geteuid() == 0:
        pytest.skip('root bypasses chmod')
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    handoff = folder / 'HANDOFF.md'
    _finished(folder, '1', hq._sha12_path(handoff))
    handoff.chmod(0o000)
    try:
        out = _run(monkeypatch, capsys, handoff_stop, _stop_payload(root, 'U1'))
        assert out == ''
    finally:
        handoff.chmod(0o644)


# --- The gate's write-target exemption ---


def test_gate_fires_when_folder_precedes_redirect(monkeypatch, capsys, tmp_path):
    """Verify a read-from-folder then redirect-elsewhere trips the gate.

    Mutation: exempting any command that mentions the folder path, so
    'cat .handoff/<slug>/SPEC.md > /tmp/out' is silenced although spec.md
    is gated and the redirect target is outside the folder.
    Oracle: stdout must name SPEC.md; the folder path precedes '>' so the
    write target is not in the folder.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _gate_payload(
        root, tr, 'V1', 'Bash',
        {'command': f'cat .handoff/{_SLUG}/SPEC.md > /tmp/out.txt'})
    out = _run(monkeypatch, capsys, handoff_gate, payload)
    assert 'SPEC.md' in out


def test_gate_redirect_into_folder_stays_exempt(monkeypatch, capsys, tmp_path):
    """Verify a redirect whose target is inside the folder stays silent.

    Mutation: removing the write-target check so every command mentioning
    the folder trips the gate, including 'echo x > .handoff/<slug>/notes.md'
    which writes into the managed folder.
    Oracle: stdout must be empty; the redirect target is inside the folder.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _gate_payload(
        root, tr, 'V2', 'Bash',
        {'command': f'echo x > .handoff/{_SLUG}/notes.md'})
    out = _run(monkeypatch, capsys, handoff_gate, payload)
    assert out == ''


def test_gate_sed_inplace_into_folder_stays_exempt(monkeypatch, capsys,
                                                   tmp_path):
    """Verify sed -i targeting the folder stays silent.

    Mutation: removing the write-target check so sed -i on a folder file
    trips the gate, blocking in-place edits of managed files.
    Oracle: stdout must be empty; sed -i writes to the folder path.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _gate_payload(
        root, tr, 'V3', 'Bash',
        {'command': f'sed -i s/a/b/ .handoff/{_SLUG}/notes.md'})
    out = _run(monkeypatch, capsys, handoff_gate, payload)
    assert out == ''


def test_gate_tee_into_folder_stays_exempt(monkeypatch, capsys, tmp_path):
    """Verify tee targeting the folder stays silent.

    Mutation: removing the write-target check so 'echo x | tee
    .handoff/<slug>/notes.md' trips the gate, blocking tee writes into
    the managed folder.
    Oracle: stdout must be empty; tee's argument is inside the folder.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _gate_payload(
        root, tr, 'V4', 'Bash',
        {'command': f'echo x | tee .handoff/{_SLUG}/notes.md'})
    out = _run(monkeypatch, capsys, handoff_gate, payload)
    assert out == ''


def test_gate_relative_target_inside_folder_stays_exempt(
        monkeypatch, capsys, tmp_path):
    """A bare-name target written from inside the folder stays silent.

    Mutation: testing the command text alone for the `.handoff/<slug>/`
    prefix, so a target that reaches the folder only through cwd
    reports; or resolving redirect targets alone, so the sed -i and tee
    spellings report.
    Oracle: stdout empty for three in-folder spellings run from a
    subdirectory of the folder, then stdout naming SPEC.md for the repo
    write that follows in the same session, so no exempt write spent
    the one-shot.
    """
    root, folder = _handoff_root(tmp_path)
    inside = folder / 'evidence' / 'run-1'
    inside.mkdir(parents=True)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    spellings = [
        ('python probe.py run > smoke-A-0.log 2>&1 &\n'
         'python probe.py run > smoke-C-0.log 2>&1 &\nwait'),
        'sed -i s/a/b/ notes.md',
        'echo x | tee -a notes.md',
        ]
    for command in spellings:
        payload = _gate_payload(inside, tr, 'V9', 'Bash', {'command': command})
        assert _run(monkeypatch, capsys, handoff_gate, payload) == '', command
    payload = _gate_payload(root, tr, 'V9', 'Bash',
                            {'command': 'echo x > src/out.txt'})
    assert 'SPEC.md' in _run(monkeypatch, capsys, handoff_gate, payload)


def test_gate_target_climbing_out_of_folder_fires(monkeypatch, capsys,
                                                  tmp_path):
    """A write run from inside the folder to a path outside it reports.

    Mutation: exempting every write whose cwd is inside the folder; or
    joining the target to cwd without normalizing, so
    `<folder>/evidence/../../../src/out.txt` still carries the folder
    prefix.
    Oracle: stdout names SPEC.md for a `..` climb run from a
    subdirectory of the folder.
    """
    root, folder = _handoff_root(tmp_path)
    inside = folder / 'evidence'
    inside.mkdir()
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _gate_payload(inside, tr, 'V10', 'Bash',
                            {'command': 'echo x > ../../../src/out.txt'})
    assert 'SPEC.md' in _run(monkeypatch, capsys, handoff_gate, payload)


def test_gate_folder_mention_after_a_redirect_elsewhere_fires(
        monkeypatch, capsys, tmp_path):
    """A folder path later on the line exempts no write before it.

    Mutation: scanning all text after the operator or the verb for the
    folder prefix instead of the target words, so `> /tmp/out.txt; ls
    .handoff/<slug>/` and `git add /tmp/out.txt; ls .handoff/<slug>/`
    are exempt although their one write lands outside the folder.
    Oracle: stdout names SPEC.md for both spellings, each in a fresh
    session; the write's target is /tmp/out.txt.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    spellings = ['echo x > /tmp/out.txt', 'git add /tmp/out.txt']
    for n, write in enumerate(spellings):
        payload = _gate_payload(
            root, tr, f'V12{n}', 'Bash',
            {'command': f'{write}; ls .handoff/{_SLUG}/'})
        out = _run(monkeypatch, capsys, handoff_gate, payload)
        assert 'SPEC.md' in out, write


def test_gate_folder_boundary_is_the_armed_folder_alone(monkeypatch, capsys,
                                                        tmp_path):
    """The exemption covers the armed folder itself and no sibling.

    Mutation: dropping the trailing separator from the folder path, so
    `.handoff/<slug>-2/f` is exempt; or from the resolved target, so
    `git add .` run from the folder reports; or dropping the literal
    prefix fast path, so `$ROOT/.handoff/<slug>/f` reports.
    Oracle: stdout empty for the folder itself as a target, spelled
    `git add .` from the folder and `git add .handoff/<slug>` from the
    root, and for a redirect to `$ROOT/.handoff/<slug>/f`; stdout
    naming SPEC.md for a redirect into `.handoff/<slug>-2/`.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    exempt = [
        (folder, 'git add .'),
        (root, f'git add .handoff/{_SLUG}'),
        (root, f'echo x > $ROOT/.handoff/{_SLUG}/f'),
        ]
    for cwd, command in exempt:
        payload = _gate_payload(cwd, tr, 'V14', 'Bash', {'command': command})
        assert _run(monkeypatch, capsys, handoff_gate, payload) == '', command
    payload = _gate_payload(root, tr, 'V14', 'Bash',
                            {'command': f'echo x > .handoff/{_SLUG}-2/f'})
    assert 'SPEC.md' in _run(monkeypatch, capsys, handoff_gate, payload)


def test_gate_reads_a_noclobber_target_and_survives_a_tilde(
        monkeypatch, capsys, tmp_path):
    """A `>|` target is read, and a `~user` target never crashes the gate.

    Mutation: the redirect regex without its optional `|`, so `echo x >|
    smoke.log` run from the folder reports; or pathlib's expanduser in
    place of os.path's, which raises on an unknown user and leaves the
    gate silent for a repo write.
    Oracle: stdout empty for `>| smoke.log` run from the folder; stdout
    naming SPEC.md for `> ~nosuchuser42/out.log` run from the root.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _gate_payload(folder, tr, 'V15', 'Bash',
                            {'command': 'echo x >| smoke.log'})
    assert _run(monkeypatch, capsys, handoff_gate, payload) == ''
    payload = _gate_payload(root, tr, 'V15', 'Bash',
                            {'command': 'echo x > ~nosuchuser42/out.log'})
    assert 'SPEC.md' in _run(monkeypatch, capsys, handoff_gate, payload)


# --- The most recent open wins ---


def test_scan_transcript_last_open_wins():
    """Verify scan_transcript returns the slug of the last hq.py open.

    Mutation: the first open winning instead of the last, so a session
    that switches slugs arms on the wrong folder.
    Oracle: two sequential opens in one chunk; the second slug must be
    returned regardless of the first.
    """
    entries = [
        _bash('python3 scripts/hq.py open foo'),
        _bash('python3 scripts/hq.py open bar'),
        ]
    text = '\n'.join(json.dumps(e) for e in entries) + '\n'
    slug, _, _ = handoff_gate.scan_transcript(text)
    assert slug == 'bar'


def test_gate_quoted_target_inside_folder_stays_exempt(
        monkeypatch, capsys, tmp_path):
    """A redirect to a quoted path inside the folder stays silent.

    Mutation: quoted spans removed before the write-target scan, so the
    folder path vanishes from the text and the handoff's own write is
    reported.
    Oracle: stdout empty for a redirect whose target is the folder path
    in double quotes.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _gate_payload(
        root, tr, 'V7', 'Bash',
        {'command': f'echo x > ".handoff/{_SLUG}/notes.md"'})
    out = _run(monkeypatch, capsys, handoff_gate, payload)
    assert out == ''


def test_gate_quoted_operator_before_a_folder_read_still_fires(
        monkeypatch, capsys, tmp_path):
    """A '>' inside quotes is no write operator for the exemption.

    Mutation: quoted spans kept whole, so the quoted '>' counts as a
    redirect that precedes the folder path and the read is exempted.
    Oracle: stdout names SPEC.md when the only real redirect follows the
    folder path.
    """
    root, folder = _handoff_root(tmp_path)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path / 'state'))
    tr = _transcript(tmp_path / 't.jsonl',
                     [_bash(f'python3 scripts/hq.py open {_SLUG}')])
    payload = _gate_payload(
        root, tr, 'V8', 'Bash',
        {'command': f"grep '>' .handoff/{_SLUG}/SPEC.md > /tmp/out.txt"})
    out = _run(monkeypatch, capsys, handoff_gate, payload)
    assert 'SPEC.md' in out
