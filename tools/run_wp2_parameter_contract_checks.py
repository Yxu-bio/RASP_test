import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap import ApplicationBootstrap

ApplicationBootstrap().inject_vendor_packages()

from ete3 import Tree

from application.services.bayarea_analysis_service import BayAreaAnalysisService
from application.services.dec_dataset_builder import DECDatasetBuilder
from domain.models.bayarea_config import BayAreaConfig
from domain.models.sdec_config import SDECConfig
from infrastructure.dec.dec_runner import DECRunner
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.tree.tree_reader import TreeReader


DATA_ROOT = PROJECT_ROOT / "data" / "benchmarks" / "psychotria"
EXPECTED_PATH = DATA_ROOT / "wp2_parameter_contract_expected.json"
RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
RUN_ROOT = PROJECT_ROOT / "runs" / "wp2_parameter_contract" / RUN_STAMP
REPORT_JSON_PATH = RUN_ROOT / "report.json"
REPORT_MARKDOWN_PATH = PROJECT_ROOT / "docs" / "wp2_parameter_contract_latest.md"
LAGRANGE_EXE = PROJECT_ROOT / "engines" / "lagrange-ng" / "lagrange-ng.exe"
BAYAREA_EXE = PROJECT_ROOT / "engines" / "bayarea" / "bin" / "bayarea.exe"


class ContractFailure(AssertionError):
    pass


def check(condition, message):
    if not condition:
        raise ContractFailure(message)


def close(actual, expected, tolerance, label):
    actual = float(actual)
    expected = float(expected)
    tolerance = float(tolerance)
    if abs(actual - expected) > tolerance:
        raise ContractFailure(
            "%s differs: actual=%r expected=%r tolerance=%r"
            % (label, actual, expected, tolerance)
        )


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
        return subprocess.check_output(
            ["git"] + list(args),
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        ).strip()
    except Exception:
        return ""


