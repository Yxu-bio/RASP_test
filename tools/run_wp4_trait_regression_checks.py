import argparse
import json
import os
import shutil
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LATEST_REPORT = PROJECT_ROOT / "docs" / "wp4_trait_regression_latest.md"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read_inputs(tree_count):
    from infrastructure.io.csv_matrix_reader import CsvMatrixReader
    from tools.run_primate_bayestraits_continuous_test import _read_nexus_trees

    data_dir = PROJECT_ROOT / "data" / "benchmarks" / "primate" / "Trees_States"
    reference_tree = _read_nexus_trees(data_dir / "Primates.tree", limit=1)[0]
    matrix = CsvMatrixReader().read(str(data_dir / "characters.csv"))
    sampled_trees = _read_nexus_trees(data_dir / "100Trees.trees", limit=max(1, int(tree_count)))
    entries = [SimpleNamespace(parsed_tree=tree) for tree in sampled_trees]
    return reference_tree, matrix, entries


def check_config_dialog(matrix, reference_tree):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from domain.models.bayestraits_config import BayesTraitsConfig
    from gui.dialogs.bayestraits_config_dialog import BayesTraitsConfigDialog
    from application.services.bayestraits_dataset_builder import BayesTraitsDatasetBuilder

    app = QApplication.instance() or QApplication([])
    builder = BayesTraitsDatasetBuilder()
    taxon_ids = builder._collect_taxon_ids(matrix, list(reference_tree.get_leaf_names()))
    records = builder.build_node_records(reference_tree, taxon_ids)
    columns = list(matrix.state_columns)
    config = BayesTraitsConfig.default_for_columns(columns, node_ids=[record["display_node_id"] for record in records])
    dialog = BayesTraitsConfigDialog(columns, records, config=config)
    dialog.show()
    app.processEvents()

    require(dialog.output_mode_combo.currentData() == "SELECTED_NODES", "MultiState must use selected-node reconstruction.")
    require(not dialog.left_panel.isHidden(), "MultiState node selection panel must be visible.")
    require(not dialog.resall_combo.isHidden(), "MultiState ML must expose the all-rate restriction control.")
    require(dialog.hpall_combo.isHidden(), "MCMC hyper-priors must remain hidden in MultiState ML mode.")

    dialog._set_combo_data(dialog.model_combo, "CONTINUOUS_RANDOM_WALK")
    app.processEvents()
    require(dialog.output_mode_combo.count() == 2, "Continuous Model A must expose statistics and internal-node outputs.")
    require(dialog.output_mode_combo.currentData() == "MODEL_STATISTICS", "Continuous Model A must default to model statistics.")
    require(dialog.left_panel.isHidden(), "Continuous models must not show the MultiState selected-node panel.")
    require(not dialog.continuous_transform_combo.isHidden(), "Continuous transform must be visible for continuous models.")

    dialog._set_combo_data(dialog.output_mode_combo, "INTERNAL_NODES")
    app.processEvents()
    require(dialog.analysis_combo.currentData() == "MCMC", "Continuous internal-node reconstruction must force MCMC.")
    require(not dialog.iterations_spin.isHidden(), "MCMC iterations must be visible in MCMC mode.")
    require(dialog.mltries_spin.isHidden(), "MLTries must be hidden in MCMC mode.")

    dialog._set_combo_data(dialog.model_combo, "INDEPENDENT_CONTRAST")
    app.processEvents()
    require(dialog.output_mode_combo.currentData() == "MODEL_STATISTICS", "Independent Contrast is statistics-only.")
    require(dialog.output_mode_combo.count() == 1, "Statistics-only models must not expose node reconstruction.")

    dialog._set_combo_data(dialog.model_combo, "CONTINUOUS_DIRECTIONAL")
    app.processEvents()
    require(dialog.output_mode_combo.count() == 2, "Continuous Model B must expose statistics and internal-node outputs.")

    dialog._set_combo_data(dialog.model_combo, "FAT_TAIL")
    app.processEvents()
    require(dialog.analysis_combo.currentData() == "MCMC", "Fat Tail must force MCMC.")
    require(not dialog.analysis_combo.isEnabled(), "Forced MCMC selection must be read-only.")
    dialog.close()
    app.processEvents()
    return app


