---
name: handoff
description: >-
  Write or read a session handoff under working/ - the exit the
  context-budget warnings point at. The verb is inferred, never typed.
  Bare /handoff writes or updates this session's
  working/<slug>/HANDOFF.md. In a fresh session it reads one back
  instead. list shows what exists, check reviews one in place, and
  when, diff, artifacts, standing query the ledger. Replaces /compact,
  and replaces re-planning: the file carries the approved plan across
  sessions.
allowed-tools: Bash(hq *)
---

# Handoff

One folder per task thread, `working/<slug>/` at the repo root
(`git rev-parse --show-toplevel`; the cwd outside a repo). Its
`HANDOFF.md` carries what a fresh session needs to resume and nothing
the repo already records. Write near the budget, then kill the session:
a total clear, in which only this folder and the repo survive. Run
`/handoff <slug>` in a fresh one. A later bare `/handoff` updates the
same file.

The plugin puts `hq` on the agent's PATH while it is enabled. Every
verb but `list` takes the slug first. Five flags before the verb -
`--root DIR`, `--cycle N`, `--now ISO`, `--session ID`, `--host H` -
override the `HQ_ROOT`, `HQ_CYCLE`, `HQ_NOW`, `HQ_SESSION`, and
`HQ_HOST` environment values the script otherwise reads; a session
never needs them. Exit 0 is
done; 1 is a refusal or a blocking finding, and
nothing is written except that a refused `stamp` appends its receipt row
(R2, below); 2 is a usage error. All output is stdout, one fact per
line. Every line it prints is listed in this file beside the action it
calls for. Five usage lines can come from any verb: `hq: invalid slug
'<slug>'` (a slug is letters, digits, `.`, `_`, `-`, never `/` or `..`),
`hq: root is not a directory: <path>`, `hq: --cycle must be an integer`,
`hq: --now must be an ISO 8601 timestamp` (each exit 2), and `hq:
cycles/manifest.tsv row N has a non-integer cycle` (exit 1, a hand-edited
manifest). `hq: HANDOFF.md is a directory` (exit 1) names a folder whose
file was replaced by a directory. `hq: cannot access <path>: <reason>`
(exit 1) names a file or directory the script could not read or create -
a permission, or a path that is not a directory; fix it and re-run. A
`~` in `--root` or `HQ_ROOT` is expanded.

## The folder

```
working/auth-token-refresh/
+- HANDOFF.md        the whole read-time payload
|    header line     Written | Cycle | branch @ sha | dirty    SCRIPT
|    ## Task ## Now ## Plan ## State ## Environment
|    ## Open questions                                        AGENT
|    ## Unfiled      typed bullets, drained into standing.md  AGENT
|    <!-- hq:read -->       gated paths with resolved spans   SCRIPT
|    <!-- hq:artifacts -->  live gated rows; the rest counted SCRIPT
|    <!-- hq:standing -->   unsuperseded items                SCRIPT
|    ## Log          last three cycles plus one roll-up line  SCRIPT
+- ledger.tsv        append-only stamps: AGENT dictates, SCRIPT writes
+- standing.md       append-only decisions, constraints, dead ends:
|                    AGENT dictates, SCRIPT appends
+- cycles/           c01.md .. cNN.md, each finished HANDOFF.md
|                    verbatim; cNN.hand.md, a hand-edited file
|                    begin archived; plus manifest.tsv         SCRIPT
+- .hq.lock          held from begin to finish                 SCRIPT
+- HANDOFF.orig.md   the foreign file an adoption began from    AGENT
+- SPEC.md notes-*.md probes/    the work itself, untouched
```

The agent writes the cursor (Task through Open questions) and
`## Unfiled`, and never opens `ledger.tsv`, `standing.md`, or
`cycles/`. The script writes everything else. A hand edit below the
first `<!-- hq:` marker is overwritten by `finish`; a hand edit to the
header line is overwritten too.

## Which verb, which target

The verb is inferred, never typed. One question settles it: does this
session hold anything worth telling a fresh session?

- Yes - a file edited, a decision settled, a finding the repo does
  not already record, a handoff read here. Write.
- No - none of that. A session whose opening move this is, and
  equally one that has only looked something up. Read.

Ask it of the content, never the position: a session that answered one
question and edited nothing holds nothing worth passing on, however
many messages came first. Write is the last move of a working session,
read is the first move of the session that replaces it, and there is
no third case.

An argument is always a folder under `working/`; the document inside
is always `HANDOFF.md`, never named by the caller.

| Input                              | Action                                 |
| ---------------------------------- | -------------------------------------- |
| `/handoff`                         | write; read when the session is fresh  |
| `/handoff <slug>`                  | the same, against `working/<slug>/`    |
| `/handoff list [n]`                | this repo, newest first; n caps it     |
| `/handoff check [slug]`            | review one handoff in place, fix it    |
| `/handoff when <slug> <path>`      | one path's ledger rows, oldest first   |
| `/handoff diff <slug> <c1> <c2>`   | cursor lines that changed, c1 to c2    |
| `/handoff artifacts <slug>`        | every live ledger row, uncapped        |
| `/handoff standing <slug> [--all]` | all standing items in full; --all adds |
|                                    | superseded ones                        |

