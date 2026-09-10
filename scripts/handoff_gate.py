#!/usr/bin/env python3
"""PreToolUse hook that names the handoff files a write should have read.

A handoff ledger marks some artifacts read_before=always or edit. Those
are the files whose content the next session has to hold before it
changes anything - the spec it is building to, the decision it must not
undo. Nothing enforces that today: the agent opens the handoff, reads
the cursor, and edits the repo without ever opening the spec.

This hook watches for the first write after an ``hq open`` and, when
a gated path has not been read this session, hands the model one line
naming the path and the lines to read.

Notes
-----
- The hook runs on every Bash, Edit, Write, and NotebookEdit call on the
  machine, so the common path does one directory glob and stops. Only a
  write inside a project that already holds a handoff ledger costs more.
- It speaks once per session. A gate that repeats becomes noise, and the
  model has the message in context from the first time.
- It fails open in every direction: bad payload, missing transcript,
  unreadable ledger, or any unexpected exception exits 0 in silence. A
  broken gate must never stop a tool call.
- Evidence of a read is the Read tool, a read verb in a Bash command, or
  an ``hq read`` receipt. A path named to ``ls``, ``wc``, or ``grep``
  was listed or searched, not read.
"""

import json
import os
import pathlib
import re
import sys
from typing import Any

try:
    # Script mode puts scripts/ on sys.path; pytest and mutmut import
    # the package instead.
    import hq
except ImportError:
    from scripts import hq

STATE_DIR = os.path.expanduser('~/.claude/cache/context-budget')

WRITE_TOOL_TARGETS = {
    'Edit': 'file_path',
    'Write': 'file_path',
    'NotebookEdit': 'notebook_path',
    }

_HEREDOC = re.compile(r'<<-?\s*[\'"]?(\w+)[\'"]?')
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", re.S)
_FD_REDIRECT = re.compile(r'\d?>\s*&\s*\d')
_NULL_REDIRECT = re.compile(r'(?:\d|&)?>\s*/dev/null')
_INPLACE = re.compile(r'\bsed\s+-[a-zA-Z]*i|\bsed\s+--in-place')
_WRITE_VERB = re.compile(r'\btee\s|\bgit\s+add\b|\bgit\s+commit\b')
_READ_VERB = re.compile(r'\b(?:cat|head|tail|less)\s|\bsed\s+-n\b')
# A slug is one path component of letters, digits, '.', '_', and
# '-', so the class ends the capture at shell punctuation and a
# closing quote: `open demo; echo` arms on `demo`, not `demo;`.
_OPEN_VERB = re.compile(
    r'(?<![\w.-])hq(?:\.py)?\s+open\s+["\']?([A-Za-z0-9._-]+)')
# Notes:
# - The command word of a shell segment is hq or hq.py, bare or as a
#   path, after any variable assignments and an optional python3: the
#   segment runs the handoff tooling. A quote may open the segment
#   (`bash -c "hq ..."`) or wrap the path.
# - The word elsewhere - a commit message, a redirect target, an echo
#   - is a mention, and the write it sits in still counts.
_HQ_COMMAND = re.compile(
    r'(?:^|[;|&(`"\'\n]\s*)(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*'
    r'(?:python3?\s+)?["\']?(?:\S*/)?hq(?:\.py)?["\']?(?=\s|$)')
# Notes:
# - A quoted span is a mention of the open, not the command, only when
#   the word owning the quote searches, edits, prints, or records text;
#   a quote an executor owns - `bash -c`, `ssh`, `docker run` - runs
#   it, and an unlisted owner arms, the benign side of the guess. The
#   owner is a command word, never a flag: a `-m` belongs to docker
#   and ssh as much as to git.
# - A `$(` inside the span runs whatever follows it, whoever owns the
#   quote.
# - The owner is read from the span's own shell segment, past the last
#   `;`, `|`, `&`, or newline, with earlier quoted spans blanked first,
#   so an echo earlier on the line says nothing about a later `bash
#   -c`, and a `|` inside an earlier argument does not cut the segment.
_MENTION_VERB = re.compile(
    r'\b(?:grep|rg|ag|ack|sed|awk|perl|echo|printf|git\s+commit)\b')
_SEGMENT_SPLIT = re.compile(r'[;|&\n]')
_TOKEN_SPLIT = re.compile(r'[\s\'"]+')


def bash_writes(command: str) -> bool:
    """Decide whether a shell command can change a file.

    Parameters
    ----------
    command : str
        The command line as sent in ``tool_input.command``.

    Returns
    -------
    bool
        True when the command redirects to a file, edits in place, tees,
        or stages or commits to git.

    Notes
    -----
    - Heredoc bodies, then quoted spans, then the redirections that go
      to another descriptor or to /dev/null are removed first. What
      survives holds only the redirections that reach a file, so a bare
      ``>`` in the remainder is the whole test.
    - ``&> file`` writes and ``&>/dev/null`` does not, which is why the
      /dev/null forms are stripped by name rather than by operator.
    - A segment whose command word is ``hq`` or ``hq.py`` runs the
      handoff tooling itself and never counts, whatever it redirects;
      the word elsewhere on the line is a mention and exempts nothing.
    """
    text = _strip_heredocs(command)
    if _HQ_COMMAND.search(text):
        return False
    text = _QUOTED.sub(' ', text)
    text = _FD_REDIRECT.sub(' ', text)
    text = _NULL_REDIRECT.sub(' ', text)
    if '>' in text:
        return True
    return bool(_INPLACE.search(text) or _WRITE_VERB.search(text))