def bayes_config(columns, model, continuous_asr, transform="log10"):
    from domain.models.bayestraits_config import BayesTraitsConfig

    config = BayesTraitsConfig(
        trait_columns=list(columns),
        trait_column="Brain size species mean",
        selected_trait_columns=["Brain size species mean"],
        model=model,
        analysis_method="MCMC" if continuous_asr else "ML",
        ml_tries=5,
        iterations=2000,
        sample_frequency=100,
        burnin=1000,
        random_seed=20260828,
        continuous_asr=bool(continuous_asr),
        continuous_transform=transform,
        selected_node_ids=[],
    )
    config.validate()
    return config


def check_statistics_main_window_route(app, result):
    from domain.models.continuous_trait_result import ContinuousTraitResult
    from gui.main_window import MainWindow

    window = MainWindow()
    window.current_method_name = str(getattr(result, "model_name", "") or "BayesTraits")
    window.current_trait_result = result
    window.show()
    app.processEvents()
    window.open_result_window()
    app.processEvents()

    dialog = window.current_trait_statistics_dialog
    require(dialog is not None and dialog.isVisible(), "Main window must open the trait statistics result dialog.")
    require(
        window.current_result_window is None or not window.current_result_window.isVisible(),
        "Statistics-only output must not open the ancestral tree result view.",
    )

    dialog.close()
    zero_node_result = ContinuousTraitResult(reference_tree=None)
    zero_node_result.model_name = "phytools fastAnc"
    zero_node_result.metadata = {
        "analysis_domain": "trait",
        "result_kind": "continuous_trait_nodes",
        "node_estimates": True,
    }
    zero_node_result.parse_warnings = ["No reference clades could be mapped."]
    with patch("gui.main_window.QMessageBox.warning") as warning:
        window._apply_trait_result(zero_node_result)
        app.processEvents()
    require(warning.call_count == 1, "Zero-node reconstruction must show an explicit failure warning.")
    require(
        window.current_trait_statistics_dialog is None or not window.current_trait_statistics_dialog.isVisible(),
        "Zero-node reconstruction must not open the model-statistics dialog.",
    )
    require(
        window.current_result_window is None or not window.current_result_window.isVisible(),
        "Zero-node reconstruction must not open an empty ancestral tree view.",
    )

    window.close()
    app.processEvents()
    require(not dialog.isVisible(), "Trait statistics result dialog must close cleanly.")
    require(not window.isVisible(), "Main window must close cleanly after the statistics route check.")


def check_experimental_dtt_metadata(output_root):
    from application.services.continuous_trait_dtt_service import ContinuousTraitDTTService
    from domain.models.continuous_trait_result import ContinuousTraitResult

    service = ContinuousTraitDTTService(dataset_builder=None, runner=None, output_parser=None)
    service._shared_time_grid = lambda entries, config: [1.0]
    service._run_tree_job = lambda **kwargs: {
        "original_tree_index": 1,
        "selected_tree_index": 1,
        "root_age": 1.0,
        "run_workdir": "fixture",
        "rows": [{"time": 1.0, "variance": 0.25}],
    }
    config = SimpleNamespace(
        continuous_dtt=True,
        continuous_dtt_tree_limit=1,
        continuous_dtt_threads=1,
        continuous_dtt_random_seed=20260828,
        continuous_dtt_time_step=1.0,
        continuous_dtt_age_offset=0.0,
        continuous_dtt_bootstrap_count=1,
        continuous_dtt_weight_mode="corrected",
    )
    result = ContinuousTraitResult(reference_tree=None)
    result.metadata = {"experimental": False}
    entry = SimpleNamespace(parsed_tree=object())
    result = service.attach_dtt(
        result=result,
        matrix=None,
        config=config,
        tree_entries=[entry],
        output_dir=output_root / "experimental_dtt_contract",
    )
    require(result.figure_time_series.get("experimental") is True, "DTT time series must be marked Experimental.")
    require(result.metadata.get("experimental_dtt") is True, "DTT result metadata must be marked Experimental.")
    require(result.model_statistics.get("continuous_dtt_experimental") is True, "DTT statistics must be marked Experimental.")
    require("Experimental DTT" in result.result_note, "DTT result note must state its Experimental status.")
    payload = json.loads(
        (output_root / "experimental_dtt_contract" / "continuous_dtt_summary.json").read_text(encoding="utf-8")
    )
    require(payload.get("experimental") is True, "Persisted DTT JSON must be marked Experimental.")


