"""Stage a relocatable RASP5 Windows application from verified release inputs."""

from __future__ import print_function

import argparse
import fnmatch
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath


CHUNK_SIZE = 1024 * 1024
STAGE_MANIFEST = "RASP5-APPLICATION-MANIFEST.json"
STAGE_CONTENT_MANIFEST = "RASP5-STAGE-CONTENT.json"


class StageError(RuntimeError):
    pass


def repository_root():
    return Path(__file__).resolve().parents[1]


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def ensure_within(path, root, label):
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise StageError("%s escapes its allowed root: %s" % (label, resolved))
    return resolved


def normalize_archive_name(name):
    value = str(name).replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise StageError("Unsafe ZIP member: %s" % value)
    return str(path)


def extract_zip_safely(archive_path, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(archive_path), "r") as archive:
        for info in archive.infolist():
            relative = normalize_archive_name(info.filename)
            target = ensure_within(destination / relative, destination, "ZIP member")
            if info.is_dir() or info.filename.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, CHUNK_SIZE)


def matches_exclude(relative, archive_path, patterns):
    relative = str(relative).replace("\\", "/")
    archive_path = str(archive_path).replace("\\", "/")
    return any(
        fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(archive_path, pattern)
        for pattern in patterns
    )


def copy_mapping(root, stage, mapping, excludes, records):
    source = ensure_within(root / mapping["source"], root, "Application source")
    target = ensure_within(stage / mapping["target"], stage, "Application target")
    if not source.exists():
        raise StageError("Missing application payload: %s" % mapping["source"])

    if source.is_file():
        candidates = [(source, Path(source.name), target)]
    else:
        candidates = []
        for child in sorted(source.rglob("*"), key=lambda item: str(item).lower()):
            if not child.is_file():
                continue
            relative = child.relative_to(source)
            candidates.append((child, relative, target / relative))

    for child, relative, destination in candidates:
        archive_path = destination.relative_to(stage).as_posix()
        if matches_exclude(relative.as_posix(), archive_path, excludes):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(child), str(destination))
        records.append(
            {
                "path": archive_path,
                "size": destination.stat().st_size,
                "sha256": sha256_file(destination),
            }
        )


def verify_engine_bundle(root, engine_bundle):
    command = [
        sys.executable,
        str(root / "tools" / "build_engine_bundle.py"),
        "verify",
        str(engine_bundle),
    ]
    return_code = subprocess.call(command, cwd=str(root))
    if return_code != 0:
        raise StageError("Engine bundle verification failed")
    with zipfile.ZipFile(str(engine_bundle), "r") as archive:
        try:
            payload = json.loads(archive.read("BUNDLE-MANIFEST.json").decode("utf-8"))
        except KeyError:
            raise StageError("Engine bundle has no BUNDLE-MANIFEST.json")
    if payload.get("channel") != "public":
        raise StageError("A public Windows release requires a public engine bundle")
    return payload


def validate_runtime_archive(runtime_archive, required_files, expected_runtime):
    expected_name = str(expected_runtime.get("archive_name", "") or "")
    expected_sha256 = str(expected_runtime.get("sha256", "") or "").upper()
    if not expected_name or len(expected_sha256) != 64:
        raise StageError("Application package has no trusted Python runtime identity")
    if runtime_archive.name != expected_name:
        raise StageError(
            "Python runtime archive name differs from release manifest: %s" % runtime_archive.name
        )
    actual_sha256 = sha256_file(runtime_archive)
    if actual_sha256 != expected_sha256:
        raise StageError(
            "Python runtime archive SHA256 differs from release manifest: %s"
            % actual_sha256
        )
    with zipfile.ZipFile(str(runtime_archive), "r") as archive:
        names = set(normalize_archive_name(name).rstrip("/") for name in archive.namelist())
    missing = [name for name in required_files if name.replace("\\", "/") not in names]
    if missing:
        raise StageError(
            "Python runtime archive is not a root-level conda-pack archive; missing: %s"
            % ", ".join(missing)
        )
    return actual_sha256


def critical_fingerprints(manifest):
    fingerprints = {}
    for item in list(manifest.get("critical_files", []) or []):
        path = normalize_archive_name(str(item.get("path", "") or ""))
        if not path:
            raise StageError("Engine manifest contains an empty critical-file path")
        fingerprints[path] = (
            int(item.get("size", 0) or 0),
            str(item.get("sha256", "") or "").upper(),
        )
    return fingerprints


def verify_release_engine_manifest(root, package_manifest, bundle_manifest):
    relative = str(package_manifest.get("engine_manifest", "") or "")
    if not relative:
        raise StageError("Application package does not identify its engine manifest")
    path = ensure_within(root / relative, root, "Release engine manifest")
    release_manifest = load_json(path)
    if release_manifest.get("bundle_version") != bundle_manifest.get("bundle_version"):
        raise StageError("Engine ZIP version differs from release/engine-bundle.json")
    if release_manifest.get("platform") != bundle_manifest.get("platform"):
        raise StageError("Engine ZIP platform differs from release/engine-bundle.json")
    if critical_fingerprints(release_manifest) != critical_fingerprints(bundle_manifest):
        raise StageError(
            "Engine ZIP critical-file fingerprints differ from release/engine-bundle.json"
        )
    return path, release_manifest


def git_identity(root):
    def output(arguments):
        try:
            value = subprocess.check_output(
                ["git"] + list(arguments),
                cwd=str(root),
                stderr=subprocess.STDOUT,
            )
            return value.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    return {
        "commit": output(["rev-parse", "HEAD"]),
        "dirty": bool(output(["status", "--porcelain"])),
    }