`write` and `read` are still accepted as the first word, each with an
optional slug after it, and override the inference; `--no-check` may
sit anywhere and skips the reviewer pass. A first argument that matches
`write`, `read`, `list`, `check`, `when`, `diff`, `artifacts`, or
`standing` is that word, not a slug.

Guess neither the verb nor the target. Where either is ambiguous,
say so, list the candidates, and stop - touch nothing.

A folder argument resolves the same way everywhere: exact folder
name, else a unique prefix of the `working/*/` names, else list the
candidates and stop (write: create the folder). A target exists when
its `HANDOFF.md` exists. `hq` resolves its slug the same way and
exits 2 with `hq: ambiguous slug '<slug>': <names>` or
`hq: no folder matching '<slug>' under <path>`.

## write

Target, first match wins - an argument is never required:

1. an explicit folder argument
2. the handoff this session read, wrote, or checked, when the work
   since has been that same task; several threads this session - name
   the candidates and ask
3. an existing `working/` folder whose slug or Task line matches this
   session's task - update it, never create a twin
4. a new slug: 2-4 kebab-case words naming the task as this session
   would state it (`auth-token-refresh`), unique under `working/`

What the target holds decides the route; the write path below is the
same in every case:

- `ledger.tsv` exists: update. Read the old `HANDOFF.md` first if this
  session has not.
- `HANDOFF.md` with a conforming `Written: | Cycle:` header and no
  `ledger.tsv`: `begin` runs `adopt` first and prints
  `hq begin: ran adopt on existing HANDOFF.md`. No copy by hand on this
  route: `adopt` archives the file to `cycles/c<N>.md` at its header
  cycle and `begin` opens cycle N+1.
- `HANDOFF.md` with no conforming header: the adoption pass (below)
  comes first.
- no folder: `begin` creates it with an empty cursor and prints
  `hq begin: created <path>`.

The header line is the script's: `finish` writes it from the git
state, or without git ends it after the cycle. The agent collects no
anchors. Background tasks still running, and any second repo this
session changed (path, branch, sha), go under Environment.

### The file

Write for a reader with no memory of this session and full access to
the repo: short technical documentation in complete sentences, no
transcript narration. Task and Now are required; omit any other cursor
section that would be empty. The file is the whole bridge - a
requirement the user stated, an approval given, a quirk found the hard
way is lost unless written here. Trimming cuts what the repo records,
never what only the session knows; in doubt, write it down.

The file below is real output: three finished cycles on a synthetic
thread whose repo sits at `~/code/poller`.

```markdown
# Handoff: auth-token-refresh

Written: 2026-08-26 | Cycle: 3 | master @ fcbab89 | dirty: scripts/auth.py

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

## Environment
- test: python3 -m pytest tests/ -q
- staging IdP secret: env IDP_CLIENT_SECRET, set in ~/.env.staging

## Open questions
- Cap retry backoff at 60s, or give up after five tries? Blocks the
  integration test.

<!-- hq:read 53c21ca4645f -->
## Read first
~/code/poller/scripts/auth.py (120 lines)  poller; the 401 branch is under edit
SPEC.md:11-13  refresh contract; s3 is the retry schedule
<!-- /hq:read -->

<!-- hq:artifacts 9466c74c0e59 -->
## Artifacts
SPEC.md  spec  always  c1  refresh contract; s3 is the retry schedule
notes-idp-quirks.md  notes  edit  c1  staging IdP quirks, found the hard way
~/code/poller/scripts/auth.py  draft  always  c1  poller; the 401 branch is under edit
<!-- /hq:artifacts -->

<!-- hq:standing c89c0cedae47 -->
## Standing
### Constraints
[c01] (c1) **Never log token values** Not even at debug; the user said so.
### Decisions
[d01] (c1) **Refresh in-process, no sidecar**
### Dead ends
[x01] (c1) **httpx event hooks for auto-refresh**
[x02] (c1) **A pid in the lock.**
<!-- /hq:standing -->

## Log
- 2026-08-24 (cycle 1, master@fcbab89 +1): token store and refresh endpoint written
- 2026-08-25 (cycle 2, master@fcbab89 +1): refresh verified against staging; backoff added
- 2026-08-26 (cycle 3, master@fcbab89 +1): poll() wiring started
```

How to read the generated blocks:

- `Read first`: one line per live row with `read_before=always`. The
  span `SPEC.md:11-13` is where the row's `where` anchor resolves
  today; `(N lines)` gives the file's length - the row has no anchor,
  so the whole file is the read; `SPEC.md:?` means the anchor matches
  no heading - read the whole file, then re-stamp with a `--where` that
  resolves: for `## s4: Field-to-path mapping`, `s4`, `s4: Field-to-path
  mapping`, or `Field-to-path mapping`; for `## 4. Cache warmup`, `s4` or
  `Cache warmup`; for `# 11b. Proof`, `s11b`, `11b. Proof`, or `Proof`;
  for `#### 2a - Basis`, `s2a`, `2a - Basis`, or `Basis`. Re-run `hq
  open` after the re-stamp; a `?` that survives means the anchor is
  still wrong.