def multistate_config(reference_tree, matrix):
    from application.services.bayestraits_dataset_builder import BayesTraitsDatasetBuilder
    from domain.models.bayestraits_config import BayesTraitsConfig

    builder = BayesTraitsDatasetBuilder()
    taxon_ids = builder._collect_taxon_ids(matrix, list(reference_tree.get_leaf_names()))
    records = builder.build_node_records(reference_tree, taxon_ids)
    selected_nodes = [str(record.get("display_node_id", "")) for record in records[:3]]
    config = BayesTraitsConfig(
        trait_columns=list(matrix.state_columns),
        trait_column="Sociality",
        selected_trait_columns=["Sociality"],
        model="MULTISTATE",
        analysis_method="ML",
        ml_tries=5,
        restrict_all="RestrictAll 1",
        auto_map_categorical=True,
        selected_node_ids=selected_nodes,
    )
    config.validate()
    return config


def run_engine_checks(reference_tree, matrix, entries, output_root):
    from application.services.bayestraits_analysis_service import BayesTraitsAnalysisService
    from application.services.phytools_analysis_service import PhytoolsAnalysisService
    from application.services.result_schema_adapter import ResultSchemaAdapterFactory
    from application.services.sphytools_analysis_service import SPhytoolsAnalysisService
    from domain.models.bayestraits_config import BayesTraitsConfig
    from domain.models.phytools_config import PhytoolsConfig
    from domain.models.phytools_config import (
        PHYTOOLS_CONTINUOUS_METHODS,
        PHYTOOLS_EXPERIMENTAL_METHODS,
        phytools_is_experimental,
    )
    from PyQt5.QtWidgets import QApplication
    from gui.dialogs.trait_model_statistics_dialog import TraitModelStatisticsDialog
    from gui.main_window import MainWindow

    rscript = PROJECT_ROOT / "engines" / "R" / "bin" / "Rscript.exe"
    rlib = PROJECT_ROOT / "engines" / "R" / "site-library"
    bayes_service = BayesTraitsAnalysisService(
        executable_path=PROJECT_ROOT / "engines" / "bayestraits" / "BayesTraitsV5.exe",
        work_root=output_root / "bayestraits",
    )
    phy_service = PhytoolsAnalysisService(
        rscript_path=rscript,
        site_library_path=rlib,
        work_root=output_root / "phytools",
    )

    stats_result = bayes_service.analyze(
        reference_tree=reference_tree,
        matrix=matrix,
        config=bayes_config(matrix.state_columns, "CONTINUOUS_RANDOM_WALK", False),
        tree_entries=None,
        run_name="model_a_ml_statistics",
    )
    require(type(stats_result).__name__ == "TraitModelResult", "BayesTraits statistics-only output must use TraitModelResult.")
    require(not hasattr(stats_result, "node_results"), "Statistics-only output must not masquerade as node estimates.")
    require(stats_result.metadata.get("node_estimates") is False, "Statistics result metadata must reject node estimates.")
    require(MainWindow._is_trait_statistics_result(stats_result), "Main window must route statistics-only results away from the tree view.")
    stats_dialog = TraitModelStatisticsDialog(stats_result)
    require(bool(stats_dialog._summary_rows()), "Statistics dialog must expose parsed numeric parameters.")
    stats_dialog.close()
    check_statistics_main_window_route(QApplication.instance(), stats_result)

    multistate = bayes_service.analyze(
        reference_tree=reference_tree,
        matrix=matrix,
        config=multistate_config(reference_tree, matrix),
        tree_entries=None,
        run_name="multistate_ml_nodes",
    )
    require(bool(multistate.node_results), "BayesTraits MultiState ML must parse selected-node probabilities.")
    require(multistate.metadata.get("result_kind") == "discrete_trait_nodes", "MultiState must retain node-result semantics.")

    correlation_config = BayesTraitsConfig(
        trait_columns=list(matrix.state_columns),
        trait_column="Brain size species mean",
        selected_trait_columns=["Brain size species mean", "Body mass male mean"],
        model="INDEPENDENT_CONTRAST_CORRELATION",
        analysis_method="ML",
        ml_tries=5,
    )
    correlation_config.validate()
    correlation = bayes_service.analyze(
        reference_tree=reference_tree,
        matrix=matrix,
        config=correlation_config,
        tree_entries=None,
        run_name="independent_contrast_correlation",
    )
    require(type(correlation).__name__ == "TraitModelResult", "IC correlation must remain a statistics-only result.")
    require(not hasattr(correlation, "node_results"), "IC correlation must not masquerade as node reconstruction.")

    bayes_nodes = bayes_service.analyze(
        reference_tree=reference_tree,
        matrix=matrix,
        config=bayes_config(matrix.state_columns, "CONTINUOUS_RANDOM_WALK", True),
        tree_entries=None,
        run_name="model_a_mcmc_nodes",
    )
    require(bool(bayes_nodes.node_results), "BayesTraits Model A MCMC must parse internal-node estimates.")
    require(bayes_nodes.metadata.get("uncertainty_kind") == "posterior_interval", "BayesTraits node estimates must be posterior intervals.")
    bayes_standard = ResultSchemaAdapterFactory.create(bayes_nodes).to_standard_result(result=bayes_nodes)
    require(bool(bayes_standard.node_payloads), "BayesTraits node schema must contain node payloads.")

    model_b_nodes = bayes_service.analyze(
        reference_tree=reference_tree,
        matrix=matrix,
        config=bayes_config(matrix.state_columns, "CONTINUOUS_DIRECTIONAL", True),
        tree_entries=None,
        run_name="model_b_mcmc_nodes",
    )
    require(bool(model_b_nodes.node_results), "BayesTraits Model B MCMC must parse internal-node estimates.")
    require(model_b_nodes.metadata.get("estimation_method") == "CONTINUOUS_DIRECTIONAL", "Model B metadata must retain the directional model identity.")

    fastanc_config = PhytoolsConfig(
        trait_columns=list(matrix.state_columns),
        trait_column="Brain size species mean",
        method="FASTANC",
        continuous_transform="log10",
    )
    fastanc = phy_service.analyze(tree=reference_tree, matrix=matrix, config=fastanc_config, run_name="fastanc")
    require(bool(fastanc.node_results), "fastAnc must return internal nodes.")
    require(fastanc.metadata.get("uncertainty_kind") == "point_estimate", "fastAnc without CI must be a point estimate.")
    fastanc_payload = next(iter(ResultSchemaAdapterFactory.create(fastanc).to_standard_result(result=fastanc).node_payloads.values()))
    require("point estimate" in fastanc_payload.support_summary, "fastAnc display must not invent a confidence/posterior interval.")

    ci_config = PhytoolsConfig(
        trait_columns=list(matrix.state_columns),
        trait_column="Brain size species mean",
        method="FASTANC_CI",
        continuous_transform="log10",
    )
    fastanc_ci = phy_service.analyze(tree=reference_tree, matrix=matrix, config=ci_config, run_name="fastanc_ci")
    require(fastanc_ci.metadata.get("uncertainty_kind") == "confidence_interval", "fastAnc CI must report confidence intervals.")
    ci_payload = next(iter(ResultSchemaAdapterFactory.create(fastanc_ci).to_standard_result(result=fastanc_ci).node_payloads.values()))
    require("confidence interval" in ci_payload.state_summary, "fastAnc CI display must identify confidence intervals.")

    bayes_phy_config = PhytoolsConfig(
        trait_columns=list(matrix.state_columns),
        trait_column="Brain size species mean",
        method="ANC_BAYES",
        continuous_transform="log10",
        bayes_iterations=3000,
        bayes_sample_frequency=100,
        bayes_burnin=500,
        seed=20260828,
    )
    anc_bayes = phy_service.analyze(tree=reference_tree, matrix=matrix, config=bayes_phy_config, run_name="anc_bayes")
    require(anc_bayes.metadata.get("uncertainty_kind") == "posterior_interval", "anc.Bayes must report posterior intervals.")
    anc_bayes_key, anc_bayes_node = next(iter(anc_bayes.node_results.items()))
    require(
        abs(float(anc_bayes.analysis_node_values[anc_bayes_key]) - float(anc_bayes_node.median)) < 1e-12,
        "anc.Bayes analysis colors must use the posterior median.",
    )
    require(
        abs(float(anc_bayes.plot_node_values[anc_bayes_key]) - float(anc_bayes_node.median)) < 1e-12,
        "anc.Bayes plotted colors must use the posterior median.",
    )
    bayes_payload = next(iter(ResultSchemaAdapterFactory.create(anc_bayes).to_standard_result(result=anc_bayes).node_payloads.values()))
    require("posterior interval" in bayes_payload.state_summary, "anc.Bayes display must identify posterior intervals.")

    require(
        all(phytools_is_experimental(method) for method in PHYTOOLS_EXPERIMENTAL_METHODS),
        "All anc.ML BM/OU/EB methods must remain Experimental.",
    )
    require(
        all(str(PHYTOOLS_CONTINUOUS_METHODS[method]).startswith("Experimental:") for method in PHYTOOLS_EXPERIMENTAL_METHODS),
        "Experimental anc.ML methods must be visibly labelled in the UI.",
    )
    anc_ml_config = PhytoolsConfig(
        trait_columns=list(matrix.state_columns),
        trait_column="Brain size species mean",
        method="ANC_ML_BM",
        continuous_transform="log10",
        anc_ml_maxit=500,
    )
    anc_ml = phy_service.analyze(tree=reference_tree, matrix=matrix, config=anc_ml_config, run_name="anc_ml_bm")
    require(anc_ml.metadata.get("experimental") is True, "anc.ML results must remain Experimental.")
    require("anc.ML.BM" in str(anc_ml.metadata.get("estimator", "")), "anc.ML BM must not silently fall back to another estimator.")
    anc_ml_counts = {"ANC_ML_BM": len(anc_ml.node_results)}
    for method, expected in [("ANC_ML_OU", "anc.ML.OU"), ("ANC_ML_EB", "anc.ML.EB")]:
        config = PhytoolsConfig(
            trait_columns=list(matrix.state_columns),
            trait_column="Brain size species mean",
            method=method,
            continuous_transform="log10",
            anc_ml_maxit=500,
        )
        try:
            method_result = phy_service.analyze(
                tree=reference_tree,
                matrix=matrix,
                config=config,
                run_name=method.lower(),
            )
        except RuntimeError as exc:
            if method != "ANC_ML_EB":
                raise
            diagnostic = str(exc)
            require(
                "system is exactly singular" in diagnostic
                and "phytools::anc.ML(model='EB')" in diagnostic,
                "Experimental EB failures must identify the singular-covariance cause.",
            )
            anc_ml_counts[method] = {
                "status": "diagnosed_singular_covariance",
                "node_count": 0,
            }
            continue
        require(bool(method_result.node_results), "%s must return internal-node estimates." % method)
        require(method_result.metadata.get("experimental") is True, "%s must remain Experimental." % method)
        require(expected in str(method_result.metadata.get("estimator", "")), "%s must not silently fall back." % method)
        anc_ml_counts[method] = {
            "status": "estimated",
            "node_count": len(method_result.node_results),
        }

    ace_config = PhytoolsConfig(
        trait_columns=list(matrix.state_columns),
        trait_column="Sociality",
        method="ACE_ER",
    )
    ace = phy_service.analyze(tree=reference_tree, matrix=matrix, config=ace_config, run_name="ace_er")
    require(bool(ace.node_results), "ape::ace must return discrete internal-node probabilities.")
    require(ace.metadata.get("trait_column") == "Sociality", "Mixed matrix must preserve the selected discrete trait column.")
    require(ace.metadata.get("uncertainty_kind") == "likelihood_probability", "ape::ace probabilities must be labelled as likelihood results.")

    s_service = SPhytoolsAnalysisService(phy_service, work_root=output_root / "sphytools")
    s_config = PhytoolsConfig(
        trait_columns=list(matrix.state_columns),
        trait_column="Brain size species mean",
        method="FASTANC",
        continuous_transform="log10",
        threads=2,
    )
    s_result = s_service.analyze(
        reference_tree=reference_tree,
        matrix=matrix,
        tree_entries=entries,
        config=s_config,
        run_name_prefix="sfastanc",
    )
    require(bool(s_result.node_results), "S-phytools must aggregate reference clades.")
    require(s_result.metadata.get("tree_set") is True, "S-phytools result must be labelled as a tree-set result.")
    require(s_result.metadata.get("uncertainty_kind") == "across_tree_percentile_interval", "S-phytools intervals must be labelled as across-tree intervals.")
    s_payload = next(iter(ResultSchemaAdapterFactory.create(s_result).to_standard_result(result=s_result).node_payloads.values()))
    require("across-tree interval" in s_payload.state_summary, "S-phytools display must identify across-tree intervals.")

    return {
        "bayes_statistics_type": type(stats_result).__name__,
        "main_window_statistics_route": "passed",
        "zero_node_failure_route": "passed",
        "bayes_multistate_node_count": len(multistate.node_results),
        "bayes_ic_correlation_type": type(correlation).__name__,
        "bayes_node_count": len(bayes_nodes.node_results),
        "bayes_model_b_node_count": len(model_b_nodes.node_results),
        "fastanc_node_count": len(fastanc.node_results),
        "fastanc_ci_node_count": len(fastanc_ci.node_results),
        "anc_bayes_node_count": len(anc_bayes.node_results),
        "anc_ml_bm_node_count": len(anc_ml.node_results),
        "anc_ml_node_counts": anc_ml_counts,
        "ace_node_count": len(ace.node_results),
        "sphytools_node_count": len(s_result.node_results),
        "sphytools_effective_tree_count": int(s_result.effective_tree_count),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree-count", type=int, default=3)
    parser.add_argument("--output", default="runs/wp4_trait_regression/latest")
    args = parser.parse_args()

    from app.bootstrap import ApplicationBootstrap

    bootstrap = ApplicationBootstrap()
    bootstrap.inject_conda_dll_paths()
    bootstrap.inject_vendor_packages()

    output_root = PROJECT_ROOT / str(args.output)
    if output_root.exists():
        shutil.rmtree(str(output_root))
    output_root.mkdir(parents=True, exist_ok=True)

    reference_tree, matrix, entries = read_inputs(max(1, int(args.tree_count)))
    require("Brain size species mean" in matrix.state_columns, "Continuous Primate trait column is missing.")
    require("Sociality" in matrix.state_columns, "Discrete Primate trait column is missing.")
    qt_app = check_config_dialog(matrix, reference_tree)
    check_experimental_dtt_metadata(output_root)
    result = run_engine_checks(reference_tree, matrix, entries, output_root)
    qt_app.processEvents()
    result.update({
        "status": "passed",
        "trait_column_count": len(matrix.state_columns),
        "tree_count": len(entries),
    })
    summary_path = output_root / "wp4_trait_regression_summary.json"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report_lines = [
        "# WP4 Trait Regression - Latest",
        "",
        "Status: **passed**",
        "",
        "Command:",
        "",
        "```powershell",
        "E:\\Anaconda3\\envs\\RASP\\python.exe tools\\run_wp4_trait_regression_checks.py --tree-count %s" % len(entries),
        "```",
        "",
        "Fixed data:",
        "",
        "- `data/benchmarks/primate/Trees_States/Primates.tree`",
        "- `data/benchmarks/primate/Trees_States/100Trees.trees`",
        "- `data/benchmarks/primate/Trees_States/characters.csv`",
        "",
        "Verified:",
        "",
        "- BayesTraits Model A ML statistics use a non-tree `TraitModelResult`.",
        "- BayesTraits Model A/B MCMC internal-node reconstruction parses %s/%s nodes." % (
            result["bayes_node_count"], result["bayes_model_b_node_count"]
        ),
        "- BayesTraits MultiState ML parses selected-node probabilities; IC correlation remains statistics-only.",
        "- Main-window statistics routing opens and closes without creating an ancestral tree view.",
        "- Zero-node reconstruction is reported as a failure and cannot open a statistics/tree result view.",
        "- fastAnc, fastAnc CI, anc.Bayes, experimental anc.ML BM and ape::ace return explicit result semantics.",
        "- Experimental anc.ML BM/OU execute without estimator fallback; EB either estimates or reports its known singular-covariance limitation explicitly.",
        "- Experimental DTT metadata is persisted in the result object and summary JSON.",
        "- Mixed continuous/discrete trait columns preserve the user-selected column.",
        "- S-phytools aggregates %s sampled trees with across-tree uncertainty metadata." % result["sphytools_effective_tree_count"],
        "- The BayesTraits dialog changes output and active parameters by model and ML/MCMC mode.",
        "",
        "Machine-readable result: `%s`" % summary_path.relative_to(PROJECT_ROOT).as_posix(),
        "",
    ]
    LATEST_REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _run_cli():
    exit_code = 0
    try:
        main()
    except BaseException:
        traceback.print_exc()
        exit_code = 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
    if sys.platform == "win32":
        os._exit(exit_code)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    _run_cli()
