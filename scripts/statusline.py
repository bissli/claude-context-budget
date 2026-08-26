#!/usr/bin/env python3
"""Status line showing the live context budget and what a turn now costs.

Claude Code hands this command a JSON payload on stdin whose
``context_window.total_input_tokens`` is the billed context of the last
API call: cache reads plus cache writes plus uncached input. That is the
number cost tracks, since every call re-reads the whole conversation.

The line reads::

    myproject  Opus 5  [#######...]  262K/350K  handoff in 2 turns  $1.15/turn

and turns amber when it is time to write a handoff, red once the target
is behind you, so the moment to compact is visible several turns out.

Notes
-----
- Claude Code has no plugin surface for a status line, so unlike the Stop
  hook this script cannot install itself. Point ``statusLine.command`` in
  settings.json at it; the project README gives the exact block.
- The growth rate comes from the state file the Stop hook writes each
  turn, so the gauge and the warning never disagree. Re-deriving it here
  would mean re-reading the transcript on a line that repaints
  continuously.
- Every threshold comes from :mod:`budget`, shared with the hook, so the
  gauge cannot drift from the warning it is meant to anticipate.
"""

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import budget  # noqa: E402  (path must be set before this import resolves)

STATE_DIR = os.path.expanduser('~/.claude/cache/context-budget')

RESET = '\x1b[0m'
DIM = '\x1b[2m'
GREEN = '\x1b[32m'
YELLOW = '\x1b[33m'
RED = '\x1b[31m'

BAR_CELLS = 10


def session_growth(session: str) -> int:
    """Read this session's measured growth per call, or the fallback.

    Parameters
    ----------
    session : str
        Session id from the status line payload.

    Returns
    -------
    int
        Estimated tokens added per assistant call.
    """
    safe = session.replace('/', '_')
    try:
        with open(os.path.join(STATE_DIR, f'{safe}.json')) as handle:
            return max(1, int(json.load(handle)['growth_per_call']))
    except (OSError, ValueError, KeyError, TypeError):
        return budget.FALLBACK_GROWTH_PER_CALL


def render(payload: dict[str, Any]) -> str:
    """Build the status line from one status-line payload.

    Parameters
    ----------
    payload : dict[str, Any]
        The JSON object Claude Code writes to this command's stdin.

    Returns
    -------
    str
        A single line of ANSI-colored text, without a trailing newline.
    """
    window = payload.get('context_window') or {}
    context = int(window.get('total_input_tokens') or 0)
    model = payload.get('model') or {}
    label = str(model.get('display_name') or model.get('id') or '')
    workspace = payload.get('workspace') or {}
    cwd = str(workspace.get('current_dir') or payload.get('cwd') or '')
    head = f'{DIM}{os.path.basename(cwd) or cwd}{RESET}  {DIM}{label}{RESET}'
    if context <= 0:
        return head

    tier = budget.model_tier(str(model.get('id') or ''))
    if tier is None:
        return head
    target = budget.target_tokens(tier)
    per_call = session_growth(str(payload.get('session_id') or ''))
    per_turn = per_call * budget.CALLS_PER_TURN
    handoff_at = target - budget.reserve_tokens(target, per_call)

    filled = min(BAR_CELLS, int(context / target * BAR_CELLS))
    bar = '#' * filled + '.' * (BAR_CELLS - filled)
    cost = budget.cost_per_turn(context, tier)

    if context >= target:
        color = RED
        share = cost / budget.COST_PER_TURN_TARGET
        note = f'{share:.1f}x budget, time to compact'
    elif context >= handoff_at:
        left = max(1, int((target - context) / max(per_turn, 1)))
        color = YELLOW
        note = f'handoff now, {left} turn{"" if left == 1 else "s"} left'
    else:
        left = max(1, int((handoff_at - context) / max(per_turn, 1)))
        color = GREEN
        note = f'handoff in {left} turn{"" if left == 1 else "s"}'

    return (f'{head}  {color}[{bar}]{RESET}  {context // 1000}K/'
            f'{target // 1000}K  {color}{note}{RESET}  '
            f'{DIM}${cost:.2f}/turn{RESET}')


def main() -> int:
    """Print one status line for the payload on stdin.
    """
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    print(render(payload))
    return 0


if __name__ == '__main__':
    sys.exit(main())
