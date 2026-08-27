import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from dataclasses import asdict
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
from application.services.result_schema_adapter import ResultSchemaAdapterFactory
from application.services.sbgb_analysis_service import SBGBAnalysisService
from application.services.sdec_analysis_service import SDECAnalysisService
from application.services.sdiva_analysis_service import SDivaAnalysisService
from application.services.tree_collection_prepare_service import TreeCollectionPrepareService
from domain.models.sbgb_config import SBGBConfig
from domain.models.sdec_config import SDECConfig
from domain.models.sdiva_config import SDivaConfig, infer_sdiva_area_names
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.tree.tree_reader import TreeReader


DATA_ROOT = PROJECT_ROOT / "data" / "benchmarks" / "psychotria"
EXPECTED_PATH = DATA_ROOT / "psychotria_gold_expected.json"
RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
RUN_ROOT = PROJECT_ROOT / "runs" / "psychotria_gold" / RUN_STAMP
REPORT_PATH = RUN_ROOT / "report.json"
LATEST_PATH = PROJECT_ROOT / "docs" / "psychotria_gold_latest.md"
TREE_SAMPLE_COUNT = 25
FLOAT_TOLERANCE = 1e-5
BASELINE_METADATA_KEY = "_baseline_metadata"


class GoldFailure(AssertionError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args):
    try:
        output = subprocess.check_output(
            ["git"] + list(args),
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.STDOUT,
        )
        return output.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def estimate_root_age(tree):
    _leaf, distance = tree.get_farthest_leaf()
    return "%g" % float(distance)


def load_inputs():
    tree_text = TreeReader().read_tree(str(DATA_ROOT / "Psychotria.tree"))
    tree = Tree(tree_text, format=1)
    matrix = CsvMatrixReader().read(str(DATA_ROOT / "distribution.csv"))
    collection = TreeReader().read_tree_collection(str(DATA_ROOT / "dataset.trees"))
    prepared = TreeCollectionPrepareService().prepare(
        collection,
        pre_burnin=0,
        post_burnin=0,
        enable_random_sampling=False,
        random_sample_size=0,
    )
    entries = list(prepared.analysis_entries or [])[:TREE_SAMPLE_COUNT]
    if len(entries) != TREE_SAMPLE_COUNT:
        raise GoldFailure("Psychotria tree sample is incomplete")
    return tree, matrix, entries, collection, prepared


def infer_taxon_ranges(matrix, dec_service):
    area_names, rows = dec_service.dataset_builder._collect_area_names_and_rows(matrix)
    values = [
        "".join(area for area, bit in zip(area_names, bits) if bit == "1")
        for _taxon, bits in rows
    ]
    return [value for value in values if value]


def node_sort_key(node):
    text = str(node.get("display_node_id", "") or "")
    try:
        return (0, int(text), str(node.get("clade_key", "")))
    except Exception:
        return (1, text, str(node.get("clade_key", "")))


def clean_float_map(values):
    result = {}
    for key, value in sorted(dict(values or {}).items(), key=lambda item: str(item[0])):
        number = float(value)
        if not math.isfinite(number):
            raise GoldFailure("Non-finite value for %s: %r" % (key, value))
        result[str(key)] = number
    return result


def finite_float(value, label):
    number = float(value)
    if not math.isfinite(number):
        raise GoldFailure("Non-finite %s: %r" % (label, value))
    return number