- `Artifacts`: one full line, `path  kind  read_before  cNN  label`,
  per live row with `read_before` in {always, edit, mention}, and
  `path  spec?  unstamped` for a file on disk with no row. Rows with
  `read_before=never` collapse to counts such as
  `notes x11  snapshot x6  - hq artifacts <slug>`; past 40 full
  lines the overflow folds into those counts; rows no longer live
  collapse to `superseded n  archived n  missing n  - hq when <slug>
  <path>`, where `<path>` is a placeholder for the row to expand. The
  command named on a line expands it.
- `Standing`: ids are `d` decision, `c` constraint, `x` dead end;
  `(c1)` is the cycle that recorded the item. Constraints print in
  full, the rest as headlines; `superseded n  - hq standing <slug>`
  counts the superseded items and `... n more  - hq standing <slug>`
  names the cut past 80 lines. `hq standing <slug>` prints every
  item in full.
- `Log`: `+1` counts dirty paths at that finish. An adopted folder's
  first line reads `adopted`, or `adopted; prior Log: N lines in
  cycles/cNN.md` when the file had a Log; the archived file holds those
  lines, and the manifest row's `note` field carries them joined with
  ` / `.

Rules:

- Point, never paste: a rehomed sibling is stamped with `hq stamp`;
  its pointer line is generated, never typed.
- Skip what the repo records: git history, CLAUDE.md, README content.
- Too big for the file but worth keeping (a log excerpt, a survey):
  a sibling file `working/<slug>/notes-<topic>.md`, stamped
  `--read-before edit` when the cursor points at it, so its label stays
  in the Artifacts block instead of a count.
- Name where a credential lives, never its value.
- Absolute dates. ASCII only.
- Now is the single next action; Plan is what follows it. Plan
  carries the approved plan; neither is re-opened.
- The cursor is rewritten from `## Task` down every cycle, and every
  cursor line this session did not settle is carried forward verbatim:
  an Open question leaves only when answered, a Plan item only when
  done or rehomed. `finish` owns the header line.
- Anything still awaiting the user - a question, an unapproved plan -
  goes under `Open questions`; read stops there. Now is rewritten
  every cycle; an unanswered question is carried forward until it is
  answered, however old.
- An item recorded with `note` or under `## Unfiled` is not repeated
  in State: the Standing block carries it.
- Under 120 hand-written cursor lines fits most sessions; 200 is the
  ceiling. `finish` counts the cursor it writes back, `## Task` through
  the last cursor section, blank lines included and `## Unfiled` already
  drained, and prints the count. The generated blocks do not count - the
  script bounds them.

### The artifact ledger

The ledger (`ledger.tsv`) is append-only; the agent never opens it.
Rows are dictated through `hq stamp`, `hq note`, and `hq supersede`.
`stamp` and `note` also take `--batch`, reading one row per stdin
line.

Thirteen fields per stamp row: `cycle ts path base kind status
read_before successor where sha12 lines reason label`.

Kind inference, first match wins:

| Name or shape                                     | kind      | read_before |
| ------------------------------------------------- | --------- | ----------- |
| contains `conflicted copy`; a tab or newline in   | skip      | -           |
| the name; not a regular file or directory         |           |             |
| `*.pre-*`, `*.prev.*`, `*.orig.*`, `*.bak`        | snapshot  | never       |
| `HANDOFF*.md` at the folder's top level (nested   | snapshot  | never       |
| or outside: other)                                |           |             |
| name contains `cycle<digits>`                     | snapshot  | never       |
| a directory                                       | probe-dir | never       |
| `SPEC*`, `DESIGN*`, `PROPOSAL*`, `*-DECLARATION*` | spec      | always      |
| first heading starts `Spec`/`Design`, any level   | spec      | always      |
| `*.py`, `*.sql`, `*.js`, `*.ts`, `*.ps1` at the   | draft     | always      |
| folder's top level (nested or outside: other)     |           |             |
| `notes-*`, `REVIEW*`                              | notes     | never       |
| `todo*`, `TODO*`                                  | todo      | never       |
| anything else                                     | other     | never       |

When a stem (e.g. `SPEC`) has several members, `adopt` and `begin`
gate only the newest spec-kind file. Every older stem-mate is stamped
`superseded/never` pointing at the newest spec.

Rules the script enforces:

- R1 A row whose inferred kind is spec or draft, or whose stored or
  `--kind` kind is, may not lower `read_before` from `always`, leave
  `live`, or change kind, unless its `successor`, passed or carried
  forward, names a file on disk other than itself, or `--archive
  --reason` is given (`--status archived --reason` is the same thing).
  An explicit `--successor` whose own current row is not live is
  refused, so two specs cannot name each other; a successor with no row
  yet is accepted, and the next `begin` lists it as unstamped. A path
  that has ever been spec or draft - inferred, stored, or `--kind` -
  stays gated: its only way back to `live` is with `read_before`
  `always`.
- R2 A refused stamp still appends a row: the previous fields, and
  `reason` set to `refused: <why>`; with no previous row, the kind
  table's seed and the file's sha and line count. The attempt is in the
  record and clears nothing.
- R3 A live row with `read_before` in {always, edit} whose file sha
  differs from `sha12` blocks `finish` until the agent re-stamps it.
  A re-stamp alone clears R3.
