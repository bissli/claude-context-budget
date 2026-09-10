"""Adoption of Key files pointers: merged rows, comma lists, loose
bullets, section-letter seeds, the Log roll-up, and the top-level
HANDOFF rule.
"""

import pathlib

import pytest
from scripts import hq

_SLUG = 'ptr-test'
_SESSION = 'session-ptr'
_NOW = '2026-09-01T12:00:00'

_CURSOR = (
    '## Task\n\nDo the work.\n\n'
    '## Now\n\nNext step.\n\n'
    '## Plan\n\nPlan line.\n\n'
    '## State\n\nState line.\n\n'
    '## Environment\n\nEnv line.\n\n'
    '## Open questions\n\nNone.\n'
)


def _root(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, slug: str = _SLUG,
) -> pathlib.Path:
    """Create HQ_ROOT and set required env vars.
    """
    root = pathlib.Path(tmp_path) / 'root'
    root.mkdir(exist_ok=True)
    monkeypatch.setenv('HQ_ROOT', str(root))
    monkeypatch.setenv('HQ_NOW', _NOW)
    monkeypatch.setenv('HQ_SESSION', _SESSION)
    monkeypatch.setenv('HQ_HOST', 'test-host')
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('HQ_GIT', '0')
    monkeypatch.delenv('HQ_CYCLE', raising=False)
    folder = root / 'working' / slug
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _handoff(
    folder: pathlib.Path, key_files: str = '', cycle: int = 3, extra: str = '',
) -> str:
    """Write a conforming HANDOFF.md with an optional Key files section.
    """
    text = (
        f'# Handoff: {folder.name}\n\n'
        f'Written: 2026-09-01 | Cycle: {cycle}\n\n'
        + _CURSOR
    )
    if key_files:
        text += '\n## Key files\n\n' + key_files
    text += extra
    (folder / 'HANDOFF.md').write_text(text, encoding='utf-8')
    return text


def _ledger(folder: pathlib.Path) -> list[dict]:
    """Return ledger rows as a list of dicts.
    """
    return hq._read_tsv(folder / 'ledger.tsv', hq.LEDGER_FIELDS)


def _manifest(folder: pathlib.Path) -> list[dict]:
    """Return manifest rows as a list of dicts.
    """
    return hq._read_tsv(
        folder / 'cycles' / 'manifest.tsv', hq.MANIFEST_FIELDS)


# --- Two pointers to one path ---


