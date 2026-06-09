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

from application.services.bayarea_analysis_service import BayAreaAnalysisService
from application.services.bayestraits_analysis_service import BayesTraitsAnalysisService
from application.services.bbm_analysis_service import BBMAnalysisService
from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
from application.services.biogeobears_model_test_service import BioGeoBEARSModelTestService
from application.services.dec_analysis_service import DECAnalysisService
from application.services.diva_analysis_service import DivaAnalysisService
from application.services.result_schema_adapter import ResultSchemaAdapterFactory
from application.services.sbgb_analysis_service import SBGBAnalysisService
from application.services.sdec_analysis_service import SDECAnalysisService
from application.services.sdiva_analysis_service import SDivaAnalysisService
from application.services.tree_collection_prepare_service import TreeCollectionPrepareService
from domain.models.bayarea_config import BayAreaConfig
from domain.models.bayestraits_config import BayesTraitsConfig
from domain.models.bbm_config import BBMConfig
from domain.models.sbgb_config import SBGBConfig
from domain.models.sdec_config import SDECConfig
from domain.models.sdiva_config import SDivaConfig, infer_sdiva_area_names
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.tree.tree_reader import TreeReader


RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_ROOT = PROJECT_ROOT / "runs" / "benchmarks" / ("psychotria_%s" % RUN_STAMP)
DOCS_DIR = PROJECT_ROOT / "docs"
STATE_PATH = RUN_ROOT / "benchmark_state.json"
REPORT_PATH = DOCS_DIR / ("psychotria_benchmark_%s.md" % RUN_STAMP)
PROGRESS_PATH = RUN_ROOT / "progress.log"


def log(message):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    text = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message)
    print(text, flush=True)
    with PROGRESS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def find_data_dir():
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
    raise FileNotFoundError("Psychotria benchmark data was not found.")


def parse_tree(path):
    text = TreeReader().read_tree(str(path))
    return Tree(text, format=1), text


def load_tree_entries(path):
    collection = TreeReader().read_tree_collection(str(path))
    prepared = TreeCollectionPrepareService().prepare(
        collection,
        pre_burnin=0,
        post_burnin=0,
        enable_random_sampling=False,
        random_sample_size=0,
    )
    return collection, prepared


def estimate_root_age(tree):
    try:
        _leaf, distance = tree.get_farthest_leaf()
        if float(distance) > 0:
            return "%g" % float(distance)
    except Exception:
        pass
    return ""


def infer_taxon_ranges(matrix, area_names, dec_service):
    try:
        detected_areas, rows = dec_service.dataset_builder._collect_area_names_and_rows(matrix)
        if list(detected_areas) == list(area_names):
            values = []
            for _taxon, bits in rows:
                values.append("".join(area for area, bit in zip(detected_areas, bits) if str(bit) == "1"))
            return [value for value in values if value]
    except Exception:
        pass
    return []


def load_coordinates(area_names):
    candidates = [
        PROJECT_ROOT / "Sample" / "Psychotria" / "coordinates.csv",
        PROJECT_ROOT / "examples" / "Psychotria" / "coordinates.csv",
    ]
    coords = {area: (0.0, 0.0) for area in area_names}
    for path in candidates:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if len(row) < 3:
                    continue
                area = str(row[0]).strip()
                if area not in coords:
                    continue
                try:
                    coords[area] = (float(row[1]), float(row[2]))
                except Exception:
                    pass
        return coords, str(path)
    return coords, ""


def top_node_rows(result, method_name, limit=8):
    try:
        adapter = ResultSchemaAdapterFactory.create(result)
        standard = adapter.to_standard_result(result=result, method_name=method_name)
        payloads = list(standard.node_payloads.values())
    except Exception:
        return []
    payloads.sort(key=lambda item: node_sort_key(item.display_node_id, item.clade_key))
    rows = []
    for payload in payloads[:limit]:
        rows.append(
            {
                "node": str(payload.display_node_id or payload.clade_key),
                "summary": str(payload.state_summary or payload.state_text or ""),
                "supporting_trees": int(payload.supporting_tree_count or 0),
                "total_trees": int(payload.total_tree_count or 0),
            }
        )
    return rows


def node_sort_key(display_id, clade_key):
    text = str(display_id or "").strip()
    try:
        return (0, int(text))
    except Exception:
        return (1, text or str(clade_key or ""))


