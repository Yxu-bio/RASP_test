import csv
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap import ApplicationBootstrap

ApplicationBootstrap().inject_vendor_packages()

from ete3 import Tree

from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
from application.services.biogeobears_model_test_service import BioGeoBEARSModelTestService
from application.services.dec_analysis_service import DECAnalysisService
from application.services.diva_analysis_service import DivaAnalysisService
from application.services.export_service import ExportService
from application.services.heuristic_event_summary_service import HeuristicEventSummaryService
from application.services.preflight_validation_service import PreflightValidationService
from application.services.sdec_analysis_service import SDECAnalysisService
from application.services.sdiva_analysis_service import SDivaAnalysisService
from application.services.tree_collection_prepare_service import TreeCollectionPrepareService
from domain.models.sbgb_config import SBGBConfig
from domain.models.sdec_config import SDECConfig
from domain.models.sdiva_config import SDivaConfig, infer_sdiva_area_names
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.tree.tree_reader import TreeReader


RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_ROOT = PROJECT_ROOT / "runs" / "phase0_smoke" / RUN_STAMP
DOCS_DIR = PROJECT_ROOT / "docs"
REPORT_PATH = DOCS_DIR / "phase0_smoke_latest.md"
STATE_PATH = RUN_ROOT / "phase0_smoke_state.json"


def log(message):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    text = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message)
    print(text, flush=True)
    with (RUN_ROOT / "phase0_smoke.log").open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def find_psychotria_data_dir():
    for child in PROJECT_ROOT.iterdir():
        if not child.is_dir():
            continue
        if not child.name.startswith("Psychotria"):
            continue
        if (child / "Psychotria.tree").exists() and (child / "distribution.csv").exists() and (child / "dataset.trees").exists():
            return child
    fallback = PROJECT_ROOT / "examples" / "Psychotria" / "Trees_States"
    if (fallback / "Psychotria.tree").exists():
        return fallback
    raise FileNotFoundError("Psychotria test data was not found.")


def parse_tree(path):
    text = TreeReader().read_tree(str(path))
    return Tree(text, format=1), text


def load_tree_entries(path, limit):
    collection = TreeReader().read_tree_collection(str(path))
    prepared = TreeCollectionPrepareService().prepare(
        collection,
        pre_burnin=0,
        post_burnin=0,
        enable_random_sampling=False,
        random_sample_size=0,
    )
    entries = list(prepared.analysis_entries or [])
    return collection, prepared, entries[: int(limit)]


def estimate_root_age(tree):
    try:
        _leaf, distance = tree.get_farthest_leaf()
        if float(distance) > 0:
            return "%g" % float(distance)
    except Exception:
        pass
    return ""


def infer_taxon_ranges(matrix, area_names, dec_service):
    detected_areas, rows = dec_service.dataset_builder._collect_area_names_and_rows(matrix)
    values = []
    for _taxon, bits in rows:
        values.append("".join(area for area, bit in zip(detected_areas, bits) if str(bit) == "1"))
    return [value for value in values if value]


def task_record(name):
    return {
        "name": name,
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": None,
        "summary": {},
        "error": "",
    }


def save_state(payload):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(payload)


def run_task(payload, name, callback):
    log("START %s" % name)
    record = task_record(name)
    payload["tasks"].append(record)
    save_state(payload)
    started = time.perf_counter()
    try:
        record["summary"] = callback() or {}
        record["status"] = "ok"
        log("OK %s" % name)
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        record["traceback"] = traceback.format_exc()
        log("FAILED %s: %s" % (name, exc))
    finally:
        record["finished_at"] = datetime.now().isoformat(timespec="seconds")
        record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        save_state(payload)


def summarize_result(result):
    return {
        "class": type(result).__name__,
        "node_count": len(getattr(result, "node_results", {}) or {}),
        "warning_count": len(getattr(result, "parse_warnings", []) or []),
        "warnings": list(getattr(result, "parse_warnings", []) or [])[:10],
        "run_dir": str(getattr(result, "run_dir", "") or ""),
        "has_information": bool(str(getattr(result, "information_text", "") or "").strip()),
        "has_time_data": bool(getattr(result, "heuristic_time_data", None)),
    }


def assert_node_result(result, method_name):
    node_count = len(getattr(result, "node_results", {}) or {})
    if node_count <= 0:
        raise AssertionError("%s produced no node results" % method_name)
    return result


def export_node_summary(result, method_name):
    out = RUN_ROOT / ("%s_node_summary.csv" % method_name.lower().replace(" ", "_").replace("+", "j"))
    ExportService().export_node_summary_csv(result, str(out), method_name=method_name)
    rows = list(csv.DictReader(out.open("r", encoding="utf-8-sig", newline="")))
    if not rows:
        raise AssertionError("node summary CSV is empty: %s" % out)
    required = {"method", "node_id", "clade_key", "top_state", "top_prob", "state", "probability", "rank"}
    missing = sorted(required - set(rows[0].keys()))
    if missing:
        raise AssertionError("node summary CSV missing columns: %s" % ", ".join(missing))
    return str(out), len(rows)


