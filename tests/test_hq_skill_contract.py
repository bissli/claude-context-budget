"""Contract tests that hold skills/handoff/SKILL.md to scripts/hq.py.

The skill is prose an agent follows; the script is what it drives. Each
test pins one seam between them: the verbs and flags each side names, the
command examples, the lines the script prints, and the example file.
"""

import argparse
import ast
import pathlib
import re
import shlex

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent / 'scripts'
SKILL = HERE.parent / 'skills' / 'handoff' / 'SKILL.md'

from scripts import hq

_HQ_CALL = 'hq'
# Flags in the skill that belong to other tools, never to hq.py.
_FOREIGN_FLAGS = {'--no-check', '--oneline', '--porcelain', '--show-toplevel'}
# Messages the agent never meets: a usage slip the skill's own command
# forms rule out, and one internal guard.
_UNDOCUMENTED_PRINTS = {
    'hq stamp: path is required',
    'hq finish: unknown item kind',
    }


def _parser_surface():
    """Return ({verb: {flags}}, {global flags}) from the argparse tree."""
    parser = hq._build_parser()
    sub = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    verbs = {}
    for name, sp in sub.choices.items():
        verbs[name] = {
            opt for act in sp._actions for opt in act.option_strings
            if opt.startswith('--') and opt != '--help'
            }
    global_flags = {
        opt for act in parser._actions for opt in act.option_strings
        if opt.startswith('--') and opt != '--help'
        }
    return verbs, global_flags


def _fenced_commands(text):
    """Yield each hq command line from the skill's fenced blocks, joined
    across backslash continuations and cut before any heredoc marker.
    """
    in_fence = False
    buf = ''
    for line in text.splitlines():
        if line.startswith('```'):
            in_fence = not in_fence
            continue
        if not in_fence or line.startswith('#'):
            continue
        buf += line.rstrip()
        if buf.endswith('\\'):
            buf = buf[:-1] + ' '
            continue
        cmd, buf = buf, ''
        if cmd.split()[:1] == [_HQ_CALL]:
            yield cmd.split('<<')[0].strip()


def test_the_skill_and_the_parser_name_the_same_verbs():
    """Every hq.py verb the skill names exists, and every parser verb is named.

    Mutation: a verb renamed in _build_parser, a verb misspelled in the
    skill, or a parser verb added with no skill text.
    Oracle: the argparse subcommand table.
    """
    verbs, _ = _parser_surface()
    named = set(re.findall(r'\bhq (\w[\w-]*)(?![\w:-])', SKILL.read_text()))
    assert named <= set(verbs), named - set(verbs)
    assert set(verbs) <= named, set(verbs) - named


def test_every_flag_named_by_either_side_is_known_to_the_other():
    """Flags in the skill exist on some hq.py verb; verb flags appear in it.

    Mutation: a flag invented in the skill, or a parser option added with
    no skill line saying what it does.
    Oracle: the argparse option strings of every verb.
    """
    verbs, global_flags = _parser_surface()
    skill_flags = set(re.findall(r'--[a-z][a-z-]*', SKILL.read_text()))
    skill_flags -= _FOREIGN_FLAGS
    verb_flags = set().union(*verbs.values()) | global_flags
    assert skill_flags <= verb_flags, skill_flags - verb_flags
    assert verb_flags <= skill_flags, verb_flags - skill_flags


def test_every_command_example_in_the_skill_parses():
    """Each fenced hq.py example is accepted by the parser as written.

    Mutation: an example such as `note <slug> --batch -`, which the parser
    rejects while the kind slot carries choices, or a verb shown with a
    flag it lacks, or an example whose tokens the parser drops.
    Oracle: parse_known_args on the exact tokens after the slug
    placeholder is filled; the only leftover is a note body main() has an
    empty slot for.
    """
    parser = hq._build_parser()
    commands = list(_fenced_commands(SKILL.read_text()))
    assert len(commands) >= 10
    for cmd in commands:
        argv = shlex.split(cmd.replace('<slug>', 'demo'))[1:]
        try:
            args, rest = parser.parse_known_args(argv)
        except SystemExit as exc:
            raise AssertionError(f'does not parse: {cmd}') from exc
        # Notes:
        # - The bare '-' batch marker binds to a positional on 3.13 and
        #   later and is left over on 3.11; it is not a dropped token.
        # - 3.11 argparse will not read a positional that follows an
        #   option, so a note body arrives as a leftover there. main()
        #   puts it in the body slot, which is why the slot must be free.
        leftover = [tok for tok in rest if tok != '-']
        assert not [tok for tok in leftover if tok.startswith('-')], cmd
        assert not leftover or (
            args.verb == 'note' and args.body is None), cmd


