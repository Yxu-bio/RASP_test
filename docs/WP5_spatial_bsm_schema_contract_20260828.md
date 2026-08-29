# RASP5 WP5 Spatial and BSM contract

Date: 2026-08-28

This document freezes the data contracts used between spatial encoding,
BioGeoBEARS stochastic mapping, event summaries, and network visualization.
It describes persisted data and scientific counting semantics; it is not a UI
specification.

## 1. Versioned persisted formats

| Artifact | `format` | Version |
| --- | --- | ---: |
| Spatial Project JSON | `rasp5_spatial_data_project` | 1 |
| Region Builder config JSON | `rasp5_region_builder_config` | 1 |
| Region Builder GeoJSON metadata | `rasp5_region_builder_geojson` | 1 |
| BioGeoBEARS BSM summary JSON | `rasp5_biogeobears_bsm_summary` | 1 |
| BioGeoBEARS BSM event index | `rasp5_biogeobears_bsm_event_index` | 2 |
| Normalized BSM event result | `rasp5_biogeobears_bsm_events` | 1 |
| BSM dispersal network | `rasp5_bsm_dispersal_network` | 1 |
| BSM network layout JSON | `rasp5_bsm_network_layout` | 2 |

Readers accept legacy files that omit a format/version only where RASP5
already produced such files. An explicit unknown format or version is rejected;
it is never silently interpreted as the current schema.

## 2. Spatial encoding contract

Inputs are WGS84 occurrence coordinates and Polygon/MultiPolygon area features.
The encoder supports polygon holes and antimeridian-crossing polygons. For each
valid occurrence row it writes exactly one audit row with one of these statuses:

- `matched`: one area contains the point;
- `multi_area`: more than one area contains the point;
- `unmatched`: no area contains the point.

The binary range matrix is aggregated by taxon after point-to-polygon matching.
Repeating the same input, area order, and minimum-record threshold must produce
the same matrix rows and audit rows. Spatial polygons and centroids do not alter
ancestral reconstruction or BSM event counts; they only provide area metadata
and map coordinates.

## 3. BSM event completeness contract

Small runs are loaded completely. A large run is streamed through all raw CSV
rows once to calculate full event counts, route counts, sample counts,
event-through-time totals, preview rows, and network edges. These derived values
are persisted beside the source tables as `rasp5_bsm_event_index.json`. Later
loads read the index and do not rescan the large CSVs. The GUI retains at most
`event_preview_limit` event and raw rows per event stream for interaction.
Event times use the same six-decimal rounding as the standard BSM parser; the
index must not coarsen them into wider display bins.

The index is a disposable performance cache, not a replacement for the raw BSM
tables. It records the size, modification time, and sampled-content SHA-256 of
every source table that affects the result. A missing, malformed, version-mismatched,
or stale index is rebuilt from the source CSVs. New RASP BSM runs build it before
returning the result; imported legacy runs build it on their first RASP load.
The complete derived-data payload also has its own SHA-256, so internally altered
but syntactically valid cache JSON is rejected.

The result records:

- `event_row_counts`: source rows per stream;
- `events_complete` / `raw_tables_complete`;
- `summary.normalized_event_count`;
- `summary.event_preview_count` and `event_preview_counts`.
- `summary.load_index_status` (`hit`, `rebuilt`, or `rebuilt_not_saved`).

With an incomplete preview and no event filters, Summary and Time use the full
streamed aggregates. Event-table CSV exports contain the visible preview and
identify it with `data_scope=unfiltered_preview_event_table`. Time CSV exports
use `data_scope=full_scan_event_aggregate`. Applying an event filter to an
incomplete result is explicitly a preview-only operation.

## 4. Dispersal network metrics

For each directed source-target pair:

- `anagenetic_count`: anagenetic `d`/`a` event count across all maps;
- `founder_count`: cladogenetic founder-event (`j`) count across all maps;
- `total_count = anagenetic_count + founder_count`;
- `mean_per_map = total_count / nummaps`;
- `mean_per_map_per_source_richness = mean_per_map / source tip richness`;
- `mean_per_map_per_target_richness = mean_per_map / target tip richness`.

