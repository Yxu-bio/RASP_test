import argparse
import csv
import json
import math
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read_nexus_trees(path, limit=None):
    from ete3 import Tree

    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    translate = {}
    trees = []
    in_translate = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith("translate"):
            in_translate = True
            stripped = stripped[len("translate"):].strip()
            lower = stripped.lower()
        if in_translate:
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
            newick = stripped.split("=", 1)[1].strip()
            if newick.startswith("[&R]") or newick.startswith("[&U]"):
                newick = newick[4:].strip()
            tree = Tree(newick, format=1)
            for leaf in tree.iter_leaves():
                if leaf.name in translate:
                    leaf.name = translate[leaf.name]
            trees.append(tree)
            if limit and len(trees) >= limit:
                break
    return trees


def _node_depths(tree):
    depths = {tree: 0.0}
    for node in tree.traverse("preorder"):
        depth = float(depths.get(node, 0.0))
        for child in node.children:
            depths[child] = depth + max(0.0, float(child.dist or 0.0))
    return depths


def _make_ultrametric_time_tree(tree, target_root_age):
    """Convert an arbitrary branch-length tree into an extant-tip dated tree."""
    copy_tree = tree.copy(method="deepcopy")
    depths = _node_depths(copy_tree)
    leaf_depths = [float(depths[leaf]) for leaf in copy_tree.iter_leaves()]
    max_depth = max(leaf_depths) if leaf_depths else 0.0
    if max_depth <= 0.0:
        return copy_tree

    raw_ages = {}
    for node in copy_tree.traverse("postorder"):
        if node.is_leaf():
            raw_ages[node] = 0.0
        else:
            raw_ages[node] = max(
                float(child.dist or 0.0) + raw_ages.get(child, 0.0)
                for child in node.children
            )
    root_age = raw_ages.get(copy_tree, max_depth)
    scale = float(target_root_age) / root_age if root_age > 0.0 else 1.0
    ages = {node: raw_ages.get(node, 0.0) * scale for node in raw_ages}
    for node in copy_tree.traverse("preorder"):
        for child in node.children:
            child.dist = max(0.000001, ages.get(node, 0.0) - ages.get(child, 0.0))
    return copy_tree


