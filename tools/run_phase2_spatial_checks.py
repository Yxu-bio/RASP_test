import csv
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch


def _write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict((key, row.get(key, "")) for key in headers))


def _assert_close(actual, expected, tolerance=1e-9):
    assert abs(float(actual) - float(expected)) <= float(tolerance), (actual, expected)


def _edge_by_route(network):
    return {
        "%s->%s" % (row.get("source_area", ""), row.get("target_area", "")): row
        for row in list(network.get("edge_rows", []) or [])
    }


def _layout_signature(layout):
    result = {}
    for key in ("c1", "c2", "curve", "label"):
        value = layout.get(key)
        if isinstance(value, list):
            result[key] = tuple(round(float(item), 6) for item in value)
    if "curve_offset" in layout:
        result["curve_offset"] = round(float(layout["curve_offset"]), 6)
    return result


def _set_combo_data(combo, value):
    index = combo.findData(value)
    assert index >= 0, value
    combo.setCurrentIndex(index)


def _build_phase2_fixture(workdir):
    bsm_dir = workdir / "bsm_fixture"
    bsm_dir.mkdir(parents=True, exist_ok=True)
    output_json = workdir / "bgb_result.json"
    output_json.write_text(
        json.dumps({
            "attributes": {
                "model_name": "DECJ",
                "include_null_range": True,
                "treefile": "phase2_fixture.tree",
                "tip_count": 4,
                "internal_node_count": 3,
            },
            "node_results": [
                {"clade_key": "Taxon1|Taxon2"},
                {"clade_key": "Taxon3|Taxon4"},
            ],
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    (bsm_dir / "bsm_summary.json").write_text(
        json.dumps({
            "enabled": True,
            "nummaps": 2,
            "ana_maps": 2,
            "clado_maps": 2,
            "model": "DEC+J",
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    ana_headers = [
        "sample_id", "event_type", "event_txt", "abs_event_time", "node",
        "parent_br", "current_rangetxt", "new_rangetxt", "dispersal_to",
        "extirpation_from",
    ]
    _write_csv(
        bsm_dir / "bsm_ana_events.csv",
        ana_headers,
        [
            {
                "sample_id": "1", "event_type": "d", "event_txt": "A->AB",
                "abs_event_time": "10", "node": "20", "parent_br": "b1",
                "current_rangetxt": "A", "new_rangetxt": "AB", "dispersal_to": "B",
            },
            {
                "sample_id": "2", "event_type": "d", "event_txt": "AB->ABC",
                "abs_event_time": "8", "node": "21", "parent_br": "b2",
                "current_rangetxt": "AB", "new_rangetxt": "ABC", "dispersal_to": "C",
            },
            {
                "sample_id": "2", "event_type": "a", "event_txt": "B->AB",
                "abs_event_time": "6", "node": "22", "parent_br": "b3",
                "current_rangetxt": "B", "new_rangetxt": "AB", "dispersal_to": "A",
            },
        ],
    )

    clado_headers = [
        "sample_id", "clado_event_type", "clado_event_txt", "time_bp", "node",
        "SUBparent_br", "sampled_states_AT_brbots", "sampled_states_AT_nodes",
        "clado_dispersal_to",
    ]
    _write_csv(
        bsm_dir / "bsm_clado_events.csv",
        clado_headers,
        [
            {
                "sample_id": "1", "clado_event_type": "founder (j)",
                "clado_event_txt": "A->A|C", "time_bp": "9", "node": "30",
                "SUBparent_br": "c1", "sampled_states_AT_brbots": "A",
                "sampled_states_AT_nodes": "AC", "clado_dispersal_to": "C",
            },
            {
                "sample_id": "2", "clado_event_type": "founder (j)",
                "clado_event_txt": "BC->B|A", "time_bp": "4", "node": "31",
                "SUBparent_br": "c2", "sampled_states_AT_brbots": "BC",
                "sampled_states_AT_nodes": "AB", "clado_dispersal_to": "A",
            },
            {
                "sample_id": "2", "clado_event_type": "subset sympatry",
                "clado_event_txt": "AB->A|AB", "time_bp": "2", "node": "32",
                "SUBparent_br": "c3", "sampled_states_AT_brbots": "AB",
                "sampled_states_AT_nodes": "AB",
            },
        ],
    )
    return output_json, bsm_dir


def _build_spatial_inputs():
    from domain.models.spatial_data import AreaSpatialRecord
    from domain.models.state_matrix import StateMatrix

    area_specs = [
        ("A", "Area Alpha", "#4477AA", 0.0, 0.0),
        ("B", "Area Beta", "#CC6677", 30.0, 10.0),
        ("C", "Area Gamma", "#228833", -40.0, -20.0),
    ]
    areas = []
    for code, name, color, lon, lat in area_specs:
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [lon - 5.0, lat - 5.0],
                [lon + 5.0, lat - 5.0],
                [lon + 5.0, lat + 5.0],
                [lon - 5.0, lat + 5.0],
                [lon - 5.0, lat - 5.0],
            ]],
        }
        areas.append(AreaSpatialRecord(
            area_code=code,
            geometry_id="fixture-%s" % code,
            display_name=name,
            color=color,
            centroid_lon=lon,
            centroid_lat=lat,
            source="phase2 synthetic fixture",
            geometry=geometry,
            properties={"area_code": code, "display_name": name},
        ))

    matrix = StateMatrix(
        ids=["1", "2", "3", "4"],
        taxa_names=["Taxon1", "Taxon2", "Taxon3", "Taxon4"],
        state_columns=["A", "B", "C"],
        rows=[
            {"ID": "1", "Name": "Taxon1", "A": "1", "B": "0", "C": "0"},
            {"ID": "2", "Name": "Taxon2", "A": "0", "B": "1", "C": "0"},
            {"ID": "3", "Name": "Taxon3", "A": "1", "B": "1", "C": "0"},
            {"ID": "4", "Name": "Taxon4", "A": "0", "B": "0", "C": "1"},
        ],
        source_path="phase2_fixture_matrix.csv",
    )
    return areas, matrix


def _check_parser_and_event_table(workdir, app):
    from PyQt5.QtWidgets import QFileDialog

    from gui.dialogs.bsm_event_table_dialog import BSMEventTableDialog
    from infrastructure.biogeobears.biogeobears_bsm_event_parser import BioGeoBEARSBSMEventParser

    output_json, bsm_dir = _build_phase2_fixture(workdir)
    result = BioGeoBEARSBSMEventParser().parse(
        output_json_path=str(output_json),
        bsm_dir=str(bsm_dir),
    )
    assert result.source_model_name == "BioGeoBEARS-DEC+J"
    assert result.summary["nummaps"] == 2
    assert len(result.events) == 6
    assert len(result.raw_tables["anagenetic"]) == 3
    assert len(result.raw_tables["cladogenetic"]) == 3
    assert result.event_type_counts["anagenetic:d"] == 2
    assert result.event_type_counts["anagenetic:a"] == 1
    assert result.event_type_counts["cladogenetic:founder (j)"] == 2
    assert len(result.time_series) == 6
    assert "Stochastic-map events: 6" in result.information_text

    dialog = BSMEventTableDialog(result)
    assert [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())] == [
        "Events", "Summary", "Time", "Raw tables",
    ]
    assert dialog.events_table.rowCount() == 6
    assert "Filtered events: 6 / 6" in dialog.summary_text.toPlainText()

    _set_combo_data(dialog.scope_combo, "anagenetic")
    app.processEvents()
    assert len(dialog.filtered_events) == 3
    assert dialog.events_table.rowCount() == 3
    assert "3 / 6 BSM events" in dialog.events_caption_label.text()

    dialog.time_bin_edit.setText("5")
    _set_combo_data(dialog.time_direction_combo, "descending")
    app.processEvents()
    time_rows = dialog._build_time_series(dialog.filtered_events)
    assert len(time_rows) == 2
    assert time_rows[0]["time_bin_start"] == 10.0
    assert time_rows[0]["total"] == 1
    assert time_rows[1]["time_bin_start"] == 5.0
    assert time_rows[1]["total"] == 2

    event_csv = workdir / "filtered_events.csv"
    time_csv = workdir / "filtered_time.csv"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(event_csv), "")):
        dialog._export_events_csv()
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(time_csv), "")):
        dialog._export_time_csv()
    with event_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        event_rows = list(csv.DictReader(handle))
    with time_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        exported_time_rows = list(csv.DictReader(handle))
    assert len(event_rows) == 3
    assert all(row["filter_scope"] == "anagenetic" for row in event_rows)
    assert len(exported_time_rows) == 2
    assert exported_time_rows[0]["filter_time_direction"] == "descending"

    dialog.close()
    dialog.deleteLater()
    app.processEvents()
    return result, bsm_dir


