import argparse
import csv
import json
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def read_nexus_first_tree(path):
    from ete3 import Tree

    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    translate = {}
    in_translate = False
    tree_line = ""
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("translate"):
            in_translate = True
            stripped = stripped[len("translate"):].strip()
            lower = stripped.lower()
        if in_translate:
            if lower.startswith("tree "):
                in_translate = False
            else:
                part = stripped.rstrip(";").rstrip(",").strip()
                if part:
                    bits = part.split(None, 1)
                    if len(bits) == 2:
                        translate[bits[0].strip()] = (
                            bits[1].strip().strip(",;").strip("'").strip('"')
                        )
                if stripped.endswith(";"):
                    in_translate = False
                continue
        if lower.startswith("tree "):
            tree_line = stripped
            break
    if not tree_line:
        raise RuntimeError("No tree line in %s" % path)
    newick = tree_line.split("=", 1)[1].strip()
    if newick.startswith("[&R]") or newick.startswith("[&U]"):
        newick = newick[4:].strip()
    tree = Tree(newick, format=1)
    for leaf in tree.iter_leaves():
        if leaf.name in translate:
            leaf.name = translate[leaf.name]
    return tree


def group_label(raw):
    if raw == "Amniotes_total_group":
        return "Amniotes total group"
    if raw == "Ancestral_regime":
        return "Ancestral regime"
    if raw == "Dissorophoidea":
        return "Dissorophoidea including Amphibamiformes"
    if raw == "Amphibamiformes":
        return "Amphibamiformes"
    return raw or "Other"