def r_package_versions():
    rscript = PROJECT_ROOT / "engines" / "R" / "bin" / "Rscript.exe"
    packages = ["BioGeoBEARS", "ape", "optimx", "GenSA", "snow"]
    expression = (
        "pkgs <- c(%s); "
        "for (p in pkgs) { "
        "v <- if (requireNamespace(p, quietly=TRUE)) as.character(packageVersion(p)) else 'missing'; "
        "cat(p, v, sep='=', fill=TRUE) }"
        % ",".join("'%s'" % package for package in packages)
    )
    output = subprocess.check_output(
        [str(rscript), "--vanilla", "-e", expression],
        cwd=str(PROJECT_ROOT),
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    versions = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        name, version = line.strip().split("=", 1)
        if name in packages:
            versions[name] = version
    if set(versions) != set(packages):
        raise GoldFailure("Unable to record all BioGeoBEARS R package versions: %r" % versions)
    return versions


def baseline_metadata(actual):
    source_paths = [
        PROJECT_ROOT / "infrastructure" / "dec" / "dec_output_parser.py",
        PROJECT_ROOT / "application" / "services" / "sdiva_analysis_service.py",
        PROJECT_ROOT / "application" / "services" / "sdec_analysis_service.py",
        PROJECT_ROOT / "application" / "services" / "sbgb_analysis_service.py",
        PROJECT_ROOT / "application" / "services" / "result_schema_adapter.py",
        Path(__file__).resolve(),
    ]
    diff_text = git_output("diff", "--binary", "HEAD", "--", *[
        str(path.relative_to(PROJECT_ROOT)) for path in source_paths
    ])
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_status_porcelain": git_output("status", "--porcelain").splitlines(),
        "reviewed_source_sha256": {
            str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"): sha256(path)
            for path in source_paths
        },
        "reviewed_diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
        "runtime": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
    }


def snapshot_result(result, method_name):
    standard = ResultSchemaAdapterFactory.create(result).to_standard_result(
        result=result,
        method_name=method_name,
    )
    nodes = []
    for clade_key, payload in standard.node_payloads.items():
        nodes.append(
            {
                "clade_key": str(clade_key),
                "display_node_id": str(payload.display_node_id or ""),
                "state_labels": [str(value) for value in list(payload.state_labels or [])],
                "state_counts": clean_float_map(payload.state_counts),
                "state_supports": clean_float_map(payload.state_supports),
                "supporting_tree_count": int(payload.supporting_tree_count or 0),
                "total_tree_count": int(payload.total_tree_count or 0),
                "unmatched_tree_count": int(payload.unmatched_tree_count or 0),
            }
        )
    nodes.sort(key=node_sort_key)
    summary = standard.method_summary
    if len(nodes) != 18:
        raise GoldFailure("%s returned %d internal nodes instead of 18" % (method_name, len(nodes)))
    return {
        "result_class": type(result).__name__,
        "model_name": str(getattr(result, "model_name", method_name) or method_name),
        "input_tree_count": int(summary.input_tree_count or 0),
        "effective_tree_count": int(summary.effective_tree_count or 0),
        "failed_tree_count": int(summary.failed_tree_count or 0),
        "unmatched_tree_count": int(summary.unmatched_tree_count or 0),
        "unmatched_clade_count": int(summary.unmatched_clade_count or 0),
        "warning_count": len(list(summary.warnings or [])),
        "warnings": [str(value) for value in list(summary.warnings or [])],
        "state_order": [str(value) for value in list(standard.state_order or [])],
        "nodes": nodes,
    }


def snapshot_model_test(result):
    rows = []
    for row in list(result.rows or []):
        rows.append(
            {
                "model": str(row.model_name),
                "success": bool(row.success),
                "log_likelihood": finite_float(row.log_likelihood, "%s log_likelihood" % row.model_name),
                "parameter_count": int(row.num_params),
                "aic": finite_float(row.aic, "%s aic" % row.model_name),
                "aicc": finite_float(row.aicc, "%s aicc" % row.model_name),
                "weight": finite_float(row.weight, "%s weight" % row.model_name),
            }
        )
    return {
        "effective_model_count": int(result.effective_model_count or 0),
        "failed_model_count": int(result.failed_model_count or 0),
        "best_model_name": str(result.best_model_name or ""),
        "criterion_used": str(result.criterion_used or ""),
        "rows": rows,
    }


def run_method(name, callback, methods, timings):
    print("START %s" % name, flush=True)
    started = time.perf_counter()
    methods[name] = callback()
    timings[name] = round(time.perf_counter() - started, 6)
    print("OK %s %.3fs" % (name, timings[name]), flush=True)