def _check_spatial_project_roundtrip(workdir, areas, matrix):
    from application.services.spatial_data_service import SpatialDataService
    from domain.models.spatial_data import (
        EncodedOccurrenceAuditRow,
        OccurrenceRecord,
        SpatialDataProject,
        SpatialQAIssue,
    )

    project = SpatialDataProject(
        occurrences=[
            OccurrenceRecord("Taxon1", 0.0, 0.0, 2, country="Fixtureland", source="phase2"),
            OccurrenceRecord("Taxon2", 10.0, 30.0, 3, country="Fixtureland", source="phase2"),
        ],
        areas=list(areas),
        occurrence_source_path="phase2_occurrences.csv",
        area_source_path="phase2_areas.geojson",
        qa_issues=[SpatialQAIssue("warning", "fixture_warning", "Synthetic QA row", row=2, taxon="Taxon1")],
        encoded_matrix=matrix,
        encoded_audit_rows=[
            EncodedOccurrenceAuditRow(2, "Taxon1", 0.0, 0.0, ["A"], "matched"),
            EncodedOccurrenceAuditRow(3, "Taxon2", 30.0, 10.0, ["B"], "matched"),
        ],
    )
    service = SpatialDataService()
    project_path = workdir / "phase2_project.rasp-spatial.json"
    service.save_project_json(project, str(project_path))
    loaded = service.load_project_json(str(project_path))
    assert loaded.occurrence_source_path == project.occurrence_source_path
    assert loaded.area_source_path == project.area_source_path
    assert len(loaded.occurrences) == 2
    assert len(loaded.areas) == 3
    assert loaded.areas[1].display_name == "Area Beta"
    assert loaded.areas[1].geometry["type"] == "Polygon"
    assert len(loaded.qa_issues) == 1
    assert loaded.qa_issues[0].code == "fixture_warning"
    assert loaded.encoded_matrix.state_columns == ["A", "B", "C"]
    assert loaded.encoded_matrix.rows == matrix.rows
    assert len(loaded.encoded_audit_rows) == 2
    assert loaded.encoded_audit_rows[0].matched_areas == ["A"]
    return loaded