- W1, W2 `finish` and `open` check that `ledger.tsv` and `standing.md`
  are byte-prefix-identical to their last finished-cycle state; any
  edit to a recorded line is a hard fail in `finish`. When a known tool
  caused the break (a formatter, a merge), pass
  `--acknowledge "<reason>"` to `finish`; the reason lands in the
  manifest.

Stamp forms, all real:

```
hq stamp <slug> SPEC.md \
  --where "3. Retry" --label "refresh contract; s3 is the retry schedule"
hq stamp <slug> \
  ~/code/poller/scripts/auth.py --label "poller; the 401 branch is under edit"
hq stamp <slug> notes-idp-quirks.md \
  --read-before edit --label "staging IdP quirks, found the hard way"
hq stamp <slug> SPEC.md \
  --successor SPEC-v2.md
hq stamp <slug> DRAFT.py \
  --archive --reason "abandoned for the sidecar approach"
hq stamp <slug> notes-old.md --defer
```

- A path is relative to the folder: `./SPEC.md` and `sub/../SPEC.md`
  are the row `SPEC.md`. A path outside it - a repo file, a `~` path,
  an absolute path, a relative path that leaves the folder - is stored
  whole (`~/code/poller/scripts/auth.py`) and gated the same way. There
  is no search of the working directory: a repo file is stamped by its
  `~` or absolute path. `hq stamp <slug>` with no path prints `hq stamp:
  path is required` (exit 2); a path holding a tab, newline, or
  carriage return prints `hq stamp: path may not contain a tab,
  newline, or carriage return` (exit 2); a socket or a FIFO prints
  `hq stamp: <path> is not a regular file or directory` (exit 2).
- `--kind`, `--read-before`, `--status`, `--where`, and `--label` each
  default to the previous row's value; `--reason` carries only while
  kind, status, and read_before all hold. Omit `--label` and `--where`
  on a re-stamp to carry them forward. `--kind` takes spec, draft,
  notes, todo, snapshot, probe-dir, or other; `--read-before` always,
  edit, mention, or never; `--status` live, superseded, archived, or
  missing; any other value is a usage error (exit 2). `--where` joins several
  anchors with `;`, each a heading's text without its number, or `s<n>`
  for the heading numbered `<n>` - `4.`, `4:`, `4 -`, `s4.`, and `s4:`
  all count as the number 4; a bare `S4 ...` is a word, not a number. A
  number may carry one letter when a `.`, `:`, or ` - ` follows it:
  `s11b` names `# 11b. Proof`, `s11` does not, and a bare `3D ...` or
  `2a-b ...` is a word.
- `--successor P` sets `status=superseded read_before=never` unless
  the stamp says otherwise. `--archive` sets `status=archived
  read_before=never`; without `--reason` it prints `hq stamp: --archive
  requires --reason` and exits 2, writing nothing; `--status archived`
  without one prints `hq stamp: --status archived requires --reason`
  the same way. A `--reason` that starts with the receipt prefix prints
  `hq stamp: --reason may not start with 'refused: ', the receipt
  prefix` and exits 2. `--defer`
  writes `kind=other read_before=never reason=deferred` so the file
  reappears in the next work list; it is refused for a spec or draft.
- `--batch`: one stdin line per stamp, the same arguments minus the
  slug, split like a shell line. A line that does not parse - a bad
  flag value, no path, an unknown flag - prints `hq stamp: batch line N
  not parsed: <line>` (for notes, `hq note: batch line N not parsed:
  <line>`), the rest still run, and the exit is 2.

```
hq stamp <slug> --batch <<'ROWS'
SPEC.md --where "3. Retry" --label "refresh contract; s3 is the retry schedule"
notes-idp-quirks.md --read-before edit --label "staging IdP quirks"
ROWS
```

`standing.md` is an append-only flat list. Kinds are `decision`,
`constraint`, `dead-end`; any other word prints `hq note: kind must be
decision, constraint, or dead-end; got <x>` (exit 2). `--headline` is
required and one line: `hq note: --headline is required` (exit 2); a
tab or newline in it or in the body becomes a space. The body follows
the headline as the last argument. `--batch` reads one note per stdin
line (`--batch -` is accepted too); a line that fails prints `hq note:
batch line N not parsed: <line>`, the rest still run, exit 2.
`supersede` takes two ids of one kind; `hq supersede: ids must share a
prefix ('d17' vs 'c04')` and `hq supersede: 'd99' not found in
standing.md` are its refusals (exit 1).

```
hq note <slug> decision \
  --headline "Refresh in-process, no sidecar" "One caller; latency is fine."
hq note <slug> --batch <<'ROWS'
constraint --headline "Never log token values" "Not even at debug."
dead-end --headline "httpx event hooks" "A hook cannot retry the request."
ROWS
hq supersede <slug> d17 d23
```

### Unfiled

Items settled this session with no `note` call go under `## Unfiled`
as typed bullets, one per item, the headline first:

```
- decision: **<headline>** <body>
- constraint: **<headline>** <body>
- dead-end: **<headline>** <body, wrapped onto indented lines
  when long>
```

