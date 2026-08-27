# context-budget

A Claude Code plugin that tells you, in session and while there is still
room, that the conversation has grown expensive enough to hand off.

```
248K/350K [=======---] handoff in 4  $1.09/t  opus myproject
310K/350K [========--] handoff now   $1.36/t  opus myproject
452K/350K  1.3x over                 $1.99/t  opus myproject
```

## Install

```
/plugin marketplace add bissli/claude-context-budget
/plugin install context-budget@context-budget
```

That installs the warning hook and the /handoff skill together. It
needs `python3` on `PATH` and nothing else.

### Status line (optional, one manual step)

Claude Code has no plugin surface for a status line - a plugin can ship
commands, skills, agents, hooks, themes, output styles, monitors, and
workflows, but not `statusLine` - so this one is wired by hand. Add to
`~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 \"$(ls ~/.claude/plugins/cache/*/context-budget/*/scripts/statusline.py | sort -V | tail -1)\""
  }
}
```

That resolves the installed copy, which is what actually runs. An
installed plugin lives at
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` - the
version is in the path, so the glob is what keeps the line working
across an upgrade, and `sort -V` is what keeps 0.10.0 ahead of 0.9.0.
Point it at a checkout instead if you run one:
`python3 /path/to/claude-context-budget/scripts/statusline.py`.

The status line reads the growth rate from a file the hook writes each
turn, so the two never disagree - which is also why the line has to
resolve the same tree the hook runs from. Without the hook it falls
back to a default rate and still works.

### Update

```
/plugin marketplace update context-budget
```

That moves the marketplace clone. The plugin itself runs from a copy
taken at install time under `~/.claude/plugins/cache/`, pinned to the
version in its path, so the clone is the source and the copy is what
executes - check which you are looking at before concluding an edit
did nothing. There is no migration either way: the state under
`~/.claude/cache/context-budget/` is rewritten every turn by whichever
version is running, and handoff files are plain markdown that no
version needs to convert.

### Uninstall

```
/plugin uninstall context-budget@context-budget
/plugin marketplace remove context-budget
```

That removes the hook and the skill with the plugin. Two things
outlive it: the `statusLine` block above (remove it from
settings.json) and the cache directory
(`rm -rf ~/.claude/cache/context-budget`). Handoffs under `scratch/`
are yours, not the plugin's; uninstalling touches none of them.

## Why

Claude Code resends the whole conversation on every API call. A cached
re-read is ten times cheaper than a fresh one, but it is not free, so the
cost of a session tracks the area under its context curve. Past a certain
size every turn pays to re-read a history it is no longer using.

Leaving cleanly takes time. You have to write a handoff, read it back,
and reset - and each of those turns adds context of its own. By the time
a session feels too big, there is often no room left to get out.

So this plugin does not warn at a fixed token count. It warns when the
room left before your budget has shrunk to what a handoff will consume,
measured at the rate your session is actually growing. A session reading
large files fills up several times faster than a conversation, and is
warned much earlier in absolute tokens.

## What you see

At the end of a turn, once:

> Context 291K of a 350K budget, growing 19K a turn. About 4 turns of
> room left - a good point to run /handoff.

Then nothing until the next band:

> Context 362K, at the 350K budget. Run /handoff, then run it again in
> a fresh session to read it back: that restarts near 69K plus the
> file, against 123K for /compact. Compact instead only to carry the
> tail of this conversation, which buys about 12 more turns.

> Context 517K, about $2.27 a turn - 1.5x the $1.54 target. Every
> further turn pays to re-read history you are not using. Run
> /handoff.

The last two also raise a desktop notification.

## Why it says hand off rather than compact

Compaction touches only the conversation. Your `CLAUDE.md`, the system
prompt, tool schemas and instruction files are re-sent in full on the
very next call, unchanged. Measured over 296 compactions, the median
restart was 123,620 tokens: about 98,000 of untouchable instruction and
tool floor, 22,000 of summary, and 17,000 of preserved tail. Roughly 80%
of what you restart with was never conversation, so compaction squeezes
the one part that was already smallest.

A fresh session in the same project starts at that same floor with no
summary and no tail. Write the handoff to a file and the file replaces
the summary - exactly, rather than compressed:

|                              | restart                                   |
| ---------------------------- | -----------------------------------------: |
| `/compact`                   | 123,620                                   |
| handoff file + fresh session | floor + your file, typically ~20,000 less |

Compaction is also a lossy compressor applied repeatedly to its own
output. In one measured session it ran 15 times and the summary grew from
24K to 62K - paying more each cycle for a progressively worse rendering
of the same material. A file does neither.

`/compact` still earns its place for one thing: the ~17,000-token
preserved tail, the messages you were part-way through. Mid-task that is
worth carrying. Between tasks it is weight you pay to keep.

## The exit itself: /handoff

The plugin ships the skill its warnings point at. One file per task
thread, `scratch/<slug>/HANDOFF.md` at the repo root (the current
directory outside a git repo). Between sessions the reset is total -
the file and the repo are all that survive - so the skill is built to
capture exactly what rehydration needs:

```
/handoff                       writes or updates the handoff, checks it
  (kill the session, start fresh)
