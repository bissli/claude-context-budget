# Spec

## s4: Field-to-path mapping

Each cache entry maps a content sha to an output path.
The sha is computed over the source file and its template combined.
A missing template raises ValueError before the cache is consulted.

## Cache invalidation

A page is stale when its source sha or template sha has changed
since the last build. The cache entry is evicted and rebuilt.

## Display contract

The page list is sorted by path; the cache reports hits and misses
per build run as a two-line summary.

## Error handling

A missing source file raises FileNotFoundError before touching the cache.
The caller filters the source list before passing it to the build function.
