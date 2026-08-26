"""Shared budget arithmetic for the Stop hook and the status line.

The budget is set in dollars per user turn, not in tokens. Each model's
token target is derived from it and from that model's price, which is the
only way the targets stay honest: a model billing at twice the rate
reaches the same cost per turn at half the context, and should be
compacted there. One knob therefore moves every model at once.

Notes
-----
- Cost per turn is ``context * 0.1 * price_per_mtok * calls_per_turn``.
  The 0.1 is the cache-read rate; a turn deep in a session is almost
  entirely cache reads, so this is the whole bill to within a few
  percent.
- Only the expensive models are listed. A long Sonnet or Haiku session
  costs little enough that interrupting one to talk about money would
  spend more attention than it saves, so they are left alone.
"""

# Dollars per user turn. Everything else follows from this.
COST_PER_TURN_TARGET = 1.54
COST_PER_TURN_LIMIT = 2.20

# Base input price per million tokens.
PRICE_PER_MTOK = {
    'fable': 10.0,
    'opus': 5.0,
    }
CACHE_READ_MULTIPLIER = 0.1

# Assistant calls per user turn, measured across 604 compaction cycles.
CALLS_PER_TURN = 8.8

# Write the handoff, read it back, run /compact.
HANDOFF_TURNS = 3

# Growth is a recent average, so one heavy turn during the handoff can
# outrun it. This buys that slack.
HANDOFF_MARGIN = 1.5

# The warning is useless if it fires on a young session and useless if it
# leaves no room, so the reserve is held between these two bounds.
MIN_RESERVE_TOKENS = 60_000
MAX_RESERVE_FRACTION = 0.5

# Billed context on the first call after a compaction: the system prompt,
# tools, and instruction files all return, along with the summary.
# Measured median across 299 compactions.
POST_COMPACTION_TOKENS = 123_000

# Used until a session has enough history to measure its own rate.
FALLBACK_GROWTH_PER_CALL = 1_900


def model_tier(model: str) -> str | None:
    """Map a model id onto its price tier.

    Parameters
    ----------
    model : str
        Model id, as recorded on a transcript message or a status line
        payload.

    Returns
    -------
    str or None
        One of the keys of ``PRICE_PER_MTOK``, or None for a model this
        plugin has nothing worth saying about.
    """
    lowered = model.lower()
    for tier in PRICE_PER_MTOK:
        if tier in lowered:
            return tier
    return None


def cost_per_turn(context: int, tier: str) -> float:
    """Dollars one user turn costs at a given context size.

    Parameters
    ----------
    context : int
        Billed context in tokens.
    tier : str
        Price tier from :func:`model_tier`.

    Returns
    -------
    float
        Cost of a single user turn, in dollars.
    """
    return (context / 1e6 * CACHE_READ_MULTIPLIER * PRICE_PER_MTOK[tier]
            * CALLS_PER_TURN)


def tokens_for_cost(budget: float, tier: str) -> int:
    """Context size at which a turn costs a given number of dollars.

    Parameters
    ----------
    budget : float
        Dollars per user turn.
    tier : str
        Price tier from :func:`model_tier`.

    Returns
    -------
    int
        Billed context in tokens.

    Notes
    -----
    - Rounded, not truncated. The division lands a hair under a round
      number often enough that truncating shifts a threshold down by one
      token, which is invisible in use and maddening in a test.
    """
    per_token = (CACHE_READ_MULTIPLIER * PRICE_PER_MTOK[tier]
                 * CALLS_PER_TURN / 1e6)
    return round(budget / per_token)


def target_tokens(tier: str) -> int:
    """Context size a session should be compacted at.
    """
    return tokens_for_cost(COST_PER_TURN_TARGET, tier)


def over_budget_tokens(tier: str) -> int:
    """Context size past which a turn is plainly overpriced.
    """
    return tokens_for_cost(COST_PER_TURN_LIMIT, tier)


def reserve_tokens(target: int, per_call: int) -> int:
    """Room to hold back so a handoff still fits before the target.

    Parameters
    ----------
    target : int
        The compaction target for this model, in tokens.
    per_call : int
        Estimated tokens added per assistant call.

    Returns
    -------
    int
        Tokens reserved below the target, bounded by
        ``MIN_RESERVE_TOKENS`` and ``MAX_RESERVE_FRACTION``.
    """
    raw = int(HANDOFF_TURNS * per_call * CALLS_PER_TURN * HANDOFF_MARGIN)
    return min(int(target * MAX_RESERVE_FRACTION),
               max(MIN_RESERVE_TOKENS, raw))


def compaction_is_worthwhile(target: int, per_call: int) -> bool:
    """Whether compacting buys back more than a couple of turns.

    Parameters
    ----------
    target : int
        The compaction target for this model, in tokens.
    per_call : int
        Estimated tokens added per assistant call.

    Returns
    -------
    bool
        False when a compaction would land close enough to the target
        that the session is better restarted than compacted.

    Notes
    -----
    - Compacting does not reset to the summary's size. The system prompt,
      tool schemas, and instruction files all come back, so the first
      billed call afterwards lands near ``POST_COMPACTION_TOKENS`` -
      higher, on this measurement, than a brand new session starts at.
    - On an expensive model the target can sit barely above that floor,
      and then the honest advice is to start fresh, not to compact.
    """
    per_turn = per_call * CALLS_PER_TURN
    return (target - POST_COMPACTION_TOKENS) >= 2 * per_turn