New RASP-generated BSM results follow the BioGeoBEARS/Dore source-routing
workflow. `BioGeoBEARS::simulate_source_areas_ana_clado()` probabilistically
chooses one source area for each dispersal from a multi-area range. The selected
sources are stored in `ana_dispersal_from` and `clado_dispersal_from`, and the
network records `source_assignment_method=biogeobears_probabilistic_unique_source`
plus the source-assignment seed.

For large legacy runs, source assignment may be added without rewriting the
large raw event CSVs. The selected dispersal events are then stored in
`bsm_source_assigned_dispersal_events.csv`; this compact table is authoritative
for network aggregation, while the original CSVs remain authoritative for
event-detail and Time views. Its presence is authoritative even when it contains
zero event rows; an empty compact table must not fall back to fractional routing.
If final RData tables already contain source columns, postprocessing reuses them
instead of drawing a second set of source assignments.

Network-edge inputs have one explicit precedence order: the compact unique-source
table, then an existing precomputed edge table, then raw-event fractional
fallback. A lower-priority source must never overwrite a higher-priority table.
Availability is recorded separately from row count, so an authoritative empty
table produces an empty network instead of falling back to preview rows.

Legacy or externally supplied event tables may omit those two fields. Such
tables remain readable: one event is then divided equally among candidate
source areas and is explicitly marked
`source_assignment_method=fractional_equal_split_fallback`. Mixed inputs are
marked `mixed_unique_and_fractional_fallback`; the fallback is never presented
as a Dore-equivalent count.

The display threshold is always applied to `mean_per_map`; percentile filtering
is a separate visualization control. Anagenetic/founder toggles recalculate
counts both from raw events and from precomputed edge tables.

Circle and Map layouts consume the same statistical edge table. Loading spatial
area metadata may add centroids and GeoJSON features but cannot change edge
counts, normalization, ordering, or the threshold decision.

## 5. Network reconstruction assets

A reconstructable network export consists of:

1. all edge rows CSV;
2. node rows CSV with area code and richness;
3. layout JSON v2 containing layout mode, projection, controls, network schema
   reference, edge keys, and manual curve/label geometry.

The layout loader validates its own schema, restores controls before rebuilding
the network, then reapplies manual geometry by stable `source->target` edge key.

## 6. Dore Ponerinae paper-equivalent state path

Dore et al. use each adjacency matrix to derive a custom list of allowed ranges.
Their higher-range rule is broader than BioGeoBEARS native clique-based
adjacency pruning. The seven expected state counts are:

`36, 36, 27, 20, 24, 20, 38`.

The paper then sets `areas_adjacency_fn = NA` and assigns only
`lists_of_states_lists_0based`. Therefore the RASP benchmark sets
`period_state_lists_only=true`: the adjacency file remains an auditable input,
but the runner does not apply native adjacency pruning a second time.

The generated LagrangePHYLIP geography header includes the explicit ordered area
tokens: `1534 7 (A U I R N E W)`. Every time-stratified matrix file ends with
`END`, so all seven periods are read.

## 7. Regression evidence

- `tools/run_wp5_spatial_bsm_checks.py`
- `tools/run_phase2_spatial_checks.py` (index hit and invalidation contract)
- `runs/wp5_spatial_bsm_checks/wp5_check_report.json`
- `tools/run_phase1_spatial_benchmark.py`
- `runs/phase1_spatial_benchmark/full_149k_world_countries/summary.json`
- `tools/audit_dore_allowed_states.R`
- `tools/postprocess_bsm_source_areas.R`
- `docs/bsm_event_index_performance_latest.md`

The WP5 gate covers deterministic complex-polygon encoding, explicit schema
rejection, Dore state-list equivalence, large-event preview/full accounting,
network metric semantics, Event/Time CSV scope, and Circle/Map layout recovery.
It also verifies that unique-source event tables reproduce
`BioGeoBEARS::count_ana_clado_events()` exactly and that legacy tables retain the
explicit fractional fallback behavior.
