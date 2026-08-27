import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap import ApplicationBootstrap

ApplicationBootstrap().inject_vendor_packages()

from ete3 import Tree

from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
from application.services.dec_analysis_service import DECAnalysisService
from application.services.export_service import ExportService
from application.services.result_schema_adapter import ResultSchemaAdapterFactory
from application.services.sbgb_analysis_service import SBGBAnalysisService
from application.services.sdec_analysis_service import SDECAnalysisService
from application.services.sdiva_analysis_service import SDivaAnalysisService
import application.services.sdiva_analysis_service as sdiva_module
from application.services.tree_collection_prepare_service import TreeCollectionPrepareService
from domain.models.sbgb_config import SBGBConfig
from domain.models.sdec_config import SDECConfig
from domain.models.sdiva_config import SDivaConfig, infer_sdiva_area_names
from domain.models.sdiva_result import SDivaResult
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.tree.tree_reader import TreeReader


DATA_ROOT = PROJECT_ROOT / "data" / "benchmarks" / "psychotria"
RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
RUN_ROOT = PROJECT_ROOT / "runs" / "s_series_accounting" / RUN_STAMP
REPORT_PATH = RUN_ROOT / "report.json"
LATEST_PATH = PROJECT_ROOT / "docs" / "s_series_accounting_latest.md"


class AccountingFailure(AssertionError):
    pass


def estimate_root_age(tree):
    _leaf, distance = tree.get_farthest_leaf()
    return "%g" % float(distance)


def load_inputs():
    tree_text = TreeReader().read_tree(str(DATA_ROOT / "Psychotria.tree"))
    reference_tree = Tree(tree_text, format=1)
    matrix = CsvMatrixReader().read(str(DATA_ROOT / "distribution.csv"))
    collection = TreeReader().read_tree_collection(str(DATA_ROOT / "dataset.trees"))
    prepared = TreeCollectionPrepareService().prepare(
        collection,
        pre_burnin=0,
        post_burnin=0,
        enable_random_sampling=False,
        random_sample_size=0,
    )
    valid_entries = list(prepared.analysis_entries or [])[:2]
    if len(valid_entries) != 2:
        raise AccountingFailure("Psychotria fixture does not provide two valid sampled trees")
    return reference_tree, matrix, valid_entries + [SimpleNamespace(parsed_tree=None)]


def infer_taxon_ranges(matrix, dec_service):
    area_names, rows = dec_service.dataset_builder._collect_area_names_and_rows(matrix)
    return [
        "".join(area for area, bit in zip(area_names, bits) if bit == "1")
        for _taxon, bits in rows
    ]


