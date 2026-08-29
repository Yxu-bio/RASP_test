"""Dependency-free source and release-metadata checks for RASP5 CI."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace


FIRST_PARTY_ROOTS = (
    "app",
    "application",
    "domain",
    "gui",
    "infrastructure",
    "tools",
    "visualization",
)
RUNTIME_ROOTS = (
    "app",
    "application",
    "domain",
    "gui",
    "infrastructure",
    "visualization",
)
REQUIRED_RELEASE_FILES = (
    "README.md",
    "LICENSE",
    "CITATION.cff",
    "CHANGELOG.md",
    "environment-windows-py36.yml",
    "release/README.md",
    "release/THIRD_PARTY_ENGINES.md",
    "release/THIRD_PARTY_PYTHON.md",
    "release/PYTHON_RUNTIME_PACKAGES.csv",
    "release/engine-bundle.json",
    "release/application-package.json",
    "release/windows/RASP5.iss",
    "release/windows/README.md",
    "infrastructure/tree/backend/ete3_vendor/COPYING",
    "infrastructure/tree/backend/ete3_vendor/NOTICE.md",
)
TEXT_SUFFIXES = frozenset(
    (".cmd", ".iss", ".json", ".md", ".ps1", ".py", ".r", ".txt", ".yaml", ".yml")
)


def repository_root():
    return Path(__file__).resolve().parents[1]


def compile_first_party(root):
    files = []
    for folder in FIRST_PARTY_ROOTS:
        for path in (root / folder).rglob("*.py"):
            if "ete3_vendor" in path.parts:
                continue
            files.append(path)
    for path in sorted(set(files), key=lambda item: str(item).lower()):
        py_compile.compile(str(path), doraise=True)
    return len(files)


def validate_json_files(root):
    files = []
    for folder in ("data", "release"):
        base = root / folder
        if not base.exists():
            continue
        files.extend(base.rglob("*.json"))
    for path in sorted(set(files), key=lambda item: str(item).lower()):
        with path.open("r", encoding="utf-8-sig") as handle:
            json.load(handle)
    return len(files)


def validate_release_identity(root):
    missing = [name for name in REQUIRED_RELEASE_FILES if not (root / name).is_file()]
    if missing:
        raise AssertionError("Missing release files: %s" % ", ".join(missing))

    sys.path.insert(0, str(root))
    from app.version import DISPLAY_VERSION, __version__

    if __version__ != "5.0.0.dev0" or DISPLAY_VERSION != "5.0.0-dev.0":
        raise AssertionError(
            "Unexpected application version: %s / %s" % (__version__, DISPLAY_VERSION)
        )
    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    if 'version: "%s"' % DISPLAY_VERSION not in citation:
        raise AssertionError("CITATION.cff version does not match app/version.py")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if DISPLAY_VERSION not in changelog:
        raise AssertionError("CHANGELOG.md does not identify the current development version")

    manifest = json.loads(
        (root / "release" / "engine-bundle.json").read_text(encoding="utf-8")
    )
    if manifest.get("schema_version") != 1:
        raise AssertionError("Unsupported engine manifest schema")
    components = list(manifest.get("components", []) or [])
    if not components:
        raise AssertionError("Engine manifest has no components")
    for component in components:
        if not component.get("id") or not component.get("upstream"):
            raise AssertionError("Engine component lacks identity/upstream: %r" % component)
        if component.get("redistribution_status") != "cleared":
            raise AssertionError("Engine component is not cleared: %s" % component.get("id"))
        if not component.get("first_party") and not component.get("license_files"):
            raise AssertionError(
                "Third-party engine lacks bundled license: %s" % component.get("id")
            )
    application_package = json.loads(
        (root / "release" / "application-package.json").read_text(encoding="utf-8")
    )
    if application_package.get("application_version") != DISPLAY_VERSION:
        raise AssertionError("Application package version does not match app/version.py")
    return len(components)


def validate_python_runtime_inventory(root):
    path = root / "release" / "PYTHON_RUNTIME_PACKAGES.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    required_fields = {
        "record_type",
        "package",
        "version",
        "build",
        "channel_or_home_page",
        "license",
        "metadata_path",
    }
    if set(fields) != required_fields or len(rows) < 10:
        raise AssertionError("Python runtime package inventory is incomplete")
    record_types = set(row["record_type"] for row in rows)
    if record_types != {"conda-package", "python-distribution"}:
        raise AssertionError("Python runtime inventory record types are incomplete")
    for row in rows:
        metadata_path = str(row.get("metadata_path", "") or "")
        if re.match(r"^[A-Za-z]:[\\/]", metadata_path) or metadata_path.startswith("\\\\"):
            raise AssertionError("Runtime inventory leaks an absolute metadata path")
        if not row.get("package") or not row.get("version") or not row.get("license"):
            raise AssertionError("Runtime inventory contains an empty required field")
    identities = set(
        (row["package"].lower(), row["version"], row["license"].lower()) for row in rows
    )
    for package, version in (("python", "3.6.13"), ("numpy", "1.19.2")):
        if not any(item[0] == package and item[1] == version for item in identities):
            raise AssertionError("Runtime inventory lacks %s %s" % (package, version))
    if not any(item[0] == "pyqt5" and "gpl" in item[2] for item in identities):
        raise AssertionError("Runtime inventory does not disclose the PyQt5 GPL license")
    return len(rows)


def validate_windows_package_contract(root):
    package = json.loads(
        (root / "release" / "application-package.json").read_text(encoding="utf-8")
    )
    mappings = list(package.get("mappings", []) or [])
    runtime_identity = dict(package.get("python_runtime", {}) or {})
    if runtime_identity.get("archive_name") != "RASP5-python-3.6.13-windows-x86_64.zip":
        raise AssertionError("Windows package has no pinned Python runtime archive name")
    if not re.match(r"^[0-9A-Fa-f]{64}$", str(runtime_identity.get("sha256", ""))):
        raise AssertionError("Windows package has no pinned Python runtime SHA256")
    targets = []
    for mapping in mappings:
        source = root / str(mapping.get("source", ""))
        target = str(mapping.get("target", "") or "")
        if not source.exists():
            raise AssertionError("Windows package mapping is missing: %s" % source)
        if not target:
            raise AssertionError("Windows package mapping has an empty target")
        targets.append(target.replace("\\", "/").lower())
    if len(targets) != len(set(targets)):
        raise AssertionError("Windows package manifest contains duplicate targets")
    expected_targets = {
        "tools/verify_windows_stage.py",
        "tools/build_python_runtime_inventory.py",
        "tools/verify_stage_content.py",
        "docs/tutorials",
        "release/third_party_python.md",
        "release/python_runtime_packages.csv",
    }
    if not expected_targets.issubset(set(targets)):
        raise AssertionError("Windows package manifest omits release verification assets")
    if any(str(mapping.get("source", "")).replace("\\", "/") == "docs" for mapping in mappings):
        raise AssertionError("Windows package must not copy the full development docs tree")

    staging_source = (root / "tools" / "stage_windows_release.py").read_text(
        encoding="utf-8"
    )
    if '"path": str(engine_bundle)' in staging_source:
        raise AssertionError("Staged manifest leaks the engine archive build path")
    if '"path": str(runtime_archive)' in staging_source:
        raise AssertionError("Staged manifest leaks the Python archive build path")
    if (
        "%~dp0" not in staging_source
        or "conda-unpack-script.py" not in staging_source
        or '"runtime\\\\python\\\\%s" -B -m app.main' not in staging_source
    ):
        raise AssertionError("Windows launcher is not relocatable")
    for safeguard in (
        "verify_release_engine_manifest",
        "release_manifest_sha256",
        "critical_fingerprints",
        "validate_runtime_archive",
        "write_stage_content_manifest",
    ):
        if safeguard not in staging_source:
            raise AssertionError("Windows stager lacks manifest safeguard: %s" % safeguard)

    verifier_source = (root / "tools" / "verify_windows_stage.py").read_text(
        encoding="utf-8"
    )
    for safeguard in (
        "_verify_records",
        "_verify_engine_payload",
        "expected_vendor",
        "configure_qt_paths",
        "_verify_r_runtime",
        'os.environ["LOCALAPPDATA"]',
        "TemporaryDirectory",
        "_verify_runtime_archive_identity",
        "_verify_live_runtime_versions",
    ):
        if safeguard not in verifier_source:
            raise AssertionError("Windows stage verifier lacks safeguard: %s" % safeguard)

    installer_builder = (root / "tools" / "build_windows_installer.py").read_text(
        encoding="utf-8"
    )
    for safeguard in (
        "verify_stage_content",
        "subprocess.call",
        "sha256_file",
        "stage_content_digest",
        "installer_sha256",
        "verified_after",
        "discarded installer",
    ):
        if safeguard not in installer_builder:
            raise AssertionError("Windows installer builder lacks safeguard: %s" % safeguard)

    installed_smoke = (root / "tools" / "run_installed_release_smoke.py").read_text(
        encoding="utf-8"
    )
    if "assert_installed_python" not in installed_smoke:
        raise AssertionError("Installed smoke does not require the bundled Python runtime")

    inno = (root / "release" / "windows" / "RASP5.iss").read_text(
        encoding="utf-8"
    )
    if "{#StageDir}" not in inno or "E:\\RASP" in inno:
        raise AssertionError("Inno Setup definition is not stage-relative")
    if "PrivilegesRequired=lowest" not in inno:
        raise AssertionError("Windows installer must support non-admin per-user install")
    if "DefaultDirName={localappdata}\\Programs\\RASP5" not in inno:
        raise AssertionError("Windows installer default directory is not per-user")
    for safeguard in (
        "AfterInstall: RelocateRuntime",
        "procedure RelocateRuntime",
        "Exec(",
        "ResultCode <> 0",
        "SaveStringToFile",
        "GetCustomSetupExitCode",
        "RelocationSucceeded",
        "RASP5.cmd",
    ):
        if safeguard not in inno:
            raise AssertionError("Windows installer lacks relocation safeguard: %s" % safeguard)
    run_section = inno.split("[Run]", 1)[1].split("[UninstallDelete]", 1)[0]
    if "conda-unpack-script.py" in run_section:
        raise AssertionError("Windows installer relocation must check the child exit code")
    if '[UninstallDelete]' not in inno or '.rasp5-unpacked' not in inno:
        raise AssertionError("Windows installer does not clean its relocation marker")
    translation = (
        root
        / "release"
        / "windows"
        / "languages"
        / "ChineseSimplified.isl"
    )
    if not translation.is_file():
        raise AssertionError("Pinned Simplified Chinese installer translation is missing")
    if "{#SourcePath}\\languages\\ChineseSimplified.isl" not in inno:
        raise AssertionError("Inno Setup does not use the pinned Chinese translation")

    runtime_builder = (
        root / "release" / "windows" / "build-python-runtime.ps1"
    ).read_text(encoding="utf-8")
    for required in (
        "--exclude \"*.pyc\"",
        "--exclude \"*.pyo\"",
        ".sha256",
        "build_python_runtime_inventory.py",
    ):
        if required not in runtime_builder:
            raise AssertionError(
                "Python runtime builder lacks release safeguard: %s" % required
            )
    bootstrap_source = (root / "app" / "bootstrap.py").read_text(encoding="utf-8")
    for safeguard in (
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QCoreApplication.setLibraryPaths",
    ):
        if safeguard not in bootstrap_source:
            raise AssertionError("Application bootstrap lacks Qt path safeguard: %s" % safeguard)
    return len(mappings)


def validate_provenance_wiring(root):
    expected = (
        "infrastructure/diva/diva_runner.py",
        "infrastructure/dec/dec_runner.py",
        "infrastructure/biogeobears/biogeobears_runner.py",
        "infrastructure/bayarea/bayarea_runner.py",
        "infrastructure/bayestraits/bayestraits_runner.py",
        "infrastructure/mrbayes/mrbayes_runner.py",
        "infrastructure/phytools/phytools_runner.py",
        "application/services/sdiva_analysis_service.py",
        "application/services/sdec_analysis_service.py",
        "application/services/sbgb_analysis_service.py",
        "application/services/sphytools_analysis_service.py",
    )
    for relative in expected:
        text = (root / relative).read_text(encoding="utf-8")
        if text.count("write_run_provenance(") < 1:
            raise AssertionError("Engine runner lacks run provenance: %s" % relative)
    return len(expected)


def validate_no_workspace_paths(root):
    pattern = re.compile(
        r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:[\\/]|\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9$_.-]+(?:[\\/]|$))"
    )
    package = json.loads(
        (root / "release" / "application-package.json").read_text(encoding="utf-8")
    )
    paths = set()
    for mapping in package.get("mappings", []):
        source = root / str(mapping.get("source", "") or "")
        candidates = [source] if source.is_file() else source.rglob("*")
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if "ete3_vendor" in path.parts:
                continue
            paths.add(path)
    paths.add(root / "release" / "windows" / "README.md")
    paths.update((root / "engines" / "biogeobears").glob("*.R"))
    hits = []
    for path in sorted(paths, key=lambda item: str(item).lower()):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                hits.append("%s:%d" % (path.relative_to(root), line_number))
    if hits:
        raise AssertionError(
            "Packaged text contains local absolute paths: %s" % ", ".join(hits[:20])
        )
    return 0


def check_stage_engine_manifest_contract(root):
    sys.path.insert(0, str(root))
    from tools.stage_windows_release import StageError, verify_release_engine_manifest

    package = json.loads(
        (root / "release" / "application-package.json").read_text(encoding="utf-8")
    )
    release_manifest = json.loads(
        (root / package["engine_manifest"]).read_text(encoding="utf-8")
    )
    bundle_manifest = {
        "bundle_version": release_manifest["bundle_version"],
        "platform": release_manifest["platform"],
        "critical_files": release_manifest["critical_files"],
    }
    verify_release_engine_manifest(root, package, bundle_manifest)
    bad_manifest = dict(bundle_manifest)
    bad_manifest["critical_files"] = [dict(item) for item in bundle_manifest["critical_files"]]
    bad_manifest["critical_files"][0]["sha256"] = "0" * 64
    try:
        verify_release_engine_manifest(root, package, bad_manifest)
    except StageError:
        return len(bundle_manifest["critical_files"])
    raise AssertionError("Windows stager accepted mismatched engine fingerprints")


def check_stage_content_contract(root):
    sys.path.insert(0, str(root))
    from tools.stage_windows_release import write_stage_content_manifest
    from tools.verify_stage_content import StageContentError, verify_stage_content

    with tempfile.TemporaryDirectory(prefix="rasp5_stage_content_") as folder:
        stage = Path(folder)
        (stage / "runtime" / "python").mkdir(parents=True)
        target = stage / "runtime" / "python" / "python.exe"
        target.write_bytes(b"runtime-probe")
        (stage / "README.md").write_text("release probe\n", encoding="utf-8")
        write_stage_content_manifest(stage)
        result = verify_stage_content(stage)
        target.write_bytes(b"tampered")
        try:
            verify_stage_content(stage)
        except StageContentError:
            return result["file_count"]
    raise AssertionError("Stage content verifier accepted a modified runtime file")


def check_runtime_archive_contract(root):
    sys.path.insert(0, str(root))
    from tools.stage_windows_release import StageError, sha256_file, validate_runtime_archive

    with tempfile.TemporaryDirectory(prefix="rasp5_runtime_archive_") as folder:
        archive_path = Path(folder) / "runtime.zip"
        with zipfile.ZipFile(str(archive_path), "w") as archive:
            archive.writestr("python.exe", b"runtime-probe")
        expected = {
            "archive_name": archive_path.name,
            "sha256": sha256_file(archive_path),
        }
        validate_runtime_archive(archive_path, ["python.exe"], expected)
        bad = dict(expected)
        bad["sha256"] = "0" * 64
        try:
            validate_runtime_archive(archive_path, ["python.exe"], bad)
        except StageError:
            return 1
    raise AssertionError("Windows stager accepted an untrusted Python runtime ZIP")


def check_r_subprocess_environment(root):
    sys.path.insert(0, str(root))
    from infrastructure.r_runtime_environment import build_r_subprocess_environment

    keys = ("R_HOME", "R_LIBS", "R_LIBS_SITE", "R_LIBS_USER", "LC_ALL", "LANG")
    previous = dict((key, os.environ.get(key)) for key in keys)
    try:
        for key in keys:
            os.environ[key] = "host-value"
        clean = build_r_subprocess_environment()
        forbidden = [key for key in keys if key in clean]
        if forbidden:
            raise AssertionError("Bundled R environment inherits host keys: %s" % forbidden)
        site = str(Path("bundled-site-library"))
        configured = build_r_subprocess_environment(site)
        for key in ("R_LIBS", "R_LIBS_SITE", "R_LIBS_USER"):
            if configured.get(key) != site:
                raise AssertionError("Bundled R environment did not pin %s" % key)
        return len(keys)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def check_spatial_contract(root):
    sys.path.insert(0, str(root))
    from application.services.spatial_data_service import SpatialDataService

    service = SpatialDataService()
    with tempfile.TemporaryDirectory(prefix="rasp5_ci_spatial_") as folder:
        folder = Path(folder)
        occurrence_path = folder / "occurrences.csv"
        occurrence_path.write_text(
            "taxon,latitude,longitude\nTaxon_A,1,1\nTaxon_B,10.5,10.5\n",
            encoding="utf-8",
        )
        geojson_path = folder / "areas.geojson"
        geojson_path.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"area_code": "A", "display_name": "Area A"},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
                            },
                        },
                        {
                            "type": "Feature",
                            "properties": {"area_code": "B", "display_name": "Area B"},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]
                                ],
                            },
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        occurrences, occurrence_issues = service.import_occurrences_csv(
            str(occurrence_path)
        )
        areas, area_issues = service.import_area_geojson(str(geojson_path))
        if [item for item in occurrence_issues + area_issues if item.level == "error"]:
            raise AssertionError("Pure spatial fixture produced errors")
        matrix, audit = service.encode_occurrences_to_matrix(occurrences, areas)
        rows = dict((row["Name"], row) for row in matrix.rows)
        if rows["Taxon_A"]["A"] != "1" or rows["Taxon_A"]["B"] != "0":
            raise AssertionError("Taxon_A spatial encoding mismatch")
        if rows["Taxon_B"]["A"] != "0" or rows["Taxon_B"]["B"] != "1":
            raise AssertionError("Taxon_B spatial encoding mismatch")
        if len(audit) != 2 or any(item.status != "matched" for item in audit):
            raise AssertionError("Spatial audit mismatch")
    return 2


def check_application_paths(root):
    sys.path.insert(0, str(root))
    from app.paths import ApplicationPaths

    previous_data_home = os.environ.get("RASP5_DATA_HOME")
    previous_local_app_data = os.environ.get("LOCALAPPDATA")
    try:
        with tempfile.TemporaryDirectory(prefix="rasp5_ci_paths_") as folder:
            folder = Path(folder)
            source_root = folder / "source"
            source_root.mkdir()
            os.environ.pop("RASP5_DATA_HOME", None)
            source_paths = ApplicationPaths.discover(source_root)
            if source_paths.data_root != source_root.resolve():
                raise AssertionError("Source checkout should keep runs under its project root")

            installed_root = folder / "installed"
            installed_root.mkdir()
            (installed_root / ApplicationPaths.INSTALL_MANIFEST).write_text(
                "{}\n", encoding="utf-8"
            )
            local_data = folder / "local-app-data"
            os.environ["LOCALAPPDATA"] = str(local_data)
            installed_paths = ApplicationPaths.discover(installed_root)
            expected = (local_data / "RASP5").resolve()
            if installed_paths.data_root != expected:
                raise AssertionError("Installed RASP5 did not use LOCALAPPDATA")

            override = folder / "custom-data"
            os.environ["RASP5_DATA_HOME"] = str(override)
            override_paths = ApplicationPaths.discover(installed_root)
            if override_paths.data_root != override.resolve():
                raise AssertionError("RASP5_DATA_HOME did not override installed data root")
    finally:
        if previous_data_home is None:
            os.environ.pop("RASP5_DATA_HOME", None)
        else:
            os.environ["RASP5_DATA_HOME"] = previous_data_home
        if previous_local_app_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = previous_local_app_data
    return 3


def check_run_provenance_contract(root):
    sys.path.insert(0, str(root))
    from infrastructure.run_provenance import PROVENANCE_FILE, write_run_provenance

    with tempfile.TemporaryDirectory(prefix="rasp5_ci_provenance_") as folder:
        folder = Path(folder)
        engine_path = folder / "fixture-engine.exe"
        engine_bytes = b"RASP5 provenance fixture\n"
        engine_path.write_bytes(engine_bytes)
        run_dir = folder / "run"
        output = write_run_provenance(
            run_dir,
            analysis="CI fixture",
            engine_paths={"fixture_engine": engine_path},
            extra={"seed": 17},
        )
        if output.name != PROVENANCE_FILE or not output.is_file():
            raise AssertionError("Run provenance file was not created")
        payload = json.loads(output.read_text(encoding="utf-8"))
        if payload.get("analysis") != "CI fixture":
            raise AssertionError("Run provenance analysis identity mismatch")
        if payload.get("extra", {}).get("seed") != 17:
            raise AssertionError("Run provenance extra metadata mismatch")
        engines = list(payload.get("engines", []) or [])
        if len(engines) != 1 or engines[0].get("role") != "fixture_engine":
            raise AssertionError("Run provenance engine record mismatch")
        expected_hash = hashlib.sha256(engine_bytes).hexdigest().upper()
        if engines[0].get("sha256") != expected_hash:
            raise AssertionError("Run provenance engine hash mismatch")
    return 1


def check_bsm_source_contract(root):
    sys.path.insert(0, str(root))
    from application.services.bsm_dispersal_network_service import (
        BSMDispersalNetworkService,
    )

    service = BSMDispersalNetworkService()
    result = SimpleNamespace(
        summary={"nummaps": 2},
        raw_tables={
            "anagenetic": [
                {
                    "sample_id": "1",
                    "event_type": "d",
                    "current_rangetxt": "AB",
                    "dispersal_to": "B",
                },
                {
                    "sample_id": "2",
                    "event_type": "d",
                    "current_rangetxt": "AC",
                    "ana_dispersal_from": "C",
                    "dispersal_to": "B",
                },
            ],
            "cladogenetic": [],
        },
        parse_warnings=[],
        precomputed_bsm_network_edges=[],
        precomputed_bsm_node_rows=[],
    )
    matrix = SimpleNamespace(state_columns=["A", "B", "C"])
    network = service.build_network(result, range_matrix=matrix, min_mean_per_map=0.0)
    edges = dict(
        ((row["source_area"], row["target_area"]), row)
        for row in network["edge_rows"]
    )
    if edges[("A", "B")]["total_count"] != 1.0:
        raise AssertionError(
            "Fallback source mass was not renormalized after excluding target area"
        )
    if edges[("C", "B")]["total_count"] != 1.0:
        raise AssertionError("Unique BioGeoBEARS source assignment was not preserved")
    if network["source_assignment_method"] != service.SOURCE_METHOD_MIXED:
        raise AssertionError("Mixed BSM source provenance was not reported")
    return len(edges)


def run_engine_audit(root):
    command = [
        sys.executable,
        str(root / "tools" / "build_engine_bundle.py"),
        "audit",
        "--channel",
        "public",
    ]
    process = subprocess.Popen(command, cwd=str(root))
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError("Public engine bundle audit failed with code %d" % return_code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-engine-audit",
        action="store_true",
        help="Also validate local external-engine payload hashes and licenses.",
    )
    args = parser.parse_args()

    root = repository_root()
    results = {
        "compiled_files": compile_first_party(root),
        "json_files": validate_json_files(root),
        "engine_components": validate_release_identity(root),
        "python_runtime_inventory_records": validate_python_runtime_inventory(root),
        "windows_package_mappings": validate_windows_package_contract(root),
        "stage_engine_manifest_records": check_stage_engine_manifest_contract(root),
        "stage_content_contract_records": check_stage_content_contract(root),
        "runtime_archive_contract_records": check_runtime_archive_contract(root),
        "r_environment_keys_isolated": check_r_subprocess_environment(root),
        "provenance_wired_entrypoints": validate_provenance_wiring(root),
        "workspace_path_hits": validate_no_workspace_paths(root),
        "spatial_fixture_rows": check_spatial_contract(root),
        "application_path_modes": check_application_paths(root),
        "run_provenance_records": check_run_provenance_contract(root),
        "bsm_edges": check_bsm_source_contract(root),
    }
    if args.with_engine_audit:
        run_engine_audit(root)
        results["engine_audit"] = "passed"
    else:
        results["engine_audit"] = "not requested"
    print(json.dumps(results, indent=2, sort_keys=True))
    print("RASP5 release source checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
