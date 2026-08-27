# Lineage Range Dynamics development record

## Current status

**Temporarily sealed on 2026-08-22.**

The result-window entry is not created, and the main window no longer feeds
spatial, matrix, tree, or BSM context into this module during normal use. The
implementation and its focused checks are retained for later redesign.

The switch is:

```python
LINEAGE_RANGE_DYNAMICS_ENABLED = False
```

in `gui/dialogs/result_view_window.py`.

This is an internal prototype, not a release-ready analysis method. It must
not be presented as inferred branch history unless the displayed data come
from actual stochastic maps.

## Why the module was proposed

The original product question was broader than a conventional ancestral-node
plot:

> At a selected time, which lineages are active, what ranges do they occupy,
> and how can the tree and geographic view be inspected together?

The interaction direction was informed by PhyloWood and Nextstrain, but this
code is not a wrapper or a direct clone of either project. The intended RASP5
workflow combined:

1. an ancestral-range reconstruction result;
2. a dated reference tree;
3. optional spatial area polygons or BayArea coordinates;
4. optional BioGeoBEARS BSM histories;
5. a time cursor shared by a tree and a map.

## Development history

### 1. Branch-time probability-field concept

The first concept attempted to draw complete multi-state probability curves
along every branch. It was rejected as a primary product direction because a
large tree became visually dense, difficult to navigate, and easy to
over-interpret. For methods that only estimate node states, the branch
interior was not model output.

### 2. Generic node interpolation

The prototype was narrowed to a playback view. For DIVA, DEC, S-methods,
BayArea, BBM, and other discrete range results, the code takes reconstructed
probabilities at the parent and child nodes and linearly interpolates them for
display.

This is explicitly a visualization approximation:

```text
parent node probabilities -> linear display interpolation -> child node probabilities
```

It does not infer the time or order of dispersal, extinction, or vicariance
events inside the branch.

### 3. BioGeoBEARS branch endpoints

When a BioGeoBEARS result contains branch-bottom and branch-top
probabilities, those model outputs replace generic parent/child endpoints.
The line drawn between them is still visual interpolation, not a stochastic
history.

### 4. BioGeoBEARS BSM integration

The prototype then gained support for actual BSM event tables. Anagenetic and
cladogenetic rows are mapped to display-tree branches and converted into
piecewise-constant state segments. Two BSM views are available internally:

- **BSM summary**: state frequencies across usable stochastic maps;
- **Single BSM map**: one sampled history and its event sequence.

The implementation checks clade overlap, branch coverage, map completeness,
and segment volume. Incomplete or incompatible BSM rows do not silently
become inferred histories.

### 5. Linked tree and map prototype

The UI added:

- a time slider and numeric time control;
- tree-wide, descendant-clade, full-continuum, and single-branch scopes;
- before-split and after-split node-boundary handling;
- branch selection and clade zoom;
- linked tree/map hover groups;
- map glyphs for expected active-lineage occupancy and clade contribution;
- frame-table and CSV export;
- limited large-tree fitting and vertical scrolling.

### 6. Reason for sealing

Manual evaluation showed that the feature boundary had become unclear:

- node interpolation, BGB endpoints, BSM summaries, and single BSM histories
  answer different scientific questions but appeared in one window;
- the map glyphs were hard to interpret and often added little for a small
  number of coarse discrete areas;
- selecting one branch segment did not initially match the user's need to
  inspect a biologically meaningful whole lineage or clade;
- large trees were visually weak and expensive to render;
- the module duplicated responsibilities belonging to Result View, Spatial
  Data Manager, BSM Events, and the BSM Network Map Editor;
- the visual polish and explanatory semantics were not release quality.

Hiding only the toolbar action was not considered sufficient. Normal result
opening now also skips construction and injection of this module's spatial,
matrix, BSM, and reference-tree context.

## Current data flow

The retained internal flow is:

```text
Ancestral reconstruction result
        + reference tree
        + tip range states
        + optional range matrix / area polygons
                         |
                         v
TemporalRangePlaybackService.build()
                         |
                         v
TemporalRangeResult
  - branches and node ages
  - endpoint probabilities
  - state-to-area membership
                         |
          optional BioGeoBEARS BSM result
                         |
                         v
BSMBranchHistoryService.attach()
  - sample IDs
  - branch state segments
  - sampling and coverage diagnostics
                         |
                         v
TemporalRangePlaybackService.frame(time, scope, mode)
                         |
              +----------+----------+
              |                     |
              v                     v
TemporalRangeTreeView       TemporalRangeMapView
```

## Retained source files

