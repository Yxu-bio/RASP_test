"""Write common RASP5 application and engine provenance beside run artifacts."""

from __future__ import print_function

import hashlib
import json
import platform
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from app.version import DISPLAY_VERSION, __version__


PROVENANCE_FILE = "rasp5_provenance.json"


def _project_root():
    return Path(__file__).resolve().parents[1]


@lru_cache(maxsize=64)
def _sha256_cached(path_text, size, modified_ns):
    del size, modified_ns
    digest = hashlib.sha256()
    with Path(path_text).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def _sha256(path):
    stat = path.stat()
    modified_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1000000000))
    return _sha256_cached(str(path.resolve()), int(stat.st_size), int(modified_ns))


def _release_manifest(root):
    candidates = (
        root / "BUNDLE-MANIFEST.json",
        root / "release" / "engine-bundle.json",
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def _relative_path(path, root):
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def _component_for_path(relative_path, manifest):
    if not relative_path:
        return {}
    for component in list(manifest.get("components", []) or []):
        for mapping in list(component.get("payload", []) or []):
            source = str(mapping.get("source", "") or "").replace("\\", "/").rstrip("/")
            if relative_path == source or relative_path.startswith(source + "/"):
                return component
    return {}


def _expected_fingerprint(relative_path, manifest):
    for item in list(manifest.get("critical_files", []) or []):
        if str(item.get("path", "") or "").replace("\\", "/") == relative_path:
            return {
                "size": int(item.get("size", 0) or 0),
                "sha256": str(item.get("sha256", "") or "").upper(),
            }
    return {}


def _engine_record(role, path, root, manifest):
    candidate = Path(path).resolve()
    record = {
        "role": str(role),
        "path": str(candidate),
        "exists": candidate.is_file(),
    }
    if not candidate.is_file():
        return record
    relative = _relative_path(candidate, root)
    component = _component_for_path(relative, manifest)
    expected = _expected_fingerprint(relative, manifest)
    actual_hash = _sha256(candidate)
    record.update(
        {
            "relative_path": relative,
            "size": int(candidate.stat().st_size),
            "sha256": actual_hash,
            "component_id": str(component.get("id", "") or ""),
            "component_version": str(component.get("version", "") or ""),
            "source_revision": str(component.get("source_revision", "") or ""),
            "license_spdx": str(component.get("license_spdx", "") or ""),
            "expected_sha256": str(expected.get("sha256", "") or ""),
            "matches_release_manifest": (
                actual_hash == expected.get("sha256")
                if expected.get("sha256")
                else None
            ),
        }
    )
    return record


def write_run_provenance(
    run_dir,
    analysis,
    engine_paths=None,
    extra=None,
    filename=PROVENANCE_FILE,
):
    root = _project_root()
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    release_manifest = _release_manifest(root)
    engines = []
    for role, path in dict(engine_paths or {}).items():
        if path is None:
            continue
        engines.append(_engine_record(role, path, root, release_manifest))
    payload = {
        "format": "rasp5_run_provenance",
        "version": 1,
        "created_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "analysis": str(analysis or ""),
        "application": {
            "name": "RASP5",
            "version": __version__,
            "display_version": DISPLAY_VERSION,
        },
        "runtime": {
            "python": platform.python_version(),
            "python_executable": str(Path(sys.executable).resolve()),
            "platform": platform.platform(),
        },
        "engine_bundle_version": str(release_manifest.get("bundle_version", "") or ""),
        "engines": engines,
        "extra": dict(extra or {}),
    }
    filename = str(filename or PROVENANCE_FILE)
    if Path(filename).name != filename:
        raise ValueError("Provenance filename must not contain a directory")
    output = run_path / filename
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