def _check_network_statistics_and_exports(workdir, result, areas, matrix):
    from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService

    service = BSMDispersalNetworkService()
    network = service.build_network(
        result,
        areas=areas,
        range_matrix=matrix,
        min_mean_per_map=0.5,
    )
    assert network["nummaps"] == 2
    assert len(network["edge_rows"]) == 5
    assert len(network["display_edge_rows"]) == 3
    edges = _edge_by_route(network)
    expected = {
        "A->B": (1.0, 0.0, 1.0, 0.5),
        "A->C": (0.5, 1.0, 1.5, 0.75),
        "B->C": (0.5, 0.0, 0.5, 0.25),
        "B->A": (1.0, 0.5, 1.5, 0.75),
        "C->A": (0.0, 0.5, 0.5, 0.25),
    }
    for route, values in expected.items():
        row = edges[route]
        for key, value in zip(
            ("anagenetic_count", "founder_count", "total_count", "mean_per_map"),
            values,
        ):
            _assert_close(row[key], value)

    nodes = dict((row["area_code"], row) for row in network["node_rows"])
    _assert_close(nodes["A"]["richness"], 1.5)
    _assert_close(nodes["B"]["richness"], 1.5)
    _assert_close(nodes["C"]["richness"], 1.0)
    _assert_close(nodes["A"]["incoming_mean_per_map"], 1.0)
    _assert_close(nodes["A"]["outgoing_mean_per_map"], 1.25)

    ana_only = service.build_network(
        result, areas=areas, range_matrix=matrix, min_mean_per_map=0.0,
        include_anagenetic=True, include_founder=False,
    )
    founder_only = service.build_network(
        result, areas=areas, range_matrix=matrix, min_mean_per_map=0.0,
        include_anagenetic=False, include_founder=True,
    )
    assert set(_edge_by_route(ana_only)) == set(["A->B", "A->C", "B->C", "B->A"])
    assert set(_edge_by_route(founder_only)) == set(["A->C", "B->A", "C->A"])

    no_map = service.build_network(
        result, areas=[], range_matrix=matrix, min_mean_per_map=0.5,
    )
    assert [
        (row["source_area"], row["target_area"], row["total_count"], row["mean_per_map"])
        for row in no_map["edge_rows"]
    ] == [
        (row["source_area"], row["target_area"], row["total_count"], row["mean_per_map"])
        for row in network["edge_rows"]
    ]
    assert not no_map["edge_geojson"]["features"]
    assert len(network["edge_geojson"]["features"]) == 3
    assert len(network["node_geojson"]["features"]) == 3

    edges_csv = workdir / "network_edges.csv"
    shown_csv = workdir / "network_display_edges.csv"
    nodes_csv = workdir / "network_nodes.csv"
    geojson_path = workdir / "network.geojson"
    service.write_edges_csv(network, str(edges_csv))
    service.write_display_edges_csv(network, str(shown_csv))
    service.write_nodes_csv(network, str(nodes_csv))
    service.write_geojson(network, str(geojson_path))
    with edges_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 5
    with shown_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 3
    with nodes_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 3
    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    assert len(geojson["features"]) == 6
    assert sum(1 for row in geojson["features"] if row["geometry"]["type"] == "LineString") == 3
    assert sum(1 for row in geojson["features"] if row["geometry"]["type"] == "Point") == 3

    return network