| Layer | File | Responsibility |
| --- | --- | --- |
| Domain | `domain/models/temporal_range_result.py` | Branch, history segment, frame, and timeline schemas |
| Service | `application/services/temporal_range_playback_service.py` | Build timelines, calculate frames, scopes, groups, marginals, and visual interpolation |
| Service | `application/services/bsm_branch_history_service.py` | Convert BioGeoBEARS BSM rows to branch state segments |
| Dialog | `gui/dialogs/temporal_range_playback_dialog.py` | Internal playback controls, linked panels, tables, warnings, and CSV export |
| Widget | `gui/widgets/temporal_range_tree_view.py` | Time-scaled interactive tree and branch/clade focus |
| Widget | `gui/widgets/temporal_range_map_view.py` | Area polygons, coordinate points, and lineage-group glyphs |
| Entry | `gui/dialogs/result_view_window.py` | Feature switch and formerly the result-toolbar entry |
| Integration | `gui/main_window.py` | Disabled context injection from the active project |
| Check | `tools/run_temporal_range_playback_checks.py` | Service, UI, semantics, export, and sealed-entry checks |
| Check | `tools/run_temporal_range_bsm_integration_check.py` | Real BSM-to-branch integration check |

## Scientific interpretation rules

These distinctions must remain visible if development resumes:

| Mode | What it displays | What it must not claim |
| --- | --- | --- |
| Node interpolation | Linear transition between reconstructed node probabilities | Inferred events or true branch-time probability |
| BGB endpoints | Branch-bottom and branch-top model probabilities plus visual interpolation | Exact within-branch history |
| BSM summary | Frequencies across sampled stochastic histories | One definitive history |
| Single BSM map | One sampled event history | Posterior consensus or uniquely inferred history |

At a cladogenetic node, before-split and after-split states may differ. They
must not be smoothed into one continuous state without an explicit display
rule.

## Known limitations

1. The product question is not narrow enough. Playback, event inspection,
   uncertainty comparison, and geographic animation should not automatically
   share one surface.
2. Generic interpolation is visually convenient but scientifically weak if
   users mistake it for inference.
3. State-to-area mapping depends on stable area codes across the result,
   matrix, and spatial project.
4. Coarse areas produce coarse map output; they cannot create a continuous
   spatial probability surface.
5. Large trees need level-of-detail rendering, clade collapsing, and stricter
   label policies before the tree view is useful.
6. BSM summary interaction is disabled above 500,000 reconstructed state
   segments; loading all histories is not the same as being able to render
   them interactively.
7. The current map glyph design has not demonstrated enough analytical value
   to justify its complexity.

## Conditions for resuming development

Do not simply set the switch to `True`. First make and document these product
decisions:

1. Define one primary user question, such as inspecting BSM histories through
   time, rather than supporting every ancestral method in one view.
2. Decide whether the release feature is BSM-only. This is the clearest
   scientifically defensible option.
3. Keep generic node interpolation, if retained, in a separately labelled
   visualization mode with an unavoidable approximation notice.
4. Specify the relationship with BSM Events, Spatial Data Manager, and BSM
   Network Map Editor so that each owns one part of the workflow.
5. Redesign large-tree navigation around clade selection and level of detail,
   not full-tree decoration.
6. Validate state/area identity with stable area codes before opening the map.
7. Establish a small gold-standard BSM fixture and a medium performance
   fixture before restoring a public action.
8. Perform manual scientific-interpretation testing, not only screenshot and
   widget tests.

After those decisions, reactivation requires both:

1. setting `LINEAGE_RANGE_DYNAMICS_ENABLED = True` in
   `gui/dialogs/result_view_window.py`;
2. retaining or revising the guarded context-injection block in
   `gui/main_window.py`.

## Internal verification

Use the project's Python environment and bundled vendor ETE3:

```powershell
E:\Anaconda3\envs\RASP\python.exe tools\run_temporal_range_playback_checks.py
E:\Anaconda3\envs\RASP\python.exe tools\run_temporal_range_bsm_integration_check.py E:\RASP\runs\biogeobears\RUN_NAME
```

The BSM integration command requires a run directory containing
`bgb_result.json` and a `bsm/` subdirectory. Its default acceptance threshold
is 100 complete maps. For a five-map Phase 0 smoke result, pass
`--minimum-maps 5`; that verifies integration only and is not a scientific
sampling standard.

The first check must confirm that the public Result View does not expose
`Lineage Range Dynamics`. The internal service, dialog, BSM conversion, and
export checks remain useful while the feature is sealed.

## Decision log

| Date | Decision |
| --- | --- |
| 2026-08-22 | Remove the Result View entry from normal use, stop normal context injection, retain code and focused checks, and require redesign before reactivation. |
