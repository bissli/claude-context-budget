# context-budget

A Claude Code plugin that tells you, in session and while there is still
room, that the conversation has grown expensive enough to hand off and
compact.

## Why

Claude Code resends the whole conversation on every API call. A cached
re-read is ten times cheaper than a fresh one, but it is not free, so the
cost of a session tracks the area under its context curve. Past a certain
size every turn is paying to re-read a history it no longer needs.

The trouble is that leaving cleanly takes time. You have to write a
handoff, read it back, and run `/compact` - and each of those turns adds
context of its own. By the time a session feels too big, there is often
no room left to get out.

So this plugin does not warn at a fixed token count. It warns when the
room left before your budget has shrunk to what a handoff will consume,
measured at the rate your session is actually growing. A session reading
large files fills up several times faster than a conversation, and is
warned much earlier in absolute tokens.

## The budget is in dollars, not tokens

One knob, `COST_PER_TURN_TARGET` in `scripts/budget.py`, set in dollars
per user turn. Every model's token target is derived from it and that
model's price:

| Model | Target                | Over budget    | $/turn at target |
| ----- | --------------------- | -------------- | ---------------: |
| Opus  | 350,000               | 500,000        |            $1.54 |
| Fable | 176,000-236,000       | 251,000-337,000 |    $1.55-$2.07 |

Opus is held by cost: 350,000 whatever the session does, and growth only
changes how many turns a cycle lasts (10 to 21).

Fable is held by the compaction cycle instead. Cost parity would put its
target at 175,000, but a compaction lands near 123,000, so a target set
there leaves under three turns of room - and at a fast growth rate it
would sit *below* the point the session restarts at, firing every turn
forever. So the target is the larger of what cost wants and what a
five-turn cycle needs. The consequence is worth stating plainly: a fable
session you must keep compacting costs $1.82 to $2.07 a turn, not $1.54.
On fable the lever is the growth rate, not the target.

Sonnet and Haiku are deliberately absent. A long session on either costs
little enough that interrupting it to talk about money would spend more
attention than it saves, so the plugin stays silent on them.

This is the part that is easy to get wrong by hand. A model billing at
twice the rate hits the same cost per turn at half the context, so giving
every model the same token target quietly lets the expensive one cost
double. Deriving the target from price is the only way the numbers stay
honest across a twofold spread in cost.

## What you see

At the end of a turn, once:

> Context is 291K of a 350K budget, growing about 19K a turn. About 3
> turns of room left, so this is a good moment to start the handoff.

Then nothing until the next band:

> Context is 362K, just past the 350K budget and growing about 19K a
> turn. A good place to finish the handoff and compact.

> Context is 517K, well past the 350K budget. Each turn costs about
> $2.28, roughly 1.5 times what it would at the budget. Worth compacting
> before you go on.

The last two also raise a desktop notification.

On an expensive model the budget can sit close enough to where a
compaction lands that compacting barely buys anything back, and the
message says so instead:

> Context is 188K, past the 175K budget for this model. Compacting would
> land near 123K and buy back barely a turn, so a fresh session is the
> cheaper reset here.

## Status line (optional)

```
myproject  Opus 5  [########..]  280K/350K  handoff now, 4 turns left  $1.23/turn
```

Claude Code has no plugin surface for a status line - a plugin can ship
commands, skills, agents, hooks, themes, output styles, monitors, and
workflows, but not `statusLine` - so this one has to be wired by hand. In
`~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/plugins/marketplaces/context-budget/scripts/statusline.py"
  }
}
```

It reads the growth rate from the state file the hook writes, so the two
always agree. Without the hook it falls back to a default rate and still
works.

## Install

```
/plugin marketplace add bissli/claude-context-budget
/plugin install context-budget@context-budget
```

The Stop hook loads itself. Requires `python3` on `PATH`; nothing else.

## How it decides

Billed context is `cache_read + cache_creation + uncached_input` on the
last assistant call - the same figure Claude Code reports as
`compactMetadata.preTokens` when you compact.

Growth is measured from the context series itself rather than by counting
turns. Transcripts interleave real user prompts with injected system
reminders, tool results, and hook output, and no reliable rule separates
them; a turn count built that way came out 35% high against an
independent oracle. The context series has no such ambiguity. The series
is cut at every drop, since a drop means a compaction and averaging
across one reads as no growth at all.

Each band fires once, on entry. A Stop hook runs every turn, so repeating
a band already reached would just be noise. Compacting drops the context
below the announced band and rearms it, so a long session keeps getting
warned on every climb.

Subagents are skipped. A subagent's context is short-lived, it cannot
compact, and warning about it gives you nothing to act on.

## Where the defaults came from

Fitted against roughly 190,000 real API calls across a month of heavy
use, where 89% of main-thread spend landed above 200K of context and 22%
above 500K:

- **$1.54 a turn** is what a 350,000-token Opus session costs. Holding to
  it cuts total spend by about 9%. Tighter budgets save more - a 200,000
  ceiling saves about 22% - at the cost of compacting every three turns.
- **$2.20 a turn** is where a fifth of that spend was going. Nothing
  above it was buying anything.
- **123,000 tokens** is the median billed context on the first call after
  a compaction. Claude Code reports `postTokens` around 22,000, but that
  counts only the conversation; the system prompt, tool schemas, and
  instruction files all come back. A brand new session starts lower, near
  69,000, which is why the plugin sometimes recommends one.

## Development

```
python3 -m pytest tests/ -q
```

State lives in `~/.claude/cache/context-budget/<session>.json` and is safe
to delete; the next turn rewrites it.

## License

MIT
