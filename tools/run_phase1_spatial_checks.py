import csv
import json
import os
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt5.QtCore import QEventLoop, QTimer
    from PyQt5.QtWidgets import QApplication

    from application.services.spatial_data_service import SpatialDataService
    from application.services.taxon_match_service import TaxonMatchService
    from application.services.export_service import ExportService
    from domain.models.diva_result import DivaNodeResult, DivaResult
    from domain.models.spatial_data import AreaSpatialRecord, EncodedOccurrenceAuditRow, OccurrenceRecord, SpatialDataProject
    from gui.dialogs.spatial_data_manager_dialog import SpatialDataManagerDialog
    from gui.workers.region_geojson_builder_worker import RegionGeoJsonBuilderWorker
    from gui.workers.spatial_area_import_worker import SpatialAreaImportWorker
    from gui.workers.spatial_encoding_worker import SpatialEncodingWorker
    from gui.workers.spatial_occurrence_import_worker import SpatialOccurrenceImportWorker

    workdir = root / "runs" / "phase1_spatial_checks"
    workdir.mkdir(parents=True, exist_ok=True)

    service = SpatialDataService()

    occurrence_path = workdir / "qa_occurrences.csv"
    occurrence_path.write_text(
        "\n".join([
            "taxon,latitude,longitude",
            "Taxon1,0,0",
            "Taxon1,0,0",
            "Taxon2,0.5,0.5",
            "Taxon3,1.5,1.5",
        ]),
        encoding="utf-8",
    )
    occurrences, issues = service.import_occurrences_csv(str(occurrence_path))
    issue_codes = sorted(set(issue.code for issue in issues))
    assert "zero_zero_coordinate" in issue_codes
    assert "duplicate_taxon_coordinate" in issue_codes
    assert len(occurrences) == 4
    import_progress = []
    occurrences_with_progress, _issues_with_progress = service.import_occurrences_csv(
        str(occurrence_path),
        progress_callback=lambda done, total, message: import_progress.append((done, total, message)),
    )
    assert len(occurrences_with_progress) == 4
    assert import_progress
    assert import_progress[-1][0] == 4
    assert import_progress[-1][1] == 4

    areas_payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"area_code": "A"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-1.0, -1.0],
                        [2.0, -1.0],
                        [2.0, 2.0],
                        [-1.0, 2.0],
                        [-1.0, -1.0],
                    ], [
                        [0.25, 0.25],
                        [0.75, 0.25],
                        [0.75, 0.75],
                        [0.25, 0.75],
                        [0.25, 0.25],
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {"area_code": "B"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [10.0, 10.0],
                        [11.0, 10.0],
                        [11.0, 11.0],
                        [10.0, 11.0],
                        [10.0, 10.0],
                    ]],
                },
            },
        ],
    }
    area_path = workdir / "areas.geojson"
    area_path.write_text(json.dumps(areas_payload), encoding="utf-8")
    areas, area_issues = service.import_area_geojson(str(area_path))
    assert not [issue for issue in area_issues if issue.level == "error"]

    area_mapping_path = workdir / "area_mapping.csv"
    area_mapping_path.write_text(
        "\n".join([
            "area_code,display_name,color,group",
            "A,Area Alpha,#3366AA,Group 1",
            "B,Area Beta,#CC6633,Group 2",
        ]),
        encoding="utf-8",
    )
    area_metadata, metadata_issues = service.read_area_mapping_csv(str(area_mapping_path))
    assert not [issue for issue in metadata_issues if issue.level == "error"]
    metadata_report = service.apply_area_metadata(areas, area_metadata)
    assert metadata_report["updated"] == 2
    assert areas[0].display_name == "Area Alpha"
    assert areas[0].color == "#3366AA"
    assert areas[0].group == "Group 1"
    exported_area_mapping = workdir / "area_mapping_export.csv"
    service.write_area_mapping_csv(areas, str(exported_area_mapping))
    exported_rows, exported_issues = service.read_area_mapping_csv(str(exported_area_mapping))
    assert not [issue for issue in exported_issues if issue.level == "error"]
    assert any(row["area_code"] == "A" and row["group"] == "Group 1" for row in exported_rows)

    matrix, audit_rows = service.encode_occurrences_to_matrix(
        occurrences,
        areas,
        min_records_per_taxon_area=3,
        source_path=str(occurrence_path),
    )
    audit_by_taxon = {}
    for row in audit_rows:
        audit_by_taxon.setdefault(row.taxon, []).append(row.status)
    assert audit_by_taxon["Taxon2"] == ["unmatched"]
    assert any(row["Name"] == "Taxon1" and row["A"] == "0" for row in matrix.rows)
    diagnostics = service.build_encoding_diagnostics(
        occurrences=occurrences,
        areas=areas,
        matrix=matrix,
        audit_rows=audit_rows,
    )
    assert "B" in diagnostics["empty_areas"]
    assert "Taxon2" in diagnostics["taxa_all_outside_polygons"]
    assert "Taxon1" in diagnostics["threshold_filtered_empty_taxa"]

    audit_csv = workdir / "encoding_audit.csv"
    service.write_encoding_audit_csv(audit_rows, str(audit_csv))
    with audit_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert "coordinate_status" in reader.fieldnames

    matcher = TaxonMatchService()
    ambiguous = matcher.match_name_to_candidates("Taxon 1", ["Taxon-1", "Taxon_1"])
    assert ambiguous["status"] == "ambiguous"
    prefix = matcher.match_name_to_candidates("Taxon1_extra_runA", ["Taxon1", "Taxon1_extra"])
    assert prefix["status"] == "prefix"
    assert prefix["matched_name"] == "Taxon1_extra"

    app = QApplication.instance() or QApplication([])
    import_worker = SpatialOccurrenceImportWorker(
        service=service,
        file_path=str(occurrence_path),
    )
    import_loop = QEventLoop()
    import_state = {}
    import_worker.succeeded.connect(lambda path, records, issues: (
        import_state.update({"ok": True, "path": path, "records": len(records), "issues": len(issues)}),
        import_loop.quit(),
    ))
    import_worker.failed.connect(lambda message: (
        import_state.update({"ok": False, "error": str(message)}),
        import_loop.quit(),
    ))
    import_worker.start()
    QTimer.singleShot(10000, import_loop.quit)
    import_loop.exec_()
    assert import_state.get("ok") is True, import_state
    assert import_state["records"] == 4
    import_worker.wait(1000)

    area_import_worker = SpatialAreaImportWorker(
        service=service,
        file_path=str(area_path),
    )
    area_import_progress = []
    area_import_loop = QEventLoop()
    area_import_state = {}
    area_import_worker.progress.connect(lambda done, total, message: area_import_progress.append((done, total, message)))
    area_import_worker.succeeded.connect(lambda path, records, issues: (
        area_import_state.update({"ok": True, "path": path, "records": len(records), "issues": len(issues)}),
        area_import_loop.quit(),
    ))
    area_import_worker.failed.connect(lambda message: (
        area_import_state.update({"ok": False, "error": str(message)}),
        area_import_loop.quit(),
    ))
    area_import_worker.start()
    QTimer.singleShot(10000, area_import_loop.quit)
    area_import_loop.exec_()
    assert area_import_state.get("ok") is True, area_import_state
    assert area_import_state["records"] == 2
    assert area_import_progress
    area_import_worker.wait(1000)

    region_config_path = root / "examples" / "phase1_reference_data" / "region_builder_examples" / "simple_region_rules.json"
    region_output_path = workdir / "simple_region_builder_output.geojson"
    region_notes_path = workdir / "simple_region_builder_notes.csv"
    region_unassigned_path = workdir / "simple_region_builder_unassigned.csv"
    region_worker = RegionGeoJsonBuilderWorker(
        config_path=str(region_config_path),
        output_path=str(region_output_path),
        notes_path=str(region_notes_path),
        unassigned_path=str(region_unassigned_path),
    )
    region_loop = QEventLoop()
    region_state = {}
    region_worker.succeeded.connect(lambda result: (
        region_state.update({"ok": True, "result": result}),
        region_loop.quit(),
    ))
    region_worker.failed.connect(lambda message: (
        region_state.update({"ok": False, "error": str(message)}),
        region_loop.quit(),
    ))
    region_worker.start()
    QTimer.singleShot(20000, region_loop.quit)
    region_loop.exec_()
    assert region_state.get("ok") is True, region_state
    assert region_output_path.exists()
    assert region_notes_path.exists()
    assert region_unassigned_path.exists()
    region_areas, region_area_issues = service.import_area_geojson(str(region_output_path))
    assert len(region_areas) == 3
    assert not [issue for issue in region_area_issues if issue.level == "error"]
    region_worker.wait(1000)

    custom_region_output_path = workdir / "custom_input_region_builder_output.geojson"
    custom_region_config = {
        "name": "manual_custom_test",
        "group": "manual_custom_test",
        "source": "RASP5 Region GeoJSON Builder custom input files",
        "boundary_kind": "custom_rule_based_reference",
        "official_author_boundary": False,
        "base_geojson": str(root / "examples" / "phase1_reference_data" / "general_world_polygons" / "world_countries_simplified.geojson"),
        "base_mapping": {
            "mapping_file": str(root / "examples" / "phase1_reference_data" / "region_builder_examples" / "simple_country_mapping.csv"),
            "value_field": "match_value",
            "area_field": "area_code",
            "feature_fields": ["name"],
        },
        "rules": [],
    }
    custom_region_worker = RegionGeoJsonBuilderWorker(
        config_data=custom_region_config,
        output_path=str(custom_region_output_path),
    )
    custom_region_loop = QEventLoop()
    custom_region_state = {}
    custom_region_worker.succeeded.connect(lambda result: (
        custom_region_state.update({"ok": True, "result": result}),
        custom_region_loop.quit(),
    ))
    custom_region_worker.failed.connect(lambda message: (
        custom_region_state.update({"ok": False, "error": str(message)}),
        custom_region_loop.quit(),
    ))
    custom_region_worker.start()
    QTimer.singleShot(20000, custom_region_loop.quit)
    custom_region_loop.exec_()
    assert custom_region_state.get("ok") is True, custom_region_state
    custom_region_areas, custom_region_issues = service.import_area_geojson(str(custom_region_output_path))
    assert len(custom_region_areas) == 3
    assert not [issue for issue in custom_region_issues if issue.level == "error"]
    custom_region_worker.wait(1000)

    project = SpatialDataProject(
        occurrences=[OccurrenceRecord("Taxon%d" % i, 0.0, 0.0, i + 1) for i in range(600)],
        encoded_audit_rows=[
            EncodedOccurrenceAuditRow(i + 1, "Taxon%d" % i, 0.0, 0.0, [], "unmatched")
            for i in range(1200)
        ],
    )
    dialog = SpatialDataManagerDialog(service=service, project=project)
    assert dialog.occurrence_table.rowCount() == dialog.OCCURRENCE_PREVIEW_LIMIT
    assert dialog.audit_table.rowCount() == dialog.AUDIT_PREVIEW_LIMIT
    assert dialog.audit_table.item(0, 4).text() == "unmatched"
    assert dialog.map_widget.drawn_point_count() == 1200
    assert dialog.map_widget.drawn_area_count() == 0
    assert "outside_all_polygons=1200" in dialog.map_widget.info_text.toPlainText()
    dialog.map_widget.status_filter_checkboxes["unmatched"].setChecked(False)
    assert dialog.map_widget.drawn_point_count() == 0
    dialog.map_widget.status_filter_checkboxes["unmatched"].setChecked(True)
    assert dialog.map_widget.drawn_point_count() == 1200
    dialog.map_widget.set_point_preview_limit(75000)
    assert dialog.map_widget.point_limit_spin.maximum() >= 1000000
    assert dialog.map_widget.point_limit_spin.value() == 75000
    dialog.tabs.setCurrentWidget(dialog.occurrence_table)
    dialog.audit_table.selectRow(5)
    assert dialog.tabs.currentWidget() == dialog.map_widget
    assert "Taxon5" in dialog.map_widget.info_text.toPlainText()
    dialog._on_map_occurrence_selected(10)
    assert dialog.audit_table.currentRow() == 9
    dialog._toggle_show_all_occurrences()
    dialog._toggle_show_all_audit()
    assert dialog.occurrence_table.rowCount() == 600
    assert dialog.audit_table.rowCount() == 1200
    app.processEvents()

    area_dialog = SpatialDataManagerDialog(
        service=service,
        project=SpatialDataProject(occurrences=occurrences, areas=areas),
    )
    assert area_dialog.map_widget.drawn_area_count() == 2
    assert area_dialog.area_table.item(0, 4).text() == "Group 1"
    area_dialog.tabs.setCurrentWidget(area_dialog.area_table)
    area_dialog.area_table.selectRow(0)
    assert area_dialog.tabs.currentWidget() == area_dialog.map_widget
    assert area_dialog.map_widget.select_area_by_code("A") is True
    assert "Area code: A" in area_dialog.map_widget.info_text.toPlainText()
    assert "Group: Group 1" in area_dialog.map_widget.info_text.toPlainText()
    area_dialog._on_map_area_selected("B")
    assert area_dialog.area_table.currentRow() == 1

    export_service = ExportService()
    diva_result = DivaResult(dataset=None)
    diva_result.state_order = ["A", "B", "AB"]
    diva_result.node_results["A|B"] = DivaNodeResult(
        node_key="A|B",
        diva_node_id=20,
        terminal_spec="1-2",
        states=["AB", "A"],
        state_supports={"AB": 75.0, "A": 25.0},
        state_counts={"AB": 3.0, "A": 1.0},
    )
    node_summary_csv = workdir / "node_range_summary.csv"
    export_service.export_node_summary_csv(diva_result, str(node_summary_csv), method_name="DIVA")
    with node_summary_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert "node_id" in reader.fieldnames
    assert "top_state" in reader.fieldnames
    assert "probability_percent" in reader.fieldnames
    assert rows[0]["node_id"] == "20"
    assert rows[0]["top_state"] == "AB"
    assert rows[0]["probability_percent"] == "75"

    worker_area = AreaSpatialRecord(
        "A",
        "A",
        geometry={"type": "Polygon", "coordinates": [[
            [0.0, 0.0],
            [1.0, 0.0],
            [1.0, 1.0],
            [0.0, 1.0],
            [0.0, 0.0],
        ]]},
    )
    worker = SpatialEncodingWorker(
        service=service,
        occurrences=[
            OccurrenceRecord("Taxon1", 0.5, 0.5, 1),
            OccurrenceRecord("Taxon2", 5.0, 5.0, 2),
        ],
        areas=[worker_area],
        min_records_per_taxon_area=1,
    )
    loop = QEventLoop()
    worker_state = {}
    worker.succeeded.connect(lambda matrix, audit, diag: (
        worker_state.update({"ok": True, "taxa": len(matrix.taxa_names), "audit": len(audit), "status": diag["status_counts"]}),
        loop.quit(),
    ))
    worker.failed.connect(lambda message: (
        worker_state.update({"ok": False, "error": str(message)}),
        loop.quit(),
    ))
    worker.start()
    QTimer.singleShot(10000, loop.quit)
    loop.exec_()
    assert worker_state.get("ok") is True, worker_state
    assert worker_state["taxa"] == 2
    assert worker_state["audit"] == 2
    assert worker_state["status"].get("matched") == 1
    assert worker_state["status"].get("unmatched") == 1
    worker.wait(1000)

    print(json.dumps({
        "checks": "passed",
        "issues": issue_codes,
        "diagnostics": {
            "empty_areas": diagnostics["empty_areas"],
            "taxa_all_outside_polygons": diagnostics["taxa_all_outside_polygons"],
            "threshold_filtered_empty_taxa": diagnostics["threshold_filtered_empty_taxa"],
        },
        "workdir": str(workdir),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
