"""Verify a staged RASP5 Windows application using the staged Python runtime."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath


STAGE_MANIFEST = "RASP5-APPLICATION-MANIFEST.json"
REQUIRED_ENGINES = (
    "engines/diva/DIVA.exe",
    "engines/lagrange-ng/lagrange-ng.exe",
    "engines/bayarea/bin/bayarea.exe",
    "engines/bayestraits/BayesTraitsV5.exe",
    "engines/mrbayes/mb.3.2.7-win32.exe",
    "engines/R/bin/Rscript.exe",
    "engines/biogeobears/bgb_runner.R",
)
CHUNK_SIZE = 1024 * 1024


def _assert_within(path, root, label):
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise AssertionError("%s is outside the stage: %s" % (label, path))


def _is_within(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def _stage_path(stage, relative, label):
    value = str(relative or "").replace("\\", "/")
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or re.match(r"^[A-Za-z]:", value)
        or value.startswith("//")
    ):
        raise AssertionError("Unsafe %s path: %s" % (label, value))
    target = stage.joinpath(*path.parts)
    _assert_within(target, stage, label)
    return target


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _critical_fingerprints(manifest):
    result = {}
    for item in list(manifest.get("critical_files", []) or []):
        relative = str(item.get("path", "") or "").replace("\\", "/")
        if not relative or relative in result:
            raise AssertionError("Invalid or duplicate critical engine path: %s" % relative)
        result[relative] = (
            int(item.get("size", 0) or 0),
            str(item.get("sha256", "") or "").upper(),
        )
    if not result:
        raise AssertionError("Engine manifest has no critical files")
    return result


def _verify_records(stage, records, label):
    seen = set()
    for item in list(records or []):
        relative = str(item.get("path", "") or "").replace("\\", "/")
        if relative in seen:
            raise AssertionError("Duplicate %s path: %s" % (label, relative))
        seen.add(relative)
        target = _stage_path(stage, relative, label)
        if not target.is_file():
            raise AssertionError("Missing %s file: %s" % (label, relative))
        expected_size = int(item.get("size", -1))
        if target.stat().st_size != expected_size:
            raise AssertionError("%s size mismatch: %s" % (label, relative))
        expected_hash = str(item.get("sha256", "") or "").upper()
        if not re.match(r"^[0-9A-F]{64}$", expected_hash):
            raise AssertionError("Invalid %s SHA256: %s" % (label, relative))
        if _sha256_file(target) != expected_hash:
            raise AssertionError("%s SHA256 mismatch: %s" % (label, relative))
    return len(seen)


def _verify_engine_payload(stage, stage_manifest):
    bundle_manifest_path = stage / "BUNDLE-MANIFEST.json"
    release_manifest_path = stage / "release" / "engine-bundle.json"
    checksum_path = stage / "SHA256SUMS.txt"
    for path in (bundle_manifest_path, release_manifest_path, checksum_path):
        if not path.is_file():
            raise AssertionError("Stage is missing engine metadata: %s" % path.name)

    bundle_manifest = _load_json(bundle_manifest_path)
    release_manifest = _load_json(release_manifest_path)
    stage_engine = dict(stage_manifest.get("engine_bundle", {}) or {})
    if bundle_manifest.get("channel") != "public":
        raise AssertionError("Staged engine bundle is not a public bundle")
    for key in ("bundle_version", "platform"):
        if release_manifest.get(key) != bundle_manifest.get(key):
            raise AssertionError("Engine manifest %s mismatch" % key)

    release_hash = _sha256_file(release_manifest_path)
    if release_hash != str(stage_engine.get("release_manifest_sha256", "")).upper():
        raise AssertionError("Staged release engine manifest SHA256 mismatch")

    release_critical = _critical_fingerprints(release_manifest)
    bundle_critical = _critical_fingerprints(bundle_manifest)
    if release_critical != bundle_critical:
        raise AssertionError("Release and bundled critical engine fingerprints differ")
    if int(stage_engine.get("critical_files", -1)) != len(bundle_critical):
        raise AssertionError("Stage manifest critical engine count mismatch")
    critical_records = [
        {"path": path, "size": values[0], "sha256": values[1]}
        for path, values in sorted(bundle_critical.items())
    ]
    critical_count = _verify_records(stage, critical_records, "critical engine")

    checksum_records = []
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError:
            raise AssertionError("Malformed engine checksum line: %s" % line)
        target = _stage_path(stage, relative, "engine payload")
        if not target.is_file():
            raise AssertionError("Missing engine payload file: %s" % relative)
        checksum_records.append(
            {"path": relative, "size": target.stat().st_size, "sha256": digest}
        )
    payload_count = _verify_records(stage, checksum_records, "engine payload")
    return critical_count, payload_count


def _verify_runtime_inventory(stage):
    path = stage / "release" / "PYTHON_RUNTIME_PACKAGES.csv"
    if not path.is_file():
        raise AssertionError("Stage is missing the Python runtime package inventory")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise AssertionError("Python runtime package inventory is empty")
    identities = {}
    for row in rows:
        package = str(row.get("package", "")).lower()
        version = str(row.get("version", ""))
        if package and version:
            identities.setdefault(package, set()).add(version)
    required = (("python", "3.6.13"), ("numpy", "1.19.2"), ("pyqt5", "5.15.4"))
    missing = [
        "%s %s" % item
        for item in required
        if item[1] not in identities.get(item[0], set())
    ]
    if missing:
        raise AssertionError(
            "Python runtime inventory lacks frozen packages: %s" % ", ".join(missing)
        )
    return len(rows), identities


def _verify_runtime_archive_identity(stage, stage_manifest):
    package = _load_json(stage / "release" / "application-package.json")
    expected = dict(package.get("python_runtime", {}) or {})
    staged = dict(stage_manifest.get("python_runtime", {}) or {})
    for key in ("archive_name", "sha256"):
        if str(staged.get(key, "")).upper() != str(expected.get(key, "")).upper():
            raise AssertionError("Staged Python runtime %s differs from release manifest" % key)
    if len(str(expected.get("sha256", "") or "")) != 64:
        raise AssertionError("Release manifest has no trusted Python runtime SHA256")
    return str(expected["sha256"]).upper()


def _verify_live_runtime_versions(identities, numpy, matplotlib, pyqt_version):
    actual = {
        "python": sys.version.split()[0],
        "numpy": str(numpy.__version__),
        "matplotlib": str(matplotlib.__version__),
        "pyqt5": str(pyqt_version),
    }
    for package, version in actual.items():
        if version not in identities.get(package, set()):
            raise AssertionError(
                "Live %s version %s differs from the frozen runtime inventory"
                % (package, version)
            )
    return actual


def _verify_r_runtime(stage):
    from infrastructure.r_runtime_environment import build_r_subprocess_environment

    rscript = stage / "engines" / "R" / "bin" / "Rscript.exe"
    site_library = stage / "engines" / "R" / "site-library"
    expression = (
        'loadNamespace("compiler"); loadNamespace("utils"); '
        'stopifnot(grepl("/engines/R$", normalizePath(R.home(), winslash="/", mustWork=TRUE), '
        'ignore.case=TRUE)); '
        'cat("R_RUNTIME_OK\\n")'
    )
    proc = subprocess.run(
        [str(rscript), "--vanilla", "-e", expression],
        cwd=str(stage),
        env=build_r_subprocess_environment(site_library),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0 or "R_RUNTIME_OK" not in stdout:
        raise AssertionError(
            "Bundled R runtime self-check failed: %s"
            % ((stderr.strip() or stdout.strip())[:1000])
        )
    return "passed"


def _manifest_absolute_paths(value, prefix=""):
    hits = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = "%s.%s" % (prefix, key) if prefix else str(key)
            hits.extend(_manifest_absolute_paths(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_manifest_absolute_paths(child, "%s[%d]" % (prefix, index)))
    elif isinstance(value, str):
        if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\"):
            hits.append("%s=%s" % (prefix, value))
    return hits


def verify(stage_dir, with_qt=False):
    stage = Path(stage_dir).resolve()
    if not stage.is_dir():
        raise AssertionError("Stage directory does not exist: %s" % stage)
    _assert_within(Path(sys.executable), stage, "Python executable")

    sys.path.insert(0, str(stage))
    from app.bootstrap import ApplicationBootstrap
    from app.paths import ApplicationPaths
    from app.version import DISPLAY_VERSION

    bootstrap = ApplicationBootstrap()
    bootstrap.inject_conda_dll_paths()
    bootstrap.inject_vendor_packages()
    bootstrap.configure_qt_paths()
    bootstrap.validate_ete3_import()

    manifest_path = stage / STAGE_MANIFEST
    manifest = _load_json(manifest_path)
    if manifest.get("application_version") != DISPLAY_VERSION:
        raise AssertionError("Stage manifest version does not match app.version")
    absolute_paths = _manifest_absolute_paths(manifest)
    if absolute_paths:
        raise AssertionError(
            "Stage manifest contains build-machine absolute paths: %s"
            % ", ".join(absolute_paths[:10])
        )

    first_party_count = _verify_records(
        stage,
        manifest.get("first_party_files", []),
        "first-party",
    )
    critical_engine_count, engine_payload_count = _verify_engine_payload(stage, manifest)
    runtime_archive_sha256 = _verify_runtime_archive_identity(stage, manifest)
    runtime_inventory_count, runtime_identities = _verify_runtime_inventory(stage)

    missing_engines = [name for name in REQUIRED_ENGINES if not (stage / name).is_file()]
    if missing_engines:
        raise AssertionError("Stage is missing engines: %s" % ", ".join(missing_engines))

    r_runtime_status = _verify_r_runtime(stage)

    import numpy
    import matplotlib
    import PyQt5
    from PyQt5.QtCore import PYQT_VERSION_STR
    import ete3

    live_runtime = _verify_live_runtime_versions(
        runtime_identities,
        numpy,
        matplotlib,
        PYQT_VERSION_STR,
    )

    expected_vendor = (
        stage / "infrastructure" / "tree" / "backend" / "ete3_vendor"
    ).resolve()
    ete3_path = Path(ete3.__file__).resolve()
    if not _is_within(ete3_path, expected_vendor):
        raise AssertionError("ETE3 was not loaded from the bundled vendor directory")

    previous_data_home = os.environ.get("RASP5_DATA_HOME")
    previous_local_app_data = os.environ.get("LOCALAPPDATA")
    previous_qt_platform = os.environ.get("QT_QPA_PLATFORM")
    qt_status = "not requested"
    isolated_data_root = ""
    try:
        with tempfile.TemporaryDirectory(prefix="rasp5-stage-data-") as isolated:
            isolated = Path(isolated)
            local_app_data = isolated / "local-app-data"
            os.environ.pop("RASP5_DATA_HOME", None)
            os.environ["LOCALAPPDATA"] = str(local_app_data)
            paths = ApplicationPaths.discover(stage)
            expected_data_root = (local_app_data / "RASP5").resolve()
            if paths.data_root != expected_data_root:
                raise AssertionError("Installed stage did not use isolated LOCALAPPDATA")
            if _is_within(paths.data_root, stage):
                raise AssertionError("Installed stage would write analysis runs into Program Files")
            isolated_data_root = str(paths.data_root)

            if with_qt:
                os.environ["QT_QPA_PLATFORM"] = "offscreen"
                qt_data_home = isolated / "qt-data"
                os.environ["RASP5_DATA_HOME"] = str(qt_data_home)
                bootstrap.configure_qt_paths()
                from PyQt5.QtWidgets import QApplication
                from gui.main_window import MainWindow

                app = QApplication.instance() or QApplication([])
                window = MainWindow()
                window.close()
                window.deleteLater()
                app.processEvents()
                qt_status = "passed"
    finally:
        if previous_data_home is None:
            os.environ.pop("RASP5_DATA_HOME", None)
        else:
            os.environ["RASP5_DATA_HOME"] = previous_data_home
        if previous_local_app_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = previous_local_app_data
        if previous_qt_platform is None:
            os.environ.pop("QT_QPA_PLATFORM", None)
        else:
            os.environ["QT_QPA_PLATFORM"] = previous_qt_platform

    return {
        "application_version": DISPLAY_VERSION,
        "python": live_runtime["python"],
        "python_executable": str(Path(sys.executable).resolve()),
        "numpy": live_runtime["numpy"],
        "matplotlib": live_runtime["matplotlib"],
        "pyqt5": live_runtime["pyqt5"],
        "pyqt5_loaded": bool(PyQt5),
        "vendor_ete3_loaded": bool(ete3),
        "vendor_ete3_path": str(ete3_path),
        "required_engines": len(REQUIRED_ENGINES),
        "first_party_files_verified": first_party_count,
        "critical_engine_files_verified": critical_engine_count,
        "engine_payload_files_verified": engine_payload_count,
        "runtime_inventory_records": runtime_inventory_count,
        "runtime_archive_sha256": runtime_archive_sha256,
        "r_runtime": r_runtime_status,
        "installed_data_policy": "%LOCALAPPDATA%\\RASP5",
        "isolated_data_root": isolated_data_root,
        "qt_main_window": qt_status,
        "manifest_absolute_paths": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage_dir")
    parser.add_argument("--with-qt", action="store_true")
    args = parser.parse_args()
    result = verify(args.stage_dir, with_qt=args.with_qt)
    print(json.dumps(result, indent=2, sort_keys=True))
    print("RASP5 Windows stage verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
