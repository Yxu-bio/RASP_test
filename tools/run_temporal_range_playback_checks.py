import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_ROOT = PROJECT_ROOT / "infrastructure" / "tree" / "backend" / "ete3_vendor"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ete3 import Tree
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from application.services.temporal_range_playback_service import TemporalRangePlaybackService
from application.services.bsm_branch_history_service import BSMBranchHistoryService
from application.services.bsm_sampling_diagnostics_service import BSMSamplingDiagnosticsService
from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
from domain.models.biogeobears_event_result import BioGeoBEARSEventResult
from domain.models.diva_result import DivaNodeResult, DivaResult
from domain.models.spatial_data import AreaSpatialRecord
from domain.models.state_matrix import StateMatrix
from gui.dialogs.temporal_range_playback_dialog import TemporalRangePlaybackDialog
from gui.dialogs.bsm_run_config_dialog import BSMRunConfigDialog
from gui.dialogs.result_view_window import ResultViewWindow
from gui.widgets.temporal_range_map_view import TemporalRangeMapView
from infrastructure.biogeobears.biogeobears_output_parser import BioGeoBEARSOutputParser


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def square(lon, lat, size=1.0):
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon, lat],
            [lon + size, lat],
            [lon + size, lat + size],
            [lon, lat + size],
            [lon, lat],
        ]],
    }


