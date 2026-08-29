import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict((key, row.get(key, "")) for key in headers))


def _read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _run_checked(command, cwd):
    completed = subprocess.run(
        [str(item) for item in command],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Command failed (%s):\n%s\n%s"
            % (completed.returncode, completed.stdout, completed.stderr)
        )
    return completed


def _check_complex_spatial_fixture(root, workdir):
    from application.services.spatial_data_service import SpatialDataService

    service = SpatialDataService()
    occurrence_path = root / "data" / "fixtures" / "spatial" / "complex_antimeridian_occurrences.csv"
    area_path = root / "data" / "fixtures" / "spatial" / "complex_antimeridian.geojson"
    occurrences, occurrence_issues = service.import_occurrences_csv(str(occurrence_path))
    areas, area_issues = service.import_area_geojson(str(area_path))
    matrix_1, audit_1 = service.encode_occurrences_to_matrix(occurrences, areas)
    matrix_2, audit_2 = service.encode_occurrences_to_matrix(occurrences, areas)

    expected = {
        "DateEast": ("D",),
        "DateWest": ("D",),
        "DateHole": (),
        "HoledOuter": ("H",),
        "HoledHole": (),
        "MultiOne": ("M",),
        "MultiTwo": ("M",),
        "Outside": (),
    }
    observed_1 = dict((row.taxon, tuple(row.matched_areas or [])) for row in audit_1)
    observed_2 = dict((row.taxon, tuple(row.matched_areas or [])) for row in audit_2)
    assert observed_1 == expected
    assert observed_2 == expected
    assert matrix_1.rows == matrix_2.rows
    assert matrix_1.state_columns == ["D", "H", "M"]

    project = service.build_project(
        occurrences=occurrences,
        areas=areas,
        occurrence_source_path=str(occurrence_path),
        area_source_path=str(area_path),
        qa_issues=list(occurrence_issues) + list(area_issues),
    )
    project.encoded_matrix = matrix_1
    project.encoded_audit_rows = audit_1
    project_path = workdir / "complex_spatial_project.rasp-spatial.json"
    service.save_project_json(project, str(project_path))
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    assert payload["format"] == service.PROJECT_FORMAT
    assert payload["version"] == service.PROJECT_VERSION
    loaded = service.load_project_json(str(project_path))
    assert loaded.encoded_matrix.rows == matrix_1.rows
    assert [row.matched_areas for row in loaded.encoded_audit_rows] == [
        row.matched_areas for row in audit_1
    ]

    bad_payload = dict(payload)
    bad_payload["version"] = 999
    try:
        service.project_from_dict(bad_payload)
    except ValueError as exc:
        assert "Unsupported spatial project version" in str(exc)
    else:
        raise AssertionError("Spatial Project accepted an incompatible explicit version.")

    return {
        "occurrences": len(occurrences),
        "areas": len(areas),
        "matched": sum(1 for values in observed_1.values() if values),
        "unmatched": sum(1 for values in observed_1.values() if not values),
        "project": str(project_path),
    }


def _check_region_builder_schema(root):
    from tools.build_region_geojson import (
        REGION_BUILDER_CONFIG_FORMAT,
        REGION_BUILDER_CONFIG_VERSION,
        REGION_BUILDER_OUTPUT_FORMAT,
        REGION_BUILDER_OUTPUT_VERSION,
        build_regions,
    )

    config_path = root / "data" / "fixtures" / "region_builder" / "simple_region_rules.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["format"] == REGION_BUILDER_CONFIG_FORMAT
    assert config["version"] == REGION_BUILDER_CONFIG_VERSION
    collection_1, notes_1, unassigned_1 = build_regions(config, config_path.parent)
    collection_2, notes_2, unassigned_2 = build_regions(config, config_path.parent)
    assert collection_1 == collection_2
    assert notes_1 == notes_2
    assert unassigned_1 == unassigned_2
    assert collection_1["metadata"]["format"] == REGION_BUILDER_OUTPUT_FORMAT
    assert collection_1["metadata"]["version"] == REGION_BUILDER_OUTPUT_VERSION

    bad_config = dict(config)
    bad_config["format"] = "not_a_rasp5_region_builder_config"
    try:
        build_regions(bad_config, config_path.parent)
    except ValueError as exc:
        assert "Unsupported Region Builder config format" in str(exc)
    else:
        raise AssertionError("Region Builder accepted an incompatible explicit format.")

    return {
        "areas": len(collection_1.get("features", []) or []),
        "build_notes": len(notes_1),
        "unassigned": len(unassigned_1),
    }


