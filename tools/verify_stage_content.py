"""Verify the immutable, pre-relocation contents of a staged Windows release."""

from __future__ import print_function

import argparse
import hashlib
import json
import sys
from pathlib import Path


CHUNK_SIZE = 1024 * 1024
MANIFEST_NAME = "RASP5-STAGE-CONTENT.json"


class StageContentError(RuntimeError):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def content_digest(records):
    digest = hashlib.sha256()
    for record in records:
        line = "%s  %d  %s\n" % (
            record["sha256"],
            int(record["size"]),
            record["path"],
        )
        digest.update(line.encode("utf-8"))
    return digest.hexdigest().upper()


def verify_stage_content(stage_dir):
    stage = Path(stage_dir).resolve()
    manifest_path = stage / MANIFEST_NAME
    if not manifest_path.is_file():
        raise StageContentError("Stage content manifest is missing: %s" % manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if payload.get("schema_version") != 1 or payload.get("algorithm") != "SHA256":
        raise StageContentError("Unsupported stage content manifest")

    records = list(payload.get("files", []) or [])
    expected_paths = set()
    normalized = []
    total_bytes = 0
    for record in records:
        relative = str(record.get("path", "") or "").replace("\\", "/")
        if not relative or relative.startswith("/") or ".." in Path(relative).parts:
            raise StageContentError("Unsafe staged path: %s" % relative)
        if relative in expected_paths:
            raise StageContentError("Duplicate staged path: %s" % relative)
        expected_paths.add(relative)
        target = (stage / relative).resolve()
        try:
            target.relative_to(stage)
        except ValueError:
            raise StageContentError("Staged path escapes root: %s" % relative)
        if not target.is_file():
            raise StageContentError("Staged file is missing: %s" % relative)
        expected_size = int(record.get("size", -1))
        expected_sha256 = str(record.get("sha256", "") or "").upper()
        actual_size = target.stat().st_size
        if actual_size != expected_size:
            raise StageContentError("Staged file size mismatch: %s" % relative)
        actual_sha256 = sha256_file(target)
        if actual_sha256 != expected_sha256:
            raise StageContentError("Staged file SHA256 mismatch: %s" % relative)
        normalized.append(
            {"path": relative, "size": expected_size, "sha256": expected_sha256}
        )
        total_bytes += expected_size

    actual_paths = set(
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file() and path.resolve() != manifest_path.resolve()
    )
    extras = sorted(actual_paths - expected_paths)
    if extras:
        raise StageContentError("Stage contains unmanifested files: %s" % ", ".join(extras[:10]))
    missing = sorted(expected_paths - actual_paths)
    if missing:
        raise StageContentError("Stage is missing manifested files: %s" % ", ".join(missing[:10]))
    if int(payload.get("file_count", -1)) != len(normalized):
        raise StageContentError("Stage content file count mismatch")

    actual_digest = content_digest(normalized)
    if actual_digest != str(payload.get("content_digest", "") or "").upper():
        raise StageContentError("Stage aggregate content digest mismatch")
    return {
        "stage": str(stage),
        "file_count": len(normalized),
        "total_bytes": total_bytes,
        "content_digest": actual_digest,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage_dir")
    args = parser.parse_args()
    result = verify_stage_content(args.stage_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    print("Stage content verification passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, StageContentError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        sys.exit(2)
