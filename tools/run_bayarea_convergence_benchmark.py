import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime
from itertools import combinations
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

from app.bootstrap import ApplicationBootstrap

ApplicationBootstrap().inject_vendor_packages()

from ete3 import Tree

from application.services.bayarea_analysis_service import BayAreaAnalysisService
from domain.models.bayarea_config import BayAreaConfig
from domain.models.sdiva_config import infer_sdiva_area_names
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.tree.tree_reader import TreeReader


DEFAULT_SPEC = PROJECT_ROOT / "data" / "benchmarks" / "psychotria" / "bayarea_convergence_spec.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "runs" / "benchmarks" / "bayarea_convergence"
DEFAULT_REPORT = PROJECT_ROOT / "docs" / "bayarea_convergence_latest.md"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the reproducible Psychotria BayArea multi-chain convergence benchmark."
    )
    parser.add_argument("--spec", default=str(DEFAULT_SPEC))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument(
        "--report",
        default=None,
        help=(
            "Markdown report path. The canonical report is updated by a standard full run only; "
            "smoke and parameter-override runs require an explicit path. Use an empty value to disable."
        ),
    )
    parser.add_argument("--chain-length", type=int)
    parser.add_argument("--sample-frequency", type=int)
    parser.add_argument("--burnin", type=int)
    parser.add_argument("--chains", type=int)
    parser.add_argument("--parallel-chains", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run two short 100,000-cycle chains and report plumbing only; convergence is not graded.",
    )
    parser.add_argument(
        "--allow-nonconverged",
        action="store_true",
        help="Write the full report but return success when the minimum diagnostic threshold is missed.",
    )
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def resolve_input(spec, name):
    path = PROJECT_ROOT / str(spec["inputs"][name])
    if not path.exists():
        raise FileNotFoundError("BayArea benchmark %s input was not found: %s" % (name, path))
    expected = str(spec["inputs"].get("sha256", {}).get(name, "") or "").upper()
    actual = sha256(path)
    if expected and actual != expected:
        raise RuntimeError(
            "BayArea benchmark %s input hash differs. Expected %s, found %s."
            % (name, expected, actual)
        )
    return path, actual


def load_coordinates(path, area_names):
    coordinates = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 3:
                continue
            area = str(row[0]).strip()
            if area in area_names:
                coordinates[area] = (float(row[1]), float(row[2]))
    missing = [area for area in area_names if area not in coordinates]
    if missing:
        raise ValueError("Coordinates are missing for areas: %s" % ", ".join(missing))
    return coordinates


def make_config(spec, args, area_names, coordinates):
    values = dict(spec.get("config", {}) or {})
    config = BayAreaConfig.default_for_areas(area_names)
    config.coordinates = coordinates
    for name in [
        "model_type",
        "chain_length",
        "sample_frequency",
        "burnin",
        "independent_chains",
        "parallel_chains",
        "seed",
        "guess_initial_rates",
        "use_auxiliary_sampling",
        "geo_distance_power_positive",
        "geo_distance_truncate",
        "gain_prior",
        "loss_prior",
        "distance_power_prior",
        "area_proposal_tuner",
        "rate_proposal_tuner",
        "distance_proposal_tuner",
    ]:
        if name in values:
            setattr(config, name, values[name])

    if args.smoke:
        config.chain_length = 100000
        config.sample_frequency = 1000
        config.burnin = 10000
        config.independent_chains = 2
        config.parallel_chains = 2
    for value, name in [
        (args.chain_length, "chain_length"),
        (args.sample_frequency, "sample_frequency"),
        (args.burnin, "burnin"),
        (args.chains, "independent_chains"),
        (args.parallel_chains, "parallel_chains"),
        (args.seed, "seed"),
    ]:
        if value is not None:
            setattr(config, name, value)
    config.validate()
    return config


def read_parameter_rows(path):
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 2:
        raise ValueError("BayArea parameters file has no samples: %s" % path)
    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            continue
        try:
            row = {name: float(value) for name, value in zip(header, parts)}
        except Exception:
            continue
        rows.append(row)
    return rows