def _latest_manifest(output_root):
    manifests = sorted(
        Path(output_root).glob("*/benchmark_manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not manifests:
        raise FileNotFoundError("No Dore validation manifest was generated in %s" % output_root)
    return manifests[0]


def _check_dore_allowed_states(root, workdir):
    output_root = workdir / "dore_validate"
    output_root.mkdir(parents=True, exist_ok=True)
    _run_checked(
        [
            sys.executable,
            root / "tools" / "run_dore_bsm_benchmark.py",
            "--validate-only",
            "--output-root",
            output_root,
        ],
        root,
    )
    manifest_path = _latest_manifest(output_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "validated"
    run_dir = Path(manifest["validated"]["generated_workdir"])
    adjacency_text = (run_dir / "areas_adjacency.txt").read_text(encoding="utf-8-sig").strip()
    assert adjacency_text.endswith("END")
    geog_header = (run_dir / "geog.data").read_text(encoding="utf-8-sig").splitlines()[0]
    assert geog_header == "1534 7 (A U I R N E W)"

    rscript = root / "engines" / "R" / "bin" / "Rscript.exe"
    audit_script = root / "tools" / "audit_dore_allowed_states.R"
    completed = _run_checked(
        [
            rscript,
            audit_script,
            root / "engines" / "R" / "site-library",
            run_dir / "areas.json",
            run_dir / "input_tree.nwk",
            run_dir / "geog.data",
        ],
        root,
    )
    audit = json.loads(completed.stdout)
    expected_counts = [36, 36, 27, 20, 24, 20, 38]
    assert audit["period_count"] == 7
    assert audit["configured_all_equal"] is True
    assert audit["native_adjacency_all_equal"] is False
    assert audit["period_state_lists_only"] is True
    assert [row["expected_count"] for row in audit["periods"]] == expected_counts
    assert [row["configured_count"] for row in audit["periods"]] == expected_counts
    assert manifest["validated"]["paper_allowed_state_counts"] == expected_counts
    assert manifest["validated"]["period_state_lists_only"] is True

    audit_path = workdir / "dore_allowed_state_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "periods": audit["period_count"],
        "paper_allowed_state_counts": expected_counts,
        "native_adjacency_state_counts": [
            row["native_adjacency_count"] for row in audit["periods"]
        ],
        "manifest": str(manifest_path),
        "audit": str(audit_path),
    }


def _build_large_bsm_fixture(workdir):
    bsm_dir = workdir / "large_bsm_preview"
    bsm_dir.mkdir(parents=True, exist_ok=True)
    (bsm_dir / "bgb_result.json").write_text(
        json.dumps({
            "attributes": {
                "model_name": "DECJ",
                "include_null_range": True,
                "treefile": "wp5_preview.tree",
                "tip_count": 4,
                "internal_node_count": 3,
            },
            "node_results": [],
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    (bsm_dir / "bsm_summary.json").write_text(
        json.dumps({
            "format": "rasp5_biogeobears_bsm_summary",
            "version": 1,
            "enabled": True,
            "nummaps": 1000,
            "model": "DEC+J",
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    ana_headers = [
        "sample_id", "event_type", "event_txt", "abs_event_time", "node",
        "parent_br", "current_rangetxt", "new_rangetxt", "dispersal_to",
        "extirpation_from",
    ]
    ana_rows = []
    for index in range(6000):
        sample_id = (index % 1000) + 1
        ana_rows.append({
            "sample_id": sample_id,
            "event_type": "d",
            "event_txt": "A->AB",
            "abs_event_time": index % 20,
            "node": 20 + (index % 3),
            "parent_br": "b%s" % (index % 3),
            "current_rangetxt": "A",
            "new_rangetxt": "AB",
            "dispersal_to": "B",
        })
    _write_csv(bsm_dir / "bsm_ana_events.csv", ana_headers, ana_rows)

    clado_headers = [
        "sample_id", "clado_event_type", "clado_event_txt", "time_bp", "node",
        "SUBparent_br", "sampled_states_AT_brbots", "sampled_states_AT_nodes",
        "clado_dispersal_to",
    ]
    clado_rows = []
    for index in range(200):
        clado_rows.append({
            "sample_id": index + 1,
            "clado_event_type": "founder (j)",
            "clado_event_txt": "A->A|C",
            "time_bp": index % 20,
            "node": 30 + (index % 3),
            "SUBparent_br": "c%s" % (index % 3),
            "sampled_states_AT_brbots": "A",
            "sampled_states_AT_nodes": "AC",
            "clado_dispersal_to": "C",
        })
    _write_csv(bsm_dir / "bsm_clado_events.csv", clado_headers, clado_rows)

    _write_csv(
        bsm_dir / "fig2b_dispersal_edges.csv",
        [
            "source_area", "target_area", "anagenetic_count", "founder_count",
            "total_count", "mean_per_map",
        ],
        [
            {
                "source_area": "A", "target_area": "B", "anagenetic_count": 6000,
                "founder_count": 0, "total_count": 6000, "mean_per_map": 6,
            },
            {
                "source_area": "A", "target_area": "C", "anagenetic_count": 0,
                "founder_count": 200, "total_count": 200, "mean_per_map": 0.2,
            },
        ],
    )
    _write_csv(
        bsm_dir / "fig2b_node_richness.csv",
        ["area_code", "display_name", "richness"],
        [
            {"area_code": "A", "display_name": "Area A", "richness": 2},
            {"area_code": "B", "display_name": "Area B", "richness": 1},
            {"area_code": "C", "display_name": "Area C", "richness": 1},
        ],
    )
    return bsm_dir


def _check_large_bsm_preview(root, workdir, app):
    from PyQt5.QtWidgets import QFileDialog

    from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
    from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService
    from gui.dialogs.bsm_event_table_dialog import BSMEventTableDialog

    bsm_dir = _build_large_bsm_fixture(workdir)
    result = BioGeoBEARSAnalysisService().load_existing_bsm_events(str(bsm_dir))
    assert result.summary["nummaps"] == 1000
    assert result.summary["normalized_event_count"] == 6200
    assert result.summary["event_preview_counts"] == {
        "anagenetic": 5000,
        "cladogenetic": 200,
    }
    assert len(result.events) == 5200
    assert result.events_complete is False
    assert result.raw_tables_complete is False
    assert result.event_type_counts["anagenetic:d"] == 6000
    assert result.event_type_counts["cladogenetic:founder (j)"] == 200
    assert sum(int(row.get("total", 0) or 0) for row in result.time_series) == 6200

    network_service = BSMDispersalNetworkService()
    both = network_service.build_network(result, min_mean_per_map=0)
    ana = network_service.build_network(
        result,
        min_mean_per_map=0,
        include_anagenetic=True,
        include_founder=False,
    )
    founder = network_service.build_network(
        result,
        min_mean_per_map=0,
        include_anagenetic=False,
        include_founder=True,
    )
    assert [(row["source_area"], row["target_area"]) for row in both["edge_rows"]] == [
        ("A", "B"), ("A", "C")
    ]
    assert [(row["source_area"], row["target_area"]) for row in ana["edge_rows"]] == [("A", "B")]
    assert [(row["source_area"], row["target_area"]) for row in founder["edge_rows"]] == [("A", "C")]
    assert both["metric_definitions"]["mean_per_map"].startswith("total_count divided by nummaps")
    assert both["threshold_metric"] == "mean_per_map"
    assert both["source_assignment_method"] == network_service.SOURCE_METHOD_FRACTIONAL

    dialog = BSMEventTableDialog(result)
    app.processEvents()
    assert dialog.events_table.rowCount() == 5200
    assert "Events summarized: 6200 (full scan)" in dialog.summary_text.toPlainText()
    assert sum(int(row.get("total", 0) or 0) for row in dialog._current_time_series()) == 6200

    events_csv = workdir / "large_preview_events.csv"
    time_csv = workdir / "large_preview_time.csv"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(events_csv), "")):
        dialog._export_events_csv()
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(time_csv), "")):
        dialog._export_time_csv()
    event_rows = _read_csv(events_csv)
    time_rows = _read_csv(time_csv)
    assert len(event_rows) == 5200
    assert set(row["data_scope"] for row in event_rows) == {"unfiltered_preview_event_table"}
    assert set(row["source_event_count"] for row in event_rows) == {"6200"}
    assert set(row["exported_event_count"] for row in event_rows) == {"5200"}
    assert set(row["data_scope"] for row in time_rows) == {"full_scan_event_aggregate"}
    assert sum(int(row.get("total", 0) or 0) for row in time_rows) == 6200

    founder_index = dialog.event_type_combo.findData("founder (j)")
    assert founder_index >= 0
    dialog.event_type_combo.setCurrentIndex(founder_index)
    app.processEvents()
    assert dialog.events_table.rowCount() == 200
    assert sum(int(row.get("total", 0) or 0) for row in dialog._current_time_series()) == 200
    dialog.close()
    dialog.deleteLater()
    app.processEvents()

    return {
        "source_events": 6200,
        "preview_events": 5200,
        "full_time_total": 6200,
        "network_edges": len(both["edge_rows"]),
        "anagenetic_edges": len(ana["edge_rows"]),
        "founder_edges": len(founder["edge_rows"]),
    }


def _check_bsm_source_assignment_semantics(workdir):
    from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
    from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService

    service = BSMDispersalNetworkService()
    unique_result = SimpleNamespace(
        summary={"nummaps": 1},
        parse_warnings=[],
        raw_tables={
            "anagenetic": [{
                "event_type": "d",
                "current_rangetxt": "AB",
                "ana_dispersal_from": "B",
                "dispersal_to": "C",
            }],
            "cladogenetic": [{
                "clado_event_type": "founder (j)",
                "clado_event_txt": "AB->A|C",
                "clado_dispersal_from": "A",
                "clado_dispersal_to": "C",
            }],
        },
    )
    unique_network = service.build_network(unique_result, min_mean_per_map=0)
    unique_edges = dict(
        ((row["source_area"], row["target_area"]), row)
        for row in unique_network["edge_rows"]
    )
    assert unique_network["source_assignment_method"] == service.SOURCE_METHOD_UNIQUE
    assert unique_edges[("B", "C")]["anagenetic_count"] == 1.0
    assert unique_edges[("A", "C")]["founder_count"] == 1.0

    fallback_result = SimpleNamespace(
        summary={"nummaps": 1},
        parse_warnings=[],
        raw_tables={
            "anagenetic": [{
                "event_type": "d",
                "current_rangetxt": "AB",
                "dispersal_to": "C",
            }],
            "cladogenetic": [],
        },
    )
    fallback_network = service.build_network(fallback_result, min_mean_per_map=0)
    fallback_edges = dict(
        ((row["source_area"], row["target_area"]), row)
        for row in fallback_network["edge_rows"]
    )
    assert fallback_network["source_assignment_method"] == service.SOURCE_METHOD_FRACTIONAL
    assert fallback_edges[("A", "C")]["anagenetic_count"] == 0.5
    assert fallback_edges[("B", "C")]["anagenetic_count"] == 0.5

    mass_acc = {}
    assert service._add_split_source_edge(
        mass_acc,
        "AB",
        "B",
        ["A", "B"],
        "anagenetic",
    )
    assert mass_acc[("A", "B")]["anagenetic_count"] == 1.0

    conflicting_result = SimpleNamespace(
        summary={"nummaps": 1, "source_assignment_method": service.SOURCE_METHOD_UNIQUE},
        parse_warnings=[],
        precomputed_bsm_network_edges=[{
            "source_area": "A",
            "target_area": "B",
            "anagenetic_count": 1,
            "founder_count": 0,
            "source_assignment_method": service.SOURCE_METHOD_FRACTIONAL,
        }],
        precomputed_bsm_node_rows=[],
        raw_tables={},
    )
    conflicting_network = service.build_network(conflicting_result, min_mean_per_map=0)
    assert conflicting_network["source_assignment_method"] == service.SOURCE_METHOD_FRACTIONAL

    compact_dir = Path(workdir) / "compact_source_assignment_fixture"
    compact_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        compact_dir / "bsm_ana_events.csv",
        ["sample_id", "event_type", "current_rangetxt", "dispersal_to"],
        [{
            "sample_id": 1,
            "event_type": "d",
            "current_rangetxt": "AB",
            "dispersal_to": "C",
        }],
    )
    _write_csv(
        compact_dir / "bsm_clado_events.csv",
        [
            "sample_id", "clado_event_type", "clado_event_txt",
            "clado_dispersal_to",
        ],
        [{
            "sample_id": 1,
            "clado_event_type": "founder (j)",
            "clado_event_txt": "AB->A|C",
            "clado_dispersal_to": "C",
        }],
    )
    _write_csv(
        compact_dir / "bsm_source_assigned_dispersal_events.csv",
        ["sample_id", "event_kind", "source_area", "target_area"],
        [
            {"sample_id": 1, "event_kind": "anagenetic", "source_area": "B", "target_area": "C"},
            {"sample_id": 1, "event_kind": "founder", "source_area": "A", "target_area": "C"},
        ],
    )
    compact_edges = BioGeoBEARSAnalysisService()._aggregate_existing_bsm_network_edges(
        compact_dir,
        1,
    )
    compact_by_key = dict(
        ((row["source_area"], row["target_area"]), row)
        for row in compact_edges
    )
    assert compact_by_key[("B", "C")]["anagenetic_count"] == 1.0
    assert compact_by_key[("A", "C")]["founder_count"] == 1.0
    assert all(
        row["source_assignment_method"] == service.SOURCE_METHOD_UNIQUE
        for row in compact_edges
    )

    empty_compact_dir = Path(workdir) / "empty_compact_source_assignment_fixture"
    empty_compact_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        empty_compact_dir / "bsm_source_assigned_dispersal_events.csv",
        ["sample_id", "event_kind", "source_area", "target_area"],
        [],
    )
    _write_csv(
        empty_compact_dir / "bsm_ana_events.csv",
        ["sample_id", "event_type", "current_rangetxt", "dispersal_to"],
        [{
            "sample_id": 1,
            "event_type": "d",
            "current_rangetxt": "AB",
            "dispersal_to": "C",
        }],
    )
    empty_compact_edges = BioGeoBEARSAnalysisService()._aggregate_existing_bsm_network_edges(
        empty_compact_dir,
        1,
    )
    assert empty_compact_edges == []

    return {
        "unique_method": unique_network["source_assignment_method"],
        "unique_edges": len(unique_network["edge_rows"]),
        "fallback_method": fallback_network["source_assignment_method"],
        "fallback_edges": len(fallback_network["edge_rows"]),
        "compact_edges": len(compact_edges),
        "empty_compact_edges": len(empty_compact_edges),
        "fallback_mass": mass_acc[("A", "B")]["anagenetic_count"],
    }


def _run_phase2_gate(root):
    completed = _run_checked(
        [sys.executable, root / "tools" / "run_phase2_spatial_checks.py"],
        root,
    )
    report_path = root / "runs" / "phase2_spatial_checks" / "phase2_check_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    return {
        "report": str(report_path),
        "network_edges": report["network_edges"],
        "stdout_tail": completed.stdout.strip().splitlines()[-1],
    }


def _run_149k_benchmark(root):
    _run_checked(
        [sys.executable, root / "tools" / "run_phase1_spatial_benchmark.py"],
        root,
    )
    summary_path = (
        root
        / "runs"
        / "phase1_spatial_benchmark"
        / "full_149k_world_countries"
        / "summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["occurrences"] == summary["audit_rows"]
    assert summary["occurrences"] >= 100000
    return {
        "summary": str(summary_path),
        "occurrences": summary["occurrences"],
        "areas": summary["areas"],
        "encoded_taxa": summary["encoded_taxa"],
        "timings_sec": summary["timings_sec"],
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Run the RASP5 WP5 spatial and BSM contract gate.")
    parser.add_argument(
        "--include-149k",
        action="store_true",
        help="Also execute the full Dore 149k occurrence benchmark.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt5.QtWidgets import QApplication

    workdir = root / "runs" / "wp5_spatial_bsm_checks"
    workdir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    started = time.perf_counter()
    sections = {}
    timings = {}

    for name, callback in [
        ("complex_spatial", lambda: _check_complex_spatial_fixture(root, workdir)),
        ("region_builder", lambda: _check_region_builder_schema(root)),
        ("dore_allowed_states", lambda: _check_dore_allowed_states(root, workdir)),
        ("bsm_source_assignment", lambda: _check_bsm_source_assignment_semantics(workdir)),
        ("large_bsm_preview", lambda: _check_large_bsm_preview(root, workdir, app)),
        ("phase2_gate", lambda: _run_phase2_gate(root)),
    ]:
        section_started = time.perf_counter()
        sections[name] = callback()
        timings[name] = round(time.perf_counter() - section_started, 4)

    if args.include_149k:
        section_started = time.perf_counter()
        sections["benchmark_149k"] = _run_149k_benchmark(root)
        timings["benchmark_149k"] = round(time.perf_counter() - section_started, 4)

    report = {
        "format": "rasp5_wp5_spatial_bsm_check_report",
        "version": 1,
        "status": "passed",
        "include_149k": bool(args.include_149k),
        "sections": sections,
        "timings_seconds": timings,
        "total_seconds": round(time.perf_counter() - started, 4),
    }
    report_path = workdir / "wp5_check_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("WP5 spatial/BSM checks passed.")
    for name in sections:
        print("  %s: %.4f s" % (name, timings[name]))
    print("  report: %s" % report_path)


if __name__ == "__main__":
    main()
