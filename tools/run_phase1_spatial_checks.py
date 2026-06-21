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
    from domain.models.spatial_data import AreaSpatialRecord, EncodedOccurrenceAuditRow, OccurrenceRecord, SpatialDataProject
    from gui.dialogs.spatial_data_manager_dialog import SpatialDataManagerDialog
    from gui.workers.spatial_encoding_worker import SpatialEncodingWorker

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
    dialog._toggle_show_all_occurrences()
    dialog._toggle_show_all_audit()
    assert dialog.occurrence_table.rowCount() == 600
    assert dialog.audit_table.rowCount() == 1200
    app.processEvents()

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