def assert_accounting(name, result, progress_events):
    actual = {
        "input_tree_count": int(getattr(result, "input_tree_count", 0) or 0),
        "effective_tree_count": int(getattr(result, "effective_tree_count", 0) or 0),
        "failed_tree_count": int(getattr(result, "failed_tree_count", 0) or 0),
        "unmatched_tree_count": int(getattr(result, "unmatched_tree_count", 0) or 0),
        "unmatched_clade_count": int(getattr(result, "unmatched_clade_count", 0) or 0),
        "failure_reasons": list(getattr(result, "tree_failure_reasons", []) or []),
    }
    if actual["input_tree_count"] != 3:
        raise AccountingFailure("%s input count is %r" % (name, actual["input_tree_count"]))
    if actual["effective_tree_count"] != 2:
        raise AccountingFailure("%s effective count is %r" % (name, actual["effective_tree_count"]))
    if actual["failed_tree_count"] != 1:
        raise AccountingFailure("%s failed count is %r" % (name, actual["failed_tree_count"]))
    if len(actual["failure_reasons"]) != 1:
        raise AccountingFailure("%s failure reasons are %r" % (name, actual["failure_reasons"]))
    if "Tree 3" not in str(actual["failure_reasons"][0]):
        raise AccountingFailure("%s failure reason lacks source tree index" % name)

    if not progress_events:
        raise AccountingFailure("%s emitted no progress events" % name)
    progress_done = [int(item[0]) for item in progress_events]
    if progress_done != sorted(progress_done):
        raise AccountingFailure("%s progress is not monotonic: %r" % (name, progress_events))
    if tuple(progress_events[-1][:2]) != (3, 3):
        raise AccountingFailure("%s final progress is not 3/3: %r" % (name, progress_events[-1]))

    node_results = list(dict(getattr(result, "node_results", {}) or {}).values())
    if len(node_results) != 18:
        raise AccountingFailure("%s returned %s nodes" % (name, len(node_results)))
    unmatched_sum = 0
    for node in node_results:
        supporting = int(getattr(node, "supporting_tree_count", 0) or 0)
        total = int(getattr(node, "total_tree_count", 0) or 0)
        unmatched = int(getattr(node, "unmatched_tree_count", 0) or 0)
        if total != actual["effective_tree_count"]:
            raise AccountingFailure("%s node total %s differs from effective count" % (name, total))
        if supporting + unmatched != total:
            raise AccountingFailure(
                "%s node accounting differs: supporting=%s unmatched=%s total=%s"
                % (name, supporting, unmatched, total)
            )
        unmatched_sum += unmatched
    if unmatched_sum != actual["unmatched_clade_count"]:
        raise AccountingFailure(
            "%s unmatched clade sum differs: nodes=%s method=%s"
            % (name, unmatched_sum, actual["unmatched_clade_count"])
        )

    standard = ResultSchemaAdapterFactory.create(result).to_standard_result(
        result=result,
        method_name=name,
    )
    summary = standard.method_summary
    for field_name in (
        "input_tree_count",
        "effective_tree_count",
        "failed_tree_count",
        "unmatched_tree_count",
        "unmatched_clade_count",
    ):
        if int(getattr(summary, field_name)) != actual[field_name]:
            raise AccountingFailure("%s schema %s differs" % (name, field_name))
    if list(summary.tree_failure_reasons or []) != actual["failure_reasons"]:
        raise AccountingFailure("%s schema failure reasons differ" % name)
    for payload in standard.node_payloads.values():
        if payload.supporting_tree_count + payload.unmatched_tree_count != payload.total_tree_count:
            raise AccountingFailure("%s standard node accounting differs" % name)

    analysis_log = Path(str(getattr(result, "analysis_log_path", "") or ""))
    log_text = analysis_log.read_text(encoding="utf-8")
    for marker in (
        "[ACCOUNTING]",
        "Input trees=3",
        "Effective trees=2",
        "Failed trees=1",
        "Unmatched clade observations=%s" % actual["unmatched_clade_count"],
        "[FAILURES]",
        str(actual["failure_reasons"][0]),
    ):
        if marker not in log_text:
            raise AccountingFailure("%s analysis log lacks %r" % (name, marker))

    csv_path = RUN_ROOT / (name.lower().replace("-", "_") + "_nodes.csv")
    ExportService().export_result_csv(result, str(csv_path), method_name=name)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != len(node_results):
        raise AccountingFailure("%s result CSV row count differs" % name)
    first_row = rows[0]
    expected_method_fields = {
        "method_input_tree_count": actual["input_tree_count"],
        "method_effective_tree_count": actual["effective_tree_count"],
        "method_failed_tree_count": actual["failed_tree_count"],
        "method_zero_contribution_tree_count": actual["unmatched_tree_count"],
        "method_unmatched_clade_count": actual["unmatched_clade_count"],
    }
    for field_name, expected in expected_method_fields.items():
        if int(first_row.get(field_name, -1)) != expected:
            raise AccountingFailure("%s CSV %s differs" % (name, field_name))
    if json.loads(first_row.get("tree_failure_reasons_json", "[]")) != actual["failure_reasons"]:
        raise AccountingFailure("%s CSV failure reasons differ" % name)
    if int(first_row.get("unmatched_tree_count", -1)) != int(
        getattr(node_results[0], "unmatched_tree_count", 0) or 0
    ):
        raise AccountingFailure("%s CSV node unmatched count differs" % name)

    summary_csv_path = RUN_ROOT / (name.lower().replace("-", "_") + "_node_summary.csv")
    ExportService().export_node_summary_csv(result, str(summary_csv_path), method_name=name)
    with summary_csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        summary_rows = list(csv.DictReader(handle))
    if not summary_rows:
        raise AccountingFailure("%s node summary CSV is empty" % name)
    for field_name, expected in expected_method_fields.items():
        if int(summary_rows[0].get(field_name, -1)) != expected:
            raise AccountingFailure("%s node summary CSV %s differs" % (name, field_name))
    actual["node_count"] = len(node_results)
    actual["analysis_log"] = str(analysis_log)
    actual["export_csv"] = str(csv_path)
    actual["node_summary_csv"] = str(summary_csv_path)
    actual["progress_events"] = [list(item) for item in progress_events]
    return actual