def _check_precomputed_network(bsm_dir, expected_network, areas, matrix):
    from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
    from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService

    network_service = BSMDispersalNetworkService()
    edge_path = Path(bsm_dir) / "fig2b_dispersal_edges.csv"
    node_path = Path(bsm_dir) / "fig2b_node_richness.csv"
    network_service.write_edges_csv(expected_network, str(edge_path))
    network_service.write_nodes_csv(expected_network, str(node_path))

    loaded = BioGeoBEARSAnalysisService().load_existing_bsm_events(str(bsm_dir))
    assert loaded.summary["nummaps"] == 2
    assert len(loaded.precomputed_bsm_network_edges) == 5
    assert len(loaded.precomputed_bsm_node_rows) == 3

    network = network_service.build_network(
        loaded, areas=areas, range_matrix=matrix, min_mean_per_map=5,
    )
    assert network["nummaps"] == 2
    assert len(network["edge_rows"]) == 5
    assert len(network["display_edge_rows"]) == 0
    edges = _edge_by_route(network)
    _assert_close(edges["A->B"]["mean_per_map"], 0.5)
    _assert_close(edges["A->C"]["mean_per_map"], 0.75)
    nodes = dict((row["area_code"], row) for row in network["node_rows"])
    _assert_close(nodes["A"]["richness"], 1.5)