def build_gold_payload():
    tree, matrix, entries, collection, prepared = load_inputs()
    dec_service = DECAnalysisService(
        engine_path=PROJECT_ROOT / "engines" / "lagrange-ng" / "lagrange-ng.exe",
        work_root=RUN_ROOT / "dec",
    )
    area_names = infer_sdiva_area_names(matrix)
    root_age = estimate_root_age(tree)
    taxon_ranges = infer_taxon_ranges(matrix, dec_service)

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
    sbgb_service = SBGBAnalysisService(bgb_service, project_root=PROJECT_ROOT)
    model_test_service = BioGeoBEARSModelTestService(bgb_service)

    methods = {}
    timings = {}
    run_method(
        "diva",
        lambda: snapshot_result(
            diva_service.run(
                tree,
                matrix,
                tree_name="Psychotria",
                distribution_name="distribution",
                config=sdiva_config,
                timeout_seconds=300,
            ),
            "DIVA",
        ),
        methods,
        timings,
    )
    run_method(
        "sdiva_25",
        lambda: snapshot_result(
            sdiva_service.run(
                tree_entries=entries,
                matrix=matrix,
                reference_tree=tree,
                distribution_name="distribution",
                config=sdiva_config,
            ),
            "S-DIVA",
        ),
        methods,
        timings,
    )
    run_method(
        "dec",
        lambda: snapshot_result(
            dec_service.analyze(
                tree=tree,
                matrix=matrix,
                run_name="psychotria_gold_dec",
                scale_tree_to_root_age=True,
                config=dec_config,
            ),
            "DEC",
        ),
        methods,
        timings,
    )
    run_method(
        "sdec_25",
        lambda: snapshot_result(
            sdec_service.analyze(
                reference_tree=tree,
                matrix=matrix,
                tree_entries=entries,
                run_name_prefix="psychotria_gold_sdec",
                config=sdec_config,
            ),
            "S-DEC",
        ),
        methods,
        timings,
    )
    run_method(
        "bgb_dec",
        lambda: snapshot_result(
            bgb_service.analyze(
                tree=tree,
                matrix=matrix,
                config=bgb_config,
                run_name="psychotria_gold_bgb_dec",
                scale_tree_to_root_age=True,
            ),
            "BioGeoBEARS-DEC",
        ),
        methods,
        timings,
    )
    run_method(
        "sbgb_dec_25",
        lambda: snapshot_result(
            sbgb_service.analyze(
                reference_tree=tree,
                matrix=matrix,
                tree_entries=entries,
                config=bgb_config,
                run_name_prefix="psychotria_gold_sbgb_dec",
            ),
            "S-BioGeoBEARS-DEC",
        ),
        methods,
        timings,
    )
    run_method(
        "bgb_model_test",
        lambda: snapshot_model_test(
            model_test_service.analyze(
                tree=tree,
                matrix=matrix,
                config=bgb_config,
                run_name_prefix="psychotria_gold_model_test",
            )
        ),
        methods,
        timings,
    )

    return {
        "schema_version": 1,
        "float_tolerance": FLOAT_TOLERANCE,
        "provenance": {
            "inputs": {
                "Psychotria.tree": sha256(DATA_ROOT / "Psychotria.tree"),
                "distribution.csv": sha256(DATA_ROOT / "distribution.csv"),
                "dataset.trees": sha256(DATA_ROOT / "dataset.trees"),
            },
            "engines": {
                "DIVA.exe": sha256(PROJECT_ROOT / "engines" / "diva" / "DIVA.exe"),
                "lagrange-ng.exe": sha256(PROJECT_ROOT / "engines" / "lagrange-ng" / "lagrange-ng.exe"),
                "Rscript.exe": sha256(PROJECT_ROOT / "engines" / "R" / "bin" / "Rscript.exe"),
                "bgb_runner.R": sha256(PROJECT_ROOT / "engines" / "biogeobears" / "bgb_runner.R"),
            },
            "tree_collection": {
                "raw_count": int(collection.raw_tree_count or 0),
                "analysis_count": int(prepared.analysis_count or 0),
                "sample_count": len(entries),
                "sample_policy": "first_25_after_parse_and_bifurcation_filter",
            },
            "areas": list(area_names),
            "root_age": root_age,
            "r_packages": r_package_versions(),
            "configurations": {
                "sdiva": asdict(sdiva_config),
                "dec": asdict(dec_config),
                "sdec": asdict(sdec_config),
                "biogeobears": asdict(bgb_config),
            },
        },
        "methods": methods,
        "timings_seconds": timings,
    }