def assert_zero_contribution_predicates(sdiva_service, sdec_service, sbgb_service):
    for name, service in (("S-DEC", sdec_service), ("S-BioGeoBEARS", sbgb_service)):
        predicate = service._has_state_contribution
        if predicate({}) or predicate({"A": 0.0}) or predicate({"A": -1.0}):
            raise AccountingFailure("%s accepts a non-positive state table as a contribution" % name)
        if not predicate({"A": 0.01, "B": 0.0}):
            raise AccountingFailure("%s rejects a positive state contribution" % name)
        filtered = service._filter_valid_state_percentages(
            {"A": 10.0, "ZZ": 90.0},
            {"A"},
        )
        if filtered != {"A": 10.0}:
            raise AccountingFailure("%s did not reject an unknown positive state" % name)

    fixture_dir = RUN_ROOT / "sdiva_zero_contribution"
    fixture_dir.mkdir(parents=True, exist_ok=False)
    (fixture_dir / "1.diva").write_text(
        "Optimal distributions\n"
        "node 1 (anc. of terminals 1-2): ZZ\n\n",
        encoding="utf-8",
    )
    clade = sdiva_service._legacy_clade(["1", "2"])
    aggregation = sdiva_service._legacy_do_analysis(
        run_dir=fixture_dir,
        prepared=[{"tree_index": 1, "source_tree_index": 1, "tokens": ["1", "2"]}],
        reference_nodes=[{"legacy_clade": clade}],
        state_order=["A"],
        index_to_name={1: "one", 2: "two"},
        warnings=[],
    )
    if int(aggregation["effective_tree_count"]) != 1:
        raise AccountingFailure("S-DIVA zero-contribution fixture was not parsed")
    if int(aggregation["unmatched_tree_count"]) != 1:
        raise AccountingFailure("S-DIVA unknown state was counted as a contribution")
    if int(aggregation["presence"][clade]) != 0:
        raise AccountingFailure("S-DIVA unknown state inflated clade support")

    (fixture_dir / "1.diva").write_text(
        "Optimal distributions\n"
        "node 1 (anc. of terminals 1-2): A ZZ\n\n",
        encoding="utf-8",
    )
    mixed = sdiva_service._legacy_do_analysis(
        run_dir=fixture_dir,
        prepared=[{"tree_index": 1, "source_tree_index": 1, "tokens": ["1", "2"]}],
        reference_nodes=[{"legacy_clade": clade}],
        state_order=["A"],
        index_to_name={1: "one", 2: "two"},
        warnings=[],
    )
    if float(mixed["counts"][clade]["A"]) != 0.5 or int(mixed["presence"][clade]) != 1:
        raise AccountingFailure("S-DIVA no longer preserves legacy pre-filter weighting")

    legacy_result = SDivaResult(reference_tree=None, tree_count_total=4)
    legacy_summary = ResultSchemaAdapterFactory.create(legacy_result).build_method_summary()
    if legacy_summary.input_tree_count != 4 or legacy_summary.effective_tree_count != 4:
        raise AccountingFailure("legacy S-DIVA tree_count_total fallback is broken")


