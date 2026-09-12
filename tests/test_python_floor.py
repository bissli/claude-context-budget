"""Shipped Python parses under the floor version pyproject declares.

The plugin runs on whatever `python3` the user's shell resolves. A
construct newer than the declared floor is a SyntaxError at import, not
a lint finding, so `hq` dies before it prints anything.
"""

import pathlib
import re
import shutil
import subprocess
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent

_PROBE = """
import pathlib
import sys

for name in sys.argv[1:]:
    try:
        compile(pathlib.Path(name).read_text(), name, 'exec')
    except SyntaxError as exc:
        print(f'{name}:{exc.lineno}: {exc.msg}')
"""


def test_every_tracked_python_file_parses_under_the_declared_floor():
    """Verify tracked .py files compile under the pyproject floor interpreter.

    Mutation: a construct newer than the floor lands in shipped code - a
    backslash or a reused quote inside an f-string expression, a PEP 695
    `type` alias, an `except*` clause - and every user whose python3 is
    the floor gets a SyntaxError instead of hq.
    Oracle: a real CPython parser at the declared floor, run as a
    differential against the newer interpreter collecting this test.
    """
    pyproject = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    declared = pyproject['tool']['poetry']['dependencies']['python']
    floor = re.search(r'\d+\.\d+', declared)
    assert floor, f'pyproject declares no floor version in {declared!r}'
    interpreter = shutil.which(f'python{floor.group()}')
    assert interpreter, f'python{floor.group()} is not on PATH'
    tracked = subprocess.run(
        ['git', '-C', str(ROOT), 'ls-files', '*.py'],
        capture_output=True, text=True, check=True).stdout.split()
    assert len(tracked) > 1
    probe = subprocess.run(
        [interpreter, '-c', _PROBE, *tracked],
        cwd=ROOT, capture_output=True, text=True, check=True)
    assert probe.stdout == ''