def checkpoint_summary(service, rows_by_chain, end_cycle, burnin, trace_names, thresholds):
    selected_rows = [
        [row for row in rows if int(row.get("n", 0)) >= burnin and int(row.get("n", 0)) <= end_cycle]
        for rows in rows_by_chain
    ]
    traces = {}
    for name in trace_names:
        values_by_chain = [
            [float(row[name]) for row in rows if name in row and math.isfinite(float(row[name]))]
            for rows in selected_rows
        ]
        if not values_by_chain or any(not values for values in values_by_chain):
            continue
        diagnostics = [service.output_parser._trace_diagnostic(values) for values in values_by_chain]
        trace_summary = {
            "split_rhat": service._split_rhat(values_by_chain),
            "retained_samples_by_chain": [len(values) for values in values_by_chain],
            "ess_by_chain": [float(item.get("ess_approx", 0.0) or 0.0) for item in diagnostics],
            "minimum_per_chain_ess": min(float(item.get("ess_approx", 0.0) or 0.0) for item in diagnostics),
            "maximum_standardized_half_shift": max(
                float(item.get("standardized_half_shift", 0.0) or 0.0) for item in diagnostics
            ),
            "means_by_chain": [sum(values) / float(len(values)) for values in values_by_chain],
        }
        trace_summary["minimum_passed"] = diagnostics_passed({name: trace_summary}, thresholds["minimum"])
        trace_summary["target_passed"] = diagnostics_passed({name: trace_summary}, thresholds["target"])
        traces[name] = trace_summary
    all_traces_present = all(name in traces for name in trace_names)
    return {
        "end_cycle": int(end_cycle),
        "burnin": int(burnin),
        "traces": traces,
        "all_traces_present": all_traces_present,
        "missing_traces": [name for name in trace_names if name not in traces],
        "minimum_passed": all_traces_present and diagnostics_passed(traces, thresholds["minimum"]),
        "target_passed": all_traces_present and diagnostics_passed(traces, thresholds["target"]),
    }


def diagnostics_passed(traces, threshold):
    if not traces:
        return False
    for item in traces.values():
        rhat = item.get("split_rhat")
        if rhat is None or not math.isfinite(float(rhat)):
            return False
        if float(rhat) > float(threshold["maximum_split_rhat"]):
            return False
        if float(item.get("minimum_per_chain_ess", 0.0)) < float(threshold["minimum_per_chain_ess"]):
            return False
        if float(item.get("maximum_standardized_half_shift", float("inf"))) > float(
            threshold["maximum_standardized_half_shift"]
        ):
            return False
    return True


def distribution_for_node(node_result):
    counts = dict(getattr(node_result, "raw_method_payload", {}).get("bayarea_counts", {}) or {})
    total = float(sum(float(value) for value in counts.values()))
    if total <= 0.0:
        return {}
    return {state: float(value) / total for state, value in counts.items()}


def total_variation(left, right):
    states = set(left) | set(right)
    return 0.5 * sum(abs(float(left.get(state, 0.0)) - float(right.get(state, 0.0))) for state in states)


