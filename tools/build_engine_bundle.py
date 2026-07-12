#!/usr/bin/env python
"""Build and verify the separately distributed RASP5 engine bundle."""

from __future__ import print_function

import argparse
import csv
import datetime
import fnmatch
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath


CHUNK_SIZE = 1024 * 1024
CHECKSUM_NAME = "SHA256SUMS.txt"
MANIFEST_NAME = "BUNDLE-MANIFEST.json"
R_INVENTORY_NAME = "R_PACKAGE_INVENTORY.csv"
INTERNAL_NOTICE_NAME = "INTERNAL-TEST-BUNDLE.txt"


class BundleError(RuntimeError):
    pass


def repository_root():
    return Path(__file__).resolve().parent.parent


def load_manifest(path):
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != 1:
        raise BundleError("Unsupported engine manifest schema_version")
    return manifest


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest().upper()


def ensure_repo_path(root, relative_path):
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise BundleError("Manifest source escapes repository: {}".format(relative_path))
    return candidate


def normalize_archive_path(value):
    value = str(value).replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise BundleError("Unsafe archive path: {}".format(value))
    return str(path)


def path_is_excluded(relative_path, archive_path, patterns):
    rel = relative_path.replace("\\", "/")
    target = archive_path.replace("\\", "/")
    for pattern in patterns:
        pattern = pattern.replace("\\", "/")
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(target, pattern):
            return True
    return False


def add_mapping(root, files, source_value, target_value, component_id, excludes):
    source = ensure_repo_path(root, source_value)
    target = normalize_archive_path(target_value)
    if not source.exists():
        raise BundleError("Missing bundle source: {}".format(source_value))

    if source.is_file():
        candidates = [(source, "", target)]
    else:
        candidates = []
        for child in sorted(source.rglob("*"), key=lambda item: str(item).lower()):
            if not child.is_file():
                continue
            relative = child.relative_to(source).as_posix()
            archive_path = normalize_archive_path(target + "/" + relative)
            candidates.append((child, relative, archive_path))

    for child, relative, archive_path in candidates:
        if path_is_excluded(relative, archive_path, excludes):
            continue
        if archive_path in files:
            previous = files[archive_path]["source"]
            raise BundleError(
                "Duplicate archive path {} from {} and {}".format(
                    archive_path, previous, child
                )
            )
        files[archive_path] = {
            "source": child,
            "component": component_id,
        }


def validate_public_release(component):
    if component.get("redistribution_status") != "cleared":
        raise BundleError(
            "Component {} is not cleared for public redistribution".format(
                component.get("id", "<unknown>")
            )
        )
    if not component.get("first_party") and not component.get("license_files"):
        raise BundleError(
            "Component {} has no bundled license notice".format(component["id"])
        )
    if not component.get("upstream"):
        raise BundleError("Component {} has no upstream source URL".format(component["id"]))


def validate_critical_files(root, manifest):
    validated = []
    for item in manifest.get("critical_files", []):
        path = ensure_repo_path(root, item["path"])
        if not path.is_file():
            raise BundleError("Missing critical file: {}".format(item["path"]))
        actual_size = path.stat().st_size
        if actual_size != int(item["size"]):
            raise BundleError(
                "Critical file size mismatch for {}: expected {}, got {}".format(
                    item["path"], item["size"], actual_size
                )
            )
        actual_hash = sha256_file(path)
        expected_hash = item["sha256"].upper()
        if actual_hash != expected_hash:
            raise BundleError(
                "Critical file SHA256 mismatch for {}: expected {}, got {}".format(
                    item["path"], expected_hash, actual_hash
                )
            )
        validated.append(item["path"])
    return validated


def collect_bundle_files(root, manifest, channel):
    files = {}
    for component in manifest.get("components", []):
        if channel == "public":
            validate_public_release(component)
        excludes = component.get("exclude", [])
        for section in ("payload", "license_files", "source_material"):
            for mapping in component.get(section, []):
                add_mapping(
                    root,
                    files,
                    mapping["source"],
                    mapping["target"],
                    component["id"],
                    excludes if section == "payload" else [],
                )

    for mapping in manifest.get("bundle_files", []):
        add_mapping(
            root,
            files,
            mapping["source"],
            mapping["target"],
            "release-metadata",
            [],
        )
    return files


def parse_description(path):
    fields = {}
    current = None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except TypeError:
        text = path.read_text(encoding="utf-8")
    for raw_line in text.splitlines():
        if raw_line.startswith((" ", "\t")) and current:
            fields[current] = fields[current] + " " + raw_line.strip()
            continue
        if ":" not in raw_line:
            current = None
            continue
        key, value = raw_line.split(":", 1)
        current = key.strip()
        fields[current] = value.strip()
    return fields