def _build_inputs(tree_count, trait_column, target_root_age):
    from domain.models.state_matrix import StateMatrix

    data_dir = PROJECT_ROOT / "examples" / "Primate" / "Trees_States"
    tree_path = data_dir / "Primates.tree"
    trees_path = data_dir / "100Trees.trees"
    characters_path = data_dir / "characters.csv"

    reference_tree = _make_ultrametric_time_tree(
        _read_nexus_trees(tree_path, limit=1)[0],
        target_root_age,
    )
    candidate_trees = _read_nexus_trees(trees_path, limit=max(1, tree_count))
    dated_trees = [
        _make_ultrametric_time_tree(tree, target_root_age)
        for tree in candidate_trees[:tree_count]
    ]
    if not dated_trees:
        dated_trees = [reference_tree.copy(method="deepcopy")]

    leaf_set = set(reference_tree.get_leaf_names())
    rows = []
    group_values = {}
    occurrences = []
    with open(str(characters_path), newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            taxon = str(row.get("Name", "") or "").strip()
            if taxon not in leaf_set:
                continue
            raw_value = str(row.get(trait_column, "") or "").strip()
            if not raw_value:
                continue
            try:
                value = float(raw_value)
            except Exception:
                continue
            if not math.isfinite(value) or value <= 0.0:
                continue
            rows.append({
                "ID": str(row.get("ID", taxon) or taxon).strip(),
                "Name": taxon,
                trait_column: str(value),
            })
            group = "Sociality %s" % (str(row.get("Sociality", "") or "?").strip() or "?")
            plot_value = math.log10(value)
            group_values.setdefault(group, []).append(plot_value)
            occurrences.append({
                "taxon": taxon,
                "age": 0.0,
                "value": plot_value,
                "group": group,
            })

    matrix = StateMatrix(
        ids=[row["ID"] for row in rows],
        taxa_names=[row["Name"] for row in rows],
        state_columns=[trait_column],
        rows=rows,
        source_path=str(characters_path),
    )
    entries = [SimpleNamespace(parsed_tree=tree) for tree in dated_trees]
    return reference_tree, matrix, entries, occurrences, group_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20000)
    parser.add_argument("--sample", type=int, default=1000)
    parser.add_argument("--burnin", type=int, default=5000)
    parser.add_argument("--tree-count", type=int, default=25)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--bootstrap", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260608)
    parser.add_argument("--root-age", type=float, default=74.0)
    parser.add_argument("--trait", default="Brain size species mean")
    parser.add_argument(
        "--model",
        choices=["CONTINUOUS_RANDOM_WALK", "CONTINUOUS_DIRECTIONAL"],
        default="CONTINUOUS_RANDOM_WALK",
    )
    parser.add_argument("--run-name", default="")
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
        "primate_%s_%strees_%siter"
        % (args.trait.lower().replace(" ", "_"), tree_count, int(args.iterations))
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

    log("Loading Primate data and creating %s synthetic dated trees" % tree_count)
    reference_tree, matrix, entries, occurrences, group_values = _build_inputs(
        tree_count,
        args.trait,
        args.root_age,
    )
    log("Matrix rows=%s trait=%s" % (matrix.row_count(), args.trait))

    config = BayesTraitsConfig(
        trait_columns=[args.trait],
        trait_column=args.trait,
        selected_trait_columns=[args.trait],
        model=args.model,
        analysis_method="MCMC",
        ml_tries=10,
        iterations=int(args.iterations),
        sample_frequency=int(args.sample),
        burnin=int(args.burnin),
        continuous_asr=True,
        continuous_transform="log10",
        continuous_display_scale="original",
        continuous_plot_scale="analysis",
        continuous_dtt=True,
        continuous_dtt_tree_limit=tree_count,
        continuous_dtt_threads=max(1, int(args.threads)),
        continuous_dtt_random_seed=int(args.seed),
        continuous_dtt_time_step=5.0,
        continuous_dtt_age_offset=0.0,
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
    result.figure_group_order = sorted(group_values.keys())
    result.figure_group_colors = {
        "Sociality A": "#6d6ab1",
        "Sociality B": "#60b8e6",
        "Sociality C": "#78b97a",
        "Sociality D": "#e07a5f",
        "Sociality AB": "#b68ccf",
        "Sociality AC": "#d5bd48",
        "Sociality AD": "#8aa8d9",
        "Sociality BC": "#64b5a5",
        "Sociality BD": "#ce9c5d",
        "Sociality CD": "#a1a85a",
        "Sociality BCD": "#d47a9f",
    }

    figure_path = out_root / ("%s.png" % run_name)
    ContinuousTraitPublicationFigureExporter().export(
        result,
        str(figure_path),
        method_name="BayesTraits MCMC Primate continuous test",
    )

    summary_path = out_root / ("%s_summary.json" % run_name)
    payload = {
        "run_name": run_name,
        "trait": args.trait,
        "matrix_rows": matrix.row_count(),
        "node_count": len(result.node_results),
        "tip_count": len(result.tip_values),
        "tree_count": tree_count,
        "root_age": float(args.root_age),
        "time_series_points": len(result.figure_time_series.get("x", [])),
        "time_series_x": result.figure_time_series.get("x", []),
        "time_series_y": result.figure_time_series.get("y", []),
        "time_series_lower": result.figure_time_series.get("lower", []),
        "time_series_upper": result.figure_time_series.get("upper", []),
        "model_statistics": dict(getattr(result, "model_statistics", {}) or {}),
        "figure_path": str(figure_path),
        "analysis_log_path": str(getattr(result, "analysis_log_path", "") or ""),
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log("Wrote figure: %s" % figure_path)
    log("Wrote summary: %s" % summary_path)


if __name__ == "__main__":
    main()