def chain_state_agreement(service, tree, result, config):
    statistics = dict(result.model_statistics or {})
    records = list(statistics.get("bayarea_chain_runs", []) or [])
    expected_chains = int(config.independent_chains)
    if len(records) != expected_chains:
        raise RuntimeError(
            "Expected %d BayArea chain records for posterior comparison, found %d."
            % (expected_chains, len(records))
        )
    chain_results = []
    for record in records:
        chain_result, _run_files = service._parse_existing_chain(
            reference_tree=tree,
            record=record,
            burnin=int(config.burnin),
            config=config,
            fallback_stats=statistics,
        )
        chain_results.append(chain_result)

    expected_node_count = sum(1 for node in tree.traverse("postorder") if not node.is_leaf())
    node_keys_by_chain = [set(chain_result.node_results) for chain_result in chain_results]
    for index, node_keys in enumerate(node_keys_by_chain, start=1):
        if len(node_keys) != expected_node_count:
            raise RuntimeError(
                "BayArea chain %d parsed %d internal nodes; expected %d from the input tree."
                % (index, len(node_keys), expected_node_count)
            )
    reference_node_keys = node_keys_by_chain[0]
    for index, node_keys in enumerate(node_keys_by_chain[1:], start=2):
        if node_keys != reference_node_keys:
            raise RuntimeError(
                "BayArea chain %d has a different internal-node set from chain 1."
                % index
            )

    node_rows = []
    for clade_key in sorted(reference_node_keys):
        distributions = [distribution_for_node(item.node_results[clade_key]) for item in chain_results]
        if any(not distribution for distribution in distributions):
            raise RuntimeError(
                "BayArea node %s has an empty posterior distribution in at least one chain."
                % clade_key
            )
        top_states = [
            max(distribution.items(), key=lambda pair: (pair[1], pair[0]))[0] if distribution else ""
            for distribution in distributions
        ]
        pairwise_tv = [total_variation(distributions[a], distributions[b]) for a, b in combinations(range(len(distributions)), 2)]
        template = chain_results[0].node_results[clade_key]
        node_rows.append({
            "clade_key": clade_key,
            "node_id": str(getattr(template, "display_node_id", "") or ""),
            "top_states": top_states,
            "unanimous_top_state": len(set(top_states)) == 1,
            "maximum_pairwise_total_variation": max(pairwise_tv) if pairwise_tv else 0.0,
        })

    tv_values = sorted(float(item["maximum_pairwise_total_variation"]) for item in node_rows)
    median_tv = 0.0
    if tv_values:
        midpoint = len(tv_values) // 2
        if len(tv_values) % 2:
            median_tv = tv_values[midpoint]
        else:
            median_tv = (tv_values[midpoint - 1] + tv_values[midpoint]) / 2.0
    disagreements = sorted(
        [item for item in node_rows if not item["unanimous_top_state"]],
        key=lambda item: (-float(item["maximum_pairwise_total_variation"]), item["node_id"]),
    )
    return {
        "expected_node_count": expected_node_count,
        "node_count": len(node_rows),
        "unanimous_top_state_count": sum(1 for item in node_rows if item["unanimous_top_state"]),
        "unanimous_top_state_fraction": (
            sum(1 for item in node_rows if item["unanimous_top_state"]) / float(len(node_rows))
            if node_rows else 0.0
        ),
        "median_maximum_pairwise_total_variation": median_tv,
        "maximum_pairwise_total_variation": max(tv_values) if tv_values else 0.0,
        "largest_disagreements": disagreements[:10],
    }


def format_number(value, digits=3):
    if value is None:
        return "n/a"
    if not math.isfinite(float(value)):
        return "infinite"
    return ("%%.%df" % digits) % float(value)


def display_path(path_text):
    path = Path(str(path_text or "")).resolve()
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def resolve_report_path(args, spec_path):
    if args.report is not None:
        return Path(args.report).resolve() if str(args.report).strip() else None
    has_parameter_override = any(
        value is not None
        for value in [
            args.chain_length,
            args.sample_frequency,
            args.burnin,
            args.chains,
            args.parallel_chains,
            args.seed,
        ]
    )
    if not args.smoke and Path(spec_path).resolve() == DEFAULT_SPEC.resolve() and not has_parameter_override:
        return DEFAULT_REPORT.resolve()
    return None


