---
name: handoff
description: >-
  Write or read a session handoff under scratch/ - the exit the
  context-budget warnings point at. The verb is inferred, never typed.
  Bare /handoff writes or updates this session's
  scratch/<slug>/HANDOFF.md. In a fresh session it reads one back
  instead. list shows what exists, check reviews one in place.
  Replaces /compact, and replaces re-planning: the file carries the
  approved plan across sessions.
---

# Handoff

One file per task thread, `scratch/<slug>/HANDOFF.md` at the repo root
(`git rev-parse --show-toplevel`; the cwd outside a repo), carrying
what a fresh session needs to resume and nothing the repo already
records. Write near the budget, then kill the session - a total
clear: only this file and the repo survive - and `/handoff <slug>`
in a fresh one. A later bare `/handoff` updates the same file.

## Which verb, which target

The verb is inferred, never typed. One question settles it: does this
session hold anything worth telling a fresh session?

- Yes - a file edited, a decision settled, a finding the repo does
  not already record, a handoff read here. Write.
- No - none of that. A session whose opening move this is, and
  equally one that has only looked something up. Read.

Ask it of the content, never the position: a session that answered one
question and edited nothing holds nothing worth passing on, however
many messages came first. That is how the two are used. Write is the
last move of a working session, read is the first move of the session
that replaces it, and there is no third case.

An argument is always a folder under `scratch/`; the document inside
is always `HANDOFF.md`, never named by the caller. It pins the
target and leaves the verb inferred.

| Input                   | Action                                       |
| ----------------------- | -------------------------------------------- |
| `/handoff`              | write, or read when the session is fresh     |
| `/handoff <slug>`       | the same, against `scratch/<slug>/`          |
| `/handoff list [n]`     | this repo, newest first; n caps how many     |
| `/handoff check [slug]` | reviewer pass on an existing handoff, fix it |

`write` and `read` are still accepted as the first word and override
the inference; `--no-check` may sit anywhere. A first argument that
matches `write`, `read`, `list`, or `check` is that word, not a slug.
`list` takes one more word, a count; every other verb takes a slug.

Guess neither the verb nor the target. Where either is ambiguous,
say so, list the candidates, and stop - touch nothing.

A folder argument resolves the same way everywhere: exact folder
name, else a unique prefix of the `scratch/*/` names, else list the
candidates and stop (write: create the folder). A target exists when
its `HANDOFF.md` exists.

## write

Target, first match wins - an argument is never required:

1. an explicit folder argument
2. the handoff this session read, wrote, or checked, when the work
   since has been that same task; several threads this session - name
   the candidates and ask
3. an existing `scratch/` folder whose slug or Task line matches this
   session's task - update it, never create a twin
4. a new slug: 2-4 kebab-case words drawn from the Task line
   (`auth-token-refresh`), unique under `scratch/`

An existing target means update mode - read the old file first if
this session has not; a target some other process wrote - no conforming
`Written: | Cycle:` header line - means adoption (below). Otherwise
write fresh. Collect anchors, read-only:
branch, `git rev-parse --short HEAD`, `git status --porcelain` (up to
five file names; past that, `N files dirty`), and background tasks
still running, which go under Environment - as does any second repo
this session changed (path, branch, sha). Outside a git repo, omit
the git fields from the header.

### The file

Write for a reader with no memory of this session and full access to
the repo: short technical documentation in complete sentences, no
transcript narration. Task and Now are required; omit any section
that would be empty. The file is the whole bridge - a requirement the
user stated, an approval given, a quirk found the hard way is lost
unless written here. Trimming cuts what the repo records, never what
only the session knows; in doubt, write it down.

