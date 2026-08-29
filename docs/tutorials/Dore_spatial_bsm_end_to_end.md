# Dore Ponerinae spatial and BSM workflow

This case checks a 1534-tip tree, seven biogeographic regions, spatial data, a
BioGeoBEARS reconstruction, stochastic maps, event tables, and a directed
dispersal network. It is intentionally much larger than the Psychotria case.

## Inputs

- Tree: `data/benchmarks/dore_ponerinae/final_inputs/Ponerinae_phylogeny_MCC_1534t.tree`
- Fixed seven-area range matrix:
  `data/benchmarks/dore_ponerinae/taxa_bioregions_7areas_matrix.csv`
- Region polygons:
  `data/benchmarks/dore_ponerinae/Ponerinae_7_bioregions.geojson`
- Optional occurrence preview:
  `data/benchmarks/dore_ponerinae/ponerinae_occurrences_subset_5000.csv`
- Formal benchmark specification:
  `data/benchmarks/dore_ponerinae/dore_bsm_1000_benchmark_spec.json`

The 5000-row occurrence file is a UI/performance preview. It must not replace
the fixed 1534-taxon range matrix in a paper-equivalent reconstruction.

## Spatial project check

1. Open **Spatial Data > Spatial Data Manager**.
2. Load the seven-region GeoJSON and confirm that seven named areas are shown.
3. Optionally load the 5000-row occurrence subset. Review Summary/QA and the
   audit table, then use **Show all** only when the full table is needed.
4. Select occurrence or area rows and confirm that the map highlights the
   selected feature. This tests spatial metadata and interaction; it does not
   rerun an ancestral reconstruction.

## Large-tree reconstruction

1. Open the 1534-tip tree and the fixed seven-area matrix from the paths above.
2. Wait for taxon matching to finish before opening an analysis configuration.
3. Select **Ancestral Distribution Reconstruction > On Consensus Tree >
   BioGeoBEARS**.
4. A short installation check may use DEC with simple settings, but it is not a
   reproduction of the Dore paper-rule analysis.
5. The fixed formal benchmark uses DEC+J, `max_range_size=5`, null range enabled,
   seven periods, seed 12345, and the per-period allowed-state rules documented
   in the benchmark specification. Those custom rules are validated by the
   benchmark tool and should not be replaced with an approximate GUI matrix.

Large-tree fitting can take substantial time. Keep the progress panel visible
and do not treat a responsive result window as evidence that an engine job has
finished.

## BSM events and network

1. After a BioGeoBEARS result is current, select **Biogeographic Event Analysis
   > Generate BioGeoBEARS BSM Events**.
2. Use a reduced map count only for workflow inspection. The fixed production
   benchmark uses 1000 maps and seed 12345.
3. Open **BSM Event Table Viewer**. Check raw/normalized event counts, Summary,
   Time, source-assignment method, and CSV export.
4. Open **BSM Network Map Editor**. Circle mode works from network data alone;
   map mode additionally uses the loaded seven-region spatial project.
5. Adjust edge filtering and width without changing the underlying edge table.
   Export edge and node CSV together with the figure.

The completed fixed benchmark has 1000/1000 maps, 42 directed network edges,
and exact agreement with BioGeoBEARS official source-area counts. Example mean
events per map include `I->U=88.905`, `I->E=49.978`, `U->I=41.444`,
`A->I=36.865`, and `N->R=16.319`.

## Exact benchmark validation for a source checkout

The paper-rule benchmark has a dedicated validation path because its period-
specific allowed-state lists are more specific than the normal GUI surface:

```powershell
python tools/run_dore_bsm_benchmark.py --validate-only
```

Running the complete 1000-map benchmark is a long production computation and is
not required for every installation smoke test. Its fixed evidence and caveats
are documented in `docs/WP5_spatial_bsm_closure_20260828.md`.

## Artifacts to retain

Keep the fitted BioGeoBEARS result, BSM event files, network edge/node tables,
configuration/seed, spatial project or GeoJSON, exports, and
`rasp5_provenance.json`. A network reconstructed with fallback fractional source
assignment must not be described as the official BioGeoBEARS unique-source
counting path.