def git_worktree_status():
    porcelain = git_output("status", "--porcelain")
    unstaged = subprocess.call(
        ["git", "diff", "--quiet"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    staged = subprocess.call(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {
        "tracked_dirty": bool(unstaged or staged),
        "porcelain": porcelain.splitlines() if porcelain else [],
    }


def load_inputs():
    tree_text = TreeReader().read_tree(str(DATA_ROOT / "Psychotria.tree"))
    tree = Tree(tree_text, format=1)
    matrix = CsvMatrixReader().read(str(DATA_ROOT / "distribution.csv"))
    coordinates = {}
    for raw_line in (DATA_ROOT / "coordinates.csv").read_text(encoding="utf-8-sig").splitlines():
        parts = [part.strip() for part in raw_line.split(",")]
        if len(parts) >= 3:
            coordinates[parts[0]] = (float(parts[1]), float(parts[2]))
    return tree, matrix, coordinates


def extract_llh(stdout):
    matches = re.findall(r"(?:^|\s)LLH:\s*([-+0-9.eE]+)", str(stdout or ""))
    if not matches:
        raise ContractFailure("lagrange-ng stdout did not contain LLH")
    return float(matches[-1])


def run_lagrange(config, tree, matrix, run_name):
    builder = DECDatasetBuilder()
    run_files = builder.build(
        tree=tree,
        matrix=matrix,
        output_dir=RUN_ROOT / "lagrange_ng",
        run_name=run_name,
        **config.builder_kwargs()
    )
    output = DECRunner(engine_path=LAGRANGE_EXE).run(run_files)
    (run_files.workdir / "engine_stdout.log").write_text(output.stdout, encoding="utf-8")
    (run_files.workdir / "engine_stderr.log").write_text(output.stderr, encoding="utf-8")
    raw = json.loads(output.results_json_path.read_text(encoding="utf-8"))
    return {
        "workdir": str(run_files.workdir),
        "config_path": str(run_files.config_path),
        "config_text": run_files.config_path.read_text(encoding="utf-8"),
        "results_path": str(output.results_json_path),
        "stdout_path": str(run_files.workdir / "engine_stdout.log"),
        "stdout": output.stdout,
        "attributes": dict(raw.get("attributes", {}) or {}),
        "params": list(raw.get("params", []) or []),
        "llh": extract_llh(output.stdout),
    }


def lagrange_fixed_de_check(expected, tree, matrix):
    config = SDECConfig.default_for_areas(["A", "B", "C", "D"])
    config.mode = "evaluate"
    config.use_fixed_rates = True
    config.dispersion = expected["dispersion"]
    config.extinction = expected["extinction"]
    config.max_areas = expected["max_areas"]

    result = run_lagrange(config, tree, matrix, "fixed_de")
    raw_config = result["config_text"]
    check("mode = evaluate" in raw_config, "evaluate mode was not written to run.conf")
    check("dispersion = 2.0" in raw_config, "fixed dispersion was not written to run.conf")
    check("extinction = 3.0" in raw_config, "fixed extinction was not written to run.conf")
    check("maxareas = 2" in raw_config, "maxareas was not written to run.conf")
    check(len(result["params"]) == 1, "fixed d/e run did not return one parameter block")
    close(result["params"][0]["dispersion"], expected["dispersion"], 1e-12, "fixed dispersion")
    close(result["params"][0]["extinction"], expected["extinction"], 1e-12, "fixed extinction")
    check(result["attributes"].get("max-areas") == expected["max_areas"], "raw max-areas differs")
    check(result["attributes"].get("periods") == expected["period_count"], "raw period count differs")
    check(result["attributes"].get("state-count") == expected["state_count"], "raw state count differs")
    close(result["llh"], expected["llh"], expected["llh_tolerance"], "fixed d/e LLH")
    stdout_match = re.search(
        r"Period:\s*default,\s*Dispersion:\s*([-+0-9.eE]+),\s*Extinction:\s*([-+0-9.eE]+)",
        result["stdout"],
    )
    check(stdout_match is not None, "engine stdout did not report the fixed d/e")
    close(stdout_match.group(1), expected["dispersion"], 1e-12, "stdout fixed dispersion")
    close(stdout_match.group(2), expected["extinction"], 1e-12, "stdout fixed extinction")
    result.pop("stdout")
    result.pop("config_text")
    return result


def period_config(expected, *, use_matrix, use_exclude):
    config = SDECConfig.default_for_areas(["A", "B", "C", "D"])
    config.mode = "evaluate"
    config.use_fixed_rates = True
    config.dispersion = 2.0
    config.extinction = 3.0
    config.max_areas = expected["max_areas"]
    config.period_times = [0.0, 1.0, 2.0, 6.0]
    matrices = [SDECConfig._default_dispersal_matrix(4) for _index in range(3)]
    if use_matrix:
        matrices[1][0][1] = 0.5
        matrices[1][1][0] = 0.5
    config.dispersal_matrices = matrices
    config.period_include_area_bits = ["", "", ""]
    config.period_exclude_area_bits = ["", "", "0001" if use_exclude else ""]
    config.extra_control_lines = [
        "period period_0 dispersion = 0.5",
        "period period_0 extinction = 0.8",
        "period period_1 dispersion = 0.001",
        "period period_1 extinction = 0.002",
    ]
    return config


def lagrange_period_check(expected, tree, matrix):
    variants = {}
    for name, use_matrix, use_exclude in [
        ("baseline", False, False),
        ("matrix_only", True, False),
        ("exclude_only", False, True),
        ("combined", True, True),
    ]:
        variants[name] = run_lagrange(
            period_config(expected, use_matrix=use_matrix, use_exclude=use_exclude),
            tree,
            matrix,
            "period_%s" % name,
        )

    result = variants["combined"]
    raw_config = result["config_text"]
    for required in [
        "period period_1 matrix = period_1_matrix.csv",
        "period period_2 exclude = 0001",
        "period period_0 dispersion = 0.5",
        "period period_1 extinction = 0.002",
    ]:
        check(required in raw_config, "period config line is missing: %s" % required)
    matrix_path = Path(result["workdir"]) / "period_1_matrix.csv"
    check(matrix_path.exists(), "period dispersal matrix file was not written")
    check("A,B,0.5" in matrix_path.read_text(encoding="utf-8"), "period matrix value was not written")
    check(result["attributes"].get("max-areas") == expected["max_areas"], "period raw max-areas differs")
    check(result["attributes"].get("periods") == expected["period_count"], "period count differs")
    check(result["attributes"].get("state-count") == expected["state_count"], "period state count differs")
    check(len(result["params"]) == len(expected["parameters"]), "period parameter count differs")
    for index, expected_period in enumerate(expected["parameters"]):
        close(
            result["params"][index]["dispersion"],
            expected_period["dispersion"],
            1e-12,
            "period %d dispersion" % index,
        )
        close(
            result["params"][index]["extinction"],
            expected_period["extinction"],
            1e-12,
            "period %d extinction" % index,
        )
    close(result["llh"], expected["llh"], expected["llh_tolerance"], "period-rule LLH")
    check(
        "Period: period_2, Dispersion: 2, Extinction: 3" in result["stdout"],
        "period without an override did not inherit global d/e",
    )
    check(
        variants["baseline"]["params"][1].get("distance-penalty") is None,
        "baseline unexpectedly reported a period distance penalty",
    )
    close(
        variants["matrix_only"]["params"][1].get("distance-penalty"),
        1.0,
        1e-12,
        "matrix period distance penalty",
    )
    close(
        variants["combined"]["params"][1].get("distance-penalty"),
        1.0,
        1e-12,
        "combined period distance penalty",
    )
    variant_llh = {name: item["llh"] for name, item in variants.items()}
    for name, expected_llh in dict(expected.get("variant_llh", {}) or {}).items():
        close(
            variant_llh[name],
            expected_llh,
            expected["variant_llh_tolerance"],
            "%s period-rule LLH" % name,
        )
    check(
        len(set(round(value, 6) for value in variant_llh.values())) == 4,
        "matrix and exclude A/B variants did not produce four distinct likelihoods",
    )
    summary = {}
    for name, item in variants.items():
        item = dict(item)
        item.pop("stdout")
        item.pop("config_text")
        summary[name] = item
    summary["period_matrix_path"] = str(matrix_path)
    summary["variant_llh"] = variant_llh
    return summary


def bayarea_config(coordinates, seed, prior_scale, guess_initial_rates):
    config = BayAreaConfig.default_for_areas(["A", "B", "C", "D"])
    config.coordinates = dict(coordinates)
    config.chain_length = 1
    config.sample_frequency = 1
    config.seed = int(seed)
    config.guess_initial_rates = bool(guess_initial_rates)
    config.gain_prior = float(prior_scale)
    config.loss_prior = float(prior_scale)
    config.distance_power_prior = float(prior_scale)
    config.area_proposal_tuner = 0.0
    config.rate_proposal_tuner = 1e-9
    config.distance_proposal_tuner = 1e-9
    return config


def first_parameter_row(path):
    lines = [line for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    check(len(lines) >= 2, "BayArea parameter file has no sampled row: %s" % path)
    names = lines[0].split("\t")
    values = lines[1].split("\t")
    check(len(values) >= len(names), "BayArea parameter row is incomplete: %s" % path)
    return {name: float(value) for name, value in zip(names, values)}


def run_bayarea_single(tree, matrix, config, run_name):
    service = BayAreaAnalysisService(
        executable_path=BAYAREA_EXE,
        work_root=RUN_ROOT / "bayarea",
    )
    result = service.analyze(tree=tree, matrix=matrix, config=config, run_name=run_name)
    stats = dict(result.model_statistics or {})
    parameter_path = Path(stats["parameters_path"])
    workdir = parameter_path.parent
    stdout_path = workdir / "bayarea_stdout.log"
    manifest_path = workdir / "bayarea_manifest.json"
    return {
        "workdir": str(workdir),
        "parameter_path": str(parameter_path),
        "stdout_path": str(stdout_path),
        "manifest_path": str(manifest_path),
        "stdout": stdout_path.read_text(encoding="utf-8", errors="replace"),
        "manifest": json.loads(manifest_path.read_text(encoding="utf-8")),
        "row": first_parameter_row(parameter_path),
        "node_count": len(result.node_results),
        "seed": stats.get("seed"),
    }


def assert_bayarea_stdout(result, seed, prior_scale, guess_initial_rates):
    stdout = result["stdout"]
    expected_guess = "True" if guess_initial_rates else "False"

    def setting(label):
        match = re.search(r"^\s*\*\s*%s\s*=\s*(\S+)\s*$" % re.escape(label), stdout, re.MULTILINE)
        if not match:
            raise ContractFailure("BayArea stdout did not report setting: %s" % label)
        return match.group(1)

    check(int(setting("Random number seed")) == int(seed), "BayArea stdout seed differs")
    close(setting("Area gain prior"), prior_scale, 1e-12, "BayArea stdout gain prior")
    close(setting("Area loss prior"), prior_scale, 1e-12, "BayArea stdout loss prior")
    close(setting("Distance power prior"), prior_scale, 1e-12, "BayArea stdout distance prior")
    check(setting("Guess initial rates") == expected_guess, "BayArea stdout initial-rate mode differs")
    runtime = dict(result["manifest"].get("runtime", {}) or {})
    close(runtime.get("gain_prior"), prior_scale, 1e-12, "BayArea manifest gain prior")
    close(runtime.get("loss_prior"), prior_scale, 1e-12, "BayArea manifest loss prior")
    close(runtime.get("distance_power_prior"), prior_scale, 1e-12, "BayArea manifest distance prior")
    check(runtime.get("seed") == seed, "BayArea manifest seed differs")
    check(runtime.get("guess_initial_rates") is bool(guess_initial_rates), "BayArea manifest initial-rate mode differs")


def bayarea_prior_and_initial_rate_check(expected, tree, matrix, coordinates):
    seed = int(expected["single_chain_seed"])
    low_expected = expected["prior_low"]
    high_expected = expected["prior_high"]
    heuristic_expected = expected["heuristic_initial_rates"]

    low = run_bayarea_single(
        tree,
        matrix,
        bayarea_config(coordinates, seed, low_expected["scale"], False),
        "prior_low",
    )
    high = run_bayarea_single(
        tree,
        matrix,
        bayarea_config(coordinates, seed, high_expected["scale"], False),
        "prior_high",
    )
    heuristic = run_bayarea_single(
        tree,
        matrix,
        bayarea_config(coordinates, seed, low_expected["scale"], True),
        "heuristic_initial_rates",
    )

    assert_bayarea_stdout(low, seed, low_expected["scale"], False)
    assert_bayarea_stdout(high, seed, high_expected["scale"], False)
    assert_bayarea_stdout(heuristic, seed, low_expected["scale"], True)

    field_names = {
        "gain": "gain",
        "loss": "loss",
        "distance_power": "distP",
    }
    for expected_name, raw_name in field_names.items():
        close(
            low["row"][raw_name],
            low_expected[expected_name],
            low_expected["value_tolerance"],
            "BayArea prior-low %s" % expected_name,
        )
        multiplier = high["row"][raw_name] / low["row"][raw_name]
        close(
            multiplier,
            high_expected["expected_multiplier"],
            high_expected["multiplier_tolerance"],
            "BayArea prior multiplier %s" % expected_name,
        )
        close(
            heuristic["row"][raw_name],
            heuristic_expected[expected_name],
            heuristic_expected["value_tolerance"],
            "BayArea heuristic %s" % expected_name,
        )

    summary = {}
    for name, result in [("prior_low", low), ("prior_high", high), ("heuristic", heuristic)]:
        result = dict(result)
        result.pop("stdout")
        result.pop("manifest")
        summary[name] = result
    return summary


def raw_chain_hashes(chain_runs):
    rows = []
    for chain in chain_runs:
        row = {"seed": int(chain["seed"]), "workdir": str(chain["workdir"]), "files": {}}
        for field in ["parameters_path", "area_states_path", "area_probs_path", "nhx_path"]:
            path = Path(chain[field])
            row["files"][field] = {"path": str(path), "sha256": sha256(path)}
        rows.append(row)
    return rows


def raw_chain_state_counts(chain_runs):
    counts = {}
    for chain in chain_runs:
        manifest = json.loads(Path(chain["manifest_path"]).read_text(encoding="utf-8"))
        index_to_clade = {
            int(index): str(clade)
            for index, clade in dict(manifest.get("node_index_to_clade", {}) or {}).items()
        }
        path = Path(chain["area_states_path"])
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            try:
                node_index = int(parts[2])
            except Exception:
                continue
            clade = index_to_clade.get(node_index)
            if not clade:
                continue
            bits = "".join(ch for ch in parts[3].strip() if ch in ("0", "1"))
            node_counts = counts.setdefault(clade, {})
            node_counts[bits] = int(node_counts.get(bits, 0)) + 1
    return counts


def run_bayarea_multi(tree, matrix, coordinates, seed, run_name):
    config = bayarea_config(coordinates, seed, 0.1, False)
    config.independent_chains = 2
    config.parallel_chains = 2
    service = BayAreaAnalysisService(
        executable_path=BAYAREA_EXE,
        work_root=RUN_ROOT / "bayarea_multi",
    )
    result = service.analyze(tree=tree, matrix=matrix, config=config, run_name=run_name)
    stats = dict(result.model_statistics or {})
    combined_counts = {}
    combined_samples = {}
    combined_supports = {}
    for clade, node in result.node_results.items():
        payload = dict(node.raw_method_payload or {})
        combined_counts[str(clade)] = {
            str(bits): int(count)
            for bits, count in dict(payload.get("bayarea_bit_counts", {}) or {}).items()
        }
        combined_samples[str(clade)] = int(payload.get("bayarea_samples", 0) or 0)
        combined_supports[str(clade)] = {
            str(state): float(value)
            for state, value in dict(node.state_supports or {}).items()
        }
    chain_runs = list(stats.get("bayarea_chain_runs", []) or [])
    return {
        "node_count": len(result.node_results),
        "chain_count": int(stats.get("bayarea_chain_count", 0) or 0),
        "chain_seeds": list(stats.get("bayarea_chain_seeds", []) or []),
        "sampled_lnl_count": int(stats.get("sampled_lnL_count", 0) or 0),
        "chains": raw_chain_hashes(chain_runs),
        "raw_chain_state_counts": raw_chain_state_counts(chain_runs),
        "combined_state_counts": combined_counts,
        "combined_samples": combined_samples,
        "combined_supports": combined_supports,
    }


def assert_bayarea_pooling(run):
    check(
        run["combined_state_counts"] == run["raw_chain_state_counts"],
        "BayArea combined node probabilities do not contain the summed raw chain states",
    )
    area_names = ["A", "B", "C", "D"]
    for clade, counts in run["combined_state_counts"].items():
        sample_count = sum(counts.values())
        check(
            run["combined_samples"].get(clade) == sample_count,
            "BayArea combined sample denominator differs for clade %s" % clade,
        )
        expected_supports = {}
        for bits, count in counts.items():
            label = "".join(area for area, bit in zip(area_names, bits) if bit == "1") or "/"
            expected_supports[label] = float(count) * 100.0 / float(sample_count)
        actual_supports = run["combined_supports"].get(clade, {})
        check(set(actual_supports) == set(expected_supports), "BayArea pooled states differ for clade %s" % clade)
        for state, expected_support in expected_supports.items():
            close(
                actual_supports[state],
                expected_support,
                1e-12,
                "BayArea pooled support %s %s" % (clade, state),
            )


def bayarea_multi_chain_check(expected, tree, matrix, coordinates):
    first = run_bayarea_multi(tree, matrix, coordinates, expected["base_seed"], "repeat_a")
    second = run_bayarea_multi(tree, matrix, coordinates, expected["base_seed"], "repeat_b")
    check(first["chain_count"] == 2, "BayArea did not report two independent chains")
    check(first["chain_seeds"] == expected["expected_seeds"], "BayArea per-chain seeds differ")
    check(first["node_count"] == expected["expected_node_count"], "BayArea pooled node count differs")
    check(first["sampled_lnl_count"] == 2, "BayArea did not pool one sample from each chain")
    assert_bayarea_pooling(first)
    assert_bayarea_pooling(second)
    check(second["chain_seeds"] == first["chain_seeds"], "BayArea repeated run changed chain seeds")
    check(len(first["chains"]) == len(second["chains"]) == 2, "BayArea chain artifacts are incomplete")
    for index in range(2):
        first_hashes = {name: item["sha256"] for name, item in first["chains"][index]["files"].items()}
        second_hashes = {name: item["sha256"] for name, item in second["chains"][index]["files"].items()}
        check(first_hashes == second_hashes, "BayArea fixed-seed chain %d was not reproducible" % (index + 1))
    first_seed_hashes = {
        name: item["sha256"] for name, item in first["chains"][0]["files"].items()
    }
    second_seed_hashes = {
        name: item["sha256"] for name, item in first["chains"][1]["files"].items()
    }
    check(
        first_seed_hashes != second_seed_hashes,
        "BayArea distinct chain seeds produced identical native artifacts",
    )
    check(first["combined_state_counts"] == second["combined_state_counts"], "BayArea pooled counts changed on repeat")
    check(first["combined_supports"] == second["combined_supports"], "BayArea pooled supports changed on repeat")
    return {"repeat_a": first, "repeat_b": second}


def run_case(name, callback, cases):
    started = time.perf_counter()
    try:
        details = callback()
        cases.append(
            {
                "name": name,
                "status": "passed",
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "details": details,
            }
        )
    except Exception as exc:
        cases.append(
            {
                "name": name,
                "status": "failed",
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "error": "%s: %s" % (type(exc).__name__, exc),
            }
        )


def write_reports(report):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# WP2 Parameter Contract Checks",
        "",
        "- Generated: `%s`" % report["generated_at"],
        "- Git commit: `%s`" % report["code_identity"]["git_commit"],
        "- Tracked worktree dirty at run start: `%s`" % report["code_identity"]["tracked_worktree_dirty"],
        "- Untracked/status entries at run start: `%d`" % len(report["code_identity"]["git_status_porcelain"]),
        "- Python: `%s`" % report["runtime_identity"]["python_version"],
        "- Overall status: **%s**" % report["status"].upper(),
        "- Run root: `%s`" % report["run_root"],
        "",
        "## Cases",
        "",
        "| Case | Status | Seconds |",
        "| --- | --- | ---: |",
    ]
    for case in report["cases"]:
        lines.append(
            "| %s | %s | %.3f |"
            % (case["name"], case["status"], float(case["elapsed_seconds"]))
        )
        if case.get("error"):
            lines.append("")
            lines.append("Failure: `%s`" % case["error"])
    lines.extend(
        [
            "",
            "## Scope",
            "",
            "This is a native-engine parameter contract, not a convergence or biological-result benchmark.",
            "It proves that fixed d/e, period d/e inheritance/override, maxareas and period masks/matrices",
            "change lagrange-ng raw output in controlled A/B runs, and that BayArea prior scales, seed,",
            "initial-rate mode, independent-chain execution and pooled raw state counts are reproducible.",
            "",
            "The one-cycle BayArea probes are intentionally diagnostic and must not be interpreted as MCMC results.",
            "",
            "Machine-readable report: `%s`" % REPORT_JSON_PATH,
        ]
    )
    REPORT_MARKDOWN_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    input_paths = {
        "Psychotria.tree": DATA_ROOT / "Psychotria.tree",
        "distribution.csv": DATA_ROOT / "distribution.csv",
        "coordinates.csv": DATA_ROOT / "coordinates.csv",
    }
    engine_paths = {
        "lagrange-ng.exe": LAGRANGE_EXE,
        "bayarea.exe": BAYAREA_EXE,
    }
    for name, path in input_paths.items():
        check(
            sha256(path).upper() == expected["provenance"]["inputs"][name].upper(),
            "WP2 input hash differs for %s" % name,
        )
    for name, path in engine_paths.items():
        check(
            sha256(path).upper() == expected["provenance"]["engines"][name].upper(),
            "WP2 engine hash differs for %s" % name,
        )
    tree, matrix, coordinates = load_inputs()
    cases = []
    report = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
        "run_root": str(RUN_ROOT),
        "expected_path": str(EXPECTED_PATH),
        "inputs": {
            "tree": {"path": str(DATA_ROOT / "Psychotria.tree"), "sha256": sha256(DATA_ROOT / "Psychotria.tree")},
            "matrix": {"path": str(DATA_ROOT / "distribution.csv"), "sha256": sha256(DATA_ROOT / "distribution.csv")},
            "coordinates": {"path": str(DATA_ROOT / "coordinates.csv"), "sha256": sha256(DATA_ROOT / "coordinates.csv")},
        },
        "engines": {
            "lagrange_ng": {"path": str(LAGRANGE_EXE), "sha256": sha256(LAGRANGE_EXE)},
            "bayarea": {"path": str(BAYAREA_EXE), "sha256": sha256(BAYAREA_EXE)},
        },
        "runtime_identity": {
            "python_executable": sys.executable,
            "python_version": sys.version.replace("\n", " "),
            "platform": platform.platform(),
        },
        "code_identity": {
            "git_commit": git_output("rev-parse", "HEAD"),
            "tracked_worktree_dirty": git_worktree_status()["tracked_dirty"],
            "git_status_porcelain": git_worktree_status()["porcelain"],
            "script_sha256": sha256(Path(__file__)),
            "expected_sha256": sha256(EXPECTED_PATH),
        },
        "cases": cases,
    }

    run_case(
        "lagrange-ng fixed d/e + maxareas",
        lambda: lagrange_fixed_de_check(expected["lagrange_ng"]["fixed_de"], tree, matrix),
        cases,
    )
    run_case(
        "lagrange-ng period d/e + matrix/exclude rules",
        lambda: lagrange_period_check(expected["lagrange_ng"]["period_rules"], tree, matrix),
        cases,
    )
    run_case(
        "BayArea prior wiring + initial-rate mode",
        lambda: bayarea_prior_and_initial_rate_check(expected["bayarea"], tree, matrix, coordinates),
        cases,
    )
    run_case(
        "BayArea fixed-seed multi-chain reproducibility",
        lambda: bayarea_multi_chain_check(expected["bayarea"]["multi_chain"], tree, matrix, coordinates),
        cases,
    )

    report["status"] = "passed" if all(case["status"] == "passed" for case in cases) else "failed"
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    write_reports(report)
    print("WP2 parameter contract: %s" % report["status"])
    print("Report: %s" % REPORT_JSON_PATH)
    print("Latest: %s" % REPORT_MARKDOWN_PATH)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
