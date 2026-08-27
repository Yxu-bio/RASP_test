import json
import sys
import time
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from application.services.spatial_data_service import SpatialDataService

    data_root = root / "data"
    occurrence_path = data_root / "benchmarks" / "dore_ponerinae" / "ponerinae_occurrences_full_149k.csv"
    area_path = data_root / "spatial" / "base_layers" / "world_countries_simplified.geojson"
    workdir = root / "runs" / "phase1_spatial_benchmark" / "full_149k_world_countries"
    workdir.mkdir(parents=True, exist_ok=True)
    output_matrix_path = workdir / "encoded_matrix.csv"
    output_audit_path = workdir / "encoding_audit.csv"
    output_summary_path = workdir / "summary.json"

    if not occurrence_path.exists():
        raise FileNotFoundError(str(occurrence_path))
    if not area_path.exists():
        raise FileNotFoundError(str(area_path))

    service = SpatialDataService()
    timings = {}

    start = time.perf_counter()
    occurrences, occurrence_issues = service.import_occurrences_csv(str(occurrence_path))
    timings["import_occurrences_sec"] = time.perf_counter() - start

    start = time.perf_counter()
    areas, area_issues = service.import_area_geojson(str(area_path))
    timings["import_areas_sec"] = time.perf_counter() - start

    progress_path = workdir / "progress.log"
    if progress_path.exists():
        progress_path.unlink()

    progress_state = {"bucket": -1}

    def on_progress(done, total, message):
        percent = int(round(float(done or 0) * 100.0 / float(total or 1)))
        bucket = int(percent // 5)
        if done == 1 or done == total or bucket > progress_state["bucket"]:
            progress_state["bucket"] = bucket
            with progress_path.open("a", encoding="utf-8") as handle:
                handle.write("%s/%s %s\n" % (done, total, message))

    start = time.perf_counter()
    matrix, audit_rows = service.encode_occurrences_to_matrix(
        occurrences,
        areas,
        min_records_per_taxon_area=1,
        source_path=str(occurrence_path),
        progress_callback=on_progress,
    )
    timings["encode_sec"] = time.perf_counter() - start

    start = time.perf_counter()
    service.write_state_matrix_csv(matrix, str(output_matrix_path))
    service.write_encoding_audit_csv(audit_rows, str(output_audit_path))
    timings["write_outputs_sec"] = time.perf_counter() - start

    diagnostics = service.build_encoding_diagnostics(
        occurrences=occurrences,
        areas=areas,
        matrix=matrix,
        audit_rows=audit_rows,
    )
    summary = {
        "occurrence_path": str(occurrence_path),
        "area_path": str(area_path),
        "occurrences": len(occurrences),
        "areas": len(areas),
        "occurrence_issues": len(occurrence_issues),
        "area_issues": len(area_issues),
        "encoded_taxa": len(getattr(matrix, "taxa_names", []) or []),
        "encoded_area_columns": len(getattr(matrix, "state_columns", []) or []),
        "audit_rows": len(audit_rows),
        "coordinate_status_counts": diagnostics.get("status_counts", {}),
        "empty_area_count": len(diagnostics.get("empty_areas", []) or []),
        "taxa_all_outside_polygons_count": len(diagnostics.get("taxa_all_outside_polygons", []) or []),
        "matrix_empty_range_taxa_count": len(diagnostics.get("matrix_empty_range_taxa", []) or []),
        "timings_sec": dict((key, round(value, 3)) for key, value in timings.items()),
        "output_matrix": str(output_matrix_path),
        "output_audit": str(output_audit_path),
        "progress_log": str(progress_path),
    }
    output_summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