```markdown
# Handoff: auth-token-refresh

Written: 2026-08-26 | Cycle: 3 | master @ d46ac73 | dirty: scripts/auth.py

## Task
Refresh expired OAuth tokens in the poller instead of failing the run.

## Now
Wire refresh_token() into poll() at scripts/auth.py:88, in the 401 branch.

## Plan
- [x] Steps 1-3: token store, refresh endpoint, unit tests (cycles 1-2)
- [ ] Wire refresh into the poll() 401 branch
- [ ] Integration test against the staging IdP

## State
- Verified: refresh_token() round-trips against staging (cycle 2).
- Unverified: retry backoff - written, never exercised.
- In progress: poll() edit stopped mid-way; the 401 branch still re-raises.

## Key files
Read now:
- scripts/auth.py:60-120 - poller and the 401 branch under edit
Reference only:
- scripts/idp_client.py - refresh wrapper, working, do not touch
- scratch/auth-token-refresh/notes-idp-quirks.md - staging IdP quirks

## Decisions
- Refresh in-process, no sidecar - one caller, latency fine. Settled.

## Constraints
- User: never log token values, even at debug.

## Dead ends
- httpx event hooks for auto-refresh: a hook cannot retry the original
  request. Do not retry this.

## Environment
- test: python3 -m pytest tests/ -q
- staging IdP secret: env IDP_CLIENT_SECRET, set in ~/.env.staging

## Open questions
- Cap retry backoff at 60s, or give up after five tries? Blocks the
  integration test.

## Log
- 2026-08-24 (cycle 1): token store and refresh endpoint written.
- 2026-08-25 (cycle 2): refresh verified against staging; backoff added.
- 2026-08-26 (cycle 3): poll() wiring started.
```

Rules:

- Point, never paste: `scripts/auth.py:60-120`, not a code block that
  lives in a file. Paste only what exists nowhere else - an error
  message, the user's exact words, output of a process that is gone.
- Skip what the repo records: git history, CLAUDE.md, README content.
- Too big for the file but worth keeping (a log excerpt, a survey):
  a sibling file `scratch/<slug>/notes-<topic>.md`, one pointer line
  under `Reference only`.
- Name where a credential lives, never its value.
- Absolute dates. ASCII only.
- Now is the single next action; Plan is what follows it. Plan
  carries the approved plan; Decisions carries what the user settled,
  quoted where the wording matters - neither is re-opened.
- Anything still awaiting the user - a question, an unapproved plan -
  goes under `Open questions`; read stops there.
- `Read now` carries only what the Now step needs - one to three
  ranges. Everything else is `Reference only`.
- Under 200 lines fits most sessions; 400 is the ceiling.

### A plan that lives in a todo file

Work often has a ledger of its own - `todo/foobar.md`, tracked in
the repo. One home per fact, or the copies drift: the todo file
owns what is open and done; the handoff owns how this thread works
it - state, decisions, the Now step. Neither restates the other.

- Plan points at the live item (`todo/foobar.md item 3`) and keeps
  only thread-only steps of its own. Never copy the item's text
  across.
- write syncs the todo first - mark what this session closed,
  append what it found, in the todo file's own format - then writes
  the handoff against the result. A todo left dirty shows in the
  header's dirty list.
- On first pointing at an item, add one back-pointer line under it:
  `entry: scratch/<slug>/HANDOFF.md`. Add nothing else to the todo
  from here.
- An untracked todo file cannot anchor to a sha: mark the pointer
  `(untracked)`, and at read its current content is the truth.

### Update mode

A living document, not a log: after every update it must still read as
"what a fresh session needs now". Overwrite `HANDOFF.prev.md` with the
old file (scratch/ is untracked, so this is the one-step history),
rewrite the header from the new anchors, bump `Cycle:` (a fresh write
is cycle 1), then merge by section:

- Task: rewrite only if the goal moved.
- Now, State, Key files, Environment: rewrite from the current
  session.
- Plan: keep; mark done `[x]`; collapse a finished stretch to one
  line; append new steps; a pointed todo file syncs first, per its
  rule above.
- Decisions, Constraints, Dead ends: append and tighten wording; never
  silently drop - a superseded item is replaced by its successor.
- Log: append one line for this cycle; keep the last three cycles and
  collapse older ones to a single line.

### Adoption

A target some other process wrote - no conforming header - is
massaged toward the schema, never started over: converge the form,
destroy no content. The adoption pass meets the ceiling by rehoming
alone. Cuts, the trimmer seat, and the opus rewrite wait for later
cycles.

- First copy the file once to `HANDOFF.orig.md`. Never overwrite or
  delete that copy. `HANDOFF.prev.md` stays the rolling one-step
  history beside it.
- Convert structure, not content: write the header (cycle 1), map
  each foreign section to the schema section carrying the same kind
  of fact, keep every fact. What fits no section, or would hold the
  file over the ceiling, moves whole to sibling `notes-<topic>.md`
  files, one pointer line each under the schema section it belongs
  to (`Reference only` when none fits) - rehomed, never cut.
