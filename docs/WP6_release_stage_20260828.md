# WP6 Windows release-stage evidence (2026-08-28)

## Status

RASP5 has reproducible Windows release inputs and a verified relocatable stage.
This is release-engineering evidence for the feature-complete beta; it is not a
Release Candidate claim. An Inno Setup installer, clean-machine installation,
uninstallation, and external-user acceptance remain pending.

## Source and regression gates

- `tools/run_release_source_checks.py --with-engine-audit`: passed.
- Public engine audit: 7 components, 15 critical files, 14,423 payload files,
  606,689,768 bytes, and 188 bundled R-package records cleared.
- Phase 0 smoke: all 8 tasks passed, including DIVA, S-DIVA (25 trees), DEC,
  S-DEC (25 trees), BioGeoBEARS DEC, six-model model test, and 5-map BSM.
  Evidence root: `E:\RASP\runs\phase0_smoke\20260828_200409`.
- WP4 trait regression (`--tree-count 3`): passed BayesTraits statistics and
  node routes, continuous Model A/B node reconstruction, phytools continuous
  methods, EB failure diagnosis, and S-phytools aggregation.
- The major engine entry points write `rasp5_provenance.json` with application,
  runtime, engine path/hash, and release-manifest match information.

## Built release inputs

### Public engine bundle

- Path: `F:\RASP5_release\engine\RASP5-engine-bundle-2026.08.28-dev-windows-x86_64-public.zip`
- Size: 314,698,506 bytes
- SHA256: `F722226730DC24D46C7F3ECAEADA4C5FCAF9BA3CEE18625ED1678A7FF41D2394`
- Archive verification: passed, 14,426 files including manifests.

### Frozen Python runtime

- Path: `F:\RASP5_release\runtime\RASP5-python-3.6.13-windows-x86_64.zip`
- Size: 589,383,638 bytes
- SHA256: `175247E78CFD19B188F30D747644D097907DF3221F5782E828B4FA4082B250E0`
- Archive verification: 9,380 entries, no duplicate names, no cached `.pyc` or
  `.pyo` entries, and root-level `python.exe`, `pythonw.exe`, and
  `Scripts/conda-unpack.exe` present.

### Pristine installer stage

- Path: `F:\RASP5_release\stage_pristine_20260828\RASP5-5.0.0-dev.0-windows-x86_64`
- Files: 24,462
- Uncompressed bytes: 1,757,987,383
- The stage is intentionally not passed through `conda-unpack`; it remains a
  pristine input for Inno Setup, which relocates the runtime after installation.
- `RASP5-APPLICATION-MANIFEST.json` records archive names and hashes without
  build-machine absolute paths.

## Relocation and GUI verification

A separate disposable stage was relocated and checked with its own bundled
Python runtime. The verifier used an isolated temporary `RASP5_DATA_HOME`, so
GUI startup could not clean or modify real user run directories.

Verified facts:

- application `5.0.0-dev.0`;
- Python `3.6.13` from the staged runtime;
- NumPy `1.19.2`, Matplotlib `3.3.4`, and PyQt5 loaded;
- bundled vendor ETE3 loaded through the same bootstrap path as the application;
- all 7 required engine entry points present;
- installed runs resolve to `%LOCALAPPDATA%\RASP5\runs`, outside program files;
- offscreen `MainWindow` construction and close passed;
- staged manifest contained zero absolute build-machine paths.

## Remaining release blockers

1. Compile the Inno Setup installer. Inno Setup is not installed on the current
   build machine, so no setup executable exists yet.
2. On clean Windows x64 machines without Python, Conda, or R, test default,
   space-containing, and Chinese-character install paths.
3. Run DIVA, DEC, BioGeoBEARS, result rendering, PNG/CSV export, and uninstall
   checks from the installed application.
4. Re-run all three end-to-end tutorials from the installer.
5. Obtain at least one independent external-user reproduction before M2.

Until these are complete, the correct status is **M1 feature-complete beta with
WP6 release engineering in progress**, not Release Candidate.
