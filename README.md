# RASP5

RASP5 is a Windows desktop workbench for historical biogeography and ancestral
trait reconstruction. It connects phylogenetic trees, range or trait matrices,
occurrence records, spatial polygons, established analysis engines, normalized
ancestral-state results, and BioGeoBEARS stochastic-mapping events in one
auditable workflow.

The repository is under active development toward RASP5 5.0. The current code
is a feature-complete beta candidate, not a final public release. Scientific
results should be checked against the recorded engine output and the method's
own assumptions before publication.

## What is implemented

### Ancestral distribution reconstruction

- DIVA and S-DIVA through the RASP-modified DIVA executable.
- DEC and S-DEC through the RASP-patched `lagrange-ng` engine.
- BioGeoBEARS and S-BioGeoBEARS with DEC, DEC+J, DIVALIKE,
  DIVALIKE+J, BAYAREALIKE, and BAYAREALIKE+J.
- BioGeoBEARS six-model comparison and BSM event generation/loading.
- BayArea `DISTANCE_NORM` reconstruction; `INDEPENDENCE` is retained only as a
  compatibility mode and is not recommended.
- BBM through MrBayes.

### Trait reconstruction

- BayesTraits discrete and continuous model workflows.
- `ape` and `phytools` single-tree methods.
- S-phytools tree-set reconstruction.
- Continuous ancestral-state rendering and optional experimental presentation
  exports. DTT and publication-style A/B/C exports remain experimental.

### Spatial and event workflow

- Occurrence and polygon import with QA, taxon matching, and range encoding.
- Region GeoJSON Builder for template-based or user-defined regionalization.
- BSM event tables, event-through-time summaries, dispersal networks, circle
  layouts, and map-based network editing.
- Large-tree result rendering and export using the bundled vendor ETE3 code.

`Lineage Range Dynamics` is a sealed prototype and is intentionally absent from
the public menu. It is not part of the RASP5 5.0 release scope.

## Repository and engine bundle

RASP5 has separate source and engine layers:

1. This Git repository contains first-party Python/R wrapper source, fixtures,
   tests, documentation, engine patches, and release manifests.
2. A separately built Windows x64 engine bundle supplies external executables,
   the R runtime, and installed R packages under the expected `engines/` paths.
3. The Windows staging and Inno Setup workflow combines a source snapshot with
   the verified runtime and engine bundle. A same-host development installer
   has passed installation and engine smoke tests; clean-machine release gates
   remain open.

See [release/README.md](release/README.md) and
[release/THIRD_PARTY_ENGINES.md](release/THIRD_PARTY_ENGINES.md). A source clone
without the matching engine bundle cannot run all analyses.

## Development runtime

RASP5 5.0 freezes the validated Windows runtime at Python 3.6.13, PyQt5 5.15.4,
NumPy 1.19.2, and Matplotlib 3.3.4. This is a release-stabilization decision,
not a claim that Python 3.6 remains suitable for long-term maintenance. Runtime
migration is deferred until after the 5.0 release because it changes the native
Qt/ETE3 boundary and must be validated independently.

The reproducible development specification is
[`environment-windows-py36.yml`](environment-windows-py36.yml). ETE3 must not be
installed separately: RASP5 loads its bundled vendor copy from
`infrastructure/tree/backend/ete3_vendor`.

Start the application from the repository root:

```powershell
conda activate RASP
python -m app.main
```

The current validated local interpreter is Python 3.6.13. The GitHub source CI
uses a supported Python only for syntax, metadata, and dependency-free contract
checks; it does not replace Windows engine or GUI validation.

## Basic workflow

1. Load a reference/consensus tree or a tree collection.
2. Load a matrix containing binary geographic areas or trait columns.
3. Select the relevant column profile in the matrix.
4. Choose an analysis under **Ancestral Distribution Reconstruction** or
   **Trait Reconstruction**.
5. Review the method configuration, run log, native engine artifacts, and the
   normalized result view.
6. Generate or load BSM events separately when event-level inference is needed.
7. Export tables and figures together with the analysis run directory.

Each primary engine run writes `rasp5_provenance.json` before launching the
child process. It records the RASP5/runtime identity and the actual engine or
wrapper hashes, including whether they match the release manifest.

Spatial records and polygons are managed through **Spatial Data Manager**.
They can be used to construct a binary range matrix and to provide area names,
colors, centroids, and map geometry for event-network visualization.

## Validation

Run the dependency-free source gate:

```powershell
python tools/run_release_source_checks.py
```

On the validated Windows development machine, also run the public engine audit:

```powershell
python tools/build_engine_bundle.py audit --channel public
```

The authoritative task book and evidence reports are:

- [RASP5 task book](docs/RASP5_%E4%BB%BB%E5%8A%A1%E4%B9%A6_20260822.md)
- [WP1 test evidence](docs/WP1_%E6%B5%8B%E8%AF%95%E4%BA%8B%E5%AE%9E%E6%8A%A5%E5%91%8A_20260827.md)
- [WP2 numerical baselines](docs/WP2_%E5%8F%82%E6%95%B0%E4%BC%A0%E6%92%AD%E4%B8%8E%E6%95%B0%E5%80%BC%E5%9F%BA%E5%87%86_20260827.md)
- [WP5 spatial/BSM closure](docs/WP5_spatial_bsm_closure_20260828.md)

Compact regression datasets are organized under `data/benchmarks/` and
`data/fixtures/`. Runtime outputs belong under `runs/` and are intentionally not
versioned.

End-to-end GUI workflows are documented in:

- [Psychotria ancestral-range reconstruction](docs/tutorials/Psychotria_end_to_end.md)
- [BayArea DISTANCE NORM multi-chain convergence](docs/tutorials/BayArea_distance_norm_convergence.md)
- [Primate trait reconstruction](docs/tutorials/Primate_trait_end_to_end.md)
- [Dore Ponerinae spatial and BSM workflow](docs/tutorials/Dore_spatial_bsm_end_to_end.md)

## Scientific and software boundaries

RASP5 orchestrates and validates established engines; it does not claim that
their underlying DIVA, DEC, BioGeoBEARS, BayArea, BayesTraits, MrBayes, ape, or
phytools algorithms were invented by RASP5. Cite the original method and engine
papers appropriate to every analysis, in addition to RASP/RASP5.

The RASP5 first-party source is distributed under the MIT License. Bundled
engines and R packages retain their own licenses and attribution requirements;
the root license does not relicense them.

## Citation

Citation metadata is provided in [`CITATION.cff`](CITATION.cff). The current
author list and release metadata must be reviewed once more before the first
public 5.0 tag.