- The file's own conventions outrank the merge rules: a reading
  order it declares, a backup or worktree it says never to delete,
  a directive it quotes. Carry each under Constraints or a pointer,
  and touch no sibling file except to add.
- The reviewer pass runs without the trimmer, and the merge auditor
  diffs orig. Update-mode merging binds from the next cycle.

### Reviewer pass

With the file on disk, spawn the seats that apply in one message
(Agent tool, type `general-purpose`, model `sonnet`). Each returns
only numbered `line: finding` items; re-check each yourself, apply
what survives, and stop - never loop the reviewers.

- Always - skeptic: from the file alone, fill five slots - the task,
  the next action, why it is next, how to verify it, what to ask the
  user; an empty slot is a finding. Also check every path and line
  anchor exists, and that Now agrees with each pointed todo's live
  item.
- Update or adoption write, or check beside a `HANDOFF.prev.md` or
  `HANDOFF.orig.md` - merge auditor: diff prev (adoption: orig)
  against current; flag dropped lines not marked done, superseded,
  or rehomed, and surviving lines about finished work.
- Any write over 150 lines - trimmer: line ranges that restate the
  repo, paste code, or pad. Log tails and decisions the shipped code
  now proves may go; Constraints and Dead ends stay.

Past cycle 5 or 400 lines, after those fixes land, one opus-tier
agent rewrites the whole file for precision and returns it. Apply it
and land back under the ceiling - compress wording, rehome overflow
to sibling files, never drop what only the session knows. Past the
budget, prefer `/handoff --no-check` and run `/handoff check` from
the fresh session instead.

### Report

Whatever else the turn contains, its final message names the absolute
path, the size, and the resume line - with `--no-check` too:

```
Wrote scratch/auth-token-refresh/HANDOFF.md (~1.4K tokens, cycle 3).
Resume: kill this session, start a fresh one, run
  /handoff auth-token-refresh
```

## read

1. Resolve `<slug>` per the shared rule. With none given: one
   `scratch/*/HANDOFF.md` exists, read it; several exist, list the
   slugs and ask which; none exists, say `scratch/` holds no handoff.
   The last two stop there - never pick the newest, and never fall
   through to write.
2. Read the file, then the `Read now` files and every todo file the
   Plan points at. A target with no conforming header names its own
   reading order or read-first pointers - follow those instead.
   Read nothing else, and never read `HANDOFF.prev.md`.
3. Drift check: HEAD moved from the header sha - run
   `git log --oneline <sha>..HEAD`, adding `-- <path>` per pointed
   todo file; header says dirty - run `git status --porcelain`. No
   conforming header - skip. A pointed todo moved or disagrees with
   the file: the todo wins on what is open or done, the handoff on
   approach and decisions. Note drift in one line and proceed.
4. Do not re-plan and do not reopen Decisions. Open questions
   present: put them to the user and stop. Otherwise state the task
   and the Now step in two sentences, then execute Now; the Plan
   follows.
5. A later bare `/handoff` targets this handoff - write rule 2.

## list

The handoffs in this repo, newest first. A bare `list` shows every one;
`/handoff list 5` shows the five most recent, `list 1` the most recent
alone. A count over the number that exist shows them all.

`ls -t scratch/*/HANDOFF.md` orders them without reading anything, so a
count saves the reading and not just the output: take that many off the
top and open only those. Read each down to the end of its `## Plan`
section - 40 lines reaches it in a normal handoff.

Report per file: slug, Written date, Cycle, plan items done over total,
Task line. Count a `- [ ]` or `- [x]` only under `## Plan`; a checkbox
under State or Dead ends is not a plan item. A file with no Plan
section reports `-`.

Plan progress is what tells a live thread from a finished one: `7/7` is
done, `0/5` never started, and the cycle count says neither - it counts
how often the thread was worked, not how far it got.

## check

Resolve like read. A target with no conforming header instead runs
the adoption pass (write, above), reviewer pass included, and stops.
Otherwise run the seats that apply - skeptic always, merge auditor
beside a `HANDOFF.prev.md` or `HANDOFF.orig.md`, trimmer over 150
lines, the opus rewrite past 400 - apply what survives, and report
what changed.