def render_markdown(payload):
    config = payload["config"]
    final = payload["checkpoints"][-1]
    agreement = payload["state_agreement"]
    lines = [
        "# BayArea Psychotria multi-chain convergence benchmark",
        "",
        "Last run: `%s`" % payload["finished_at"],
        "",
        "This is a real RASP service-path run of the patched BayArea executable, not a synthetic diagnostic. "
        "The diagnostics are the same lightweight split-Rhat and autocorrelation ESS used by the RASP Tracer view; "
        "they are not rank-normalized Stan diagnostics.",
        "",
        "## Case",
        "",
        "- Dataset: bundled Psychotria tree and four-area range matrix (19 taxa).",
        "- Model: `%s`." % config["model_type"],
        "- Chains: `%d` independent chains, up to `%d` in parallel." % (
            config["independent_chains"], config["parallel_chains"]
        ),
        "- Chain length: `%d`; sample frequency: `%d`; final burn-in: `%d`." % (
            config["chain_length"], config["sample_frequency"], config["burnin"]
        ),
        "- Base seed: `%d`; actual chain seeds: `%s`." % (
            config["seed"], ", ".join(str(value) for value in payload["chain_seeds"])
        ),
        "- Wall time: `%.2f s`." % float(payload["elapsed_seconds"]),
        "- Raw run directory: `%s`." % display_path(payload["run_root"]),
        "",
        "## Convergence trajectory",
        "",
        "| End cycle | Burn-in | Trace | Split-Rhat | Min per-chain ESS | Max half-shift | Minimum | Target |",
        "| ---: | ---: | --- | ---: | ---: | ---: | :---: | :---: |",
    ]
    for checkpoint in payload["checkpoints"]:
        for name in payload["trace_names"]:
            item = checkpoint["traces"].get(name, {})
            lines.append(
                "| %d | %d | `%s` | %s | %s | %s | %s | %s |"
                % (
                    checkpoint["end_cycle"],
                    checkpoint["burnin"],
                    name,
                    format_number(item.get("split_rhat"), 3),
                    format_number(item.get("minimum_per_chain_ess"), 1),
                    format_number(item.get("maximum_standardized_half_shift"), 3),
                    "pass" if item.get("minimum_passed") else "not yet",
                    "pass" if item.get("target_passed") else "not yet",
                )
            )
    lines.extend([
        "",
        "Operational minimum: split-Rhat <= `%.3f`, minimum per-chain ESS >= `%.0f`, and maximum half-mean shift <= `%.3f` posterior SD for every monitored trace. "
        "The stricter target is split-Rhat <= `%.3f`, ESS >= `%.0f`, and half-mean shift <= `%.3f` SD."
        % (
            payload["thresholds"]["minimum"]["maximum_split_rhat"],
            payload["thresholds"]["minimum"]["minimum_per_chain_ess"],
            payload["thresholds"]["minimum"]["maximum_standardized_half_shift"],
            payload["thresholds"]["target"]["maximum_split_rhat"],
            payload["thresholds"]["target"]["minimum_per_chain_ess"],
            payload["thresholds"]["target"]["maximum_standardized_half_shift"],
        ),
        "",
        "Final diagnostic result: **%s**; strict target: **%s**."
        % ("minimum passed" if final["minimum_passed"] else "minimum not passed", "passed" if final["target_passed"] else "not passed"),
        "",
        "## Node posterior agreement",
        "",
        "After the final burn-in, `%d/%d` internal nodes (`%.1f%%`) had the same highest-probability range in all `%d` chains. "
        "The median of each node's maximum pairwise total-variation distance was `%.3f`; the maximum was `%.3f`. "
        "Differences at uncertain nodes are reported rather than treated as an automatic convergence failure."
        % (
            agreement["unanimous_top_state_count"],
            agreement["node_count"],
            agreement["unanimous_top_state_fraction"] * 100.0,
            config["independent_chains"],
            agreement["median_maximum_pairwise_total_variation"],
            agreement["maximum_pairwise_total_variation"],
        ),
    ])
    if agreement["largest_disagreements"]:
        lines.extend([
            "",
            "| Node | Chain top ranges | Max pairwise TV |",
            "| --- | --- | ---: |",
        ])
        for item in agreement["largest_disagreements"]:
            lines.append(
                "| %s | %s | %.3f |"
                % (
                    item["node_id"] or "(unnumbered)",
                    " / ".join(item["top_states"]),
                    item["maximum_pairwise_total_variation"],
                )
            )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "A completed BayArea process is not by itself a convergence result. Use all monitored traces, independent seeds, "
        "and the node posterior comparison together. If the minimum is missed, increase chain length, retain the same "
        "sampling interval, choose a defensible burn-in from the trace, and rerun independent chains. Do not repair a "
        "failed diagnostic by pooling non-converged chains.",
        "",
        "Fixed input and engine SHA256 values are stored in "
        "`data/benchmarks/psychotria/bayarea_convergence_spec.json`; each run also copies them into its raw JSON report.",
        "",
    ])
    return "\n".join(lines)


