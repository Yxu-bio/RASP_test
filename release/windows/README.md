# RASP5 Windows packaging

The Windows release is assembled from three independently verified inputs:

1. the tagged RASP5 source snapshot described by
   `release/application-package.json`;
2. a root-level `conda-pack` archive of the frozen Python 3.6.13 runtime;
3. a public engine bundle produced by `tools/build_engine_bundle.py`.

The build deliberately does not install packaging tools into the validated
RASP runtime. Prepare `conda-pack` and Inno Setup 6 in a separate build
environment. The Simplified Chinese installer translation is pinned under
`release/windows/languages` because it is an unofficial file in the official
Inno Setup source repository and is not installed with every compiler build.

## 1. Validate source and engines

```powershell
python tools\run_release_source_checks.py --with-engine-audit
```

## 2. Build the public engine archive

```powershell
python tools\build_engine_bundle.py build --channel public
```

Keep the ZIP and adjacent SHA256 file. Do not substitute an internal bundle;
the staging tool rejects it.

## 3. Pack the Python runtime

Run `release/windows/build-python-runtime.ps1` from a build shell where
`conda-pack` is available. The archive must contain `python.exe`, `pythonw.exe`,
`Scripts/conda-unpack.exe`, and `Scripts/conda-unpack-script.py` at its root.
The build script excludes cached
bytecode so the ZIP does not contain duplicate `.pyc` entries generated under
different source-prefix layouts. It also regenerates
`release/PYTHON_RUNTIME_PACKAGES.csv` from the exact environment being packed;
review that inventory before staging.
Record the reviewed ZIP name and SHA256 in `release/application-package.json`;
the staging command rejects any runtime archive that does not match both values.

## 4. Stage the application

```powershell
python tools\stage_windows_release.py `
  --python-runtime dist\runtime\RASP5-python-3.6.13-windows-x86_64.zip `
  --engine-bundle dist\RASP5-engine-bundle-2026.08.28-dev-windows-x86_64-public.zip
```

The stage contains source payload, compact examples, Python runtime, engines,
launchers, `RASP5-APPLICATION-MANIFEST.json`, and
`RASP5-STAGE-CONTENT.json`. The latter hashes every pre-relocation file in the
stage. No developer-machine absolute path is written into runtime source.

Keep this stage pristine for Inno Setup. Relocation rewrites files in place, so
perform the verification on a disposable copy rather than on `StageDir` itself:

```powershell
$stage = "<stage>"
$verifyStage = "<disposable-verification-copy>"
python tools\verify_stage_content.py $stage
Copy-Item -LiteralPath $stage -Destination $verifyStage -Recurse
python tools\verify_stage_content.py $verifyStage
Set-Location -LiteralPath $verifyStage

.\runtime\python\python.exe -B .\runtime\python\Scripts\conda-unpack-script.py
$env:QT_QPA_PLATFORM = "offscreen"
.\runtime\python\python.exe -B .\tools\verify_windows_stage.py . --with-qt
```

Run the content verifier before relocation with a trusted build Python. Run the
installed verifier with the Python executable inside the relocated copy. The
two checks cover the complete immutable stage payload before relocation, the
pinned source runtime ZIP identity, live Python/NumPy/Matplotlib/PyQt versions,
core imports, bundled vendor ETE3, required engines, installed writable-data
policy, and absence of build-machine paths in the staged manifest. Delete the
disposable copy after recording the result.

## 5. Compile the installer

```powershell
python tools\build_windows_installer.py `
  --iscc "<path-to-ISCC.exe>" `
  --stage-dir "<pristine-stage-directory>" `
  --app-version "5.0.0-dev.0" `
  --output-dir "<installer-output-directory>"
```

This wrapper verifies `RASP5-STAGE-CONTENT.json` immediately before and after
Inno Setup reads the stage. If the stage changes during compilation, it discards
the installer. Otherwise it writes the installer SHA256 sidecar plus a
machine-readable build record that binds it to the stage content digest. Do not
compile the release installer by calling ISCC directly.

Inno Setup performs a per-user installation under
`%LOCALAPPDATA%\Programs\RASP5` by default and runs the bundled conda relocation
script through `python.exe -B` after copying files to the final directory.
The installer checks the relocation process exit code and creates the success
marker only after a zero exit code. A failure leaves an explicit failure marker,
suppresses automatic launch, and gives Setup a non-zero custom exit code; the
guarded launcher retries initialization on the next start.
Start-menu shortcuts also use `-B`, so normal launches do not leave generated
bytecode below the immutable application directory. Both shortcuts pass through
the guarded launchers, and a separate debug-console shortcut invokes
`python.exe`.

Application files and engines are treated as immutable after installation.
Analysis runs are written separately to `%LOCALAPPDATA%\RASP5\runs` by default;
`RASP5_DATA_HOME` can override this location. Source checkouts continue to use
their local `runs/` directory.

## Required clean-machine gate

Test on a Windows x64 machine without Conda, Python, R, or development tools:

- install under the default path;
- install under a path containing spaces and Chinese characters;
- launch, import Psychotria, and run one DIVA, DEC, and BioGeoBEARS analysis;
- open a result tree and export PNG/CSV;
- uninstall and confirm only user-created run outputs remain by policy;
- repeat after a clean reboot.

The installer is not release-ready until this gate has been executed and its
stage-content digest plus application, runtime-archive, engine, and installer
hashes are archived with the release record.