def summarize_result(result, method_name):
    stats = dict(getattr(result, "model_statistics", {}) or {})
    return {
        "method_name": method_name,
        "result_class": type(result).__name__,
        "model_name": str(getattr(result, "model_name", method_name) or method_name),
        "node_count": len(getattr(result, "node_results", {}) or {}),
        "warning_count": len(getattr(result, "parse_warnings", []) or []),
        "warnings": list(getattr(result, "parse_warnings", []) or [])[:20],
        "input_tree_count": int(getattr(result, "input_tree_count", getattr(result, "tree_count_total", 1)) or 1),
        "effective_tree_count": int(getattr(result, "effective_tree_count", getattr(result, "tree_count_total", 1)) or 1),
        "run_dir": str(getattr(result, "run_dir", "") or extract_workdir(getattr(result, "result_note", ""))),
        "analysis_log_path": str(getattr(result, "analysis_log_path", "") or ""),
        "state_order": list(getattr(result, "state_order", []) or []),
        "model_statistics": stats,
        "top_nodes": top_node_rows(result, method_name),
    }


def extract_workdir(text):
    marker = "workdir="
    text = str(text or "")
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].split()[0]


def summarize_model_test(result):
    return {
        "method_name": "BioGeoBEARS Model Test",
        "result_class": type(result).__name__,
        "effective_model_count": int(getattr(result, "effective_model_count", 0) or 0),
        "failed_model_count": int(getattr(result, "failed_model_count", 0) or 0),
        "warnings": list(getattr(result, "warnings", []) or [])[:20],
        "rows": [
            {
                "model": row.model_name,
                "display": row.display_name,
                "success": bool(row.success),
                "lnL": row.log_likelihood,
                "AIC": row.aic,
                "AICc": row.aicc,
                "weight": row.weight,
                "workdir": row.workdir,
                "error": row.error_message,
            }
            for row in list(getattr(result, "rows", []) or [])
        ],
    }


def save_state(payload):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(payload)


def write_report(payload):
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("# Psychotria Benchmark Report")
    lines.append("")
    lines.append("- Started: `%s`" % payload.get("started_at", ""))
    lines.append("- Finished: `%s`" % payload.get("finished_at", ""))
    lines.append("- Data dir: `%s`" % payload.get("data_dir", ""))
    lines.append("- Tree entries: raw=%s, bifurcating=%s, analysis=%s" % (
        payload.get("tree_collection", {}).get("raw_count", ""),
        payload.get("tree_collection", {}).get("bifurcating_count", ""),
        payload.get("tree_collection", {}).get("analysis_count", ""),
    ))
    lines.append("- Areas: `%s`" % ", ".join(payload.get("area_names", [])))
    lines.append("- Root age estimate: `%s`" % payload.get("root_age", ""))
    lines.append("")
    lines.append("## Methods")
    lines.append("")
    for item in payload.get("results", []):
        lines.append("### %s" % item.get("name", ""))
        lines.append("")
        lines.append("- Status: `%s`" % item.get("status", ""))
        lines.append("- Elapsed seconds: `%s`" % item.get("elapsed_seconds", ""))
        if item.get("error"):
            lines.append("- Error: `%s`" % item.get("error", "").replace("\n", " ")[:500])
        summary = item.get("summary", {}) or {}
        if summary:
            for key in ["model_name", "node_count", "warning_count", "input_tree_count", "effective_tree_count", "run_dir", "analysis_log_path"]:
                if key in summary and summary.get(key) not in (None, ""):
                    lines.append("- %s: `%s`" % (key, summary.get(key)))
            if summary.get("top_nodes"):
                lines.append("")
                lines.append("| Node | Summary | Trees |")
                lines.append("|---|---|---|")
                for row in summary["top_nodes"]:
                    lines.append("| %s | %s | %s/%s |" % (
                        row.get("node", ""),
                        str(row.get("summary", "")).replace("|", "\\|"),
                        row.get("supporting_trees", ""),
                        row.get("total_trees", ""),
                    ))
            if summary.get("rows"):
                lines.append("")
                lines.append("| Model | Success | lnL | AICc | Weight | Error |")
                lines.append("|---|---:|---:|---:|---:|---|")
                for row in summary["rows"]:
                    lines.append("| %s | %s | %s | %s | %s | %s |" % (
                        row.get("display", row.get("model", "")),
                        row.get("success", ""),
                        row.get("lnL", ""),
                        row.get("AICc", ""),
                        row.get("weight", ""),
                        str(row.get("error", "") or "").replace("|", "\\|")[:120],
                    ))
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_task(payload, name, callback):
    log("START %s" % name)
    started = time.perf_counter()
    record = {
        "name": name,
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": None,
        "summary": {},
        "error": "",
    }
    payload["results"].append(record)
    save_state(payload)
    try:
        summary = callback()
        record["summary"] = summary or {}
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