def _check_network_editor(workdir, app, result, areas, matrix):
    from PyQt5.QtCore import QPointF
    from PyQt5.QtWidgets import QFileDialog

    from gui.dialogs.bsm_network_map_editor_dialog import BSMNetworkMapEditorDialog

    map_dialog = BSMNetworkMapEditorDialog(result, area_records=areas, range_matrix=matrix)
    map_dialog.threshold_edit.setText("0")
    map_dialog.refresh_network(reset_layout=False)
    app.processEvents()
    assert map_dialog._active_layout_mode == "map"
    assert len(map_dialog._visible_edge_rows) == 5
    assert len(map_dialog.node_geometry) == 3
    statistics_before = [
        (row["source_area"], row["target_area"], row["total_count"], row["mean_per_map"])
        for row in map_dialog.current_network["edge_rows"]
    ]

    key = "A->C"
    original = map_dialog.edge_layout[key]
    curve = original["curve"]
    map_dialog.update_edge_control(key, "curve", QPointF(float(curve[0]) + 35.0, float(curve[1]) + 30.0))
    manual_signature = _layout_signature(map_dialog.manual_edge_layout[key])
    assert manual_signature == _layout_signature(map_dialog.edge_layout[key])

    map_dialog.width_scale_edit.setText("1.8")
    map_dialog.redraw_edges_only()
    app.processEvents()
    assert _layout_signature(map_dialog.edge_layout[key]) == manual_signature
    assert _layout_signature(map_dialog.manual_edge_layout[key]) == manual_signature

    map_dialog.show_area_labels_check.setChecked(True)
    app.processEvents()
    assert _layout_signature(map_dialog.edge_layout[key]) == manual_signature

    map_dialog.threshold_edit.setText("1.0")
    map_dialog.refresh_network(reset_layout=False)
    app.processEvents()
    assert key not in [map_dialog._edge_key(row) for row in map_dialog._visible_edge_rows]
    assert _layout_signature(map_dialog.manual_edge_layout[key]) == manual_signature
    map_dialog.threshold_edit.setText("0")
    map_dialog.refresh_network(reset_layout=False)
    app.processEvents()
    assert _layout_signature(map_dialog.edge_layout[key]) == manual_signature
    assert statistics_before == [
        (row["source_area"], row["target_area"], row["total_count"], row["mean_per_map"])
        for row in map_dialog.current_network["edge_rows"]
    ]

    layout_path = workdir / "phase2_layout.bsm-network-layout.json"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(layout_path), "")):
        map_dialog.save_layout()
    layout_payload = json.loads(layout_path.read_text(encoding="utf-8"))
    assert layout_payload["format"] == "rasp5_bsm_network_layout"
    assert layout_payload["version"] == 1
    assert _layout_signature(layout_payload["edges"][key]) == manual_signature

    restored = BSMNetworkMapEditorDialog(result, area_records=areas, range_matrix=matrix)
    restored.threshold_edit.setText("0")
    restored.refresh_network(reset_layout=False)
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(layout_path), "")):
        restored.load_layout()
    app.processEvents()
    assert _layout_signature(restored.edge_layout[key]) == manual_signature
    assert _layout_signature(restored.manual_edge_layout[key]) == manual_signature

    circle = BSMNetworkMapEditorDialog(result, area_records=[], range_matrix=matrix)
    circle.threshold_edit.setText("0")
    circle.refresh_network(reset_layout=False)
    app.processEvents()
    assert circle._active_layout_mode == "network"
    assert len(circle.node_geometry) == 3
    assert all(row.get("layout") == "circle" for row in circle.node_geometry.values())
    assert [
        (row["source_area"], row["target_area"], row["total_count"], row["mean_per_map"])
        for row in circle.current_network["edge_rows"]
    ] == statistics_before

    circle_original = circle.edge_layout[key]
    circle_curve = circle_original["curve"]
    circle.update_edge_control(
        key, "curve", QPointF(float(circle_curve[0]) - 25.0, float(circle_curve[1]) + 40.0),
    )
    circle_signature = _layout_signature(circle.manual_edge_layout[key])
    circle.width_scale_edit.setText("2.2")
    circle.redraw_edges_only()
    app.processEvents()
    assert _layout_signature(circle.edge_layout[key]) == circle_signature

    circle.edge_percentile_edit.setText("50")
    circle.redraw()
    app.processEvents()
    assert 0 < len(circle._visible_edge_rows) < 5
    assert [
        (row["source_area"], row["target_area"], row["total_count"], row["mean_per_map"])
        for row in circle.current_network["edge_rows"]
    ] == statistics_before

    for dialog in (circle, restored, map_dialog):
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt5.QtWidgets import QApplication

    workdir = root / "runs" / "phase2_spatial_checks"
    workdir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])

    timings = {}
    started = time.perf_counter()

    section = time.perf_counter()
    result, bsm_dir = _check_parser_and_event_table(workdir, app)
    timings["event_parser_table_time"] = time.perf_counter() - section

    areas, matrix = _build_spatial_inputs()
    section = time.perf_counter()
    loaded_project = _check_spatial_project_roundtrip(workdir, areas, matrix)
    timings["spatial_project_roundtrip"] = time.perf_counter() - section

    section = time.perf_counter()
    network = _check_network_statistics_and_exports(
        workdir, result, loaded_project.areas, loaded_project.encoded_matrix,
    )
    _check_precomputed_network(
        bsm_dir,
        network,
        loaded_project.areas,
        loaded_project.encoded_matrix,
    )
    timings["network_statistics_exports"] = time.perf_counter() - section

    section = time.perf_counter()
    _check_network_editor(
        workdir, app, result, loaded_project.areas, loaded_project.encoded_matrix,
    )
    timings["map_circle_layout_regressions"] = time.perf_counter() - section

    timings["total"] = time.perf_counter() - started
    report = {
        "status": "passed",
        "fixture": "deterministic two-map synthetic BioGeoBEARS BSM",
        "nummaps": result.summary.get("nummaps"),
        "normalized_events": len(result.events),
        "network_edges": len(network.get("edge_rows", [])),
        "display_edges_at_threshold_0_5": len(network.get("display_edge_rows", [])),
        "checks": [
            "BSM raw parser and normalized event schema",
            "event filtering, time binning, and CSV export",
            "Spatial Project JSON round-trip into Phase 2",
            "anagenetic/founder network aggregation and mean-per-map denominator",
            "edge/node CSV and GeoJSON export",
            "precomputed BSM network loading",
            "map/circle statistical equivalence",
            "manual curve persistence across width, labels, threshold, and layout JSON reload",
        ],
        "timings_seconds": dict((key, round(value, 4)) for key, value in timings.items()),
    }
    (workdir / "phase2_check_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print("Phase 2 spatial/BSM checks passed.")
    print("  normalized events: %s" % report["normalized_events"])
    print("  network edges: %s" % report["network_edges"])
    print("  display edges at threshold 0.5: %s" % report["display_edges_at_threshold_0_5"])
    for key in sorted(timings):
        print("  %s: %.4f s" % (key, timings[key]))
    print("  report: %s" % (workdir / "phase2_check_report.json"))


if __name__ == "__main__":
    main()
