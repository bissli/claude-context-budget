"""The work-dir verb: resolution order, the pin, and the advisories.

Each test pins one defect of the placement machinery: a source read out of
order, a refused token that still writes the pin, a scan that pins on its
own, a kind folder whose files keep their name-based kind, and a finish
advisory that fires on a row placed under an earlier ruling.
"""

import pathlib

from scripts import hq

_SLUG = 'wd-slug'
_SESSION = 'session-wd'
_HOST = 'test-host'
_NOW = '2026-09-11T12:00:00'


def _root(tmp_path, monkeypatch):
    """Create an HQ_ROOT with the HQ_* environment set; return the root."""
    root = pathlib.Path(tmp_path) / 'root'
    root.mkdir(exist_ok=True)
    monkeypatch.setenv('HQ_ROOT', str(root))
    monkeypatch.setenv('HQ_CYCLE', '1')
    monkeypatch.setenv('HQ_NOW', _NOW)
    monkeypatch.setenv('HQ_SESSION', _SESSION)
    monkeypatch.setenv('HQ_HOST', _HOST)
    monkeypatch.setenv('HQ_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('HQ_GIT', '0')
    monkeypatch.delenv('HQ_WORK_DIR', raising=False)
    return root


def _pin(root):
    """Return the pin file's text, or None when no pin exists."""
    pin = root / '.handoff' / 'work-dir'
    return pin.read_text() if pin.is_file() else None


def test_env_wins_over_the_pin_and_a_bad_env_falls_through_to_it(
        tmp_path, monkeypatch, capsys):
    """HQ_WORK_DIR short-circuits the pin; one that fails its check is named
    and the pin is read.

    Mutation: the pin read before the env var, or a failing env var left the
    thread unpinned instead of falling through.
    Oracle: 'docs (env)' with both set; with HQ_WORK_DIR naming a file,
    the env line plus 'design (pin)', exit 0 both times.
    """
    root = _root(tmp_path, monkeypatch)
    (root / 'docs').mkdir()
    (root / 'design').mkdir()
    (root / 'afile').write_text('x\n')
    (root / '.handoff').mkdir()
    (root / '.handoff' / 'work-dir').write_text('design\n')
    monkeypatch.setenv('HQ_WORK_DIR', 'docs')

    assert hq.main(['work-dir']) == 0
    assert capsys.readouterr().out == 'work dir: docs (env)\n'

    monkeypatch.setenv('HQ_WORK_DIR', 'afile')
    assert hq.main(['work-dir']) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith('HQ_WORK_DIR=afile is not a directory - ')
    assert out[1] == 'work dir: design (pin)'


def test_a_pin_of_dot_handoff_resolves_to_the_folder_and_names_the_kind_folders(
        tmp_path, monkeypatch, capsys):
    """The literal .handoff passes the check the folder itself would fail.

    Mutation: the under-.handoff refusal applied before the literal is
    recognized, so 'none found' can never be pinned.
    Oracle: 'hq work-dir .handoff' exits 0 and writes '.handoff'; the next
    'hq work-dir' prints '.handoff (pin)' with the kind folders in its move.
    """
    root = _root(tmp_path, monkeypatch)

    assert hq.main(['work-dir', '.handoff']) == 0
    assert _pin(root) == '.handoff\n'
    capsys.readouterr()

    assert hq.main(['work-dir']) == 0
    out = capsys.readouterr().out
    assert out.startswith('work dir: .handoff (pin) - made files go under notes/')


def test_refused_tokens_write_no_pin_and_each_names_its_reason(
        tmp_path, monkeypatch, capsys):
    """The root, a path under .handoff/, a temp path, an outside path, and a
    plain file are refused with nothing written.

    Mutation: any one check dropped, so a dump target or a temp path is
    pinned and every later session writes there.
    Oracle: exit 1 and no pin file for each token; the printed reason clause
    per token, hand-listed.
    """
    root = _root(tmp_path, monkeypatch)
    (root / '.handoff' / 'other').mkdir(parents=True)
    (root / 'afile').write_text('x\n')
    cases = {
        '.': 'is the root itself',
        '.handoff/other': 'is under .handoff/',
        '/tmp': 'is under the system temp directory',
        '/usr': 'is outside the root',
        'afile': 'is not a directory',
        }
    for token, reason in cases.items():
        capsys.readouterr()
        assert hq.main(['work-dir', token]) == 1, token
        out = capsys.readouterr().out
        assert out.startswith(f'hq work-dir: {token} {reason}'), out
        assert ' - name a directory under the root' in out
    assert _pin(root) is None


def test_a_declared_directory_is_made_when_missing(tmp_path, monkeypatch, capsys):
    """An env var, a pin, or a pin command naming a directory not on disk
    creates it, so the declaration alone settles the place.

    Mutation: the mkdir dropped at any of the three sites, or the missing
    directory refused as before.
    Oracle: the directory exists on disk after each call and each exits 0.
    """
    root = _root(tmp_path, monkeypatch)
    monkeypatch.setenv('HQ_WORK_DIR', 'scratch/x')
    assert hq.main(['work-dir']) == 0
    assert (root / 'scratch' / 'x').is_dir()
    monkeypatch.delenv('HQ_WORK_DIR')
    (root / '.handoff').mkdir()
    (root / '.handoff' / 'work-dir').write_text('lab\n')
    assert hq.main(['work-dir']) == 0
    assert (root / 'lab').is_dir()
    assert hq.main(['work-dir', 'sandbox/run']) == 0
    assert (root / 'sandbox' / 'run').is_dir()
    assert _pin(root) == 'sandbox/run\n'
    assert capsys.readouterr().out.splitlines() == [
        'work dir: scratch/x (env)',
        'work dir: lab (pin)',
        'work dir: sandbox/run - pinned in .handoff/work-dir',
        ]


def test_a_pinned_directory_is_stored_root_relative_from_any_spelling(
        tmp_path, monkeypatch, capsys):
    """An absolute spelling under the root pins the same value as the
    relative one, so a clone at another path reads the pin unchanged.

    Mutation: the token stored as typed.
    Oracle: 'docs/design' in the pin after each spelling, and the success
    line naming the pin file.
    """
    root = _root(tmp_path, monkeypatch)
    (root / 'docs' / 'design').mkdir(parents=True)

    assert hq.main(['work-dir', str(root / 'docs' / 'design')]) == 0
    assert _pin(root) == 'docs/design\n'
    assert hq.main(['work-dir', 'docs/design/']) == 0
    assert _pin(root) == 'docs/design\n'
    assert capsys.readouterr().out.splitlines()[-1] == (
        'work dir: docs/design - pinned in .handoff/work-dir')


def test_unpinned_exits_1_with_the_judgment_line_and_pins_nothing(
        tmp_path, monkeypatch, capsys):
    """With neither source set, the verb hands the choice to the agent and
    writes no pin, whatever the tree holds.

    Mutation: a name scan reintroduced that pins or lists docs/ on its
    own, so a project's user docs become the dump.
    Oracle: exit 1, the judgment line, and no pin file, with a docs/ and a
    design/ present in the tree.
    """
    root = _root(tmp_path, monkeypatch)
    (root / 'docs').mkdir()
    (root / 'design').mkdir()
    (root / 'docs' / 'a.md').write_text('# A\n')

    assert hq.main(['work-dir']) == 1

    assert capsys.readouterr().out == (
        'work dir: unpinned - judge the project layout and CLAUDE.md, then'
        ' hq work-dir <dir>, or .handoff when nothing fits\n')
    assert _pin(root) is None


def test_begin_prints_the_resolved_work_dir_for_the_thread(
        tmp_path, monkeypatch, capsys):
    """Begin names the concrete thread folder for a .handoff pin, the
    directory for a real pin, and 'unpinned' with the verb to run.

    Mutation: begin resolving against the thread folder instead of the
    root, so the pin is never found; or the .handoff value printed bare.
    Oracle: the three hand-written lines, one per state.
    """
    root = _root(tmp_path, monkeypatch)
    assert hq.main(['begin', _SLUG]) == 0
    assert 'work dir: unpinned - run hq work-dir' in capsys.readouterr().out
    assert hq.main(['finish', _SLUG, '--log', 'c1']) == 0
    (root / '.handoff' / 'work-dir').write_text('.handoff\n')
    capsys.readouterr()
    assert hq.main(['begin', _SLUG]) == 0
    assert (f'work dir: .handoff/{_SLUG}/ (pin) - made files go under notes/'
            in capsys.readouterr().out)
    assert hq.main(['finish', _SLUG, '--log', 'c2']) == 0
    (root / 'docs').mkdir()
    (root / '.handoff' / 'work-dir').write_text('docs\n')
    capsys.readouterr()
    assert hq.main(['begin', _SLUG]) == 0
    assert 'work dir: docs (pin)\n' in capsys.readouterr().out


def test_a_kind_folder_sets_the_kind_and_the_walk_lists_its_files(
        tmp_path, monkeypatch, capsys):
    """A file one level under specs/, drafts/, notes/, or outputs/ takes the
    folder's kind whatever its name; the walk lists it and not the folder.

    Mutation: name-based inference kept for nested files, so specs/auth.md
    lands other/never and drafts/x.py other; the walk listing the kind
    folder as one probe-dir entry.
    Oracle: the inferred rows read from the ledger; the begin work list
    naming 'specs/auth.md' and never 'specs', and grading a HANDOFF-named
    file under specs/ as the spec the stamp will record; a .py two levels
    down other; the bare token 'specs' refused with no row.
    """
    root = _root(tmp_path, monkeypatch)
    folder = root / '.handoff' / _SLUG
    for sub in ('specs', 'drafts', 'notes', 'outputs', 'probes'):
        (folder / sub).mkdir(parents=True)
    (folder / 'specs' / 'auth.md').write_text('# Auth\n\nBody.\n')
    (folder / 'specs' / 'HANDOFF-old.md').write_text('# Old\n')
    (folder / 'drafts' / 'x.py').write_text('x = 1\n')
    (folder / 'notes' / 'quirks.md').write_text('# Quirks\n')
    (folder / 'outputs' / 'SPEC-chart.md').write_text('# Spec\n')
    (folder / 'probes' / 'p.py').write_text('y = 2\n')
    (folder / 'drafts' / 'deep').mkdir()
    (folder / 'drafts' / 'deep' / 'z.py').write_text('z = 3\n')
    assert hq.main(['begin', _SLUG]) == 0
    work_list = capsys.readouterr().out
    assert '\n  unstamped spec x2: specs/HANDOFF-old.md, specs/auth.md' in work_list
    assert 'drafts/deep' in work_list
    assert '\n  unstamped probe-dir x2: probes, drafts/deep - stamp each' in work_list
    assert 'specs  ' not in work_list
    assert ' specs,' not in work_list

    for token in ('specs/auth.md', 'specs/HANDOFF-old.md', 'drafts/x.py',
                  'notes/quirks.md', 'outputs/SPEC-chart.md', 'probes/p.py',
                  'drafts/deep/z.py'):
        assert hq.main(['stamp', _SLUG, token]) == 0, token
    capsys.readouterr()
    assert hq.main(['stamp', _SLUG, 'specs']) == 2
    assert capsys.readouterr().out.startswith('hq stamp: specs is a kind folder - ')

    rows = (folder / 'ledger.tsv').read_text().splitlines()[1:]
    kinds = {r.split('\t')[2]: (r.split('\t')[4], r.split('\t')[6]) for r in rows}
    assert kinds == {
        'specs/auth.md': ('spec', 'always'),
        'specs/HANDOFF-old.md': ('spec', 'always'),
        'drafts/x.py': ('draft', 'always'),
        'notes/quirks.md': ('notes', 'never'),
        'outputs/SPEC-chart.md': ('other', 'never'),
        'probes/p.py': ('other', 'never'),
        'drafts/deep/z.py': ('other', 'never'),
        }


def test_a_file_stamped_inside_a_folder_records_the_folder(
        tmp_path, monkeypatch, capsys):
    """A folder of the work's own whose file carries a row is not listed as
    unstamped by begin, finish, or artifacts.

    Mutation: the recorded test reduced to a row under the folder's own
    path, so a folder stamped file by file is nagged every cycle.
    Oracle: no 'probe-dir' unstamped line after the inner stamp, and one
    before it.
    """
    root = _root(tmp_path, monkeypatch)
    folder = root / '.handoff' / _SLUG
    (folder / 'experiments').mkdir(parents=True)
    (folder / 'experiments' / 'e1.py').write_text('e = 1\n')
    assert hq.main(['begin', _SLUG]) == 0
    assert 'unstamped probe-dir x1: experiments' in capsys.readouterr().out
    assert hq.main(['stamp', _SLUG, 'experiments/e1.py', '--label', 'first run']) == 0
    (folder / 'HANDOFF.md').write_text(
        (folder / 'HANDOFF.md').read_text().replace(
            '## Task\n', '## Task\nT.\n').replace('## Now\n', '## Now\nN.\n'))
    capsys.readouterr()
    assert hq.main(['finish', _SLUG, '--log', 'c1']) == 0
    assert 'probe-dir' not in capsys.readouterr().out
    assert hq.main(['artifacts', _SLUG]) == 0
    assert 'unstamped' not in capsys.readouterr().out


def test_finish_names_a_made_file_first_stamped_this_cycle_against_the_work_dir(
        tmp_path, monkeypatch, capsys):
    """With a real work dir, a draft first stamped in the folder this cycle is
    named and a spec is not; with .handoff pinned, only a loose top-level
    file is; a notes file, a directory of any name, and a row from an
    earlier cycle never are.

    Mutation: the first-cycle test dropped, so every old row is nagged each
    cycle; a spec claimed by the work dir; notes or a directory counted as
    made; either case flagging a file already filed under a kind folder or
    a folder of the agent's own name.
    Oracle: the hand-written advisory lines and their absence, per case.
    """
    root = _root(tmp_path, monkeypatch)
    folder = root / '.handoff' / _SLUG
    (folder / 'specs').mkdir(parents=True)
    (folder / 'probes').mkdir()
    (folder / 'SPEC-old.md').write_text('# Spec\n\nOld.\n')
    (folder / 'proto.py').write_text('p = 1\n')
    (folder / 'notes-a.md').write_text('# A\n')
    (folder / 'outputs').mkdir()
    (folder / 'outputs' / 'table.csv').write_text('a,b\n')
    (folder / 'reviews').mkdir()
    (folder / 'reviews' / 'skeptic.md').write_text('# Skeptic\n')
    (root / 'working').mkdir()
    (root / '.handoff' / 'work-dir').write_text('working\n')
    assert hq.main(['begin', _SLUG]) == 0
    for token in ('SPEC-old.md', 'proto.py', 'notes-a.md', 'probes',
                  'outputs/table.csv', 'reviews/skeptic.md'):
        assert hq.main(['stamp', _SLUG, token]) == 0, token
    (folder / 'HANDOFF.md').write_text(
        (folder / 'HANDOFF.md').read_text().replace(
            '## Task\n', '## Task\nT.\n').replace('## Now\n', '## Now\nN.\n'))
    capsys.readouterr()
    assert hq.main(['finish', _SLUG, '--log', 'c1']) == 0
    out = capsys.readouterr().out
    assert ('advisory: made in the folder x1: proto.py'
            ' - move each to working, or under notes/ when it is evidence,'
            " then re-stamp with --successor and the file's ~ or absolute path") in out

    monkeypatch.setenv('HQ_CYCLE', '2')
    (root / '.handoff' / 'work-dir').write_text('.handoff\n')
    (folder / 'SPEC-new.md').write_text('# Spec\n\nNew.\n')
    (folder / 'specs' / 'inside.md').write_text('# Inside\n')
    (folder / 'experiments').mkdir()
    assert hq.main(['begin', _SLUG]) == 0
    assert hq.main(['stamp', _SLUG, 'SPEC-old.md', '--label', 'old, re-stamped']) == 0
    assert hq.main(['stamp', _SLUG, 'SPEC-new.md']) == 0
    assert hq.main(['stamp', _SLUG, 'specs/inside.md']) == 0
    assert hq.main(['stamp', _SLUG, 'experiments']) == 0
    capsys.readouterr()
    assert hq.main(['finish', _SLUG, '--log', 'c2']) == 0
    out = capsys.readouterr().out
    assert ('advisory: made at the top level x1: SPEC-new.md'
            ' - move each under notes/, specs/, drafts/, or outputs/'
            ' and re-stamp with --successor') in out
    assert not any(
        'SPEC-old.md' in ln for ln in out.splitlines()
        if ln.startswith('advisory: made'))


def test_an_unmakeable_work_dir_writes_no_pin_and_never_aborts_a_cycle(
        tmp_path, monkeypatch, capsys):
    """A directory that cannot be made is refused by the pin command with no
    pin written, and a pin already naming one is reported and passed over
    by begin and finish rather than aborting them.

    Mutation: the pin written before the mkdir, so a failed mkdir leaves a
    pin; the OSError escaping resolve_work_dir, so begin exits 1 with the
    lock taken.
    Oracle: no pin file after the refusal; begin and finish exit 0 with the
    could-not-be-made line in begin's output.
    """
    root = _root(tmp_path, monkeypatch)
    (root / 'ro').mkdir()
    (root / 'ro').chmod(0o500)
    try:
        assert hq.main(['work-dir', 'ro/sub']) == 1
        assert capsys.readouterr().out.startswith(
            'hq work-dir: ro/sub could not be made: ')
        assert _pin(root) is None
        (root / '.handoff').mkdir()
        (root / '.handoff' / 'work-dir').write_text('ro/sub\n')
        assert hq.main(['begin', _SLUG]) == 0
        out = capsys.readouterr().out
        assert ".handoff/work-dir names 'ro/sub': could not be made: " in out
        assert 'work dir: unpinned - run hq work-dir' in out
        folder = root / '.handoff' / _SLUG
        (folder / 'HANDOFF.md').write_text(
            (folder / 'HANDOFF.md').read_text().replace(
                '## Task\n', '## Task\nT.\n').replace('## Now\n', '## Now\nN.\n'))
        assert hq.main(['finish', _SLUG, '--log', 'c1']) == 0
    finally:
        (root / 'ro').chmod(0o700)


def test_a_work_dir_under_a_former_handoff_name_is_not_a_stale_path(
        tmp_path, monkeypatch, capsys):
    """A cursor line naming working/<slug>/ is stale only while working/ is
    not the pinned work dir; open never creates the directory.

    Mutation: the stale scan reading _FORMER_HANDOFF_DIRNAMES unfiltered,
    or open resolving with make=True.
    Oracle: the stale line with no pin, none with the pin, and the pinned
    directory absent from disk after open when it was never made.
    """
    root = _root(tmp_path, monkeypatch)
    folder = root / '.handoff' / _SLUG
    assert hq.main(['begin', _SLUG]) == 0
    (folder / 'HANDOFF.md').write_text(
        (folder / 'HANDOFF.md').read_text().replace(
            '## Task\n', '## Task\nT.\n').replace(
            '## Now\n', f'## Now\nRun working/{_SLUG}/proto.py again.\n'))
    assert hq.main(['finish', _SLUG, '--log', 'c1']) == 0
    capsys.readouterr()
    assert hq.main(['open', _SLUG]) == 0
    assert f'stale folder path in HANDOFF.md: working/{_SLUG}/ x1' in (
        capsys.readouterr().out)
    (root / '.handoff' / 'work-dir').write_text('working\n')
    assert hq.main(['open', _SLUG]) == 0
    assert 'stale folder path' not in capsys.readouterr().out
    assert not (root / 'working').exists()
