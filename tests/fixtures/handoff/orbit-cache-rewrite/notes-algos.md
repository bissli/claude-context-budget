# Research notes: incremental diffing strategies

## Prior art

Three approaches were evaluated: full rebuild, incremental diff,
and event-sourcing.

Full rebuild: recompute every page on each run. Simple to implement;
build time scales with total page count. At 500 pages the rebuild took
140 ms per source change.

Incremental diff: maintain a previous sha map and diff on each run.
O(n) in changed sources, which is typically 1-5% of total. Measured
at under 2 ms on the same 500-page set.

Event-sourcing: subscribe to file-change events and apply patches.
Most complex; requires a reliable event bus not available in the
current environment.

## Decision basis

The incremental diff approach was chosen. It meets the latency target
with no new infrastructure dependencies. The full-rebuild approach was
the dead end recorded at cycle 2.

## Implementation notes

The diff function is a pure function of two sha maps. Comparing sorted
key lists allows a single O(n) pass using two pointers.