def test_every_line_the_script_prints_is_named_in_the_skill():
    """Each message hq.py prints appears, by its literal text, in the skill.

    Mutation: a print added to hq.py with no skill line saying what the
    agent does about it, or a message reworded on one side only.
    Oracle: the longest string constant of every print call in hq.py's
    source, eight characters or more after stripping.
    """
    tree = ast.parse((SCRIPTS / 'hq.py').read_text())
    # The skill wraps at 72 columns, so whitespace runs compare as one space.
    text = ' '.join(SKILL.read_text().split())
    pieces = []
    for node in ast.walk(tree):
        is_print = (
            isinstance(node, ast.Call)
            and getattr(node.func, 'id', '') == 'print' and node.args)
        if not is_print:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            consts = [arg.value]
        elif isinstance(arg, ast.JoinedStr):
            consts = [
                v.value for v in arg.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)]
        else:
            continue
        consts = [' '.join(c.split()) for c in consts if len(c.strip()) >= 8]
        if consts:
            pieces.append((node.lineno, max(consts, key=len)))
    assert len(pieces) >= 40
    missing = [
        (line, piece) for line, piece in pieces
        if piece not in text
        and not any(piece.startswith(u) for u in _UNDOCUMENTED_PRINTS)]
    assert missing == []


def test_every_pointer_line_the_script_renders_is_named_in_the_skill():
    """Each `- hq <verb> ...` pointer hq.py renders names a real verb the
    skill shows verbatim.

    Mutation: a pointer's verb renamed in a rendered block or the begin
    work list, with the skill still showing the old word, so the agent is
    told to type a verb the file never names; or a pointer built from a
    word that is no parser verb at all.
    Oracle: every string constant in hq.py holding `- hq <word>`, checked
    against the argparse verb table and the whitespace-normalized skill.
    """
    verbs, _ = _parser_surface()
    tree = ast.parse((SCRIPTS / 'hq.py').read_text())
    skill_text = ' '.join(SKILL.read_text().split())
    pointers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            pointers += re.findall(r'- hq (\w+)', node.value)
    assert len(pointers) >= 4
    assert set(pointers) <= set(verbs), set(pointers) - set(verbs)
    assert [v for v in pointers if f'- hq {v} ' not in skill_text] == []


def test_every_refusal_string_in_the_script_is_named_in_the_skill():
    """Each refusal text hq.py builds appears in the skill's text.

    Mutation: a refusal reworded in code, or its text dropped from the
    skill, including the three R1 texts whose static prefix is under
    eight characters.
    Oracle: the skill text, whitespace-normalized; for an f-string that
    opens with `refused: ` or `R1: `, its longest static piece.
    """
    tree = ast.parse((SCRIPTS / 'hq.py').read_text())
    skill_text = ' '.join(SKILL.read_text().split())
    prefixes = ('refused: ', 'R1: ')
    pieces = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            parts = [node.value]
        elif isinstance(node, ast.JoinedStr):
            parts = [
                v.value for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)]
        else:
            continue
        if not parts or not parts[0].startswith(prefixes):
            continue
        normalized = [' '.join(part.split()) for part in parts]
        normalized = [part for part in normalized if len(part) >= 8]
        if normalized:
            pieces.append((node.lineno, max(normalized, key=len)))
    assert len(pieces) >= 5, pieces
    missing = [(line, piece) for line, piece in pieces if piece not in skill_text]
    assert missing == []


def test_every_reviewer_seat_names_the_host_tier_before_a_literal_model():
    """Each Reviewer-pass seat names the host's own tier, then a literal model.

    Mutation: a seat's host-tier clause dropped, so a host whose agent
    rules pin tiers leaves the agent with one literal type or model and
    no alternative it may use.
    Oracle: the skill's Skeptic and Rewrite bullets - each carries the
    word 'host' before its literal `model` name.
    """
    text = ' '.join(SKILL.read_text().split())
    seats = re.findall(r'- (Skeptic|Rewrite) \((.*?)\)', text)
    assert [name for name, _ in seats] == ['Skeptic', 'Rewrite'], seats
    for name, seat in seats:
        assert 'host' in seat and 'model `' in seat, (name, seat)
        assert seat.index('host') < seat.index('model `'), (name, seat)
