"""Build a deterministic package/license inventory for a frozen Python runtime."""

from __future__ import print_function

import argparse
import csv
import json
import re
from email.parser import Parser
from pathlib import Path


COLUMNS = (
    "record_type",
    "package",
    "version",
    "build",
    "channel_or_home_page",
    "license",
    "metadata_path",
)


def _clean(value, missing=""):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or missing


def _relative(path, prefix):
    return path.resolve().relative_to(prefix.resolve()).as_posix()


def conda_rows(prefix):
    rows = []
    for path in sorted((prefix / "conda-meta").glob("*.json"), key=lambda p: p.name.lower()):
        with path.open("r", encoding="utf-8-sig") as handle:
            item = json.load(handle)
        rows.append(
            {
                "record_type": "conda-package",
                "package": _clean(item.get("name"), "NOT_REPORTED"),
                "version": _clean(item.get("version"), "NOT_REPORTED"),
                "build": _clean(item.get("build"), "NOT_REPORTED"),
                "channel_or_home_page": _clean(item.get("channel"), "NOT_REPORTED"),
                "license": _clean(
                    item.get("license") or item.get("license_family"),
                    "NOT_REPORTED",
                ),
                "metadata_path": _relative(path, prefix),
            }
        )
    return rows


def python_metadata_rows(prefix):
    rows = []
    site_packages = prefix / "Lib" / "site-packages"
    candidates = list(site_packages.glob("*.dist-info/METADATA"))
    candidates.extend(site_packages.glob("*.egg-info/PKG-INFO"))
    for path in sorted(candidates, key=lambda p: str(p).lower()):
        metadata = Parser().parsestr(path.read_text(encoding="utf-8", errors="replace"))
        rows.append(
            {
                "record_type": "python-distribution",
                "package": _clean(metadata.get("Name"), path.parent.name),
                "version": _clean(metadata.get("Version"), "NOT_REPORTED"),
                "build": "NOT_APPLICABLE",
                "channel_or_home_page": _clean(
                    metadata.get("Home-page"),
                    "NOT_REPORTED",
                ),
                "license": _clean(metadata.get("License"), "NOT_REPORTED"),
                "metadata_path": _relative(path, prefix),
            }
        )
    return rows


def build_inventory(prefix, output):
    prefix = Path(prefix).resolve()
    if not (prefix / "python.exe").is_file():
        raise RuntimeError("Python runtime prefix has no python.exe: %s" % prefix)
    rows = conda_rows(prefix) + python_metadata_rows(prefix)
    rows.sort(
        key=lambda row: (
            row["record_type"].lower(),
            row["package"].lower(),
            row["version"].lower(),
            row["metadata_path"].lower(),
        )
    )
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, help="Frozen conda environment prefix")
    parser.add_argument("--output", required=True, help="Output CSV path")
    args = parser.parse_args()
    rows = build_inventory(args.prefix, args.output)
    counts = {}
    for row in rows:
        counts[row["record_type"]] = counts.get(row["record_type"], 0) + 1
    print("Python runtime inventory written: %s" % Path(args.output).resolve())
    for key in sorted(counts):
        print("  %s: %d" % (key, counts[key]))
    print("  total records: %d" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
