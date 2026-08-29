# BSM event index performance

Date: 2026-08-29

## Scope

The benchmark uses the completed Dore Ponerinae DEC+J 1000-map result. Its raw
event inputs contain:

- 152,498 anagenetic rows (`bsm_ana_events.csv`, 46.8 MB);
- 4,074,000 cladogenetic rows (`bsm_clado_events.csv`, 1.083 GB);
- 1,685,498 normalized events;
- 152,775 distinct event times at the parser's six-decimal precision;
- 42 directed dispersal-network edges.

## Result

| Operation | Elapsed |
| --- | ---: |
| Previous full-service load | 199.372 s |
| Final v2 index build, including cache write | 199.501 s |
| Validated v2 index load | 1.340 s |

The persistent index is 19,961,929 bytes (19.04 MiB). The index-loaded result
retained exactly the same raw row counts, normalized event count, event-time
count, preview count, and 42 network edges. Comparing all 42 edges with
`bsm_dore_reference_edges.csv` produced zero missing routes, zero extra routes,
and a maximum absolute difference of 0.0 across anagenetic, founder, total, and
mean-per-map values.

An earlier v1 benchmark reported 3,299 time buckets because the cache builder
incorrectly rounded times to two decimal places. Review caught that scientific
regression before closure. Version 2 restores the parser's six-decimal behavior
and forces v1 caches to rebuild. The Phase 2 regression also verifies malformed
cache recovery, source-file invalidation, network input precedence, and a
single raw-table scan when legacy metadata is incomplete.

Each v2 index includes a SHA-256 over its complete derived-data payload. Cache
hits therefore validate both source signatures and internal index content; this
raises the warm-load time from the earlier 0.76-second prototype to about 1.35
seconds while preventing valid-looking but internally altered JSON from being
used silently.

The index is stored as `rasp5_bsm_event_index.json` beside the raw BSM files. It
may be deleted safely; RASP will rebuild it from the authoritative CSV inputs.
