# Handoff: orbit-cache-rewrite

Written: 2026-09-01 | Cycle: 5

## Task

Rewrite the build-cache module so the orbit static-site generator
invalidates stale pages without a full rebuild.
The cache key scheme must be content-addressed to survive template changes.
Integration with the existing page-render pipeline is the primary deliverable.

Task detail 01: specification point that governs scope and acceptance.
Task detail 02: specification point that governs scope and acceptance.
Task detail 03: specification point that governs scope and acceptance.
Task detail 04: specification point that governs scope and acceptance.
Task detail 05: specification point that governs scope and acceptance.
Task detail 06: specification point that governs scope and acceptance.
Task detail 07: specification point that governs scope and acceptance.
Task detail 08: specification point that governs scope and acceptance.
Task detail 09: specification point that governs scope and acceptance.
Task detail 10: specification point that governs scope and acceptance.
Task detail 11: specification point that governs scope and acceptance.
Task detail 12: specification point that governs scope and acceptance.

## Now

Deploy the new cache key computation and hook it into the page-render pipeline.

Now step 01: execute this action before moving to the next phase.
Now step 02: execute this action before moving to the next phase.
Now step 03: execute this action before moving to the next phase.
Now step 04: execute this action before moving to the next phase.
Now step 05: execute this action before moving to the next phase.
Now step 06: execute this action before moving to the next phase.
Now step 07: execute this action before moving to the next phase.
Now step 08: execute this action before moving to the next phase.
Now step 09: execute this action before moving to the next phase.
Now step 10: execute this action before moving to the next phase.
Now step 11: execute this action before moving to the next phase.
Now step 12: execute this action before moving to the next phase.

## Plan

01. Plan item 01: complete this before the next phase begins.
02. Plan item 02: complete this before the next phase begins.
03. Plan item 03: complete this before the next phase begins.
04. Plan item 04: complete this before the next phase begins.
05. Plan item 05: complete this before the next phase begins.
06. Plan item 06: complete this before the next phase begins.
07. Plan item 07: complete this before the next phase begins.
08. Plan item 08: complete this before the next phase begins.
09. Plan item 09: complete this before the next phase begins.
10. Plan item 10: complete this before the next phase begins.
11. Plan item 11: complete this before the next phase begins.
12. Plan item 12: complete this before the next phase begins.
13. Plan item 13: complete this before the next phase begins.
14. Plan item 14: complete this before the next phase begins.
15. Plan item 15: complete this before the next phase begins.
16. Plan item 16: complete this before the next phase begins.
17. Plan item 17: complete this before the next phase begins.
18. Plan item 18: complete this before the next phase begins.
19. Plan item 19: complete this before the next phase begins.
20. Plan item 20: complete this before the next phase begins.
21. Plan item 21: complete this before the next phase begins.
22. Plan item 22: complete this before the next phase begins.
23. Plan item 23: complete this before the next phase begins.
24. Plan item 24: complete this before the next phase begins.
25. Plan item 25: complete this before the next phase begins.

## State

Cache module: implemented and unit-tested.
Pipeline integration: in progress, blocked by template schema change.
Performance: meets the 5 ms target on the benchmark page set.

State item 01: current status of this sub-system is nominal.
State item 02: current status of this sub-system is nominal.
State item 03: current status of this sub-system is nominal.
State item 04: current status of this sub-system is nominal.
State item 05: current status of this sub-system is nominal.
State item 06: current status of this sub-system is nominal.
State item 07: current status of this sub-system is nominal.
State item 08: current status of this sub-system is nominal.
State item 09: current status of this sub-system is nominal.
State item 10: current status of this sub-system is nominal.
State item 11: current status of this sub-system is nominal.
State item 12: current status of this sub-system is nominal.
State item 13: current status of this sub-system is nominal.

## Environment

Python 3.11, stdlib only. No third-party dependencies in the cache module.
Env item 01: verified and stable.
Env item 02: verified and stable.
Env item 03: verified and stable.
Env item 04: verified and stable.
Env item 05: verified and stable.
Env item 06: verified and stable.
Env item 07: verified and stable.

## Open questions

Question 01: under investigation; resolution pending.
Question 02: under investigation; resolution pending.
Question 03: under investigation; resolution pending.
Question 04: under investigation; resolution pending.
Question 05: under investigation; resolution pending.
Question 06: under investigation; resolution pending.
Question 07: under investigation; resolution pending.
Question 08: under investigation; resolution pending.

## Key files

- `SPEC.md` Read now: cache schema and field contracts; s4 field-to-path mapping
- `notes-algos.md` Reference only: background on incremental diffing strategies

## Decisions

- **Use content-addressed cache keys** A sha256 of source and template content
  ensures stale pages are never served after a template change.
- **Cap the cache at fifty entries** Keeps memory use bounded for sites
  that generate thousands of pages; eviction is LRU.

## Constraints

- **Stdlib only in the cache module** No third-party dependencies may be
  introduced; the module ships as a single file alongside the generator.

## Dead ends

- **Mtime-based invalidation** Mtime is unreliable on networked filesystems
  and inside Docker volumes. Abandoned at cycle 2 after reproducing the fault.
