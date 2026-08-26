---
name: handoff
description: >-
  Write, read, list, or check a session handoff under scratch/ - the
  exit the context-budget warnings point at. Replaces /compact, and replaces
  re-planning: the file carries the approved plan across sessions.
  write [folder] writes or updates scratch/<folder>/HANDOFF.md, read
  <folder> rehydrates a fresh session from it, list shows what
  exists, check reviews one in place.
---

# Handoff

One file per task thread, `scratch/<slug>/HANDOFF.md` at the repo root
(`git rev-parse --show-toplevel`; the cwd outside a repo), carrying
what a fresh session needs to resume and nothing the repo already
records. Write near the budget, then kill the session - a total
clear: only this file and the repo survive - and `/handoff read
<slug>` in a fresh one. A later bare write updates the same file.

## Subcommands

The first argument must be one of these; called bare or with anything
else first, print this table and stop - never guess, touch nothing.
An argument names a folder under `scratch/`; the document inside is
always `HANDOFF.md`, never named by the caller. `write` takes the
folder and `--no-check` in either order.

| Input              | Action                                                |
| ------------------ | ----------------------------------------------------- |
| `write`            | write or update this session's handoff (target below) |
| `write <folder>`   | write or update `scratch/<folder>/HANDOFF.md`         |
| `write --no-check` | skip the reviewer pass                                |
| `read <folder>`    | rehydrate from `scratch/<folder>/HANDOFF.md`          |
| `read`             | one handoff exists: read it; several: list and ask    |
| `list`             | slug, date, cycle, task line - newest first           |
| `check [folder]`   | run the reviewer pass on an existing handoff, fix it  |

A folder argument resolves the same way everywhere: exact folder
name, else a unique prefix of the `scratch/*/` names, else list the
candidates and stop (write: create the folder). A target exists when
its `HANDOFF.md` exists.

## write

Target, first match wins - an argument is never required:

1. an explicit folder argument
2. the handoff this session read or wrote, if this session continued
   that thread; several threads this session - name the candidates
   and ask
3. an existing `scratch/` folder whose slug or Task line matches this
   session's task - update it, never create a twin
4. a new slug: 2-4 kebab-case words drawn from the Task line
   (`auth-token-refresh`), unique under `scratch/`

An existing target means update mode - read the old file first if this
session has not. Otherwise write fresh. Collect anchors, read-only:
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
  line; append new steps.
- Decisions, Constraints, Dead ends: append and tighten wording; never
  silently drop - a superseded item is replaced by its successor.
- Log: append one line for this cycle; keep the last three cycles and
  collapse older ones to a single line.

### Reviewer pass

With the file on disk, spawn the seats that apply in one message
(Agent tool, type `general-purpose`, model `sonnet`). Each returns
only numbered `line: finding` items; re-check each yourself, apply
what survives, and stop - never loop the reviewers.

- Always - skeptic: from the file alone, fill five slots - the task,
  the next action, why it is next, how to verify it, what to ask the
  user; an empty slot is a finding. Also check every path and line
  anchor exists.
- Update write, or check beside a `HANDOFF.prev.md` - merge auditor:
  diff prev against current; flag dropped lines not marked done or
  superseded, and surviving lines about finished work.
- Any write over 150 lines - trimmer: line ranges that restate the
  repo, paste code, or pad. Log tails and decisions the shipped code
  now proves may go; Constraints and Dead ends stay.

Past cycle 5 or 400 lines, after those fixes land, one opus-tier
agent rewrites the whole file for precision and returns it; apply it
and land back under the ceiling. Past the budget, prefer
`write --no-check` and run `check` from the fresh session instead.

### Report

Whatever else the turn contains, its final message names the absolute
path, the size, and the resume line - with `--no-check` too:

```
Wrote scratch/auth-token-refresh/HANDOFF.md (~1.4K tokens, cycle 3).
Resume: kill this session, start a fresh one, run
  /handoff read auth-token-refresh
```

## read

1. Resolve `<folder>` per the shared rule; none given, follow the
   table.
2. Read the file, then the `Read now` files - nothing else. Never
   read `HANDOFF.prev.md`.
3. Drift check: HEAD moved from the header sha - run
   `git log --oneline <sha>..HEAD`; header says dirty - run
   `git status --porcelain`. Note drift in one line and proceed.
4. Do not re-plan and do not reopen Decisions. Open questions
   present: put them to the user and stop. Otherwise state the task
   and the Now step in two sentences, then execute Now; the Plan
   follows.
5. This handoff is now the target of a later bare `/handoff write`.

## list

Newest first, from the first 20 lines of each `scratch/*/HANDOFF.md`:
slug, Written date, Cycle, Task line.

## check

Resolve like read, then run the seats that apply - skeptic always,
merge auditor beside a `HANDOFF.prev.md`, trimmer over 150 lines, the
opus rewrite past 400 - apply what survives, and report what changed.