def launcher_text(debug=False):
    executable = "python.exe" if debug else "pythonw.exe"
    return "\r\n".join(
        [
            "@echo off",
            "setlocal",
            'cd /d "%~dp0"',
            'if exist "runtime\\python\\.rasp5-unpacked" goto launch',
            '"runtime\\python\\python.exe" -B "runtime\\python\\Scripts\\conda-unpack-script.py"',
            "if errorlevel 1 exit /b %errorlevel%",
            'if exist "runtime\\python\\.rasp5-relocation-failed" del /q "runtime\\python\\.rasp5-relocation-failed"',
            'type nul > "runtime\\python\\.rasp5-unpacked"',
            ":launch",
            '"runtime\\python\\%s" -B -m app.main' % executable,
            "exit /b %errorlevel%",
            "",
        ]
    )


def stage_release(root, package_manifest, runtime_archive, engine_bundle, output_root, force):
    version = str(package_manifest["application_version"])
    platform = str(package_manifest["platform"])
    stage = ensure_within(
        output_root / ("RASP5-%s-%s" % (version, platform)),
        output_root,
        "Release stage",
    )
    if stage.exists():
        if not force:
            raise StageError("Release stage already exists; use --force: %s" % stage)
        if stage.parent.resolve() != output_root.resolve() or not stage.name.startswith("RASP5-"):
            raise StageError("Refusing to remove unsafe stage path: %s" % stage)
        shutil.rmtree(str(stage))
    stage.mkdir(parents=True)

    records = []
    excludes = list(package_manifest.get("exclude", []) or [])
    for mapping in package_manifest.get("mappings", []):
        copy_mapping(root, stage, mapping, excludes, records)

    runtime_dir = stage / "runtime" / "python"
    extract_zip_safely(runtime_archive, runtime_dir)
    engine_manifest = verify_engine_bundle(root, engine_bundle)
    release_engine_manifest_path, release_engine_manifest = (
        verify_release_engine_manifest(root, package_manifest, engine_manifest)
    )
    extract_zip_safely(engine_bundle, stage)

    for name, debug in (("RASP5.cmd", False), ("RASP5-debug.cmd", True)):
        path = stage / name
        path.write_text(launcher_text(debug=debug), encoding="ascii")
        records.append(
            {
                "path": name,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from app.version import DISPLAY_VERSION

    if version != DISPLAY_VERSION:
        raise StageError(
            "Application package version %s differs from app version %s"
            % (version, DISPLAY_VERSION)
        )
    runtime_sha256 = sha256_file(runtime_archive)
    manifest = {
        "schema_version": 1,
        "application_version": version,
        "platform": platform,
        "runtime_strategy": package_manifest.get("runtime_strategy"),
        "source": git_identity(root),
        "engine_bundle": {
            "archive_name": engine_bundle.name,
            "sha256": sha256_file(engine_bundle),
            "bundle_version": engine_manifest.get("bundle_version"),
            "channel": engine_manifest.get("channel"),
            "release_manifest_sha256": sha256_file(release_engine_manifest_path),
            "critical_files": len(critical_fingerprints(release_engine_manifest)),
        },
        "python_runtime": {
            "archive_name": runtime_archive.name,
            "sha256": runtime_sha256,
        },
        "first_party_files": sorted(records, key=lambda item: item["path"].lower()),
    }
    manifest_path = stage / STAGE_MANIFEST
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_stage_content_manifest(stage)
    return stage


def stage_content_records(stage):
    records = []
    manifest_path = (stage / STAGE_CONTENT_MANIFEST).resolve()
    for path in sorted(stage.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file() or path.resolve() == manifest_path:
            continue
        records.append(
            {
                "path": path.relative_to(stage).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def stage_content_digest(records):
    digest = hashlib.sha256()
    for record in records:
        line = "%s  %d  %s\n" % (
            record["sha256"],
            int(record["size"]),
            record["path"],
        )
        digest.update(line.encode("utf-8"))
    return digest.hexdigest().upper()


def write_stage_content_manifest(stage):
    records = stage_content_records(stage)
    payload = {
        "schema_version": 1,
        "algorithm": "SHA256",
        "file_count": len(records),
        "content_digest": stage_content_digest(records),
        "files": records,
    }
    (stage / STAGE_CONTENT_MANIFEST).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main():
    root = repository_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-runtime", required=True, help="Root-level conda-pack ZIP")
    parser.add_argument("--engine-bundle", required=True, help="Verified public engine ZIP")
    parser.add_argument(
        "--manifest",
        default=str(root / "release" / "application-package.json"),
    )
    parser.add_argument("--output-dir", default=str(root / "dist" / "windows-stage"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    runtime_archive = Path(args.python_runtime).resolve()
    engine_bundle = Path(args.engine_bundle).resolve()
    output_root = Path(args.output_dir).resolve()
    if not runtime_archive.is_file():
        raise StageError("Python runtime archive not found: %s" % runtime_archive)
    if not engine_bundle.is_file():
        raise StageError("Engine bundle not found: %s" % engine_bundle)
    output_root.mkdir(parents=True, exist_ok=True)

    package_manifest = load_json(manifest_path)
    if package_manifest.get("schema_version") != 1:
        raise StageError("Unsupported application package manifest schema")
    validate_runtime_archive(
        runtime_archive,
        list(package_manifest.get("required_runtime_files", []) or []),
        dict(package_manifest.get("python_runtime", {}) or {}),
    )
    stage = stage_release(
        root,
        package_manifest,
        runtime_archive,
        engine_bundle,
        output_root,
        args.force,
    )
    print("Windows release staged: %s" % stage)
    print("Compile release/windows/RASP5.iss with StageDir set to this directory.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StageError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        sys.exit(2)