def test_two_pointers_to_same_path_merge_label_where_and_rb(
        tmp_path, monkeypatch):
    """Two Key files bullets to one path merge label, where, and read_before.

    Mutation: kf_map[stored] overwritten by second pointer, so first label
    text and first where anchor are silently dropped.
    Oracle: single DESIGN.md ledger row whose label contains both pointer
    texts joined with '; ' in order, where='s2;s3', read_before='always';
    the Read first block in HANDOFF.md contains two comma-separated spans.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'DESIGN.md').write_text(
        '# Design\n\n## 2 Overview\n\ncontent\n\n## 3 Detail\n\ncontent\n')
    _handoff(folder, key_files=(
        'Read now:\n'
        '- `DESIGN.md` section 2 overview\n'
        '- `DESIGN.md` section 3 detail\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    assert 'DESIGN.md' in rows
    r = rows['DESIGN.md']
    assert 'section 2 overview' in r['label']
    assert 'section 3 detail' in r['label']
    assert r['where'] == 's2;s3'
    assert r['read_before'] == 'always'
    hf_text = (folder / 'HANDOFF.md').read_text()
    # Both spans appear in the Read first block, comma separates them.
    assert 'DESIGN.md:' in hf_text
    assert ',' in hf_text.split('DESIGN.md:')[1].split('\n')[0]


def test_two_pointers_different_rb_grade_merges_to_always(
        tmp_path, monkeypatch):
    """A Read now and a bare pointer to the same path both yield always.

    Mutation: rb_over merge drops the always override, falling back to the
    grade of whichever pointer is stored last.
    Oracle: notes-x.md read_before='always' and label contains both texts.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'notes-x.md').write_text('# X\n')
    _handoff(folder, key_files=(
        'Read now:\n'
        '- `notes-x.md` first pointer\n'
        '- `notes-x.md` second pointer\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    assert rows['notes-x.md']['read_before'] == 'always'
    assert 'first pointer' in rows['notes-x.md']['label']
    assert 'second pointer' in rows['notes-x.md']['label']


# --- Several paths on one bullet ---


def test_multi_path_bullet_seeds_one_row_per_path(tmp_path, monkeypatch):
    """A comma-separated list of paths on one bullet seeds a row per path.

    Mutation: only the first path token stored, so subsequent paths
    produce no ledger row and the first path's label begins with a comma.
    Oracle: three rows each with label 'shipped in v0.2.0'; first path's
    label does not start with a comma or backtick.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'hq.py').write_text('# hq\n')
    (folder / 'gate.py').write_text('# gate\n')
    (folder / 'cfg.json').write_text('{}')
    _handoff(folder, key_files=(
        '- `hq.py`, `gate.py`, `cfg.json` - shipped in v0.2.0\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    for path in ('hq.py', 'gate.py', 'cfg.json'):
        assert path in rows, f'expected row for {path}'
        assert rows[path]['label'] == 'shipped in v0.2.0', (
            f'{path} label: {rows[path]["label"]!r}')
    assert not rows['hq.py']['label'].startswith(',')
    assert not rows['hq.py']['label'].startswith('`')


# --- The conservation witness ---


def test_witnessed_pairs_filters_by_written_label():
    """witnessed_pairs keeps records whose label_part is in written_labels.

    Mutation: filter removed, so overwritten-pointer records count as
    carried and mask a true conservation miss.
    Oracle: three records - '-' part always kept, matching part kept,
    non-matching part excluded; result preserves insertion order.
    """
    records = [
        ('a.md', 'raw a', '-'),
        ('b.md', 'raw b', 'the detail'),
        ('c.md', 'raw c', 'missing part'),
        ]
    written_labels = {
        'a.md': 'anything goes here',
        'b.md': 'the detail and more text',
        'c.md': 'entirely different text',
        }
    result = hq.witnessed_pairs(records, written_labels)
    assert 'raw a' in result
    assert 'raw b' in result
    assert 'raw c' not in result
    assert result.index('raw a') < result.index('raw b')


def test_witnessed_pairs_absent_path_excluded_unless_dash():
    """A record whose stored path is absent from written_labels is excluded.

    Mutation: missing-key lookup returns a default that always passes, so
    ghost witnesses pollute the union.
    Oracle: record for 'd.md' not in written_labels is excluded; '-' part
    for 'e.md' is kept regardless.
    """
    records = [
        ('d.md', 'raw d', 'some label'),
        ('e.md', 'raw e', '-'),
        ]
    written_labels: dict = {}
    result = hq.witnessed_pairs(records, written_labels)
    assert 'raw d' not in result
    assert 'raw e' in result


def test_multi_path_bullet_first_line_reported_carried(
        tmp_path, monkeypatch, capsys):
    """The multi-path bullet's original line is covered by the witness.

    Mutation: witnesses for multi-path paths carry only 'path free' (the
    individual token + free text), not the full original line, so the
    comma-separated line fails the conservation substring check.
    Oracle: capsys output contains 'every original line carried'.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'hq.py').write_text('# hq\n')
    (folder / 'gate.py').write_text('# gate\n')
    _handoff(folder, key_files=(
        '- `hq.py`, `gate.py` - shared label\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    out = capsys.readouterr().out
    assert 'every original line carried' in out


# --- A loose bullet and its continuation lines ---


def test_loose_key_files_bullet_with_continuation_is_one_unfiled(
        tmp_path, monkeypatch):
    """A loose Key files bullet joined with indented lines is one unfiled.

    Mutation: indented lines after a loose bullet each open their own
    unfiled entry, producing three bullets instead of one.
    Oracle: exactly one unfiled bullet whose text contains all three parts;
    the continuation text does not appear as a standalone unfiled entry.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'notes-a.md').write_text('# A\n')
    _handoff(folder, key_files=(
        '- `notes-a.md` the live sketch\n'
        '- Earlier cycles material: `evidence/old/`,\n'
        '  data from prior runs\n'
        '  and archived notes\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    hf_text = (folder / 'HANDOFF.md').read_text()
    assert '- unfiled: - Earlier cycles material:' in hf_text
    assert 'data from prior runs' in hf_text
    assert 'and archived notes' in hf_text
    standalone_continuation = [
        ln for ln in hf_text.splitlines()
        if ln.startswith('- unfiled:')
        and 'data from prior runs' in ln
        and 'Earlier cycles' not in ln
    ]
    assert not standalone_continuation, (
        'continuation text appeared as its own unfiled entry')


# --- The where seed and section letters ---


def test_where_seed_accepts_trailing_letter_on_section_number(
        tmp_path, monkeypatch):
    """'section 11b' seeds 's11b' and 'section 12, Migration' seeds 's12'.

    Mutation: regex without [a-z]? suffix on the number group truncates
    'section 11b' to 's11'.
    Oracle: ledger where field is 's11b;s12' for a pointer whose free text
    cites 'section 11b' and 'section 12, Migration'.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'DESIGN.md').write_text(
        '# Design\n\n## 11b. Proof\n\nx\n\n## 12. Migration\n\ny\n')
    _handoff(folder, key_files=(
        '- `DESIGN.md` covers section 11b and section 12, Migration\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    assert rows['DESIGN.md']['where'] == 's11b;s12'


def test_where_seed_plain_number_unchanged(tmp_path, monkeypatch):
    """'section 5' still seeds 's5' when no trailing letter is present.

    Mutation: [a-z]? pattern breaks the digit-only case so 's5' is not
    matched or is corrupted.
    Oracle: ledger where field is 's5'.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'DESIGN.md').write_text('# Design\n\n## 5. Details\n\nx\n')
    _handoff(folder, key_files='- `DESIGN.md` see section 5 for details\n')

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    assert rows['DESIGN.md']['where'] == 's5'


def test_where_seed_keeps_only_anchors_the_file_resolves(
        tmp_path, monkeypatch, capsys):
    """An `s<n>` word whose section is not in the pointed file is not seeded.

    Mutation: the mined anchors written unfiltered, so `s1` from prose
    naming another file's step seeds `where=s1`, the read block renders
    `?`, and `open` reports it every cycle; or the dropped anchor not
    printed, so the loss is silent at adopt time.
    Oracle: notes-cache.md has headings 2 and 4 only; the label cites
    `s1`, `s2`, and `section 4`, so the row's where is `s2;s4` and the
    summary prints `where dropped: notes-cache.md 's1'`.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'notes-cache.md').write_text(
        '# Cache\n\n## 2. Layout\n\nx\n\n## 4. Eviction\n\ny\n')
    _handoff(folder, key_files=(
        '- `notes-cache.md` Read now: layout (s2), the S1 premise, and\n'
        '  eviction under section 4\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    assert rows['notes-cache.md']['where'] == 's2;s4'
    out = capsys.readouterr().out
    assert "  where dropped: notes-cache.md 's1'" in out


# --- The adopt Log roll-up ---


def test_adopt_log_field_is_summary_not_full_lines(tmp_path, monkeypatch):
    """Adopt manifest log carries a line-count summary, not the line text.

    Mutation: adopt_log inlines all legacy log lines into the log field,
    so the manifest log field grows unbounded with prior text.
    Oracle: log == 'adopted; prior Log: 2 lines in cycles/c02.md'; note
    field carries the joined lines; HANDOFF.md Log section has the
    summary, not the prior lines verbatim.
    """
    folder = _root(tmp_path, monkeypatch)
    folder.mkdir(parents=True, exist_ok=True)
    log_lines = [
        '- 2026-08-30 (cycle 1): cache layout drafted.',
        '- 2026-08-31 (cycle 2): generator wired to the layout.',
        ]
    (folder / 'HANDOFF.md').write_text(
        f'# Handoff: {folder.name}\n\nWritten: 2026-08-31 | Cycle: 2\n\n'
        '## Task\nx\n\n## Now\ny\n\n## Log\n' + '\n'.join(log_lines) + '\n')

    assert hq.main(['adopt', _SLUG]) == 0

    manifest = _manifest(folder)
    last = manifest[-1]
    assert last['log'] == 'adopted; prior Log: 2 lines in cycles/c02.md'
    assert '2026-08-30' in last['note']
    assert '2026-08-31' in last['note']
    hf_text = (folder / 'HANDOFF.md').read_text()
    assert 'adopted; prior Log: 2 lines in cycles/c02.md' in hf_text
    assert 'cache layout drafted' not in hf_text


def test_adopt_log_field_is_bare_adopted_with_no_log_section(
        tmp_path, monkeypatch):
    """Adopt sets log='adopted' with no suffix when the file has no Log.

    Mutation: legacy_log condition missing, so the summary suffix is
    appended even when there are no legacy lines (e.g. '0 lines in ...').
    Oracle: manifest log == 'adopted' exactly; note == '-'.
    """
    folder = _root(tmp_path, monkeypatch)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'HANDOFF.md').write_text(
        f'# Handoff: {folder.name}\n\nWritten: 2026-09-01 | Cycle: 1\n\n'
        '## Task\nx\n\n## Now\ny\n')

    assert hq.main(['adopt', _SLUG]) == 0

    manifest = _manifest(folder)
    last = manifest[-1]
    assert last['log'] == 'adopted'
    assert last['note'] == '-'


# --- HANDOFF*.md at the top level only ---


def test_infer_kind_handoff_md_at_top_level_is_snapshot():
    """HANDOFF.md at top_level=True is classified snapshot (preserved behavior).

    Mutation: HANDOFF*.md check removed from _SNAPSHOT_PATS without a
    top_level-gated replacement, so top-level HANDOFF.md is no longer snapshot.
    Oracle: infer_kind('HANDOFF.md', False, '', top_level=True) ==
    ('snapshot', 'never').
    """
    assert hq.infer_kind('HANDOFF.md', False, '', top_level=True) == (
        'snapshot', 'never')


def test_infer_kind_handoff_md_nested_is_other():
    """HANDOFF.md at top_level=False is 'other', not snapshot.

    Mutation: HANDOFF*.md check fires regardless of top_level, so an
    outside HANDOFF.md pointer is seeded kind 'snapshot' instead of 'other'.
    Oracle: infer_kind('HANDOFF.md', False, '# Handoff: x', top_level=False)
    == ('other', 'never').
    """
    assert hq.infer_kind(
        'HANDOFF.md', False, '# Handoff: x', top_level=False) == (
        'other', 'never')


def test_other_snapshot_patterns_are_level_independent():
    """Patterns *.pre-*, *.bak, etc. yield snapshot at any top_level value.

    Mutation: all snapshot patterns gated on top_level, so nested *.pre-*
    and *.bak files no longer classify as snapshot.
    Oracle: notes.bak and SPEC.prev.md return ('snapshot', 'never') at
    top_level=False.
    """
    assert hq.infer_kind('notes.bak', False, '', top_level=False) == (
        'snapshot', 'never')
    assert hq.infer_kind('SPEC.prev.md', False, '', top_level=False) == (
        'snapshot', 'never')


def test_adopt_outside_handoff_pointer_seeds_kind_other(
        tmp_path, monkeypatch):
    """A Read now pointer to an outside HANDOFF.md seeds kind 'other'.

    Mutation: HANDOFF*.md check fires for any path, so the outside handoff
    is seeded kind 'snapshot' instead of 'other'.
    Oracle: ledger row for ~/OTHER/HANDOFF.md has kind='other',
    read_before='always'.
    """
    folder = _root(tmp_path, monkeypatch)
    home = pathlib.Path(tmp_path) / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    other_dir = home / 'OTHER'
    other_dir.mkdir()
    other_hf = other_dir / 'HANDOFF.md'
    other_hf.write_text(
        '# Handoff: other\n\nWritten: 2026-09-01 | Cycle: 1\n')
    _handoff(folder,
             key_files='Read now:\n- `~/OTHER/HANDOFF.md` ref handoff\n')

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    r = rows.get('~/OTHER/HANDOFF.md')
    assert r is not None
    assert r['kind'] == 'other'
    assert r['read_before'] == 'always'


def test_multi_path_bullet_wrapped_over_lines_shares_the_whole_text(
        tmp_path, monkeypatch, capsys):
    """A comma list that wraps onto indented lines still seeds every path.

    Mutation: the comma list split on the first physical line before its
    continuation lines join, so the shared text is that line's tail (a
    bare comma) and the wrapped paths land under Unfiled.
    Oracle: five rows carrying the hand-written shared label, no Unfiled
    section, and 'every original line carried' printed.
    """
    folder = _root(tmp_path, monkeypatch)
    for name in ('a.py', 'b.py', 'c.py', 'd.json', 'e.md'):
        (folder / name).write_text('x\n')
    _handoff(folder, key_files=(
        '- `a.py`, `b.py`, `c.py`,\n'
        '  `d.json`, `e.md` - shipped in v0.2.0; the\n'
        '  installed copies live under\n'
        '  `~/x/`.\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    expected = 'shipped in v0.2.0; the installed copies live under `~/x/`.'
    for name in ('a.py', 'b.py', 'c.py', 'd.json', 'e.md'):
        assert rows[name]['label'] == expected, name
    hf_text = (folder / 'HANDOFF.md').read_text()
    assert '## Unfiled' not in hf_text
    assert 'every original line carried' in capsys.readouterr().out


def test_separator_pointer_is_reported_carried(tmp_path, monkeypatch, capsys):
    """A pointer written as path, ` - `, text passes conservation.

    Mutation: the witness text built after the separator strip, so the
    original line with its ` - ` is a substring of nothing in the union.
    Oracle: 'every original line carried' printed and the label is the
    text alone.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'notes-a.md').write_text('# A\n')
    _handoff(folder, key_files='- `notes-a.md` - the sketch, kept live\n')

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    assert rows['notes-a.md']['label'] == 'the sketch, kept live'
    assert 'every original line carried' in capsys.readouterr().out


def test_merged_labels_join_after_a_sentence_with_a_space(
        tmp_path, monkeypatch):
    """Two labels for one path join with a space when the first ends a sentence.

    Mutation: the join fixed to '; ', producing 'first clause.; second'.
    Oracle: the hand-written merged label 'first clause. second clause'.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'notes-x.md').write_text('# X\n')
    _handoff(folder, key_files=(
        '- `notes-x.md` first clause.\n'
        '- `notes-x.md` second clause\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    assert rows['notes-x.md']['label'] == 'first clause. second clause'


def test_bare_first_token_with_glued_comma_opens_the_list(
        tmp_path, monkeypatch):
    """A bare first path with a glued comma still seeds every later path.

    Mutation: the glued comma cut from the first token without being
    handed back to the list walk, so the second path never opens and its
    text sinks into the first path's label.
    Oracle: two rows, both read_before always under Read now, both with
    the hand-written label; the second path is not inside the first's
    label.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'a.md').write_text('a\n')
    (folder / 'b.md').write_text('b\n')
    _handoff(folder, key_files='Read now:\n- a.md, b.md - bare tokens\n')

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    for name in ('a.md', 'b.md'):
        assert rows[name]['label'] == 'bare tokens', name
        assert rows[name]['read_before'] == 'always', name


def test_list_ending_in_a_word_drops_the_leading_comma(tmp_path, monkeypatch):
    """A comma list closed by a word keeps that word, not the comma before it.

    Mutation: the separator strip applied only to ` - `, so a walk that
    halts on a word leaves a label that opens with a comma.
    Oracle: both rows carry the hand-written label 'and their tests - the
    shared text'.
    """
    folder = _root(tmp_path, monkeypatch)
    (folder / 'a.md').write_text('a\n')
    (folder / 'b.md').write_text('b\n')
    _handoff(folder, key_files=(
        '- `a.md`, `b.md`, and their tests - the shared text\n'))

    assert hq.main(['adopt', _SLUG]) == 0

    rows = {r['path']: r for r in _ledger(folder)}
    for name in ('a.md', 'b.md'):
        assert rows[name]['label'] == 'and their tests - the shared text', name
