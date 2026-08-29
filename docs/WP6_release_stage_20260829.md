# WP6 Windows release evidence (2026-08-29)

## Status

RASP5 now has a compiled per-user Windows installer and a completed same-host
install/run/uninstall cycle. The cycle used a path containing Chinese
characters and spaces, the installed Python runtime, and the engines copied by
the installer. This closes the local packaging implementation loop. The
installer is usable as a development or beta build. Before broad public
distribution, the matching source snapshot should be archived and the
installer should preferably be repeated on another Windows machine and by one
external user. Code signing is optional and is not a release blocker.

## Current package after BayArea convergence closure

The BayArea multi-chain benchmark, convergence diagnostics, and tutorial were
added after the same-host installation cycle below. A new stage and installer
were therefore built from the current workspace on 2026-08-29:

- Stage:
  `F:\RASP5_release\stage_current2_20260829_bayarea\RASP5-5.0.0-dev.0-windows-x86_64`
- Stage files: 23,893; total bytes: 1,598,643,039
- Stage content digest:
  `866A129EBE8AC1368868D349844090C20817055DA8601E5F6C701E476F6A8FFC`
- First-party manifest records: 644
- Installer:
  `F:\RASP5_release\installer_current2_20260829_bayarea\RASP5-5.0.0-dev.0-windows-x86_64-setup.exe`
- Installer size: 421,949,860 bytes
- Installer SHA256:
  `2D8E1F6F4991D5CC5CDD7E11B997024D53F90DB6075E23591FE2B31C93A4AAF9`

The stage content check passed before and after installer compilation, and the
installer build record contains the same stage digest. The packaged files
include `docs/tutorials/BayArea_distance_norm_convergence.md`,
`docs/bayarea_convergence_latest.md`, and `docs/bayarea-release-status.md`.
Source and installed copies of those files, the benchmark specification, the
BayArea parser, and the Tracer dialog were byte-identical.

The current installer was then tested at
`F:\RASP5_release\BayArea最终包终验 20260829\RASP5`. The installed verifier passed 644
first-party files, 16 critical engine files, the pinned Python runtime,
NumPy/Matplotlib/PyQt, vendor ETE3, bundled R, and an offscreen main window.
Installed DIVA, DEC, and BioGeoBEARS DEC each parsed 18 Psychotria internal
nodes with zero parser warnings. The installer and uninstaller both returned
zero. After uninstall, the application directory, its parent test directory,
HKCU uninstall key, Start Menu group, and desktop shortcut were absent.

- Install log:
  `F:\RASP5_release\bayarea_final_install_20260829.log`
- Installed analysis report:
  `runs/installed_release_smoke/20260829_bayarea_final/installed_release_smoke.json`
- Uninstall log:
  `F:\RASP5_release\bayarea_final_uninstall_20260829.log`

This current package is the one to use for the remaining another-machine and
external-user checks. The earlier evidence below records the packaging defects
that were found and fixed while establishing the same-host workflow.

## Frozen inputs

### Public engine bundle

- Path: `F:\RASP5_release\engine_final2_20260829\RASP5-engine-bundle-2026.08.28-dev-windows-x86_64-public.zip`
- Size: 314,698,975 bytes
- SHA256: `AC80CD47A8EED3FA8C5991C13E041460892F711CB7900C62F977B9A3D4FD27B5`
- Audit: 7 components, 16 critical files, 14,423 payload files,
  606,690,673 payload bytes, and 188 R-package inventory rows.

### Frozen Python runtime

- Path: `F:\RASP5_release\runtime_final_20260829\RASP5-python-3.6.13-windows-x86_64.zip`
- Size: 430,824,298 bytes
- SHA256: `E0C07978163B7405919E9EF5DD0CC6D0ADAFE8A7CE0FC5685BA2CF6B26407897`
- Inventory: 63 records; Python 3.6.13, PyQt5 5.15.4, NumPy 1.19.2,
  Matplotlib 3.3.4, and legacy SIP required by bundled ETE3.

### Pristine application stage

- Path: `F:\RASP5_release\stage_pristine_20260829_final6\RASP5-5.0.0-dev.0-windows-x86_64`
- Files: 23,890 total; `RASP5-STAGE-CONTENT.json` covers the other 23,889.
- Manifest-covered bytes: 1,598,596,199
- Aggregate stage content digest:
  `49B1605EA4DDCE8F73F15D288E613A327EF181D550B3031976F2095A5F7E34F0`
- First-party manifest records: 640
- Source commit recorded by the manifest:
  `a50296cae17e3f018d580b49557688fa75595eb7`
- Source dirty flag: `true`; this is therefore development evidence, not a
  reproducible release-tag artifact.

## Source and stage gates

