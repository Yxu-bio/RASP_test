import json
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from application.services.spatial_data_service import SpatialDataService

    workdir = root / "runs" / "phase1_spatial_smoke"
    workdir.mkdir(parents=True, exist_ok=True)

    occurrences_path = workdir / "occurrences.csv"
    areas_path = workdir / "areas.geojson"
    output_matrix_path = workdir / "encoded_matrix.csv"
    output_area_mapping_path = workdir / "area_mapping.csv"
    output_audit_path = workdir / "encoding_audit.csv"
    output_taxon_matching_path = workdir / "taxon_matching.csv"
    output_project_path = workdir / "spatial_project.rasp-spatial.json"

    occurrences_path.write_text(
        "\n".join([
            "taxon,latitude,longitude,country,source",
            "Taxon1,0.5,0.5,X,fixture",
            "Taxon1,0.7,0.7,X,fixture",
            "Taxon2,0.5,1.5,Y,fixture",
            "Taxon3,5.0,5.0,Z,fixture",
        ]),
        encoding="utf-8",
    )
    areas_payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "A",
                "properties": {"area_code": "A", "name": "Area A"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [0.0, 0.0],
                        [1.0, 0.0],
                        [1.0, 1.0],
                        [0.0, 1.0],
                        [0.0, 0.0],
                    ]],
                },
            },
            {
                "type": "Feature",
                "id": "B",
                "properties": {"area_code": "B", "name": "Area B"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [1.0, 0.0],
                        [2.0, 0.0],
                        [2.0, 1.0],
                        [1.0, 1.0],
                        [1.0, 0.0],
                    ]],
                },
            },
        ],
    }
    areas_path.write_text(json.dumps(areas_payload), encoding="utf-8")

    service = SpatialDataService()
    occurrences, occurrence_issues = service.import_occurrences_csv(str(occurrences_path))
    areas, area_issues = service.import_area_geojson(str(areas_path))
    matrix, audit_rows = service.encode_occurrences_to_matrix(
        occurrences,
        areas,
        min_records_per_taxon_area=1,
        source_path=str(occurrences_path),
    )
    service.write_state_matrix_csv(matrix, str(output_matrix_path))
    project = service.build_project(
        occurrences=occurrences,
        areas=areas,
        occurrence_source_path=str(occurrences_path),
        area_source_path=str(areas_path),
        qa_issues=list(occurrence_issues) + list(area_issues),
    )
    project.encoded_matrix = matrix
    project.encoded_audit_rows = audit_rows
    service.write_area_mapping_csv(areas, str(output_area_mapping_path))
    service.write_encoding_audit_csv(audit_rows, str(output_audit_path))
    service.write_taxon_mapping_csv(
        tree_taxa=["Taxon1_runA", "Taxon2", "TreeOnly"],
        matrix_taxa=matrix.taxa_names,
        occurrence_taxa=[record.taxon for record in occurrences],
        file_path=str(output_taxon_matching_path),
        mode="normalized_prefix",
    )
    service.save_project_json(project, str(output_project_path))
    loaded_project = service.load_project_json(str(output_project_path))

    rows_by_taxon = dict((row["Name"], row) for row in matrix.rows)
    assert matrix.state_columns == ["A", "B"]
    assert rows_by_taxon["Taxon1"]["A"] == "1"
    assert rows_by_taxon["Taxon1"]["B"] == "0"
    assert rows_by_taxon["Taxon2"]["A"] == "0"
    assert rows_by_taxon["Taxon2"]["B"] == "1"
    assert rows_by_taxon["Taxon3"]["A"] == "0"
    assert rows_by_taxon["Taxon3"]["B"] == "0"
    assert len(audit_rows) == 4
    assert any(row.status == "unmatched" and row.taxon == "Taxon3" for row in audit_rows)
    assert output_matrix_path.exists()
    assert output_area_mapping_path.exists()
    assert output_audit_path.exists()
    assert output_taxon_matching_path.exists()
    mapping_rows = service.build_taxon_mapping_rows(
        tree_taxa=["Taxon1_runA", "Taxon2", "TreeOnly"],
        matrix_taxa=matrix.taxa_names,
        occurrence_taxa=[record.taxon for record in occurrences],
        mode="normalized_prefix",
    )
    assert any(
        row["source_taxon"] == "Taxon1_runA"
        and row["matched_taxon"] == "Taxon1"
        and row["match_status"] == "prefix"
        for row in mapping_rows
    )
    assert output_project_path.exists()
    assert len(loaded_project.occurrences) == len(occurrences)
    assert len(loaded_project.areas) == len(areas)
    assert loaded_project.encoded_matrix is not None
    assert loaded_project.encoded_matrix.state_columns == ["A", "B"]

    summary = {
        "occurrences": len(occurrences),
        "areas": len(areas),
        "occurrence_issues": len(occurrence_issues),
        "area_issues": len(area_issues),
        "taxa": len(matrix.taxa_names),
        "columns": matrix.state_columns,
        "output": str(output_matrix_path),
        "area_mapping": str(output_area_mapping_path),
        "audit": str(output_audit_path),
        "taxon_matching": str(output_taxon_matching_path),
        "project": str(output_project_path),
        "audit_statuses": sorted(set(row.status for row in audit_rows)),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