def main():
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    spec = read_json(spec_path)
    tree_path, tree_hash = resolve_input(spec, "tree")
    matrix_path, matrix_hash = resolve_input(spec, "matrix")
    coordinates_path, coordinates_hash = resolve_input(spec, "coordinates")
    engine_path = PROJECT_ROOT / "engines" / "bayarea" / "bin" / "bayarea.exe"
    if not engine_path.exists():
        raise FileNotFoundError("BayArea executable was not found: %s" % engine_path)
    engine_hash = sha256(engine_path)
    expected_engine = str(spec["inputs"].get("sha256", {}).get("engine", "") or "").upper()
    if expected_engine and engine_hash != expected_engine:
        raise RuntimeError(
            "BayArea executable hash differs. Expected %s, found %s." % (expected_engine, engine_hash)
        )

    tree_text = TreeReader().read_tree(str(tree_path))
    tree = Tree(tree_text, format=1)
    matrix = CsvMatrixReader().read(str(matrix_path))
    area_names = infer_sdiva_area_names(matrix)
    coordinates = load_coordinates(coordinates_path, area_names)
    config = make_config(spec, args, area_names, coordinates)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = Path(args.output_root).resolve() / ("%s_%s" % (spec["case_id"], stamp))
    run_root.mkdir(parents=True, exist_ok=True)
    service = BayAreaAnalysisService(
        executable_path=engine_path,
        work_root=run_root / "chains",
    )
    progress_state = {"percent": -5}

    def progress(percent, message):
        percent = int(percent)
        if percent >= progress_state["percent"] + 5 or percent >= 100:
            progress_state["percent"] = percent
            print("[%3d%%] %s" % (percent, message), flush=True)

    print("BayArea convergence benchmark: %s" % spec["case_id"], flush=True)
    print("Run root: %s" % run_root, flush=True)
    started_at = datetime.now()
    started = time.monotonic()
    result = service.analyze(
        tree=tree,
        matrix=matrix,
        config=config,
        run_name=spec["case_id"],
        progress_callback=progress,
    )
    elapsed = time.monotonic() - started
    finished_at = datetime.now()

    statistics = dict(result.model_statistics or {})
    parameter_paths = [Path(value) for value in statistics.get("bayarea_chain_parameters_paths", [])]
    if len(parameter_paths) != int(config.independent_chains):
        raise RuntimeError(
            "Expected %d chain parameter files, found %d."
            % (config.independent_chains, len(parameter_paths))
        )
    rows_by_chain = [read_parameter_rows(path) for path in parameter_paths]
    diagnostic_spec = dict(spec.get("diagnostics", {}) or {})
    trace_names = list(diagnostic_spec.get("traces", ["lnL", "gain", "loss", "distP"]))
    burnin_fraction = float(diagnostic_spec.get("burnin_fraction", 0.1))
    checkpoints = []
    for fraction in diagnostic_spec.get("checkpoint_fractions", [1.0]):
        end_cycle = int(round(float(config.chain_length) * float(fraction)))
        end_cycle = max(int(config.sample_frequency), min(int(config.chain_length), end_cycle))
        burnin = int(math.floor(end_cycle * burnin_fraction / config.sample_frequency)) * int(config.sample_frequency)
        if end_cycle == int(config.chain_length):
            burnin = int(config.burnin)
        checkpoints.append(
            checkpoint_summary(
                service,
                rows_by_chain,
                end_cycle,
                burnin,
                trace_names,
                diagnostic_spec,
            )
        )

    agreement = chain_state_agreement(service, tree, result, config)
    payload = {
        "schema_version": 1,
        "case_id": spec["case_id"],
        "spec_path": str(spec_path),
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
        "elapsed_seconds": elapsed,
        "run_root": str(run_root),
        "input_hashes": {
            "tree": tree_hash,
            "matrix": matrix_hash,
            "coordinates": coordinates_hash,
            "engine": engine_hash,
        },
        "config": config.to_preset_dict(),
        "chain_seeds": list(statistics.get("bayarea_chain_seeds", []) or []),
        "parameter_paths": [str(path) for path in parameter_paths],
        "trace_names": trace_names,
        "thresholds": {
            "minimum": dict(diagnostic_spec["minimum"]),
            "target": dict(diagnostic_spec["target"]),
        },
        "checkpoints": checkpoints,
        "state_agreement": agreement,
        "parse_warnings": list(result.parse_warnings or []),
    }
    json_path = run_root / "bayarea_convergence_report.json"
    markdown_path = run_root / "bayarea_convergence_report.md"
    markdown = render_markdown(payload)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    report_path = resolve_report_path(args, spec_path)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(markdown, encoding="utf-8")

    final = checkpoints[-1]
    print("Completed in %.2f seconds." % elapsed, flush=True)
    print("Minimum convergence diagnostic: %s" % ("PASS" if final["minimum_passed"] else "FAIL"), flush=True)
    print("Strict target diagnostic: %s" % ("PASS" if final["target_passed"] else "NOT MET"), flush=True)
    print("JSON report: %s" % json_path, flush=True)
    print("Markdown report: %s" % markdown_path, flush=True)
    if report_path is not None:
        print("Latest report: %s" % report_path, flush=True)
    if not args.smoke and not args.allow_nonconverged and not final["minimum_passed"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