def main():
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    log("Psychotria benchmark run root: %s" % RUN_ROOT)

    data_dir = find_data_dir()
    tree_path = data_dir / "Psychotria.tree"
    matrix_path = data_dir / "distribution.csv"
    trees_path = data_dir / "dataset.trees"

    reference_tree, reference_tree_text = parse_tree(tree_path)
    matrix = CsvMatrixReader().read(str(matrix_path))
    collection, prepared = load_tree_entries(trees_path)
    tree_entries = list(prepared.analysis_entries or [])

    dec_service = DECAnalysisService(
        engine_path=PROJECT_ROOT / "engines" / "lagrange-ng" / "lagrange-ng.exe",
        work_root=RUN_ROOT / "dec",
    )
    area_names = infer_sdiva_area_names(matrix)
    taxon_ranges = infer_taxon_ranges(matrix, area_names, dec_service)
    root_age = estimate_root_age(reference_tree)
    coordinates, coordinates_path = load_coordinates(area_names)

    payload = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": "",
        "run_root": str(RUN_ROOT),
        "data_dir": str(data_dir),
        "tree_path": str(tree_path),
        "matrix_path": str(matrix_path),
        "trees_path": str(trees_path),
        "coordinates_path": coordinates_path,
        "area_names": area_names,
        "taxon_ranges": taxon_ranges,
        "root_age": root_age,
        "reference_tree": reference_tree_text,
        "tree_collection": {
            "raw_count": int(collection.raw_tree_count),
            "loaded_count": int(prepared.loaded_count),
            "parse_error_count": int(prepared.parse_error_count),
            "bifurcating_count": int(prepared.bifurcating_count),
            "analysis_count": int(prepared.analysis_count),
        },
        "results": [],
    }
    save_state(payload)

    diva_service = DivaAnalysisService(project_root=str(PROJECT_ROOT))
    sdiva_service = SDivaAnalysisService(project_root=str(PROJECT_ROOT))
    sdec_service = SDECAnalysisService(dec_service, project_root=PROJECT_ROOT)
    bgb_service = BioGeoBEARSAnalysisService(
        rscript_path=PROJECT_ROOT / "engines" / "R" / "bin" / "Rscript.exe",
        wrapper_script_path=PROJECT_ROOT / "engines" / "biogeobears" / "bgb_runner.R",
        work_root=RUN_ROOT / "biogeobears",
        site_library_path=PROJECT_ROOT / "engines" / "R" / "site-library",
    )
    sbgb_service = SBGBAnalysisService(bgb_service, project_root=PROJECT_ROOT)
    model_test_service = BioGeoBEARSModelTestService(bgb_service)
    bayarea_service = BayAreaAnalysisService(
        executable_path=PROJECT_ROOT / "engines" / "bayarea" / "bin" / "bayarea.exe",
        work_root=RUN_ROOT / "bayarea",
    )
    bbm_service = BBMAnalysisService(
        executable_path=PROJECT_ROOT / "engines" / "mrbayes" / "mb.3.2.7-win32.exe",
        work_root=RUN_ROOT / "bbm",
    )
    bayestraits_service = BayesTraitsAnalysisService(
        executable_path=PROJECT_ROOT / "engines" / "bayestraits" / "BayesTraitsV5.exe",
        work_root=RUN_ROOT / "bayestraits",
    )

    sdiva_config = SDivaConfig.default_for_areas(area_names)
    sdiva_config.threads = 4

    dec_config = SDECConfig.default_for_areas(area_names)
    dec_config.root_age = root_age
    dec_config.threads = 1

    sdec_config = SDECConfig.default_for_areas(area_names)
    sdec_config.root_age = root_age
    sdec_config.threads = 4

    bgb_base_config = SBGBConfig.default_for_areas(area_names, taxon_ranges)
    bgb_base_config.root_age = root_age
    bgb_base_config.cores = 4
    bgb_base_config.model_name = "DEC"

    bayarea_config = BayAreaConfig.default_for_areas(area_names)
    bayarea_config.coordinates = coordinates
    bayarea_config.chain_length = 5000000
    bayarea_config.sample_frequency = 1000
    bayarea_config.burnin = 0
    bayarea_config.model_type = "DISTANCE_NORM"

    bbm_node_records = bbm_service.dataset_builder.build_node_records(
        reference_tree,
        bbm_service.dataset_builder._collect_taxon_ids(
            matrix,
            [name for name in reference_tree.get_leaf_names()],
        ),
    )
    bbm_node_ids = [
        str(record.get("display_node_id", "")).strip()
        for record in bbm_node_records
        if str(record.get("display_node_id", "")).strip()
    ]
    bbm_config = BBMConfig.default_for_areas(area_names, node_ids=bbm_node_ids)

    bayestraits_node_records = bayestraits_service.dataset_builder.build_node_records(
        reference_tree,
        bayestraits_service.dataset_builder._collect_taxon_ids(
            matrix,
            list(reference_tree.get_leaf_names()),
        ),
    )
    bayestraits_node_ids = [
        str(record.get("display_node_id", "")).strip()
        for record in bayestraits_node_records
        if str(record.get("display_node_id", "")).strip()
    ]
    trait_columns = list(getattr(matrix, "state_columns", []) or [])
    bayestraits_config = BayesTraitsConfig.default_for_columns(trait_columns, node_ids=bayestraits_node_ids)
    bayestraits_config.analysis_method = "ML"
    bayestraits_config.ml_tries = 10
    bayestraits_config.use_tree_collection = True

    run_task(
        payload,
        "DIVA",
        lambda: summarize_result(
            diva_service.run(
                reference_tree,
                matrix,
                tree_name="psychotria",
                distribution_name="distribution",
                config=sdiva_config,
                timeout_seconds=300,
            ),
            "DIVA",
        ),
    )

    run_task(
        payload,
        "S-DIVA full tree set",
        lambda: summarize_result(
            sdiva_service.run(
                tree_entries=tree_entries,
                matrix=matrix,
                reference_tree=reference_tree,
                distribution_name="distribution",
                config=sdiva_config,
            ),
            "S-DIVA",
        ),
    )

    run_task(
        payload,
        "DEC",
        lambda: summarize_result(
            dec_service.analyze(
                tree=reference_tree,
                matrix=matrix,
                run_name="psychotria_dec",
                scale_tree_to_root_age=True,
                config=dec_config,
            ),
            "DEC",
        ),
    )

    run_task(
        payload,
        "S-DEC full tree set",
        lambda: summarize_result(
            sdec_service.analyze(
                reference_tree=reference_tree,
                matrix=matrix,
                tree_entries=tree_entries,
                run_name_prefix="psychotria_sdec",
                config=sdec_config,
            ),
            "S-DEC",
        ),
    )

    for model_name in ["DEC", "DECJ", "DIVALIKE", "DIVALIKEJ", "BAYAREALIKE", "BAYAREALIKEJ"]:
        def run_bgb(model=model_name):
            config = SBGBConfig.default_for_areas(area_names, taxon_ranges)
            config.root_age = root_age
            config.cores = 4
            config.model_name = model
            return summarize_result(
                bgb_service.analyze(
                    tree=reference_tree,
                    matrix=matrix,
                    config=config,
                    run_name="psychotria_bgb_%s" % model.lower(),
                    scale_tree_to_root_age=True,
                ),
                "BioGeoBEARS-%s" % model,
            )
        run_task(payload, "BioGeoBEARS %s" % model_name, run_bgb)

    run_task(
        payload,
        "BioGeoBEARS model test",
        lambda: summarize_model_test(
            model_test_service.analyze(
                tree=reference_tree,
                matrix=matrix,
                config=bgb_base_config,
                run_name_prefix="psychotria_bgb_model_test",
            )
        ),
    )

    run_task(
        payload,
        "S-BioGeoBEARS DEC full tree set",
        lambda: summarize_result(
            sbgb_service.analyze(
                reference_tree=reference_tree,
                matrix=matrix,
                tree_entries=tree_entries,
                config=bgb_base_config,
                run_name_prefix="psychotria_sbgb_dec",
                progress_callback=lambda done, total, message: log("S-BGB progress %s/%s %s" % (done, total, message)),
            ),
            "S-BioGeoBEARS-DEC",
        ),
    )

    run_task(
        payload,
        "BayArea 5M",
        lambda: summarize_result(
            bayarea_service.analyze(
                tree=reference_tree,
                matrix=matrix,
                config=bayarea_config,
                run_name="psychotria_bayarea_5m",
            ),
            "BayArea",
        ),
    )

    run_task(
        payload,
        "BBM",
        lambda: summarize_result(
            bbm_service.analyze(
                tree=reference_tree,
                matrix=matrix,
                config=bbm_config,
                run_name="psychotria_bbm",
            ),
            "BBM",
        ),
    )

    run_task(
        payload,
        "BayesTraits MultiState",
        lambda: summarize_result(
            bayestraits_service.analyze(
                reference_tree=reference_tree,
                matrix=matrix,
                config=bayestraits_config,
                tree_entries=tree_entries,
                run_name="psychotria_bayestraits_multistate",
            ),
            "BayesTraits MultiState",
        ),
    )

    payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
    save_state(payload)
    log("Benchmark finished. Report: %s" % REPORT_PATH)


if __name__ == "__main__":
    main()