A bullet with no bold span takes its first sentence as the headline.
`finish` drains `## Unfiled` into `standing.md` and removes the
section. An unprefixed bullet is a hard fail: `finish` prints
`hq finish: untyped Unfiled bullet: '<line>'` and writes nothing; the
section
must sit above the first `<!-- hq:` marker, or `finish` prints
`hq finish: '## Unfiled' sits below the first hq: marker; move it
above` and writes nothing. `adopt` leaves
`- unfiled: <text>` bullets for content that fit no cursor section;
retype each as one of the three kinds, move it into a cursor section,
or rehome it to a `notes-<topic>.md` sibling before `finish`. The
section is optional: omit it when every item went through `note`.

### The gate and the Stop hook

Two hooks ship with the plugin beside `scripts/hq.py`. Both report
and never block, and `finish` consults neither: what blocks `finish`
is R3, and a re-stamp clears R3.

- The gate runs on every Bash, Edit, Write, and NotebookEdit call. It
  arms on the first `hq open <slug>` in the session's transcript and
  follows the slug opened most recently.
  On the first write after that - an Edit or Write outside
  `working/<slug>/`, or a Bash command that redirects to a file, runs
  `sed -i`, `tee`, `git add`, or `git commit` - it names each gated
  path (`read_before` in {always, edit}) with no read-shaped evidence
  in the session: `handoff gate: <slug>: N gated path(s) not read this
  session - <path> (lines a-b), ...; read each or run: hq read
  <slug> <path>`. Read each named span, or run `hq read` on it,
  before going on with the write; the line comes once per session.
  Evidence is a Read tool call, a `cat`/`head`/`tail`/`less`/`sed -n`
  naming the path, or an `hq read` receipt; `ls`, `wc`, `grep`, and
  a `stamp` naming the path do not count. A command whose command
  word is `hq` or `hq.py` - the tooling itself - and a write whose
  target is inside the handoff folder are exempt; the word elsewhere
  on the line exempts nothing, a command that only reads from the
  folder is not exempt, and a target reached through a shell variable
  is not recognized. `HQ_GATE=0` in the environment turns the gate
  off; `HQ_GATE_DENY=1` makes it deny the write instead of reporting.
- The Stop hook runs at the end of every turn. When a folder's
  `HANDOFF.md` no longer matches the sha its last finished cycle
  recorded and no cycle is open, it tells the user once (the line can
  repeat when the state directory cannot be written): `handoff:
  working/<slug>/HANDOFF.md was written by hand since cycle N finished;
  run hq begin <slug>, then hq finish <slug> --log "...", or the
  next open reports LEDGER BEHIND`. The move is the one it names.

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
  `entry: working/<slug>/HANDOFF.md`. Add nothing else to the todo
  from here.
- An untracked todo file cannot anchor to a sha: mark the pointer
  `(untracked)`, and at read its current content is the truth.

### Write path

Run these steps in order:

1. `hq begin <slug>` takes the lock and prints the work list, then
   `cycle N begun by <session> on <host>`. Each class shows up to five
   names and `... and N more`, every line indented two spaces under
   `begin`'s own. Each work-list line and its move:
   - `unstamped <kind> xN: <names>` - stamp each in step 3.
   - `sha moved: <path>` - re-read the span (`hq read <slug> <path>`
     records the read; a `cat` of the span counts too), then re-stamp
     (R3).
   - `missing live: <path> - hq when <slug> <path>` - run the command
     shown to check the path was stored right (a repo file is stamped by
     its `~` or absolute path) and re-stamp the correct path; a file
     genuinely gone takes `stamp --successor` or `stamp --archive
     --reason`, which drops it from the read block; `--defer` for a
     non-gated kind.
   - `successor missing: <path> -> <successor>` - the successor left
     the disk; name a new one or archive the row.
   - `conflicted copy: <name>` - a sync duplicate; resolve it by hand.
   - `unstampable name: <name>` - a tab, carriage return, or newline in
     the file name, or a file that is not a regular file or directory (a
     socket, a FIFO); rename or remove it, or leave it and it stays out
     of the ledger.
   - `deferred xN: <names>` - still waiting for a decision.
   - `W1: ledger prefix changed ...` or `W2: standing prefix changed
     ...` - a recorded line was edited; find the tool that did it and
     pass `--acknowledge` to `finish`.
   - `hq begin: HANDOFF.md changed since last finish; saved to
     cNN.hand.md` - a hand edit was archived; `begin` continues, and
     says so again on every `begin` while the file still differs.
   - `hq begin: lock held by <session> on <host> since <time>; use
     --force to take over` (exit 1) - another session is inside a
     cycle less than two hours old. Stop and say so; `begin --force`
     only when the user confirms that session is dead. `hq begin: lock
     file unreadable; use --force to take over` (exit 1) is the same
     stop for a lock file that cannot be parsed. An older lock is
     taken over without `--force`; `begin` prints `hq begin: took over
     from <session>` and `cycle N begun by <session> on <host> at
     <time>, never finished`.
2. One `hq note` per item settled this session, or one `--batch`.
   `advisory: standing.md lacked its trailing newline; restored` (also
   for `ledger.tsv`, from `stamp`) says a sync or an editor cut the
   file's last byte and the append put it back; nothing else to do. One
   `hq supersede <slug> <old-id> <new-id>` when a ruling reverses an
   earlier one.