def summarize_model_test(result):
    return {
        "class": type(result).__name__,
        "effective_model_count": int(getattr(result, "effective_model_count", 0) or 0),
        "failed_model_count": int(getattr(result, "failed_model_count", 0) or 0),
        "best_model_name": str(getattr(result, "best_model_name", "") or ""),
        "criterion_used": str(getattr(result, "criterion_used", "") or ""),
        "teststable_path": str(getattr(result, "teststable_path", "") or ""),
        "rows": [
            {
                "model": row.model_name,
                "success": bool(row.success),
                "aicc": row.aicc,
                "weight": row.weight,
                "error": str(row.error_message or "")[:160],
            }
            for row in list(getattr(result, "rows", []) or [])
        ],
    }


def summarize_bsm(result):
    event_count = len(getattr(result, "events", []) or [])
    raw_tables = dict(getattr(result, "raw_tables", {}) or {})
    if event_count <= 0:
        raise AssertionError("BSM generated no parsed events")
    if not raw_tables:
        raise AssertionError("BSM generated no raw tables")
    return {
        "class": type(result).__name__,
        "event_count": event_count,
        "raw_tables": {name: len(rows or []) for name, rows in raw_tables.items()},
        "summary": dict(getattr(result, "summary", {}) or {}),
        "warnings": list(getattr(result, "parse_warnings", []) or [])[:10],
    }


def summarize_preflight(report):
    issues = list(getattr(report, "issues", []) or [])
    blockers = list(getattr(report, "blockers", []) or [])
    if blockers:
        raise AssertionError("; ".join("%s: %s" % (issue.code, issue.message) for issue in blockers[:5]))
    return {
        "ok": bool(getattr(report, "ok", False)),
        "issue_count": len(issues),
        "warnings": [
            "%s: %s" % (issue.code, issue.message)
            for issue in list(getattr(report, "warnings", []) or [])[:10]
        ],
    }