def assert_sdiva_partial_failure(
    service,
    tree_entries,
    matrix,
    reference_tree,
    config,
):
    original_runner = service._run_diva_proc_files
    simulated_process_reason = "DIVA.exe failed with return code 7 (simulated accounting check)."

    def simulated_runner(proc_paths, run_dir, tree_count, progress_callback=None):
        console_log, warnings = original_runner(
            proc_paths,
            run_dir,
            tree_count,
            progress_callback=progress_callback,
        )
        missing_path = Path(run_dir) / "2.diva"
        if missing_path.exists():
            missing_path.unlink()
        return console_log, list(warnings) + [simulated_process_reason]

    progress_events = []
    service._run_diva_proc_files = simulated_runner
    try:
        result = service.run(
            tree_entries=list(tree_entries[:2]),
            matrix=matrix,
            reference_tree=reference_tree,
            distribution_name="distribution",
            config=config,
            progress_callback=lambda done, total, message: progress_events.append(
                (int(done), int(total), str(message))
            ),
        )
    finally:
        service._run_diva_proc_files = original_runner

    if (result.input_tree_count, result.effective_tree_count, result.failed_tree_count) != (2, 1, 1):
        raise AccountingFailure("S-DIVA partial failure accounting is incorrect")
    reasons = list(result.tree_failure_reasons or [])
    if simulated_process_reason not in reasons:
        raise AccountingFailure("S-DIVA process failure reason is not exposed")
    if not any("Tree 2 has no optimal distributions block" in reason for reason in reasons):
        raise AccountingFailure("S-DIVA missing output was not attributed to tree 2")
    if not progress_events or tuple(progress_events[-1][:2]) != (2, 2):
        raise AccountingFailure("S-DIVA partial failure progress did not finish at 2/2")
    log_text = Path(result.analysis_log_path).read_text(encoding="utf-8")
    if simulated_process_reason not in log_text:
        raise AccountingFailure("S-DIVA process failure reason is absent from analysis log")
    return {
        "input_tree_count": result.input_tree_count,
        "effective_tree_count": result.effective_tree_count,
        "failed_tree_count": result.failed_tree_count,
        "failure_reasons": reasons,
        "progress_events": [list(item) for item in progress_events],
    }


def assert_sdiva_nonzero_process_runner(service):
    fixture_dir = RUN_ROOT / "sdiva_nonzero_process"
    fixture_dir.mkdir(parents=True, exist_ok=False)
    proc_path = fixture_dir / "SDIVA_0.proc"
    proc_path.write_text("quit;\n", encoding="ascii")

    class FakeProcess:
        def poll(self):
            return 7

        def wait(self, timeout=None):
            return 7

        def kill(self):
            return None

    original_popen = sdiva_module.subprocess.Popen
    progress_events = []
    sdiva_module.subprocess.Popen = lambda *args, **kwargs: FakeProcess()
    try:
        _console_log, warnings = service._run_diva_proc_files(
            [proc_path],
            fixture_dir,
            1,
            progress_callback=lambda done, total, message: progress_events.append(
                (int(done), int(total), str(message))
            ),
        )
    finally:
        sdiva_module.subprocess.Popen = original_popen

    if not any("return code 7" in warning for warning in warnings):
        raise AccountingFailure("S-DIVA nonzero proc return code was not preserved")
    if not progress_events or tuple(progress_events[-1][:2]) != (1, 1):
        raise AccountingFailure("S-DIVA nonzero proc progress did not finish at 1/1")