3. One `hq stamp` per artifact created, re-read, or moved, or one
   `--batch`. A refusal (exit 1) means the row stays as it was. The
   texts: `hq stamp: refused: R1: <kind> read_before must stay always
   without --successor or --archive`, `... R1: <kind> status must stay
   live without --successor or --archive`, `... R1: <kind> kind must
   stay spec or draft without --successor or --archive`, `hq stamp:
   refused: R1: successor <path> is <status>, not live`, and `hq stamp:
   refused: --defer not allowed for inferred <kind>`. Supply the
   successor or the archive reason, or leave the row gated - unless its
   file is missing, which blocks `finish` until the row is re-pointed,
   superseded, or archived.
4. Rewrite the cursor from `## Task` down: Task, Now, Plan, State,
   Environment, Open questions, above the first `<!-- hq:` marker,
   carrying forward every line this session did not settle. Leave the
   header line and everything below the marker alone. Anything
   settled with no `note` call goes under `## Unfiled`.
5. Run the Reviewer pass (below): the skeptic seat, and past 160
   cursor lines the rewrite seat. Each surviving finding becomes a
   `note`, a `stamp`, or a cursor edit in this cycle; return to step 2
   for it, then continue.
6. `hq finish <slug> --log "<one line for the Log>"`. It checks, in
   order, and exits 1 having written nothing on the first class that
   fires:
   - `hq finish: lock held by <session>; this is <session>` - run
     `begin` first.
   - `W1 ...` / `W2 ...` - as above; `--acknowledge "<reason>"` turns
     the line into `acknowledged: W1: ...` (or W2) and records the
     break and the reason in the manifest. With no break,
     `advisory: --acknowledge given, no witness broke`.
   - `R3: <path> sha moved; re-stamp before finish` - re-read, then
     re-stamp.
   - `missing live gated: <path>; use --successor or --archive
     --reason` - re-point, supersede, or archive it (step 1's move).
   - `hq finish: '## Unfiled' sits below the first hq: marker; move it
     above` - move the section up.
   - `hq finish: untyped Unfiled bullet: '<line>'` - type it; `hq
     finish: Unfiled bullet has no headline: '<line>'` - the bold span,
     or the first sentence, has no word in it; give it one.
   Then it writes everything in one pass: drains Unfiled, renders the
   blocks, writes the header and Log, archives the file to
   `cycles/cNN.md`, appends the manifest row, releases the lock, and
   prints `<path>  N cursor lines  N tokens (cursor a, read b,
   artifacts c, standing d)` - the payload's token estimate split into
   the hand-written cursor and the three generated blocks - and
   `resume: /handoff <slug>`. A `<path>:?` in the rendered read block
   is not a blocking line, but the anchor is unresolved: re-stamp with
   a `--where` that resolves and re-run `open`.
   Lines prefixed `advisory:` never block: `advisory: unstamped <kind>
   xN: <names>`, `advisory: conflicted copy: <name>`, `advisory:
   unstampable name: <name>`, `advisory: abs path not on disk: <path>`,
   `advisory: successor missing: <path> -> <successor>`, `advisory:
   label shorter than predecessor: <path>` (check the new label kept
   every backticked token and `s<n>` reference the old one carried;
   otherwise ignore it), `advisory: label dropped {...}: <path>` (one
   of those tokens is gone; put it back or accept the loss), and
   `advisory: collides: <term> <- <where> "<text>"`, where `<where>` is
   `<file>:<line>` for a spec heading and a standing id such as `x01`
   for a dead-end headline: a term in the Now step also names a dead
   end or a spec heading - check that the Now step does not retry a
   rejected idea.

One whole cycle on the example thread, in order:

```
hq begin auth-token-refresh
hq note auth-token-refresh decision \
  --headline "Refresh in-process, no sidecar" "One caller; latency is fine."
hq stamp auth-token-refresh SPEC.md \
  --where "3. Retry" --label "refresh contract; s3 is the retry schedule"
hq stamp auth-token-refresh \
  ~/code/poller/scripts/auth.py --label "poller; the 401 branch is under edit"
# rewrite the cursor; spawn the skeptic; apply what survives
hq finish auth-token-refresh \
  --log "token store and refresh endpoint written"
```

### Adoption

A target with no conforming header was written by some other process.
Converge the form, destroy no content, in this order:

1. `hq adopt <slug>`. On a file with no conforming header it
   changes nothing and prints `hq adopt: non-conforming header; write
   a conforming HANDOFF.md first` and the heading inventory (exit 1) -
   the map for step 3.
2. `cp -n working/<slug>/HANDOFF.md working/<slug>/HANDOFF.orig.md`,
   before any other write; skip it when the copy already exists. That
   copy is never overwritten or deleted; the walk stamps it as a
   `snapshot` row. A `HANDOFF.prev.md` needs no copy: `adopt` archives
   it to `cycles/c<N-1>.md` itself.
3. Rewrite `HANDOFF.md` by hand: `# Handoff: <slug>`, a blank line,
   `Written: <today> | Cycle: 1`, then the sections. Five foreign
   sections `adopt` reads itself; keep each under its own heading,
   wording unchanged: `## Key files`, its bullets under a `Read now:`
   line and a `Reference only:` line - a clause after the label is fine,
   `Read now, under x/ unless noted:` - with a path first on each bullet
   and its text on the same line or an indented line below (`adopt`
   grades them into the ledger and the read block; several paths on one
   bullet, comma-separated, each take a row sharing the bullet's text;
   two bullets naming one path merge into one row, labels joined with
   `; `, or a space after a label that ends a sentence, and anchors with
   `;`; a bullet whose first token is not a path
   lands whole under `## Unfiled`, its indented lines joined); `##
   Decisions`, `## Constraints`, and `## Dead ends` (moved whole into
   `standing.md`, one item per bullet or unindented line); and `## Log`
   (carried in the manifest row). Map every other foreign section to
   the cursor section carrying the same kind of fact - Task, Now, Plan,
   State, Environment, Open questions - and keep every fact. A
   directive the file quotes - a reading order, a backup or worktree
   it says never to delete - becomes a `## Constraints` entry. What
   fits nowhere, or would hold the cursor over the ceiling, moves whole
   to a sibling `notes-<topic>.md`, stamped `--read-before edit` when
   the cursor points at it - rehomed, never cut. Touch no sibling file
   except to add.
4. Continue at Write path step 1: `begin` sees the conforming header
   with no `ledger.tsv`, runs `adopt`, prints `hq begin: ran adopt on
   existing HANDOFF.md`, and opens cycle 2 - the hand-written file is
   cycle 1, archived as `cycles/c01.md`. `adopt` infers kinds, seeds
   the read obligations, and prints what still needs judgment: `label:
   <text>` per seeded label, `read_before=<x>: <n>` counts, `gated
   (n): <names>`, `where dropped: <path> '<anchor>'` (an `s<n>` or
   `section <n>` the label cites that names no heading of that file -
   `s1` in prose most often means another file's step; where it was
   meant, re-stamp with a `--where` that resolves), `Key files pointer
   not on disk: <path>`, `skipped conflicted copy: <name>`,
   `unstampable name: <name>` (a tab or
   newline in the name, or a socket or FIFO; rename the file before
   stamping it), `advisory: R1 ...`, and the conservation line:
   `conservation: every original line carried`, or `conservation: N
   original lines not carried` with one `not carried: <line>` line under
   it per missing line, each printed whole - text of the file `adopt`
   read that reached neither the cursor, nor `standing.md`, nor a
   label. Where `HANDOFF.orig.md` exists a second line measures the hand
   rewrite against it, counting a line rehomed into a live notes sibling
   or any row graded `edit` as carried: `conservation vs HANDOFF.orig.md:
   N lines not carried` (or `conservation vs HANDOFF.orig.md: every line
   carried`), with the same `not carried:` lines under it. Rehome each
   not-carried line - a typed `## Unfiled` bullet, a cursor section, or
   a stamped sibling - and settle each label with a `stamp` in step 3.

`hq adopt <slug>` on an adopted folder prints `hq adopt: already
adopted; ledger.tsv exists`, and on an empty one `hq adopt: no
HANDOFF.md in <folder>` (exit 1 each). On success it prints `hq adopt:
seeded N entries in <slug>` - the ledger's row count: every walk entry
but `HANDOFF.md`, `ledger.tsv`, `standing.md`, `cycles/`, `.hq.lock`,
and dotfiles, plus every Key files pointer the walk cannot see - and the
judgment lines listed in step 4.

### Reviewer pass

With the file on disk, spawn the seats below before `finish`. The
skeptic returns one numbered item per finding, `<n>. <finding>`;
re-check each in the write session, apply what survives, and stop -
never loop. A question it raises for the user goes under `## Open
questions`; do not stop for it.

- Skeptic (always; Agent tool, type `general-purpose`, model `sonnet` -
  or the reviewer tier the host's own agent rules name, when they name
  one): from the file alone, fill five slots - the task, the next
  action, why it is next, how to verify it, what to ask the user; an
  empty slot is a finding. For each
  line of the read block, open the resolved span and report any point
  where the Now step contradicts it. For each todo file the Plan
  points at, verify that the Now step agrees with the corresponding
  live item in that file.
- Rewrite (past 160 cursor lines, as `finish` counts them): one
  opus-tier agent (Agent tool, model `opus`) rewrites the cursor for
  precision and returns it; apply it before `finish`.

### Report

Whatever else the turn contains, its final message names the absolute
path, the size `finish` printed, and the resume line - with
`--no-check` too:

```
Wrote /home/me/code/poller/working/auth-token-refresh/HANDOFF.md
  (~528 tokens, cycle 3).
Resume: kill this session, start a fresh one, run
  /handoff auth-token-refresh
```

## read

1. Resolve `<slug>` per the shared rule. With none given, run `hq list`:
   one line, read that slug; several, list them and ask which; `hq list:
   no handoff under <path>`, say so. The last two stop there - never
   pick the newest, and never fall through to write.
2. Run `hq open <slug>`. It is read-only and prints only what is wrong;
   silence is good. Each line and its move:
   - `WARNING: W1 ...` / `WARNING: W2 ...` - a recorded line was
     edited since the last finish; report it, read on.
   - `unfinished cycle N held by <session> on <host>` - a session
     died mid-cycle or is still running; the file may be behind its
     stamps. Report it; the write session's `begin` handles the lock.
   - `LEDGER BEHIND: file cycle N > last finished M` - the header was
     hand-edited past the ledger; trust the ledger, report it.
   - `sha moved since stamp: <path>` - the file changed after its
     stamp; read the file, not the span alone.
   - `git drift: header <b>@<sha> -> now <b>@<sha>` - run
     `git log --oneline <sha>..HEAD` to see what landed, and
     `-- <todo path>` for each todo file the Plan points at.
   - `block sha mismatch: hq:<block> ...` - a block was hand-edited;
     trust `hq artifacts` / `hq standing`, not the block.
   - `unresolved anchor in <path>: '<anchor>'` - the heading moved or
     was renamed; read the whole file and, at write time, re-stamp
     with a `--where` that resolves (the worked forms are under "How
     to read the generated blocks"), then re-run `open`.
   - `span moved: <path> [...] -> [...]` - the read block's line
     numbers are stale; the printed spans are current.
3. Read `HANDOFF.md`. Then, for each line of the `## Read first` block,
   run `hq read <slug> <path>`, the path in any spelling `stamp`
   accepts - the block's `~` form or its expansion: it prints the
   resolved span (or the whole file when the row has no anchor) and
   records the read. A `? unresolved: <anchor>` line follows the spans
   that did resolve, one per anchor that did not; when nothing else
   printed, read that file whole. `hq read: <path> not in ledger` means
   the path was never stamped - read it whole by hand; `hq read: <path>
   not on disk` means it is gone; `hq read: receipt not written:
   <error>` (exit 1, after the spans) means the read happened but the
   state directory refused the receipt - the gate will not credit it.
   Then read every todo file the Plan points at. A conforming target
   with no `ledger.tsv` has no generated blocks yet: follow its `## Key
   files` `Read now:` pointers by hand; the first write adopts it. A
   target with no conforming header names its own reading order or
   read-first pointers - follow those instead. Read nothing else.
4. Drift check: the header says dirty - run `git status --porcelain`
   and note what is still uncommitted. No sha in the header (written
   outside a repo) or no conforming header - skip the git steps. A
   pointed todo moved or disagrees with the file: the todo wins on
   what is open or done, the handoff on approach and decisions. Note
   drift in one line and proceed.
5. Do not re-plan and do not reopen a Standing item. Open questions
   present: put them to the user and stop. Otherwise state the task
   and the Now step in two sentences, then execute Now; the Plan
   follows.
6. A later bare `/handoff` targets this handoff - write rule 2.

## list

`hq list [n]` prints one line
per folder under `working/` that holds a `HANDOFF.md`, newest
first by the time that file last changed, and writes nothing:
`<slug>  <Written date>  c<N>  <done>/<total>  <Task line>`. A bare
`list` shows every one; `list 5` the five most recent; `list 1` the
most recent alone; a count over the number that exist shows them all.
A count below 1 prints `hq list: count must be a positive integer`
(exit 2). Show the user the lines unchanged.

`<done>/<total>` counts `- [x]` (or `- [X]`) over all `- [ ]` and
`- [x]` items under `## Plan` alone; a checkbox under State is not a
plan item. A file with no Plan section, or a Plan with no checkbox item
(numbered lines only), shows `-`, never `0/0`. A file with no conforming
header shows `-` for the date and the cycle. The Task line is the first
non-empty line under `## Task`, `-` when there is none. A file the
script cannot read shows `-  -  -  unreadable: <reason>` after its slug
and the survey goes on. Files changed in the same second list A to Z by
slug. `hq list: no handoff under <path>` (exit 0) means `working/` holds
no folder with a `HANDOFF.md`.

Plan progress is what tells a live thread from a finished one: `7/7` is
done, `0/5` never started, and the cycle count says neither - it counts
how often the thread was worked, not how far it got.

## check

Resolve like read, then read steps 2 and 3. Open questions do not stop
a check; its job is the review. Then run the write path: `begin`; steps
2 to 4 only for findings - what `open` printed and what the skeptic seat
returns - as notes, stamps, and cursor edits; the skeptic seat; and
`finish --log "check: <n> findings applied"`, counting both kinds. A
check with nothing to apply still runs `finish`, which releases the lock
and advances the cycle by one. A folder with no `ledger.tsv` has `begin`
run `adopt` first. A target with no conforming header instead runs the
adoption pass (write, above) and stops.

## when, diff, artifacts, standing

Each runs the `hq` verb of the same name and shows the user its
output, unchanged. None writes anything.

- `hq when <slug> <path>`: every ledger row for the path, oldest
  first, seven tab-separated columns: `path cycle status read_before
  successor reason label`. Over 30 rows, the newest 30 and one line
  `N older rows omitted`.
- `hq diff <slug> <c1> <c2>`: cursor lines of `cycles/c<c1>.md`
  absent from `cycles/c<c2>.md` as `- line`, the reverse as `+ line`;
  at most 60 lines plus one naming the cut. No output means the two
  cursors are identical (so `diff <slug> 5 5` prints nothing). `hq
  diff: cNN.md not found` (exit 1) means that cycle was never finished
  here.
- `hq artifacts <slug>`: every live row as a full line, no cap,
  then `<name>  <kind>?  unstamped` for a file with no row,
  `<name>  conflicted copy` for a sync duplicate, and
  `<name>  unstampable` for a name holding a tab or newline or an entry
  that is not a regular file.
- `hq standing <slug> [--all]`: every unsuperseded item in full;
  `--all` adds the superseded ones.