def write_report(payload):
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 0 Smoke Test Latest",
        "",
        "- Started: `%s`" % payload.get("started_at", ""),
        "- Finished: `%s`" % payload.get("finished_at", ""),
        "- Run root: `%s`" % payload.get("run_root", ""),
        "- Data dir: `%s`" % payload.get("data_dir", ""),
        "- Tree set sample size: `%s`" % payload.get("tree_set_sample_size", ""),
        "",
        "## Tasks",
        "",
    ]
    for task in payload.get("tasks", []):
        lines.append("### %s" % task.get("name", ""))
        lines.append("")
        lines.append("- Status: `%s`" % task.get("status", ""))
        lines.append("- Elapsed seconds: `%s`" % task.get("elapsed_seconds", ""))
        if task.get("error"):
            lines.append("- Error: `%s`" % str(task.get("error", "")).replace("\n", " ")[:500])
        summary = task.get("summary", {}) or {}
        for key, value in summary.items():
            text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
            lines.append("- %s: `%s`" % (key, text[:600]))
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    data_dir = find_psychotria_data_dir()
    tree, tree_text = parse_tree(data_dir / "Psychotria.tree")
    matrix = CsvMatrixReader().read(str(data_dir / "distribution.csv"))
    _collection, prepared, tree_entries = load_tree_entries(data_dir / "dataset.trees", limit=25)

    dec_service = DECAnalysisService(
        engine_path=PROJECT_ROOT / "engines" / "lagrange-ng" / "lagrange-ng.exe",
        work_root=RUN_ROOT / "dec",
    )
    area_names = infer_sdiva_area_names(matrix)
    taxon_ranges = infer_taxon_ranges(matrix, area_names, dec_service)
    root_age = estimate_root_age(tree)
    heuristic = HeuristicEventSummaryService()

    payload = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": "",
        "run_root": str(RUN_ROOT),
        "data_dir": str(data_dir),
        "tree_set_sample_size": len(tree_entries),
        "tree_collection": {
            "raw_count": int(getattr(_collection, "raw_tree_count", 0) or 0),
            "analysis_count": int(getattr(prepared, "analysis_count", 0) or 0),
        },
        "tasks": [],
    }
    save_state(payload)

    sdiva_config = SDivaConfig.default_for_areas(area_names)
    sdiva_config.threads = 2

    dec_config = SDECConfig.default_for_areas(area_names)
    dec_config.root_age = root_age
    dec_config.threads = 1

    sdec_config = SDECConfig.default_for_areas(area_names)
    sdec_config.root_age = root_age
    sdec_config.threads = 2

    bgb_config = SBGBConfig.default_for_areas(area_names, taxon_ranges)
    bgb_config.root_age = root_age
    bgb_config.cores = 1
    bgb_config.model_name = "DEC"

    diva_service = DivaAnalysisService(project_root=str(PROJECT_ROOT))
    sdiva_service = SDivaAnalysisService(project_root=str(PROJECT_ROOT))
    sdec_service = SDECAnalysisService(dec_service, project_root=PROJECT_ROOT)
    bgb_service = BioGeoBEARSAnalysisService(
        rscript_path=PROJECT_ROOT / "engines" / "R" / "bin" / "Rscript.exe",
        wrapper_script_path=PROJECT_ROOT / "engines" / "biogeobears" / "bgb_runner.R",
        work_root=RUN_ROOT / "biogeobears",
        site_library_path=PROJECT_ROOT / "engines" / "R" / "site-library",
    )
    model_test_service = BioGeoBEARSModelTestService(bgb_service)
    preflight = PreflightValidationService()

    run_task(
        payload,
        "P0-001 preflight range analysis",
        lambda: summarize_preflight(
            preflight.validate_range_analysis(method_name="DIVA", tree=tree, matrix=matrix, config=sdiva_config)
        ),
    )

    def run_diva():
        result = diva_service.run(tree, matrix, tree_name="Psychotria", distribution_name="distribution", config=sdiva_config, timeout_seconds=300)
        result = heuristic.attach(result=result, tree=tree, range_matrix=matrix, method_name="DIVA")
        assert_node_result(result, "DIVA")
        path, row_count = export_node_summary(result, "DIVA")
        summary = summarize_result(result)
        summary["node_summary_csv"] = path
        summary["node_summary_rows"] = row_count
        return summary

    run_task(payload, "P0-004/P0-005 DIVA node result and export", run_diva)

    def run_sdiva():
        result = sdiva_service.run(
            tree_entries=tree_entries,
            matrix=matrix,
            reference_tree=tree,
            distribution_name="distribution",
            config=sdiva_config,
        )
        result = heuristic.attach(result=result, tree=tree, range_matrix=matrix, method_name="S-DIVA")
        assert_node_result(result, "S-DIVA")
        path, row_count = export_node_summary(result, "S-DIVA")
        summary = summarize_result(result)
        summary["input_tree_count"] = int(getattr(result, "tree_count_total", 0) or 0)
        summary["node_summary_csv"] = path
        summary["node_summary_rows"] = row_count
        return summary

    run_task(payload, "P0-004/P0-005 S-DIVA sampled node result and export", run_sdiva)

    def run_dec():
        result = dec_service.analyze(tree=tree, matrix=matrix, run_name="phase0_dec", scale_tree_to_root_age=True, config=dec_config)
        result = heuristic.attach(result=result, tree=tree, range_matrix=matrix, method_name="DEC")
        assert_node_result(result, "DEC")
        path, row_count = export_node_summary(result, "DEC")
        summary = summarize_result(result)
        summary["node_summary_csv"] = path
        summary["node_summary_rows"] = row_count
        return summary

    run_task(payload, "P0-004/P0-005 DEC node result and export", run_dec)

    def run_sdec():
        result = sdec_service.analyze(
            reference_tree=tree,
            matrix=matrix,
            tree_entries=tree_entries,
            run_name_prefix="phase0_sdec",
            config=sdec_config,
        )
        result = heuristic.attach(result=result, tree=tree, range_matrix=matrix, method_name="S-DEC")
        assert_node_result(result, "S-DEC")
        path, row_count = export_node_summary(result, "S-DEC")
        summary = summarize_result(result)
        summary["node_summary_csv"] = path
        summary["node_summary_rows"] = row_count
        return summary

    run_task(payload, "P0-004/P0-005 S-DEC sampled node result and export", run_sdec)

    def run_bgb_dec():
        result = bgb_service.analyze(tree=tree, matrix=matrix, config=bgb_config, run_name="phase0_bgb_dec", scale_tree_to_root_age=True)
        result = heuristic.attach(result=result, tree=tree, range_matrix=matrix, method_name="BioGeoBEARS-DEC")
        assert_node_result(result, "BioGeoBEARS DEC")
        path, row_count = export_node_summary(result, "BioGeoBEARS-DEC")
        summary = summarize_result(result)
        summary["node_summary_csv"] = path
        summary["node_summary_rows"] = row_count
        return summary

    run_task(payload, "P0-002/P0-004/P0-005 BioGeoBEARS DEC result and export", run_bgb_dec)

    run_task(
        payload,
        "P0-003 BioGeoBEARS model test six models",
        lambda: summarize_model_test(
            model_test_service.analyze(
                tree=tree,
                matrix=matrix,
                config=bgb_config,
                run_name_prefix="phase0_bgb_model_test",
            )
        ),
    )

    run_task(
        payload,
        "P0-006/P0-007/P0-008/P0-009 BioGeoBEARS BSM events",
        lambda: summarize_bsm(
            bgb_service.generate_bsm_events(
                tree=tree,
                matrix=matrix,
                config=bgb_config,
                run_name="phase0_bgb_bsm",
                nummaps=5,
                seed=12345,
                maxtries_per_branch=40000,
                scale_tree_to_root_age=True,
            )
        ),
    )

    payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
    save_state(payload)
    failed = [task for task in payload["tasks"] if task.get("status") != "ok"]
    if failed:
        raise SystemExit("Phase 0 smoke failed: %s" % ", ".join(task["name"] for task in failed))
    log("Phase 0 smoke passed. Report: %s" % REPORT_PATH)


if __name__ == "__main__":
    main()