def _strip_heredocs(command: str) -> str:
    """Return the command with every heredoc body removed.

    Parameters
    ----------
    command : str
        The command line as sent in ``tool_input.command``.

    Returns
    -------
    str
        The command's own lines, each heredoc body dropped.
    """
    kept: list[str] = []
    delimiter = ''
    for line in command.splitlines():
        if delimiter:
            if line.strip() == delimiter:
                delimiter = ''
            continue
        kept.append(line)
        opener = _HEREDOC.search(line)
        if opener:
            delimiter = opener.group(1)
    return '\n'.join(kept)


def scan_transcript(text: str) -> tuple[str, list[str], list[str]]:
    """Pull the armed slug and the reading a transcript chunk records.

    Parameters
    ----------
    text : str
        A run of transcript JSONL, whole lines, not necessarily from the
        start of the file.

    Returns
    -------
    tuple[str, list[str], list[str]]
        The slug of the last ``hq open`` in the chunk or '' when it
        holds none, the file_path of every Read tool call, and every
        Bash command carrying a read verb.

    Notes
    -----
    - A line that is not JSON, not an assistant record, or holds no
      tool_use block is skipped; a transcript truncated mid-write costs
      at most its last line.
    - An ``hq open`` quoted under a word that searches, edits, prints,
      or records text - a grep or sed on the phrase, a commit message -
      is a mention and arms nothing; quoted under an executor such as
      ``bash -c``, or inside a ``$(``, it is the command and arms.
    """
    slug = ''
    reads: list[str] = []
    commands: list[str] = []
    for line in text.splitlines():
        if '"tool_use"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get('type') != 'assistant':
            continue
        content = (entry.get('message') or {}).get('content')
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            fields = block.get('input') or {}
            if block.get('name') == 'Read':
                target = fields.get('file_path')
                if target:
                    reads.append(str(target))
            elif block.get('name') == 'Bash':
                command = str(fields.get('command') or '')
                mention_spans = [
                    m.span() for m in _QUOTED.finditer(command)
                    if '$(' not in m.group(0)
                    and _MENTION_VERB.search(_SEGMENT_SPLIT.split(
                        _QUOTED.sub(' ', command[:m.start()]))[-1])
                    ]
                for opened in _OPEN_VERB.finditer(command):
                    if not any(a <= opened.start() < b for a, b in mention_spans):
                        slug = opened.group(1)
                if _READ_VERB.search(command):
                    commands.append(command)
    return slug, reads, commands