def main():
    tree = Tree("((tip_a:1,tip_b:1):1,tip_c:2);", format=1)
    root_key = "tip_a|tip_b|tip_c"
    child_key = "tip_a|tip_b"
    payload = {
        "attributes": {"model_name": "DEC", "include_null_range": True},
        "node_results": [
            {
                "clade_key": root_key,
                "display_node_id": "5",
                "top_probabilities": {"A": 1.0, "B": 0.0, "AB": 0.0},
                "bottom_probabilities": {"A": 1.0, "B": 0.0, "AB": 0.0},
                "states": [{"label": "A", "prob": 1.0, "prob_percent": 100.0, "bottom_prob": 1.0}],
            },
            {
                "clade_key": child_key,
                "display_node_id": "4",
                "top_probabilities": {"A": 0.0, "B": 1.0, "AB": 0.0},
                "bottom_probabilities": {"A": 1.0, "B": 0.0, "AB": 0.0},
                "states": [{"label": "B", "prob": 1.0, "prob_percent": 100.0, "bottom_prob": 0.0}],
            },
        ],
    }

    with tempfile.TemporaryDirectory(prefix="rasp_temporal_check_") as tmp:
        output_path = Path(tmp) / "bgb_output.json"
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        result = BioGeoBEARSOutputParser().parse(reference_tree=tree, output_json_path=output_path)

    child_result = result.node_results[child_key]
    check(child_result.branch_bottom_supports.get("A") == 100.0, "Complete branch-bottom probabilities were not parsed.")
    check(child_result.branch_top_supports.get("B") == 100.0, "Complete branch-top probabilities were not parsed.")
    child_result.raw_method_payload["bgb_node_id"] = "42"

    matrix = StateMatrix(
        ids=["1", "2", "3"],
        taxa_names=["tip_a", "tip_b", "tip_c"],
        state_columns=["A", "B"],
        rows=[
            {"ID": "1", "Name": "tip_a", "A": "1", "B": "0"},
            {"ID": "2", "Name": "tip_b", "A": "0", "B": "1"},
            {"ID": "3", "Name": "tip_c", "A": "1", "B": "1"},
        ],
        source_path="synthetic",
    )
    matrix.area_code_to_label = {"A": "Area Alpha", "B": "Area Beta"}
    areas = [
        AreaSpatialRecord(
            area_code="Area Alpha",
            geometry_id="alpha",
            display_name="Area Alpha",
            centroid_lon=0.5,
            centroid_lat=0.5,
            geometry=square(0.0, 0.0),
        ),
        AreaSpatialRecord(
            area_code="Area Beta",
            geometry_id="beta",
            display_name="Area Beta",
            centroid_lon=2.5,
            centroid_lat=0.5,
            geometry=square(2.0, 0.0),
        ),
    ]
    leaf_states = {"tip_a": "A", "tip_b": "B", "tip_c": "AB"}
    service = TemporalRangePlaybackService()
    timeline = service.build(
        result=result,
        method_name="BioGeoBEARS-DEC",
        leaf_state_map=leaf_states,
        area_records=areas,
        range_matrix=matrix,
    )
    check(timeline.source_kind == "bgb_endpoints", "BioGeoBEARS endpoint mode was not selected.")
    branch = next(item for item in timeline.branches if item.child_clade_key == child_key)
    check(branch.metadata.get("engine_child_node_id") == "42", "The original BioGeoBEARS node ID was not retained.")
    midpoint = (branch.older_time + branch.younger_time) / 2.0
    midpoint_probs = service.branch_probabilities_at(branch, midpoint)
    check(abs(midpoint_probs.get("A", 0.0) - 0.5) < 1e-9, "A midpoint probability is not 0.5.")
    check(abs(midpoint_probs.get("B", 0.0) - 0.5) < 1e-9, "B midpoint probability is not 0.5.")

    marginals = service.area_marginals({"AB": 1.0}, timeline.state_area_members)
    check(marginals.get("Area Alpha") == 1.0, "AB did not contribute to Area Alpha.")
    check(marginals.get("Area Beta") == 1.0, "AB did not contribute to Area Beta.")

    frame = service.frame(
        timeline,
        midpoint,
        selected_branch_id=branch.branch_id,
        display_scope="selected_lineage",
    )
    check(frame.active_branch_count >= 1, "No active branch was found at the midpoint.")
    check(abs(frame.area_probabilities.get("Area Alpha", 0.0) - 0.5) < 1e-9, "Selected-lineage Area Alpha marginal is incorrect.")
    check(abs(frame.area_probabilities.get("Area Beta", 0.0) - 0.5) < 1e-9, "Selected-lineage Area Beta marginal is incorrect.")

    after_split_frame = service.frame(timeline, 1.0, node_boundary_mode="after_split")
    before_split_frame = service.frame(timeline, 1.0, node_boundary_mode="before_split")
    child_branch_ids = set(
        item.branch_id for item in timeline.branches if item.parent_clade_key == child_key
    )
    check(branch.branch_id not in after_split_frame.active_branch_probabilities, "After-split mode retained the incoming branch.")
    check(child_branch_ids.issubset(set(after_split_frame.active_branch_probabilities)), "After-split mode omitted child branches.")
    check(branch.branch_id in before_split_frame.active_branch_probabilities, "Before-split mode omitted the incoming branch.")
    check(not child_branch_ids.intersection(set(before_split_frame.active_branch_probabilities)), "Before-split mode retained child branches.")

    clado_rows = []
    for sample_id in ["1", "2"]:
        for current_branch in timeline.branches:
            top_state = "B" if sample_id == "1" and current_branch.branch_id == branch.branch_id else "A"
            clado_rows.append({
                "sample_id": sample_id,
                "node": current_branch.metadata.get("engine_child_node_id") or current_branch.child_node_id,
                "sampled_states_AT_brbots_txt": "A",
                "sampled_states_AT_nodes_txt": top_state,
                "edge.length": str(max(0.0, current_branch.older_time - current_branch.younger_time)),
            })
    bsm_result = BioGeoBEARSEventResult(
        summary={"nummaps": 2},
        raw_tables={
            "cladogenetic": clado_rows,
            "anagenetic": [
                {
                    "sample_id": "1", "node": "42", "current_rangetxt": "A", "new_rangetxt": "B",
                    "abs_event_time": "1.5", "event_time": "0.5", "edge.length": "1.0",
                },
            ],
        }
    )
    BSMBranchHistoryService().attach(timeline, bsm_result)
    check(timeline.history_sample_ids == ["1", "2"], "BSM sample IDs were not attached in order.")
    sampling = dict(timeline.metadata.get("bsm_sampling_diagnostics", {}) or {})
    check(sampling.get("sampling_tier") == "debug_only", "Two BSM maps were not classified as debug-only.")
    check(
        float(sampling.get("worst_case_mc95_half_width", 0.0) or 0.0) > 0.5,
        "Two BSM maps produced an implausibly narrow Monte Carlo interval.",
    )
    count_diagnostics = BSMSamplingDiagnosticsService()
    check(count_diagnostics.describe_count(50)["sampling_tier"] == "exploratory", "Fifty BSM maps were misclassified.")
    check(count_diagnostics.describe_count(100)["sampling_tier"] == "standard", "One hundred BSM maps were misclassified.")
    bsm_frame = service.frame(
        timeline,
        1.25,
        selected_branch_id=branch.branch_id,
        display_scope="selected_lineage",
        history_mode="bsm_summary",
    )
    check(abs(bsm_frame.selected_range_probabilities.get("A", 0.0) - 0.5) < 1e-9, "BSM summary A probability is incorrect.")
    check(abs(bsm_frame.selected_range_probabilities.get("B", 0.0) - 0.5) < 1e-9, "BSM summary B probability is incorrect.")
    sample_frame = service.frame(
        timeline,
        1.25,
        selected_branch_id=branch.branch_id,
        display_scope="selected_lineage",
        history_mode="bsm_sample",
        sample_id="1",
    )
    check(sample_frame.selected_range_probabilities == {"B": 1.0}, "Single BSM map state is incorrect.")
    boundary_frame = service.frame(
        timeline,
        1.5,
        selected_branch_id=branch.branch_id,
        display_scope="selected_lineage",
        history_mode="bsm_sample",
        sample_id="1",
    )
    check(boundary_frame.selected_range_probabilities == {"B": 1.0}, "BSM event boundary did not use the post-event state.")
    absent_frame = service.frame(
        timeline,
        0.5,
        selected_branch_id=branch.branch_id,
        display_scope="selected_lineage",
        history_mode="bsm_sample",
        sample_id="1",
    )
    check(not absent_frame.selected_range_probabilities, "A lineage was extended outside its branch time span.")

    incomplete_timeline = service.build(
        result=result,
        method_name="BioGeoBEARS-DEC",
        leaf_state_map=leaf_states,
        area_records=areas,
        range_matrix=matrix,
    )
    incomplete_bsm = deepcopy(bsm_result)
    incomplete_bsm.summary["nummaps"] = 1000
    BSMBranchHistoryService().attach(incomplete_timeline, incomplete_bsm)
    check(not incomplete_timeline.metadata.get("bsm_history_complete"), "A BSM preview was marked complete.")
    check(
        not incomplete_timeline.metadata.get("bsm_summary_interactive_available"),
        "An incomplete BSM preview incorrectly enabled all-map summaries.",
    )

    mismatch_timeline = service.build(
        result=result,
        method_name="BioGeoBEARS-DEC",
        leaf_state_map=leaf_states,
        area_records=areas,
        range_matrix=matrix,
    )
    mismatch_bsm = deepcopy(bsm_result)
    mismatch_bsm.source_clade_keys = ["other_a|other_b"]
    BSMBranchHistoryService().attach(mismatch_timeline, mismatch_bsm)
    check(not mismatch_timeline.history_segments, "Mismatched BSM clades were attached to the tree.")

    bayarea_result = deepcopy(result)
    bayarea_result.model_name = "BayArea"
    for node_result in bayarea_result.node_results.values():
        node_result.branch_top_supports = {}
        node_result.branch_bottom_supports = {}
        node_result.raw_method_payload.pop("bgb_node_id", None)
    bayarea_timeline = service.build(
        result=bayarea_result,
        method_name="BayArea",
        leaf_state_map=leaf_states,
        area_records=areas,
        range_matrix=matrix,
    )
    check(bayarea_timeline.source_kind == "node_interpolation", "BayArea did not use node interpolation.")

    diva_result = DivaResult(dataset=object())
    diva_result.state_order = ["A", "B"]
    diva_result.state_colors = {"A": "#2a9d8f", "B": "#e76f51"}
    diva_result.node_results[root_key] = DivaNodeResult(
        node_key=root_key,
        diva_node_id=5,
        terminal_spec="",
        states=["A"],
        state_supports={"A": 100.0},
    )
    diva_result.node_results[child_key] = DivaNodeResult(
        node_key=child_key,
        diva_node_id=4,
        terminal_spec="",
        states=["B"],
        state_supports={"B": 100.0},
    )
    diva_timeline = service.build(
        result=diva_result,
        method_name="DIVA",
        leaf_state_map=leaf_states,
        area_records=areas,
        range_matrix=matrix,
        reference_tree=tree,
    )
    check(diva_timeline.source_kind == "node_interpolation", "DIVA did not use node interpolation.")

    app = QApplication.instance() or QApplication([])
    dialog = TemporalRangePlaybackDialog(
        result=result,
        method_name="BioGeoBEARS-DEC",
        leaf_state_map=leaf_states,
        area_records=areas,
        range_matrix=matrix,
        bsm_result=bsm_result,
    )
    check("Debug only BSM sampling" in dialog.sampling_label.text(), "The playback sampling warning is missing.")
    dialog.time_slider.setValue(500)
    app.processEvents()
    check(dialog.range_table.rowCount() > 0, "The playback range table is empty.")
    check(len(dialog.map_view._area_items) == 2, "The playback map did not draw both areas.")
    selected_id = dialog.timeline.branches[0].branch_id
    dialog.tree_view._branch_items[selected_id].setSelected(True)
    app.processEvents()
    check(dialog._selected_branch_id == selected_id, "Tree branch selection did not reach the playback dialog.")
    dialog.time_slider.setValue(650)
    app.processEvents()
    check(dialog._selected_branch_id == selected_id, "Time refresh cleared the selected branch.")
    dialog.scope_combo.setCurrentIndex(0)
    dialog.time_slider.setValue(500)
    app.processEvents()
    with tempfile.TemporaryDirectory(prefix="rasp_temporal_export_") as export_tmp:
        export_path = Path(export_tmp) / "frame.csv"
        dialog._write_frame_csv(export_path)
        exported = export_path.read_text(encoding="utf-8-sig")
        check("history_mode" in exported.splitlines()[0], "Frame CSV lacks history mode provenance.")
        check("node_boundary_mode" in exported.splitlines()[0], "Frame CSV lacks node-boundary provenance.")
        check("branch_range_probability" in exported, "Frame CSV lacks branch probabilities.")
        check("map_area_marginal_probability" in exported, "Frame CSV lacks map marginals.")
    screenshot_path = str(os.environ.get("RASP_TEMPORAL_SCREENSHOT", "") or "").strip()
    if screenshot_path:
        dialog.show()
        app.processEvents()
        QTest.qWait(150)
        dialog._fit_views()
        app.processEvents()
        Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
        check(dialog.grab().save(screenshot_path), "Could not save the playback screenshot.")
    dialog.close()
    app.processEvents()

    bsm_config_dialog = BSMRunConfigDialog()
    bsm_config_dialog.maps_spin.setValue(2)
    check("Debug only" in bsm_config_dialog.sampling_note.text(), "BSM config lacks the debug-only warning.")
    bsm_config_dialog.maps_spin.setValue(100)
    check("Standard" in bsm_config_dialog.sampling_note.text(), "BSM config lacks the standard sampling guidance.")
    bsm_config_dialog.close()

    result_window = ResultViewWindow()
    result_window.set_leaf_state_context(leaf_states)
    result_window.set_result(result)
    result_window.set_window_title_by_method("BioGeoBEARS-DEC")
    result_window.set_temporal_playback_context(area_records=areas, range_matrix=matrix, bsm_result=bsm_result)
    check(result_window.temporal_playback_action.isEnabled(), "The Result View playback action is disabled.")
    result_window._open_temporal_playback()
    app.processEvents()
    check(result_window._temporal_playback_dialog is not None, "Result View did not open the playback dialog.")
    result_window._temporal_playback_dialog.close()
    result_window.close()
    app.processEvents()

    diva_window = ResultViewWindow()
    diva_window.set_leaf_state_context(leaf_states)
    diva_window.set_result(diva_result)
    diva_window.set_window_title_by_method("DIVA")
    diva_window.set_temporal_playback_context(
        area_records=areas,
        range_matrix=matrix,
        reference_tree=tree,
    )
    check(diva_window.temporal_playback_action.isEnabled(), "DIVA playback action is disabled.")
    diva_window.close()

    trait_named_window = ResultViewWindow()
    trait_named_window.set_result(result)
    trait_named_window.set_window_title_by_method("BayesTraits-MultiState")
    trait_named_window.set_temporal_playback_context(reference_tree=tree)
    check(
        not trait_named_window.temporal_playback_action.isEnabled(),
        "A non-geographic trait result incorrectly enabled range playback.",
    )
    trait_named_window.close()

    coordinate_map = TemporalRangeMapView()
    coordinate_map.set_areas([
        AreaSpatialRecord(
            area_code="Coordinate only",
            geometry_id="coordinate-only",
            centroid_lon=10.0,
            centroid_lat=20.0,
        )
    ])
    coordinate_map.set_probabilities({"Coordinate only": 0.75})
    check(len(coordinate_map._area_items) == 1, "Coordinate-only BayArea geography was not drawn.")
    coordinate_map.close()

    with tempfile.TemporaryDirectory(prefix="rasp_bsm_json_lookup_") as lookup_tmp:
        run_dir = Path(lookup_tmp) / "run"
        bsm_dir = run_dir / "bsm"
        bsm_dir.mkdir(parents=True)
        (bsm_dir / "bsm_summary.json").write_text("{}", encoding="utf-8")
        (run_dir / "bgb_result.json").write_text('{"node_results": []}', encoding="utf-8")
        lookup_service = BioGeoBEARSAnalysisService()
        found = lookup_service._find_existing_bgb_output_json(bsm_dir / "bsm_summary.json", bsm_dir)
        check(found.name == "bgb_result.json", "BSM JSON lookup preferred bsm_summary.json over bgb_result.json.")

    print(json.dumps({
        "checks": "passed",
        "branch_count": len(timeline.branches),
        "endpoint_branch_count": timeline.metadata.get("bgb_endpoint_branch_count"),
        "root_age": timeline.root_age,
        "midpoint_probabilities": midpoint_probs,
        "area_marginals": marginals,
        "bsm_history_segments": len(timeline.history_segments),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