def compare_values(expected, actual, path, tolerance, differences):
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            differences.append("%s type differs" % path)
            return
        if set(expected) != set(actual):
            differences.append(
                "%s keys differ: missing=%s extra=%s"
                % (path, sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected)))
            )
            return
        for key in sorted(expected):
            compare_values(expected[key], actual[key], "%s.%s" % (path, key), tolerance, differences)
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            differences.append("%s list length/type differs" % path)
            return
        for index, value in enumerate(expected):
            compare_values(value, actual[index], "%s[%d]" % (path, index), tolerance, differences)
        return
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            expected_number = float(expected)
            actual_number = float(actual)
        except Exception:
            differences.append("%s numeric type differs" % path)
            return
        if not math.isfinite(expected_number) or not math.isfinite(actual_number):
            differences.append(
                "%s is non-finite: expected=%r actual=%r" % (path, expected, actual)
            )
            return
        delta = abs(expected_number - actual_number)
        if delta > tolerance:
            differences.append("%s differs: expected=%r actual=%r delta=%r" % (path, expected, actual, delta))
        return
    if expected != actual:
        differences.append("%s differs: expected=%r actual=%r" % (path, expected, actual))


def write_latest(report):
    lines = [
        "# Psychotria Gold Check Latest",
        "",
        "- Generated: `%s`" % report["generated_at"],
        "- Git commit: `%s`" % report["git_commit"],
        "- Mode: `%s`" % report["mode"],
        "- Status: **%s**" % report["status"].upper(),
        "- Run root: `%s`" % report["run_root"],
        "- Python: `%s`" % report["runtime"]["python_version"],
        "",
        "| Method | Seconds | Nodes/models |",
        "| --- | ---: | ---: |",
    ]
    payload = report["actual"]
    for name, method in payload["methods"].items():
        size = len(method.get("nodes", method.get("rows", [])))
        lines.append("| %s | %.3f | %d |" % (name, payload["timings_seconds"][name], size))
    if report.get("differences"):
        lines.extend(["", "## Differences", ""])
        for difference in report["differences"][:100]:
            lines.append("- `%s`" % difference)
    lines.extend(
        [
            "",
            "The S-series daily gate uses the first 25 valid trees. Full 1001-tree acceptance runs are separate.",
            "",
            "Machine-readable report: `%s`" % REPORT_PATH,
        ]
    )
    LATEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-candidate", action="store_true")
    args = parser.parse_args()
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    actual = build_gold_payload()
    report = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_status_porcelain": git_output("status", "--porcelain").splitlines(),
        "mode": "record_candidate" if args.record_candidate else "compare",
        "status": "running",
        "run_root": str(RUN_ROOT),
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version.replace("\n", " "),
            "platform": platform.platform(),
        },
        "actual": actual,
        "differences": [],
    }
    if args.record_candidate:
        candidate_path = RUN_ROOT / "psychotria_gold_candidate.json"
        candidate = dict(actual)
        candidate[BASELINE_METADATA_KEY] = baseline_metadata(actual)
        candidate_path.write_text(
            json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report["candidate_path"] = str(candidate_path)
        report["status"] = "candidate_recorded"
    else:
        if not EXPECTED_PATH.exists():
            raise FileNotFoundError("Psychotria gold baseline is missing: %s" % EXPECTED_PATH)
        expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        differences = []
        expected_for_compare = dict(expected)
        actual_for_compare = dict(actual)
        expected_for_compare.pop(BASELINE_METADATA_KEY, None)
        expected_for_compare.pop("timings_seconds", None)
        actual_for_compare.pop("timings_seconds", None)
        compare_values(
            expected_for_compare,
            actual_for_compare,
            "gold",
            float(expected.get("float_tolerance", FLOAT_TOLERANCE)),
            differences,
        )
        report["differences"] = differences
        report["expected_path"] = str(EXPECTED_PATH)
        report["expected_sha256"] = sha256(EXPECTED_PATH)
        report["status"] = "passed" if not differences else "failed"
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_latest(report)
    print("Psychotria gold check: %s" % report["status"])
    print("Report: %s" % REPORT_PATH)
    if report["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
