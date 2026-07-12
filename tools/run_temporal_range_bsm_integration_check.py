import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_ROOT = PROJECT_ROOT / "infrastructure" / "tree" / "backend" / "ete3_vendor"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ete3 import Tree
from PyQt5.QtWidgets import QApplication

from domain.models.spatial_data import AreaSpatialRecord
from gui.dialogs.temporal_range_playback_dialog import TemporalRangePlaybackDialog
from infrastructure.biogeobears.biogeobears_bsm_event_parser import BioGeoBEARSBSMEventParser
from infrastructure.biogeobears.biogeobears_output_parser import BioGeoBEARSOutputParser


def parse_args():
    parser = argparse.ArgumentParser(description="Validate a real medium-sized BSM playback result.")
    parser.add_argument("run_dir", help="BioGeoBEARS run directory containing bgb_result.json and bsm/.")
    parser.add_argument("--tree", default="", help="Reference tree path; defaults to metadata or run_dir/input_tree.nwk.")
    parser.add_argument("--coordinates", default="", help="Optional CSV rows: area_code,latitude,longitude.")
    parser.add_argument("--minimum-maps", type=int, default=100)
    parser.add_argument("--frame-steps", type=int, default=101)
    parser.add_argument("--screenshot", default="")
    return parser.parse_args()


def resolve_paths(run_dir, tree_override):
    output_json = run_dir / "bgb_result.json"
    if not output_json.exists():
        raise FileNotFoundError("bgb_result.json was not found in %s" % run_dir)
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    candidates = []
    if tree_override:
        candidates.append(Path(tree_override))
    treefile = str(dict(payload.get("attributes", {}) or {}).get("treefile", "") or "")
    if treefile:
        candidates.append(Path(treefile))
        candidates.append(run_dir / treefile)
    candidates.append(run_dir / "input_tree.nwk")
    tree_path = next((path for path in candidates if path.exists()), None)
    if tree_path is None:
        raise FileNotFoundError("A reference tree could not be resolved for %s" % run_dir)
    bsm_dir = run_dir / "bsm"
    if not bsm_dir.exists():
        bsm_dir = run_dir / "bsm_output"
    if not bsm_dir.exists():
        raise FileNotFoundError("A bsm/ or bsm_output/ directory was not found in %s" % run_dir)
    return output_json, tree_path, bsm_dir


def read_coordinates(path):
    path = Path(path) if path else None
    if path is None or not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.reader(handle), 1):
            if len(row) < 3:
                continue
            try:
                latitude = float(row[1])
                longitude = float(row[2])
            except Exception:
                continue
            code = str(row[0] or "").strip()
            if not code:
                continue
            records.append(AreaSpatialRecord(
                area_code=code,
                geometry_id="integration-coordinate-%d" % index,
                display_name=code,
                centroid_lon=longitude,
                centroid_lat=latitude,
                source=str(path),
            ))
    return records


def main():
    args = parse_args()
    run_dir = Path(args.run_dir).resolve()
    output_json, tree_path, bsm_dir = resolve_paths(run_dir, args.tree)
    reference_tree = Tree(tree_path.read_text(encoding="utf-8"), format=1)
    result = BioGeoBEARSOutputParser().parse(
        reference_tree=reference_tree,
        output_json_path=output_json,
    )
    bsm_result = BioGeoBEARSBSMEventParser().parse(
        output_json_path=output_json,
        bsm_dir=bsm_dir,
    )
    area_records = read_coordinates(args.coordinates)

    app = QApplication.instance() or QApplication([])
    started = time.perf_counter()
    dialog = TemporalRangePlaybackDialog(
        result=result,
        method_name=result.model_name,
        area_records=area_records,
        bsm_result=bsm_result,
        reference_tree=reference_tree,
    )
    build_seconds = time.perf_counter() - started
    app.processEvents()

    frame_steps = max(2, int(args.frame_steps or 2))
    frame_times = []
    for index in range(frame_steps):
        value = int(round(index * dialog.SLIDER_STEPS / float(frame_steps - 1)))
        dialog.time_slider.setValue(value)
        frame_started = time.perf_counter()
        dialog._refresh_frame()
        app.processEvents()
        frame_times.append(time.perf_counter() - frame_started)

    if args.screenshot:
        screenshot_path = Path(args.screenshot).resolve()
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        dialog.show()
        app.processEvents()
        dialog._fit_views()
        app.processEvents()
        if not dialog.grab().save(str(screenshot_path)):
            raise RuntimeError("Could not save screenshot: %s" % screenshot_path)

    diagnostics = dict(dialog.timeline.metadata.get("bsm_sampling_diagnostics", {}) or {})
    map_count = len(dialog.timeline.history_sample_ids)
    if map_count < int(args.minimum_maps):
        raise AssertionError("Expected at least %d complete maps, found %d." % (args.minimum_maps, map_count))
    if not dialog.timeline.metadata.get("bsm_history_complete"):
        raise AssertionError("The BSM history table is incomplete.")
    if not dialog.timeline.metadata.get("bsm_summary_interactive_available"):
        raise AssertionError("The all-map interactive summary is unavailable for this integration fixture.")

    report = {
        "checks": "passed",
        "run_dir": str(run_dir),
        "tree": str(tree_path),
        "maps": map_count,
        "branches": len(dialog.timeline.branches),
        "segments": len(dialog.timeline.history_segments),
        "build_seconds": round(build_seconds, 6),
        "mean_frame_ms": round(1000.0 * sum(frame_times) / len(frame_times), 6),
        "max_frame_ms": round(1000.0 * max(frame_times), 6),
        "sampling_diagnostics": diagnostics,
    }
    report_path = run_dir / "temporal_playback_integration_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    dialog.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