/handoff auth-token-refresh    rehydrates and resumes the plan
```

There is no verb to type. The question is what the session holds, not
how long it has run. A session that edited a file or settled a
decision holds something worth telling a fresh session, so `/handoff`
writes. One that only looked something up holds nothing, so it reads a
handoff back instead. Write is the last move of a working session and
read is the first move of the session that replaces it, so the two
never collide. Neither the verb nor the target is ever guessed: where
either is ambiguous - several handoffs and no name given - the skill
lists the candidates and stops.

- Writing needs no argument: it picks a folder name from the task, or
  takes one if you choose - the file inside is always `HANDOFF.md`. It
  records the plan, the state, key files with line anchors, settled
  decisions, and dead ends - pointers into the repo, never pasted code.
  Most handoffs land between 2K and 5K tokens, against ~22K for a
  /compact summary.
- Run it again a session later and it updates the same file in place:
  state is rewritten, the plan is ticked off, decisions and dead ends
  accumulate, and a one-line log per cycle keeps the trajectory. The
  prior version stays beside it as `HANDOFF.prev.md`.
- A handoff some other tool or session wrote is adopted, not
  discarded: the first write keeps a permanent `HANDOFF.orig.md` copy,
  converts the structure, and rehomes overflow to sibling notes files.
  The form converges. The content survives.
- When the work has a ledger of its own (`todo/foobar.md`), the
  handoff points at the live item rather than copying it: writing
  syncs the todo first, and reading trusts it on what is open, the
  handoff on how. One home per fact, so nothing drifts.
- Each write ends with a reviewer pass - a skeptic that must
  rehydrate from the file alone, a merge auditor on updates, a trimmer
  once the file passes 150 lines. A reviewer seat costs cents; a
  dropped decision costs the turns it takes to re-derive.
- Reading verifies the file's git anchors, reads only the files the
  handoff marks "read now", and executes the handoff's Now step - the
  single next action, with the plan behind it. It stops only for open
  questions the file left for you; decisions stay settled, and nothing
  is re-planned or re-litigated.
- `/handoff list` shows what exists, newest first, with plan items
  ticked over plan items total beside each - `7/7` is a finished thread
  and `0/5` one that never started, which is most of what you need to
  pick. `/handoff list 5` shows only the five most recent and reads only
  those five files. `/handoff check` re-reviews one in place and applies
  what survives.

Add `scratch/` to your gitignore if handoffs should stay untracked.

## The budget is in dollars, not tokens

One knob, `COST_PER_TURN_TARGET` in `scripts/budget.py`, set in dollars
per user turn. Each model's token target is derived from it and that
model's price:

| Model | Target                  | Over budget           | $/turn at target |
| ----- | ----------------------- | --------------------- | ----------------: |
| Opus  | 350,000                 | 500,000               | $1.54            |
| Fable | 175,000+, growth-scaled | 250,000 or the target | $1.54 and up     |

A model billing at twice the rate hits the same cost per turn at half the
context, so giving every model one token target quietly lets the
expensive one cost double.

Opus is held by cost: 350,000 whatever the session does, and growth only
changes how long a cycle lasts. Fable is held by the compaction cycle
instead - cost parity would put it at 175,000, but a compaction lands
near 123,000, so a target there leaves under three turns of room, and at
a fast growth rate it would sit below where the session restarts, firing
every turn forever. Its target is therefore the larger of what cost wants
and what a five-turn cycle needs at the session's own growth rate:
206,600 at the typical 1,900 tokens a call, 400,200 for a session
reading 6,300 a call. The consequence is worth saying plainly: a fable
session you keep compacting costs what its growth demands - $1.82 a turn
at typical growth, $3.52 for that heavy reader - not $1.54. On fable the
lever is the growth rate, not the target.

Over budget stays a dollar figure. It fires at $2.20 a turn - 500,000
tokens on opus, 250,000 on fable - or at the target itself once the
cycle floor has passed that point. It is never scaled up with an
inflated target. Scaling would let a heavy fable session march to $5 a
turn before the loudest warning fired.

Sonnet and Haiku are deliberately absent. A long session on either costs
little enough that interrupting it to talk about money would spend more
attention than it saves.

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

A turn, throughout, means one thing you say plus everything Claude does
before it waits for you again, tool calls included. It is derived, not
counted: 8.8 assistant API calls, measured across 604 compaction cycles.
All the arithmetic underneath is per-call.

Each band fires once, on entry. A Stop hook runs every turn, so repeating
a band already reached would be noise. Compacting drops the context below
the announced band and rearms it. Only a real drop in context rearms a
band; slowing growth that lifts a threshold back above the context does
not.

Subagents are skipped. A subagent's context is short-lived, it cannot
compact, and warning about it gives you nothing to act on.

## Where the defaults came from

Fitted against roughly 190,000 real API calls across a month of heavy
use, where 89% of main-thread spend landed above 200K of context and 22%
above 500K:

- **$1.54 a turn** is what a 350,000-token Opus session costs. Holding to
  it cut total spend by about 9%. Tighter budgets save more - a 200,000
  ceiling saves about 22% - at the cost of handing off every three turns.
- **$2.20 a turn** is where a fifth of that spend was going.
- **123,000 tokens** is the median billed context after a compaction, and
  **69,000** is the median for a new session.

## Development

```
python3 -m pytest tests/ -q
```

State lives in `~/.claude/cache/context-budget/<session>.json` and is safe
to delete; the next turn rewrites it.

## License

MIT