def build_inputs(tree_count):
    from domain.models.state_matrix import StateMatrix

    trait_path = PROJECT_ROOT / "runs" / "paper_fig1_repro_corrected" / "body_size_for_r.csv"
    regime_path = PROJECT_ROOT / "runs" / "source_data" / "regime_used" / "regime_used" / "body_size.csv"
    tree_dir = (
        PROJECT_ROOT
        / "runs"
        / "source_data"
        / "sup_result"
        / "sup_result"
        / "Bodysize"
        / "bodysize_subtrees"
        / "Topology1"
    )

    trees = [read_nexus_first_tree(tree_dir / ("Tone_%sbs.nex" % i)) for i in range(1, tree_count + 1)]
    reference_tree = trees[0]
    leaf_set = set(reference_tree.get_leaf_names())

    trait_rows = list(csv.DictReader(open(str(trait_path), encoding="utf-8-sig")))
    regime_rows = list(csv.DictReader(open(str(regime_path), encoding="utf-8-sig")))
    regime = {row["Species"]: row.get("Topology1_test1", "") for row in regime_rows}

    matrix_rows = []
    occurrences = []
    group_values = {}
    for row in trait_rows:
        species = str(row.get("Species", "")).strip()
        if species not in leaf_set:
            continue
        try:
            skull_length = float(row.get("SL_mm", ""))
            min_age = float(row.get("Min_age", "nan"))
            max_age = float(row.get("Max_age", "nan"))
            log_value = float(row.get("Log10_CSL", "nan"))
        except Exception:
            continue
        matrix_rows.append({
            "ID": species,
            "Name": species,
            "Skull length (mm)": str(skull_length),
        })
        group = group_label(regime.get(species, ""))
        occurrences.append({
            "taxon": species,
            "age": (min_age + max_age) / 2.0,
            "value": log_value,
            "group": group,
            "min_age": min_age,
            "max_age": max_age,
        })
        group_values.setdefault(group, []).append(log_value)

    matrix = StateMatrix(
        ids=[row["ID"] for row in matrix_rows],
        taxa_names=[row["Name"] for row in matrix_rows],
        state_columns=["Skull length (mm)"],
        rows=matrix_rows,
        source_path=str(trait_path),
    )
    entries = [SimpleNamespace(parsed_tree=tree) for tree in trees]
    return reference_tree, matrix, entries, occurrences, group_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100000)
    parser.add_argument("--sample", type=int, default=1000)
    parser.add_argument("--burnin", type=int, default=10000)
    parser.add_argument("--tree-count", type=int, default=25)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--bootstrap", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260608)
    parser.add_argument("--run-name", default="")
    parser.add_argument("--no-dtt", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    from app.bootstrap import ApplicationBootstrap

    bootstrap = ApplicationBootstrap()
    bootstrap.inject_conda_dll_paths()
    bootstrap.inject_vendor_packages()

    from application.services.bayestraits_analysis_service import BayesTraitsAnalysisService
    from application.services.continuous_trait_figure_exporter import ContinuousTraitPublicationFigureExporter
    from domain.models.bayestraits_config import BayesTraitsConfig

    tree_count = max(1, min(30, int(args.tree_count)))
    run_name = args.run_name or (
        "paper_topology1_csl_dtt_%strees_%siter" % (tree_count, int(args.iterations))
    )
    out_root = PROJECT_ROOT / "runs" / "bayestraits" / run_name
    if args.clean and out_root.exists():
        shutil.rmtree(str(out_root))
    out_root.mkdir(parents=True, exist_ok=True)

    progress_path = out_root / "progress.log"

    def log(message):
        text = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
        print(text, flush=True)
        with open(str(progress_path), "a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    log("Loading paper data and %s dated trees" % tree_count)
    reference_tree, matrix, entries, occurrences, group_values = build_inputs(tree_count)

    config = BayesTraitsConfig(
        trait_columns=["Skull length (mm)"],
        trait_column="Skull length (mm)",
        selected_trait_columns=["Skull length (mm)"],
        model="CONTINUOUS_RANDOM_WALK",
        analysis_method="MCMC",
        ml_tries=10,
        iterations=int(args.iterations),
        sample_frequency=int(args.sample),
        burnin=int(args.burnin),
        continuous_asr=True,
        continuous_transform="log10",
        continuous_display_scale="original",
        continuous_plot_scale="analysis",
        continuous_dtt=not bool(args.no_dtt),
        continuous_dtt_tree_limit=tree_count,
        continuous_dtt_threads=max(1, int(args.threads)),
        continuous_dtt_random_seed=int(args.seed),
        continuous_dtt_time_step=5.0,
        continuous_dtt_age_offset=273.01,
        continuous_dtt_bootstrap_count=max(1, int(args.bootstrap)),
        continuous_dtt_weight_mode="corrected",
        selected_node_ids=[],
    )
    config.validate()

    log(
        "Running BayesTraits: iterations=%s sample=%s burnin=%s DTT threads=%s bootstrap=%s"
        % (args.iterations, args.sample, args.burnin, args.threads, args.bootstrap)
    )
    service = BayesTraitsAnalysisService(
        executable_path=PROJECT_ROOT / "engines" / "bayestraits" / "BayesTraitsV5.exe",
        work_root=out_root,
    )
    result = service.analyze(
        reference_tree=reference_tree,
        matrix=matrix,
        config=config,
        tree_entries=entries,
        run_name="run",
    )
    log("BayesTraits and DTT finished; exporting figure")

    result.figure_occurrences = occurrences
    result.figure_group_values = group_values
    result.figure_group_order = [
        "Stem tetrapod",
        "Dissorophoidea including Amphibamiformes",
        "Amphibamiformes",
        "Amniotes total group",
        "Ancestral regime",
        "Other",
    ]
    result.figure_group_colors = {
        "Amniotes total group": "#7b6bb3",
        "Ancestral regime": "#60b8e6",
        "Dissorophoidea including Amphibamiformes": "#78b97a",
        "Amphibamiformes": "#70b7d5",
        "Stem tetrapod": "#8c7bc1",
        "Other": "#999999",
    }
    result.figure_time_bands = [
        {"start": 419.2, "end": 358.9, "label": "Devonian", "color": "#d9d9d9", "alpha": 0.45},
        {"start": 358.9, "end": 298.9, "label": "Carboniferous", "color": "#eeeeee", "alpha": 0.45},
        {"start": 298.9, "end": 251.9, "label": "Permian", "color": "#d9d9d9", "alpha": 0.45},
    ]

    summary_path = out_root / ("%s_summary.json" % run_name)
    figure_path = out_root / ("%s.png" % run_name)
    ContinuousTraitPublicationFigureExporter().export(
        result,
        str(figure_path),
        method_name="BayesTraits MCMC CSL %s-tree large test" % tree_count,
    )

    payload = {
        "run_name": run_name,
        "node_count": len(result.node_results),
        "tip_count": len(result.tip_values),
        "occurrence_count": len(result.figure_occurrences),
        "time_series_points": len(result.figure_time_series.get("x", [])),
        "time_series_x": result.figure_time_series.get("x", []),
        "time_series_y": result.figure_time_series.get("y", []),
        "model_statistics": result.model_statistics,
        "figure": str(figure_path),
        "progress": str(progress_path),
    }
    with open(str(summary_path), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    log("DONE")
    print(json.dumps({
        "summary_path": str(summary_path),
        "figure_path": str(figure_path),
        "progress_path": str(progress_path),
        "node_count": payload["node_count"],
        "tip_count": payload["tip_count"],
        "occurrence_count": payload["occurrence_count"],
        "time_series_points": payload["time_series_points"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
