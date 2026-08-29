# Changelog

All notable first-party RASP5 changes are recorded here. Third-party engine
versions and patches are tracked separately in `release/engine-bundle.json` and
`release/THIRD_PARTY_ENGINES.md`.

## [Unreleased]

### Added

- A unified RASP5 application version and release metadata.
- DIVA/S-DIVA, DEC/S-DEC, BioGeoBEARS/S-BioGeoBEARS, BayArea, BBM,
  BayesTraits, phytools, and S-phytools desktop workflows.
- Spatial occurrence/polygon QA, regionalization, range encoding, BSM event
  tables, and dispersal-network visualization.
- Fixed regression fixtures for Psychotria, Primate, Dore Ponerinae, and
  Kawahara butterflies.
- Reproducible engine-bundle manifest, checksums, upstream revisions, and patch
  documentation.
- Per-run application/runtime/engine provenance with executable and wrapper
  hashes for every primary analysis engine.
- Source CI/release gates, Windows staging and Inno Setup definitions, and
  Psychotria, Primate, and Dore end-to-end tutorials.

### Changed

- Replaced Python-side S-DIVA emulation with the modified DIVA config-mode
  workflow used by legacy RASP.
- Aligned S-series clade accounting and configuration semantics with the
  verified legacy behavior where appropriate.
- Patched `lagrange-ng` fixed-rate evaluate and per-period d/e propagation.
- Patched BayArea prior wiring and modern Windows build/runtime defects.
- Separated BSM generation/loading from ordinary result-tree rendering.

### Fixed

- Large-tree rendering, node identity, matrix profile selection, parameter
  propagation, and multiple long-running child-process lifecycle defects.
- BioGeoBEARS BSM source-area assignment and network aggregation now match the
  official BioGeoBEARS reference counts on the 1000-map Dore benchmark.

### Release status

- Version `5.0.0-dev.0` is a development beta candidate.
- `Lineage Range Dynamics`, DTT, and publication-style continuous-trait exports
  are not stable release methods.
- A per-user Windows development installer now passes same-host installation,
  Chinese/space-path relocation, DIVA/DEC/BioGeoBEARS smoke tests, and clean
  uninstall. Clean-machine and external-user acceptance, a clean source tag,
  signing, and final aggregate-license review remain required before a
  release-candidate tag.
