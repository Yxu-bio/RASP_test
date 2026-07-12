# RASP5 release layout

RASP5 uses three release layers:

1. The Git repository contains application source, wrappers, reproducible
   engine patches, build documentation, and the engine manifest.
2. A GitHub Release contains a separately versioned Windows x64 engine bundle.
3. The final installer combines an application snapshot with a verified engine
   bundle without committing large runtime binaries to normal Git history.

The engine archive keeps the `engines/...` layout. Extracting it at the RASP5
repository or application root therefore installs the runtime paths expected by
the application.

## Commands

Run these commands with the RASP Python 3.6 environment:

```powershell
E:\Anaconda3\envs\RASP\python.exe tools\build_engine_bundle.py audit --channel public
E:\Anaconda3\envs\RASP\python.exe tools\build_engine_bundle.py build --channel internal
E:\Anaconda3\envs\RASP\python.exe tools\build_engine_bundle.py verify dist\RASP5-engine-bundle-2026.07.11-dev-windows-x86_64-internal.zip
```

Use `--channel internal` for local integration testing. Internal archives carry
an explicit warning file. Use `--channel public` only for a release candidate;
the builder rejects components whose redistribution status or license payload
is incomplete.

Every archive contains:

- `BUNDLE-MANIFEST.json`: bundle identity and component metadata.
- `SHA256SUMS.txt`: SHA256 for every archived payload file.
- `R_PACKAGE_INVENTORY.csv`: package name, version, license, and provenance for
  the bundled R libraries.
- `THIRD_PARTY_ENGINES.md` and license notices.
- reproducible patches and build notes for modified engines.

The builder excludes historical executable backups, caches, the BayArea nested
Git checkout, R installer uninstallers, and R's top-level development tests.
It does not remove installed R package files because the bundled BioGeoBEARS
and phytools dependency graph must remain intact.

## Public release checklist

1. Run `audit --channel public`.
2. Build with `build --channel public`.
3. Run `verify` on the resulting ZIP.
4. Smoke-test the extracted bundle in a clean application directory.
5. Confirm and add the intended RASP5 first-party project license before the
   first public source release; third-party engine licenses do not choose the
   license for RASP5's own Python and R wrapper code.
6. Publish the ZIP and its adjacent `.sha256` file as GitHub Release assets.
7. Publish the matching RASP5 source tag and retain the upstream source links
   and RASP patches listed in `THIRD_PARTY_ENGINES.md`.
8. Build the Windows installer from that exact source tag and verified bundle.

This repository does not currently create or publish the installer itself. The
bundle is the stable input boundary for a later installer definition.
