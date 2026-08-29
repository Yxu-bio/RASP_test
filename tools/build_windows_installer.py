"""Verify a pristine Windows stage and compile its Inno Setup installer."""

from __future__ import print_function

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_stage_content import verify_stage_content


CHUNK_SIZE = 1024 * 1024


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def main():
    root = ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", required=True, help="Path to ISCC.exe")
    parser.add_argument("--stage-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--app-version", required=True)
    parser.add_argument(
        "--script",
        default=str(root / "release" / "windows" / "RASP5.iss"),
    )
    args = parser.parse_args()

    iscc = Path(args.iscc).resolve()
    stage = Path(args.stage_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    script = Path(args.script).resolve()
    for label, path in (("ISCC", iscc), ("Inno script", script)):
        if not path.is_file():
            raise FileNotFoundError("%s not found: %s" % (label, path))
    output_dir.mkdir(parents=True, exist_ok=True)

    verified = verify_stage_content(stage)
    application_manifest = json.loads(
        (stage / "RASP5-APPLICATION-MANIFEST.json").read_text(encoding="utf-8-sig")
    )
    staged_version = str(application_manifest.get("application_version", "") or "")
    platform = str(application_manifest.get("platform", "") or "")
    if args.app_version != staged_version:
        raise RuntimeError(
            "Requested installer version %s differs from staged version %s"
            % (args.app_version, staged_version)
        )
    if not platform:
        raise RuntimeError("Staged application manifest has no platform")
    installer = output_dir / (
        "RASP5-%s-%s-setup.exe" % (staged_version, platform)
    )
    if installer.exists():
        raise FileExistsError(
            "Expected installer path already exists; use a clean output directory: %s"
            % installer
        )
    print(json.dumps(verified, indent=2, sort_keys=True))
    command = [
        str(iscc),
        "/DStageDir=%s" % stage,
        "/DAppVersion=%s" % args.app_version,
        "/DOutputDir=%s" % output_dir,
        str(script),
    ]
    return_code = subprocess.call(command, cwd=str(root))
    if return_code != 0:
        raise RuntimeError("Inno Setup failed with code %d" % return_code)

    if not installer.is_file():
        raise RuntimeError("Inno Setup did not produce the expected installer: %s" % installer)
    try:
        verified_after = verify_stage_content(stage)
    except Exception:
        installer.unlink()
        raise
    if verified_after != verified:
        installer.unlink()
        raise RuntimeError(
            "Stage content changed while Inno Setup was compiling; discarded installer"
        )
    digest = sha256_file(installer)
    sidecar = installer.with_suffix(installer.suffix + ".sha256")
    sidecar.write_text("%s  %s\n" % (digest, installer.name), encoding="ascii")
    build_record = {
        "schema_version": 1,
        "application_version": staged_version,
        "platform": platform,
        "stage_content_digest": verified["content_digest"],
        "stage_file_count": verified["file_count"],
        "stage_total_bytes": verified["total_bytes"],
        "installer_name": installer.name,
        "installer_size": installer.stat().st_size,
        "installer_sha256": digest,
    }
    installer.with_suffix(installer.suffix + ".build.json").write_text(
        json.dumps(build_record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Installer: %s" % installer)
    print("SHA256: %s" % digest)
    print("Verified stage content digest: %s" % verified["content_digest"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
