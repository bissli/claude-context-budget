"""The bin/hq wrapper: the command the plugin puts on the agent's PATH."""

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_bin_hq_forwards_its_arguments_to_the_script(tmp_path):
    """Verify bin/hq runs scripts/hq.py with the arguments it was given.

    Mutation: the wrapper's relative path to scripts/hq.py wrong, the
    exec bit dropped, "$@" left off, or its quotes dropped so a root with
    a space splits into two arguments.
    Oracle: a differential run of python3 scripts/hq.py on the same argv;
    the root holds no handoff, so the script prints its own `hq list: no
    handoff under <root>/.handoff` line, which the wrapper must match on
    stdout and exit code.
    """
    root = tmp_path / 'a dir'
    root.mkdir()
    argv = ['--root', str(root), 'list']
    direct = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'hq.py'), *argv],
        capture_output=True, text=True)
    wrapped = subprocess.run(
        [str(ROOT / 'bin' / 'hq'), *argv], capture_output=True, text=True)
    assert os.access(ROOT / 'bin' / 'hq', os.X_OK)
    assert direct.returncode == 0
    assert direct.stdout == f'hq list: no handoff under {root}/.handoff\n'
    assert (wrapped.returncode, wrapped.stdout) == (
        direct.returncode, direct.stdout)