- `tools/run_release_source_checks.py --with-engine-audit`: passed; 190
  first-party Python files compiled, the runtime/stage negative contracts passed,
  and no packaged workspace paths were found.
- Phase 0 smoke: all 8 tasks passed, including DIVA, S-DIVA, DEC, S-DEC,
  BioGeoBEARS DEC, six-model comparison, and five-map BSM. Evidence:
  `docs/phase0_smoke_latest.md`.
- Disposable stage path:
  `F:\RASP5_release\验证副本 20260829 final6`.
- Both the pristine stage and disposable copy passed the complete pre-relocation
  content check with the same aggregate digest above.
- Relocation used `python.exe -B conda-unpack-script.py`; no `__pycache__`
  directory was generated.
- Full staged verifier passed in that path: 640 first-party files, 16 critical
  engine files, 14,425 engine payload checksum records, 63 Python inventory
  records, pinned runtime ZIP SHA256, live Python/NumPy/Matplotlib/PyQt versions,
  vendor ETE3, bundled R standard libraries, and offscreen MainWindow.
- Installed-release analysis smoke passed DIVA, DEC, and BioGeoBEARS DEC with
  18 parsed nodes and zero parser warnings for each method.

## Installer evidence

- Installer:
  `F:\RASP5_release\installer_final_user4_20260829\RASP5-5.0.0-dev.0-windows-x86_64-setup.exe`
- Size: 421,886,093 bytes
- SHA256: `221D2391207D5EBB6E34923167703D5C7235C6A5ED20F851F90DF3414194A487`
- Adjacent `.sha256` and `.build.json`: generated and matched the installer;
  the build record binds it to stage digest `49B1605E...34F0`.
- Authenticode status: `NotSigned`.
- Install mode: per-user, no administrative privilege required.
- Test install path:
  `F:\RASP5_release\最终发布终验 20260829\RASP5`.
- Installation log:
  `runs/release_installer_user4_install_20260829_quoted.log`.
- Installed analysis report:
  `runs/installed_release_smoke/20260829_user4_final/installed_release_smoke.json`.
- Uninstallation log:
  `runs/release_installer_user4_uninstall_20260829.log`.
- Installation returned zero, created only the success relocation marker, and
  produced no `__pycache__` directories. Both Start Menu shortcuts targeted the
  guarded `RASP5.cmd` launchers.
- After uninstall, the application directory, its parent test directory, HKCU
  uninstall key, Start Menu group, and desktop shortcut were all absent.

## Release defects found and fixed

1. Relocated Qt reported an incorrectly decoded prefix in a Chinese path.
   Bootstrap now derives the plugin directories from the bundled PyQt package.
2. Windows R inherited POSIX locale variables such as `C.UTF-8`; under a
   non-ASCII install path this prevented loading R standard packages. Bundled R
   subprocesses now use a sanitized, deterministic environment and `--vanilla`.
3. The initial installer left conda-generated bytecode and its relocation
   marker after uninstall. Installer and launcher Python entry points now use
   `-B`, relocation invokes the script directly, and the marker is registered
   for uninstall deletion.
4. The original relocation entries did not bind marker creation to the child
   exit code, and shortcuts bypassed retry logic. Relocation now records success
   only for exit code zero; failures create a separate marker, suppress automatic
   launch, make Setup return code 20, and are retried by guarded shortcuts. A
   failure-injection installer verified return code 20, original child code 2,
   no success marker, and clean uninstall.
5. The runtime ZIP previously had no trusted expected hash and the installer was
   not bound to the stage that had been verified. The package manifest now pins
   runtime name/SHA256, staging writes a complete pre-relocation content
   manifest, and the installer builder verifies it before and after compilation,
   discarding an installer if the stage changes.
6. Bundled R subprocesses also clear inherited `R_LIBS`, `R_LIBS_SITE`, and
   `R_LIBS_USER`, including the phytools path where no explicit site library is
   supplied.

## Recommended before broad public distribution

1. Repeat the installer test on another Windows x64 machine without Conda, Python, R, or
   development tools, including the default `%LOCALAPPDATA%` path and reboot.
2. Complete the three GUI tutorials from the installer, including result-tree
   PNG/CSV export and large-result loading.
3. Obtain at least one independent external-user reproduction.
4. Archive the source that matches this installer as a commit/tag or source ZIP,
   together with the installer SHA256. The current `dirty=true` record only
   means that the build was made with uncommitted changes; it does not indicate
   a functional defect.
5. Keep the project license and third-party notices with the distribution and
   update them when bundled dependencies change. Code signing may be added later
   to reduce Windows unknown-publisher warnings.

The accurate project status remains **M1 feature-complete beta**, with the
same-host WP6 installer implementation complete and another-machine and
external-user validation still recommended before broad public distribution.