def build_r_package_inventory(root):
    rows = []
    r_root = root / "engines" / "R"
    for library_name in ("library", "site-library"):
        library = r_root / library_name
        if not library.is_dir():
            continue
        for description in sorted(library.glob("*/DESCRIPTION"), key=lambda p: str(p).lower()):
            fields = parse_description(description)
            package = fields.get("Package", description.parent.name)
            remote = ""
            if fields.get("RemoteUsername") and fields.get("RemoteRepo"):
                remote = "https://github.com/{}/{}".format(
                    fields["RemoteUsername"], fields["RemoteRepo"]
                )
            elif fields.get("Repository") == "CRAN":
                remote = "https://cran.r-project.org/package={}".format(package)
            elif fields.get("URL"):
                remote = fields["URL"]
            rows.append(
                {
                    "Library": library_name,
                    "Package": package,
                    "Version": fields.get("Version", ""),
                    "License": fields.get("License", ""),
                    "Repository": fields.get("Repository", ""),
                    "RemoteSha": fields.get("RemoteSha", fields.get("GithubSHA1", "")),
                    "SourceURL": remote,
                }
            )

    output = io.StringIO()
    columns = [
        "Library",
        "Package",
        "Version",
        "License",
        "Repository",
        "RemoteSha",
        "SourceURL",
    ]
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8"), len(rows)


def archive_datetime(manifest):
    value = manifest["archive_timestamp"]
    parsed = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    if parsed.year < 1980:
        raise BundleError("ZIP timestamps must be in 1980 or later")
    return (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second)


def zip_info(name, timestamp):
    info = zipfile.ZipInfo(normalize_archive_path(name), timestamp)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    suffix = PurePosixPath(name).suffix.lower()
    mode = 0o755 if suffix in (".exe", ".dll") else 0o644
    info.external_attr = mode << 16
    return info


def write_source_file(archive, name, source, timestamp):
    info = zip_info(name, timestamp)
    with source.open("rb") as input_handle:
        with archive.open(info, "w") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, CHUNK_SIZE)


def write_bytes(archive, name, value, timestamp):
    archive.writestr(zip_info(name, timestamp), value)


def bundle_summary(manifest, channel, file_records, r_package_count):
    component_totals = {}
    for record in file_records:
        item = component_totals.setdefault(record["component"], {"files": 0, "bytes": 0})
        item["files"] += 1
        item["bytes"] += record["size"]
    return {
        "schema_version": manifest["schema_version"],
        "bundle_version": manifest["bundle_version"],
        "platform": manifest["platform"],
        "channel": channel,
        "reproducible_timestamp": manifest["archive_timestamp"],
        "components": manifest["components"],
        "critical_files": manifest["critical_files"],
        "payload": {
            "files": len(file_records),
            "bytes": sum(item["size"] for item in file_records),
            "component_totals": component_totals,
            "r_package_inventory_rows": r_package_count,
        },
    }


def audit_bundle(root, manifest, channel):
    validated = validate_critical_files(root, manifest)
    files = collect_bundle_files(root, manifest, channel)
    total_size = sum(item["source"].stat().st_size for item in files.values())
    inventory, package_count = build_r_package_inventory(root)
    print("Engine bundle audit passed.")
    print("  channel: {}".format(channel))
    print("  critical files: {}".format(len(validated)))
    print("  payload files: {}".format(len(files)))
    print("  payload bytes: {}".format(total_size))
    print("  R package rows: {}".format(package_count))
    print("  R inventory bytes: {}".format(len(inventory)))
    for component in manifest["components"]:
        print(
            "  component: {id} {version} [{license}] status={status}".format(
                id=component["id"],
                version=component["version"],
                license=component["license_spdx"],
                status=component["redistribution_status"],
            )
        )
    return files