def gate(payload: dict[str, Any]) -> int:
    """Report the gated paths a write is about to run ahead of.

    Parameters
    ----------
    payload : dict[str, Any]
        The PreToolUse payload, carrying cwd, session_id,
        transcript_path, tool_name, and tool_input.

    Returns
    -------
    int
        Always 0. The hook allows the call either way; the message it
        prints is the whole effect.

    Notes
    -----
    - Session state lives beside the context-budget state, keyed
      ``<session>.handoff.json`` under HQ_STATE_DIR, and holds the
      transcript offset already scanned so no call rescans from 0.
    - The Stop hook writes the ``stop`` key of that same file, so the
      whole document is read and rewritten, never replaced.
    """
    if os.environ.get('HQ_GATE') == '0':
        return 0
    name = hq.HANDOFF_DIRNAME
    cwd = str(payload.get('cwd') or '')
    start = pathlib.Path(cwd or '.')
    root = None
    for candidate in [start, *start.parents]:
        if next((candidate / name).glob('*/ledger.tsv'), None):
            root = candidate
            break
    if root is None:
        return 0

    tool = str(payload.get('tool_name') or '')
    fields = payload.get('tool_input') or {}
    command = str(fields.get('command') or '')
    if tool in WRITE_TOOL_TARGETS:
        named = str(fields.get(WRITE_TOOL_TARGETS[tool]) or '')
        if not named:
            return 0
        target = pathlib.Path(named).expanduser()
        if not target.is_absolute():
            target = pathlib.Path(cwd) / target
        handoffs = os.path.normpath(str(root / name)) + os.sep
        if os.path.normpath(str(target)).startswith(handoffs):
            return 0
    elif tool == 'Bash':
        if not bash_writes(command):
            return 0
    else:
        return 0

    session = str(payload.get('session_id') or 'unknown').replace('/', '_')
    state_dir = pathlib.Path(os.environ.get('HQ_STATE_DIR', STATE_DIR))
    state_path = state_dir / f'{session}.handoff.json'
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    held = state.get('gate') or {}
    if held.get('reported'):
        return 0
    offset = int(held.get('offset') or 0)
    slug = str(held.get('slug') or '')
    reads = list(held.get('reads') or [])
    commands = list(held.get('read_commands') or [])

    transcript = pathlib.Path(str(payload.get('transcript_path') or ''))
    try:
        size = transcript.stat().st_size
    except OSError:
        size = 0
    if size > offset:
        with transcript.open('rb') as handle:
            handle.seek(offset)
            chunk = handle.read()
        # A line still being written is left for the next call, whole,
        # rather than split across two scans and lost.
        chunk = chunk[:chunk.rfind(b'\n') + 1]
        offset += len(chunk)
        found, new_reads, new_commands = scan_transcript(
            chunk.decode('utf-8', 'replace'))
        slug = found or slug
        reads.extend(new_reads)
        commands.extend(new_commands)

    folder = None
    if slug:
        exact = root / name / slug
        if exact.is_dir():
            folder = exact
        else:
            matches = [
                entry for entry in (root / name).iterdir()
                if entry.is_dir() and entry.name.startswith(slug)
                ]
            folder = matches[0] if len(matches) == 1 else None
    # Notes:
    # - A write inside the folder is the handoff's own bookkeeping, so
    #   the folder is exempt as a write target and never as a read
    #   source: the prefix must follow a redirect, an in-place edit, or
    #   a write verb.
    # - A quoted target keeps its text while a quoted operator loses
    #   its angle brackets, so `> "working/x/f"` counts as a write into
    #   the folder and `grep '>' working/x/f > out` does not.
    if folder is not None and f'{name}/{folder.name}/' in command:
        text = _QUOTED.sub(
            lambda m: re.sub(r'[<>]', ' ', m.group(0)[1:-1]),
            _strip_heredocs(command))
        text = _NULL_REDIRECT.sub(' ', _FD_REDIRECT.sub(' ', text))
        prefix = f'{name}/{folder.name}/'
        operator_ends = [m.end() for m in re.finditer(r'>>?', text)]
        operator_ends += [m.end() for m in _INPLACE.finditer(text)]
        operator_ends += [m.end() for m in _WRITE_VERB.finditer(text)]
        if any(prefix in text[end:] for end in operator_ends):
            folder = None

    message = ''
    reported = False
    if folder is not None:
        rows = hq.latest_rows(
            hq._read_tsv(folder / 'ledger.tsv', hq.LEDGER_FIELDS))
        try:
            receipts = (state_dir / f'hq-reads-{session}.txt').read_text(
                encoding='utf-8').splitlines()
        except OSError:
            receipts = []
        opened = set()
        for entry in reads:
            item = pathlib.Path(entry).expanduser()
            if not item.is_absolute():
                item = pathlib.Path(cwd) / item
            opened.add(os.path.normpath(str(item)))
        tokens = [set(_TOKEN_SPLIT.split(entry)) for entry in commands]
        missing: list[tuple[str, str]] = []
        for row in rows.values():
            if row['status'] != 'live' or row['read_before'] not in hq._GATE_RB:
                continue
            stored = row['path']
            if row['base'] == 'abs':
                target = pathlib.Path(stored).expanduser()
            else:
                target = folder / stored
            absolute = os.path.normpath(str(target))
            named = {stored, absolute, os.path.relpath(absolute, cwd or '.')}
            if absolute in opened:
                continue
            if any(named & seen for seen in tokens):
                continue
            tail = f' {folder.name} {stored}'
            if any(line.endswith(tail) for line in receipts):
                continue
            if row['where'] == '-':
                span = 'whole file'
            else:
                try:
                    text = target.read_text(encoding='utf-8', errors='replace')
                except OSError:
                    text = ''
                spans, _ = hq.resolve_where(
                    text,
                    [a.strip() for a in row['where'].split(';') if a.strip()])
                span = (f'lines {spans[0][0]}-{spans[0][1]}' if spans
                        else 'anchor not found')
            missing.append((stored, span))
        reported = True
        if missing:
            listed = ', '.join(f'{path} ({span})' for path, span in missing)
            message = (f'handoff gate: {folder.name}: {len(missing)} gated '
                       f'path(s) not read this session - {listed}; read each '
                       f'or run: hq read {folder.name} {missing[0][0]}')

    state['gate'] = {
        'offset': offset,
        'slug': slug,
        'reads': reads,
        'read_commands': commands,
        'reported': reported,
        }
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state), encoding='utf-8')
    except OSError:
        pass
    if not message:
        return 0
    if os.environ.get('HQ_GATE_DENY') == '1':
        decision = {'hookEventName': 'PreToolUse',
                    'permissionDecision': 'deny',
                    'permissionDecisionReason': message}
    else:
        decision = {'hookEventName': 'PreToolUse',
                    'permissionDecision': 'allow',
                    'additionalContext': message}
    json.dump({'hookSpecificOutput': decision}, sys.stdout)
    return 0


def main() -> int:
    """Read one PreToolUse payload from stdin and run the gate.
    """
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        return gate(payload)
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())
