# RASP5 test data catalog

This directory contains the canonical inputs used by RASP5 automated checks,
manual regression tests, and literature-scale benchmarks. Analysis outputs do
not belong here; they are written under `runs/`.

## Directory layout

```text
data/
  benchmarks/
    psychotria/            Small core biogeography regression dataset
    primate/               Discrete and continuous trait dataset
    dore_ponerinae/        Large-tree, spatial, BGB and BSM benchmark
    kawahara_butterflies/  Literature-derived country/region reference data
  fixtures/
    region_builder/        Small deterministic Region Builder inputs
  spatial/
    base_layers/           Reusable lightweight polygon layers
  REFERENCE_SOURCES.md     Provenance and literature notes
```

## Canonical datasets

### Psychotria

Path: `data/benchmarks/psychotria/`

Primary use:

- DIVA and S-DIVA regression;
- DEC and S-DEC regression;
- BioGeoBEARS, S-BioGeoBEARS and model test smoke runs;
- BayArea, BBM and BayesTraits execution checks;
- Information/Time and node-identity checks.

Files:

| File | Purpose |
| --- | --- |
| `Psychotria.tree` | 19-tip reference tree used by the current regression tools |
| `distribution.csv` | Four-area taxon distribution matrix |
| `dataset.trees` | Tree collection for S-method tests |
| `coordinates.csv` | BayArea geographic coordinates |
| `timeperiods.txt` | Time-stratified DEC/BGB example |
| `geog_data.txt` | Legacy geographic input reference |
| `Tree_With_Polytomies.tre` | Polytomy fixture |
| `condensed.tre` | Legacy condensed-tree reference |

The canonical regression tree is the former `Psychotria测试数据` version. It
normalizes two internal support labels to 100 and is intentionally distinct
from the older user-facing tree under `examples/Psychotria/`.

### Primate

Path: `data/benchmarks/primate/`

Primary use:

- BayesTraits MultiState and Continuous tests;
- phytools and ape tests;
- mixed discrete/continuous matrix selection;
- log/log10 and back-transformed continuous-trait display;
- tree-set trait reconstruction.

The main inputs are under `Trees_States/`: `Primates.tree`, `100Trees.trees`,
and `characters.csv`. `Alignments/` and `Results/` are retained as associated
reference material, not as required inputs for every test.

### Dore Ponerinae

Path: `data/benchmarks/dore_ponerinae/`

Primary use:

- 789-tip and 1534-tip tree rendering;
- seven-area matrix import and BGB analysis;
- 149,541-occurrence point-in-polygon benchmark;
- Region Builder and seven-bioregion map tests;
- BioGeoBEARS BSM event/network validation.

Recommended files by task:

| Task | Files |
| --- | --- |
| Fast spatial UI test | `ponerinae_occurrences_subset_1000.csv` or `_5000.csv` |
| Full spatial benchmark | `ponerinae_occurrences_full_149k.csv` |
| Reconstruction matrix | `taxa_bioregions_7areas_matrix.csv` |
| Large tree | `final_inputs/Ponerinae_phylogeny_MCC_1534t.tree` |
| Smaller tree | `Ponerinae_MCC_phylogeny_789t.tree` |
| Study regions | `Ponerinae_7_bioregions.geojson` |
| Time-stratified inputs | adjacency, dispersal multiplier and time-boundary files |

The large posterior tree collection and curated source tables under
`final_inputs/` are local benchmark assets. They should not be copied into
normal source releases unless the repository adopts Git LFS or an external
data archive. BSM outputs remain under `runs/` until a fixed benchmark asset is
selected.

The Dore-derived RASP adjacency-path 1000-map BSM rebuild specification is
`dore_bsm_1000_benchmark_spec.json`. Validate its fixed inputs and generated
BioGeoBEARS files without starting the long analysis with:

```powershell
E:\Anaconda3\envs\RASP\python.exe tools\run_dore_bsm_benchmark.py --validate-only
```

Omit `--validate-only` to run the specified DEC+J fit and 1000 stochastic
maps. Generated results and their audit manifest are written to unique,
parameter-fingerprinted subdirectories below `runs/benchmarks/dore_bsm_1000/`
and are not source-controlled. The paper manually supplies period-specific
allowed-state lists, while this benchmark exercises RASP's adjacency-file
path; numerical equivalence is a separate WP5 requirement.

### Kawahara butterflies

Path: `data/benchmarks/kawahara_butterflies/`

Primary use:

- country-level range evidence;
- Region Builder mapping and rule validation;
- comparison with another seven-region literature workflow.

This is not currently a full reconstruction gold standard.

## Spatial fixtures

`data/spatial/base_layers/world_countries_simplified.geojson` is a small,
fast world-country layer for UI and point-in-polygon tests. Higher-resolution
Natural Earth runtime layers remain under `resources/spatial_base_layers/`.

`data/fixtures/region_builder/` contains deterministic rule and mapping files
for the simple demo, Dore and Kawahara presets. These files test the builder;
they are not official author-provided bioregion polygons.

## Data outside this directory

- `examples/Psychotria/` and `examples/Ebola/` are user-facing or supplementary
  examples, not canonical automated-test inputs.
- `Sample/` contains legacy RASP sample material and expected outputs used for
  historical comparison.
- `_reference_RASP/` is the old source/reference repository.
- `runs/` contains generated analyses, logs, caches and benchmark outputs.
- `engines/` contains bundled external runtimes, not test data.

## Maintenance rules

1. Test scripts should reference canonical paths under `data/` directly.
2. Do not scan the project root for similarly named datasets.
3. Do not store generated outputs in `data/`.
4. Keep one canonical copy of each regression input; document intentional
   variants explicitly.
5. Small deterministic fixtures may be committed normally. Large literature
   archives should use Git LFS or an external archive before public release.
6. A benchmark report must record the exact input path, application commit,
   engine version/hash, configuration and elapsed time.