def build_bundle(root, manifest, channel, output_dir, verify_after=True):
    validate_critical_files(root, manifest)
    files = collect_bundle_files(root, manifest, channel)
    print("Hashing {} payload files...".format(len(files)))

    records = []
    for index, archive_path in enumerate(sorted(files), 1):
        item = files[archive_path]
        source = item["source"]
        records.append(
            {
                "path": archive_path,
                "source": source,
                "component": item["component"],
                "size": source.stat().st_size,
                "sha256": sha256_file(source),
            }
        )
        if index % 1000 == 0:
            print("  hashed {}/{}".format(index, len(files)))

    r_inventory, r_package_count = build_r_package_inventory(root)
    summary = bundle_summary(manifest, channel, records, r_package_count)
    generated = {
        MANIFEST_NAME: (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        R_INVENTORY_NAME: r_inventory,
    }
    if channel == "internal":
        generated[INTERNAL_NOTICE_NAME] = (
            "INTERNAL TEST BUNDLE\n"
            "====================\n\n"
            "This archive is for RASP5 integration testing. It is not a tagged public "
            "release and must not be cited as a stable software version.\n"
        ).encode("utf-8")

    checksums = []
    for record in records:
        checksums.append("{}  {}".format(record["sha256"], record["path"]))
    for name in sorted(generated):
        checksums.append("{}  {}".format(sha256_bytes(generated[name]), name))
    generated[CHECKSUM_NAME] = ("\n".join(sorted(checksums)) + "\n").encode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = manifest["archive_name"].format(
        bundle_version=manifest["bundle_version"],
        platform=manifest["platform"],
        channel=channel,
    )
    output_path = output_dir / archive_name
    if output_path.exists():
        output_path.unlink()

    timestamp = archive_datetime(manifest)
    print("Writing {}...".format(output_path))
    with zipfile.ZipFile(
        str(output_path), "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
    ) as archive:
        for index, record in enumerate(records, 1):
            write_source_file(archive, record["path"], record["source"], timestamp)
            if index % 1000 == 0:
                print("  wrote {}/{}".format(index, len(records)))
        for name in sorted(generated):
            write_bytes(archive, name, generated[name], timestamp)

    archive_hash = sha256_file(output_path)
    checksum_path = Path(str(output_path) + ".sha256")
    checksum_path.write_text(
        "{}  {}\n".format(archive_hash, output_path.name), encoding="ascii"
    )
    print("Archive SHA256: {}".format(archive_hash))
    print("Archive bytes: {}".format(output_path.stat().st_size))

    if verify_after:
        verify_bundle(output_path)
    return output_path


def hash_archive_member(archive, name):
    digest = hashlib.sha256()
    with archive.open(name, "r") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def verify_bundle(path):
    if not path.is_file():
        raise BundleError("Archive does not exist: {}".format(path))
    print("Verifying {}...".format(path))
    with zipfile.ZipFile(str(path), "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise BundleError("Archive contains duplicate paths")
        if CHECKSUM_NAME not in names:
            raise BundleError("Archive has no {}".format(CHECKSUM_NAME))
        bad_member = archive.testzip()
        if bad_member:
            raise BundleError("ZIP CRC failed for {}".format(bad_member))

        checksum_text = archive.read(CHECKSUM_NAME).decode("utf-8")
        expected = {}
        for line in checksum_text.splitlines():
            if not line.strip():
                continue
            try:
                digest, name = line.split("  ", 1)
            except ValueError:
                raise BundleError("Malformed checksum line: {}".format(line))
            expected[name] = digest.upper()

        actual_names = set(names) - {CHECKSUM_NAME}
        if set(expected) != actual_names:
            missing = sorted(actual_names - set(expected))
            extra = sorted(set(expected) - actual_names)
            raise BundleError(
                "Checksum inventory mismatch; missing={}, extra={}".format(missing, extra)
            )

        for index, name in enumerate(sorted(expected), 1):
            actual = hash_archive_member(archive, name)
            if actual != expected[name]:
                raise BundleError(
                    "Archived SHA256 mismatch for {}: expected {}, got {}".format(
                        name, expected[name], actual
                    )
                )
            if index % 1000 == 0:
                print("  verified {}/{}".format(index, len(expected)))

    print("Bundle verification passed: {} files".format(len(expected) + 1))
    return True


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=None,
        help="Manifest path (default: release/engine-bundle.json)",
    )
    subparsers = parser.add_subparsers(dest="command")

    audit = subparsers.add_parser("audit", help="Validate sources, hashes, and licensing metadata")
    audit.add_argument("--channel", choices=("internal", "public"), default="public")

    build = subparsers.add_parser("build", help="Build an engine bundle ZIP")
    build.add_argument("--channel", choices=("internal", "public"), default="internal")
    build.add_argument("--output-dir", default="dist")
    build.add_argument("--no-verify", action="store_true")

    verify = subparsers.add_parser("verify", help="Verify an existing engine bundle")
    verify.add_argument("archive")
    return parser


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    root = repository_root()
    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else root / "release" / "engine-bundle.json"
    )
    try:
        if args.command == "verify":
            verify_bundle(Path(args.archive).resolve())
            return 0

        manifest = load_manifest(manifest_path)
        if args.command == "audit":
            audit_bundle(root, manifest, args.channel)
            return 0
        if args.command == "build":
            output_dir = Path(args.output_dir)
            if not output_dir.is_absolute():
                output_dir = root / output_dir
            build_bundle(
                root,
                manifest,
                args.channel,
                output_dir.resolve(),
                verify_after=not args.no_verify,
            )
            return 0
    except (BundleError, OSError, ValueError, zipfile.BadZipFile) as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