def main():
    RUN_ROOT.mkdir(parents=True, exist_ok=False)
    reference_tree, matrix, tree_entries = load_inputs()
    area_names = infer_sdiva_area_names(matrix)
    root_age = estimate_root_age(reference_tree)

    dec_service = DECAnalysisService(
        engine_path=PROJECT_ROOT / "engines" / "lagrange-ng" / "lagrange-ng.exe",
        work_root=RUN_ROOT / "dec",
    )
    sdiva_service = SDivaAnalysisService(project_root=str(PROJECT_ROOT))
    sdec_service = SDECAnalysisService(dec_service, project_root=PROJECT_ROOT)
    bgb_service = BioGeoBEARSAnalysisService(
        rscript_path=PROJECT_ROOT / "engines" / "R" / "bin" / "Rscript.exe",
        wrapper_script_path=PROJECT_ROOT / "engines" / "biogeobears" / "bgb_runner.R",
        work_root=RUN_ROOT / "biogeobears",
        site_library_path=PROJECT_ROOT / "engines" / "R" / "site-library",
    )
    sbgb_service = SBGBAnalysisService(bgb_service, project_root=PROJECT_ROOT)

    assert_zero_contribution_predicates(sdiva_service, sdec_service, sbgb_service)
    assert_sdiva_nonzero_process_runner(sdiva_service)

    sdiva_config = SDivaConfig.default_for_areas(area_names)
    sdiva_config.threads = 2
    sdec_config = SDECConfig.default_for_areas(area_names)
    sdec_config.root_age = root_age
    sdec_config.threads = 2
    bgb_config = SBGBConfig.default_for_areas(
        area_names,
        infer_taxon_ranges(matrix, dec_service),
    )
    bgb_config.root_age = root_age
    bgb_config.cores = 2
    bgb_config.model_name = "DEC"

    results = {}
    progress_events = {}

    def callback_for(name):
        events = []
        progress_events[name] = events

        def callback(done, total, message):
            events.append((int(done), int(total), str(message)))

        return callback

    print("START S-DIVA accounting", flush=True)
    sdiva_progress = callback_for("S-DIVA")
    results["S-DIVA"] = assert_accounting(
        "S-DIVA",
        sdiva_service.run(
            tree_entries=tree_entries,
            matrix=matrix,
            reference_tree=reference_tree,
            distribution_name="distribution",
            config=sdiva_config,
            progress_callback=sdiva_progress,
        ),
        progress_events["S-DIVA"],
    )
    partial_failure = assert_sdiva_partial_failure(
        sdiva_service,
        tree_entries,
        matrix,
        reference_tree,
        sdiva_config,
    )
    print("START S-DEC accounting", flush=True)
    sdec_progress = callback_for("S-DEC")
    results["S-DEC"] = assert_accounting(
        "S-DEC",
        sdec_service.analyze(
            reference_tree=reference_tree,
            matrix=matrix,
            tree_entries=tree_entries,
            run_name_prefix="accounting_sdec",
            config=sdec_config,
            progress_callback=sdec_progress,
        ),
        progress_events["S-DEC"],
    )
    print("START S-BioGeoBEARS accounting", flush=True)
    sbgb_progress = callback_for("S-BioGeoBEARS-DEC")
    results["S-BioGeoBEARS-DEC"] = assert_accounting(
        "S-BioGeoBEARS-DEC",
        sbgb_service.analyze(
            reference_tree=reference_tree,
            matrix=matrix,
            tree_entries=tree_entries,
            config=bgb_config,
            run_name_prefix="accounting_sbgb",
            progress_callback=sbgb_progress,
        ),
        progress_events["S-BioGeoBEARS-DEC"],
    )

    report = {
        "schema_version": 1,
        "status": "passed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_root": str(RUN_ROOT),
        "results": results,
        "sdiva_partial_failure": partial_failure,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# S-series Accounting Latest",
        "",
        "- Status: **PASSED**",
        "- Run root: `%s`" % RUN_ROOT,
        "",
        "| Method | Input | Effective | Failed | Zero contribution | Unmatched clade observations |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, values in results.items():
        lines.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (
                name,
                values["input_tree_count"],
                values["effective_tree_count"],
                values["failed_tree_count"],
                values["unmatched_tree_count"],
                values["unmatched_clade_count"],
            )
        )
    lines.extend(["", "Machine-readable report: `%s`" % REPORT_PATH])
    LATEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("S-series accounting checks passed: %s" % REPORT_PATH)


if __name__ == "__main__":
    main()
