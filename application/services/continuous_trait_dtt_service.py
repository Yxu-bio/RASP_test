import copy
import json
import math
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


class ContinuousTraitDTTService:
    """Build disparity-through-time metadata from per-tree BayesTraits ASR runs."""

    def __init__(self, *, dataset_builder, runner, output_parser):
        self.dataset_builder = dataset_builder
        self.runner = runner
        self.output_parser = output_parser

    def attach_dtt(
        self,
        *,
        result,
        matrix,
        config,
        tree_entries,
        output_dir,
    ):
        if not bool(getattr(config, "continuous_dtt", False)):
            return result

        entries = self._select_entries(tree_entries, config)
        if not entries:
            raise ValueError("Continuous DTT requires a prepared dated tree set.")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        threads = min(max(1, int(getattr(config, "continuous_dtt_threads", 1) or 1)), len(entries))
        time_grid = self._shared_time_grid(entries, config)
        failures = []
        per_tree_summaries = []
        all_rows = []

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [
                executor.submit(
                    self._run_tree_job,
                    original_index=original_index,
                    selected_index=selected_index,
                    tree=tree,
                    matrix=matrix,
                    config=config,
                    output_dir=output_dir,
                    time_grid=time_grid,
                )
                for selected_index, (original_index, tree) in enumerate(entries, start=1)
            ]
            for future in as_completed(futures):
                try:
                    summary = future.result()
                except Exception as exc:
                    failures.append(str(exc))
                    continue
                per_tree_summaries.append(summary)
                all_rows.extend(summary.get("rows", []))

        if failures:
            raise RuntimeError(
                "Continuous DTT failed for %s tree(s).\n%s"
                % (len(failures), "\n".join(failures[:5]))
            )
        if not all_rows:
            raise RuntimeError("Continuous DTT did not produce any time-slice disparity rows.")

        time_series = self._summarise_time_series(all_rows)
        time_series.update({
            "kind": "disparity",
            "label": "BayesTraits DTT disparity",
            "x_label": "Age (Ma)" if self._age_offset(config) else "Age (tree units)",
            "y_label": "Disparity",
            "color": "#c95768",
            "weight_mode": str(getattr(config, "continuous_dtt_weight_mode", "corrected") or "corrected"),
            "estimator": "BayesTraits Continuous ASR",
            "variance_scale": str(getattr(result, "trait_transform", "none") or "none"),
            "age_offset": self._age_offset(config),
        })

        result.figure_time_series = time_series
        stats = dict(getattr(result, "model_statistics", {}) or {})
        stats.update({
            "continuous_dtt_enabled": True,
            "continuous_dtt_estimator": "BayesTraits Continuous ASR",
            "continuous_dtt_input_tree_count": len([
                entry for entry in list(tree_entries or [])
                if getattr(entry, "parsed_tree", None) is not None
            ]),
            "continuous_dtt_selected_tree_count": len(entries),
            "continuous_dtt_tree_limit": int(getattr(config, "continuous_dtt_tree_limit", 30) or 30),
            "continuous_dtt_threads": threads,
            "continuous_dtt_random_seed": int(getattr(config, "continuous_dtt_random_seed", 20260608) or 20260608),
            "continuous_dtt_time_step": float(getattr(config, "continuous_dtt_time_step", 5.0) or 5.0),
            "continuous_dtt_age_offset": self._age_offset(config),
            "continuous_dtt_bootstrap_count": int(getattr(config, "continuous_dtt_bootstrap_count", 100) or 100),
            "continuous_dtt_weight_mode": str(getattr(config, "continuous_dtt_weight_mode", "corrected") or "corrected"),
            "continuous_dtt_summary_path": str(output_dir / "continuous_dtt_summary.json"),
        })
        result.model_statistics = stats
        result.result_note = (str(getattr(result, "result_note", "") or "") + "\n"
                              "DTT uses per-tree BayesTraits internal-node estimates, corrected gradual-split "
                              "branch sampling, and variance on the analysis scale.").strip()

        payload = {
            "time_series": time_series,
            "per_tree": [
                {
                    "original_tree_index": item.get("original_tree_index"),
                    "selected_tree_index": item.get("selected_tree_index"),
                    "root_age": item.get("root_age"),
                    "row_count": len(item.get("rows", [])),
                    "run_workdir": item.get("run_workdir"),
                }
                for item in sorted(per_tree_summaries, key=lambda x: x.get("selected_tree_index", 0))
            ],
            "config": {
                "tree_limit": int(getattr(config, "continuous_dtt_tree_limit", 30) or 30),
                "threads": threads,
                "random_seed": int(getattr(config, "continuous_dtt_random_seed", 20260608) or 20260608),
                "time_step": float(getattr(config, "continuous_dtt_time_step", 5.0) or 5.0),
                "age_offset": self._age_offset(config),
                "bootstrap_count": int(getattr(config, "continuous_dtt_bootstrap_count", 100) or 100),
                "weight_mode": str(getattr(config, "continuous_dtt_weight_mode", "corrected") or "corrected"),
                "time_grid_start": time_grid[0] if time_grid else None,
                "time_grid_end": time_grid[-1] if time_grid else None,
                "time_grid_count": len(time_grid),
            },
        }
        (output_dir / "continuous_dtt_summary.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return result

    def _select_entries(self, tree_entries, config):
        indexed = []
        for idx, entry in enumerate(list(tree_entries or []), start=1):
            tree = getattr(entry, "parsed_tree", None)
            if tree is not None:
                indexed.append((idx, tree))
        if not indexed:
            return []

        limit = max(1, min(30, int(getattr(config, "continuous_dtt_tree_limit", 30) or 30)))
        if len(indexed) <= limit:
            return indexed

        seed = int(getattr(config, "continuous_dtt_random_seed", 20260608) or 20260608)
        rng = random.Random(seed)
        selected = rng.sample(indexed, limit)
        return sorted(selected, key=lambda item: item[0])

    def _run_tree_job(self, *, original_index, selected_index, tree, matrix, config, output_dir, time_grid):
        tree_config = copy.deepcopy(config)
        tree_config.continuous_asr = True
        tree_config.continuous_dtt = False
        tree_config.use_tree_collection = False
        base_seed = int(getattr(config, "continuous_dtt_random_seed", 20260608) or 20260608)
        tree_config.random_seed = self._bounded_seed(base_seed + int(original_index))

        run_name = "dtt_tree_%04d_source_%04d" % (int(selected_index), int(original_index))
        run_files = self.dataset_builder.build(
            reference_tree=tree,
            matrix=matrix,
            tree_entries=None,
            config=tree_config,
            output_dir=output_dir,
            run_name=run_name,
        )
        run_output = self.runner.run(run_files)
        per_tree_result = self.output_parser.parse(
            reference_tree=tree,
            run_files=run_files,
            run_output=run_output,
        )
        rows, root_age = self._time_slice_tree(tree, per_tree_result, config, original_index, time_grid)
        return {
            "original_tree_index": int(original_index),
            "selected_tree_index": int(selected_index),
            "root_age": root_age,
            "run_workdir": str(run_files.workdir),
            "rows": rows,
        }

    def _time_slice_tree(self, tree, per_tree_result, config, original_index, time_grid=None):
        depths = self._node_depths(tree)
        if not depths:
            return [], 0.0
        leaves = [node for node in depths if self._is_leaf(node)]
        if not leaves:
            return [], 0.0
        root_age = max(float(depths[leaf]) for leaf in leaves)
        if root_age <= 0.0:
            return [], 0.0
        age_offset = self._age_offset(config)
        ages = {node: age_offset + root_age - float(depth) for node, depth in depths.items()}
        values = self._node_values(tree, per_tree_result)
        branches = self._branches(tree, ages, values)
        if not branches:
            return [], root_age

        time_step = float(getattr(config, "continuous_dtt_time_step", 5.0) or 5.0)
        if time_step <= 0.0:
            time_step = 5.0
        if time_step >= root_age:
            time_step = max(root_age / 25.0, 0.000001)
        times = list(time_grid or self._time_grid(age_offset + root_age, age_offset, time_step))
        bootstrap_count = max(1, int(getattr(config, "continuous_dtt_bootstrap_count", 100) or 100))
        seed = int(getattr(config, "continuous_dtt_random_seed", 20260608) or 20260608)
        rng = random.Random(self._bounded_seed(seed + int(original_index) * 1000003))
        weight_mode = str(getattr(config, "continuous_dtt_weight_mode", "corrected") or "corrected")

        rows = []
        for time_value in times:
            crossed = [
                branch for branch in branches
                if self._branch_crosses_time(branch, time_value)
            ]
            if not crossed:
                continue
            if len(crossed) >= 5:
                sample_sizes = list(range(len(crossed), 4, -1))
            else:
                sample_sizes = [len(crossed)]
            for sample_size in sample_sizes:
                if sample_size < 2:
                    continue
                for _ in range(bootstrap_count):
                    chosen = rng.sample(crossed, sample_size) if sample_size < len(crossed) else list(crossed)
                    sampled_values = []
                    for branch in chosen:
                        p_ancestor = self._ancestor_probability(branch, time_value, weight_mode)
                        value = branch["ancestor_value"] if rng.random() <= p_ancestor else branch["descendant_value"]
                        sampled_values.append(float(value))
                    if len(sampled_values) < 2:
                        continue
                    rows.append({
                        "tree_index": int(original_index),
                        "time": float(time_value),
                        "variance": self._sample_variance(sampled_values),
                        "median_trait": self._quantile(sorted(sampled_values), 0.5),
                        "lineage_count": int(len(crossed)),
                        "sample_size": int(sample_size),
                    })
        return rows, root_age

    def _node_depths(self, tree):
        depths = {}
        root = tree
        depths[root] = 0.0
        for node in self._traverse(root):
            depth = float(depths.get(node, 0.0))
            for child in self._children(node):
                try:
                    dist = float(getattr(child, "dist", 0.0) or 0.0)
                except Exception:
                    dist = 0.0
                depths[child] = depth + max(0.0, dist)
        return depths

    def _node_values(self, tree, per_tree_result):
        values = {}
        tip_values = {
            str(key): float(value)
            for key, value in dict(getattr(per_tree_result, "tip_values", {}) or {}).items()
        }
        internal_values = {
            str(key): float(value)
            for key, value in dict(getattr(per_tree_result, "analysis_node_values", {}) or {}).items()
        }
        for node in self._traverse(tree):
            if self._is_leaf(node):
                name = str(getattr(node, "name", "") or "").strip()
                if name in tip_values:
                    values[node] = tip_values[name]
            else:
                key = self._clade_key(node)
                if key in internal_values:
                    values[node] = internal_values[key]
        return values

    def _branches(self, tree, ages, values):
        output = []
        for parent in self._traverse(tree):
            if parent not in ages or parent not in values:
                continue
            for child in self._children(parent):
                if child not in ages or child not in values:
                    continue
                parent_age = float(ages[parent])
                child_age = float(ages[child])
                if parent_age <= child_age:
                    continue
                output.append({
                    "ancestor_age": parent_age,
                    "descendant_age": child_age,
                    "ancestor_value": float(values[parent]),
                    "descendant_value": float(values[child]),
                })
        return output

    def _branch_crosses_time(self, branch, time_value):
        parent_age = float(branch["ancestor_age"])
        child_age = float(branch["descendant_age"])
        time_value = float(time_value)
        return parent_age + 1e-9 >= time_value >= child_age - 1e-9

    def _ancestor_probability(self, branch, time_value, weight_mode):
        parent_age = float(branch["ancestor_age"])
        child_age = float(branch["descendant_age"])
        length = parent_age - child_age
        if length <= 0.0:
            return 0.5
        if str(weight_mode) == "paper_original":
            probability = (parent_age - float(time_value)) / length
        else:
            probability = (float(time_value) - child_age) / length
        return max(0.0, min(1.0, probability))

    def _time_grid(self, start_age, end_age, time_step):
        values = []
        current = float(start_age)
        end_age = float(end_age)
        step = float(time_step)
        while current >= end_age:
            values.append(round(current, 10))
            current -= step
            if len(values) > 100000:
                break
        if values and values[-1] > end_age:
            values.append(round(end_age, 10))
        return values

    def _shared_time_grid(self, entries, config):
        time_step = float(getattr(config, "continuous_dtt_time_step", 5.0) or 5.0)
        if time_step <= 0.0:
            time_step = 5.0
        root_ages = []
        for _, tree in list(entries or []):
            root_age = self._root_age(tree)
            if root_age > 0.0:
                root_ages.append(root_age)
        if not root_ages:
            return []
        max_root_age = max(root_ages)
        if time_step >= max_root_age:
            time_step = max(max_root_age / 25.0, 0.000001)

        age_offset = self._age_offset(config)
        start_age = age_offset + max_root_age
        end_age = age_offset
        if age_offset:
            start_age = math.floor(start_age / time_step) * time_step
            end_age_rounded = math.ceil(end_age / time_step) * time_step
            values = self._time_grid(start_age, end_age_rounded, time_step)
            if values and values[-1] > end_age:
                values.append(round(end_age, 10))
            return values
        return self._time_grid(start_age, end_age, time_step)

    def _root_age(self, tree):
        depths = self._node_depths(tree)
        leaves = [node for node in depths if self._is_leaf(node)]
        if not leaves:
            return 0.0
        try:
            return max(float(depths[leaf]) for leaf in leaves)
        except Exception:
            return 0.0

    def _summarise_time_series(self, rows):
        by_time = defaultdict(list)
        for row in list(rows or []):
            try:
                time_value = float(row.get("time"))
                variance = float(row.get("variance"))
            except Exception:
                continue
            if math.isfinite(time_value) and math.isfinite(variance):
                by_time[time_value].append(variance)

        times = sorted(by_time.keys(), reverse=True)
        x_values = []
        y_values = []
        lower_values = []
        upper_values = []
        sample_counts = []
        for time_value in times:
            values = sorted(by_time[time_value])
            if not values:
                continue
            x_values.append(float(time_value))
            y_values.append(self._quantile(values, 0.5))
            lower_values.append(self._quantile(values, 0.025))
            upper_values.append(self._quantile(values, 0.975))
            sample_counts.append(len(values))
        return {
            "x": x_values,
            "y": y_values,
            "lower": lower_values,
            "upper": upper_values,
            "sample_count": sample_counts,
        }

    def _sample_variance(self, values):
        values = [float(value) for value in list(values or [])]
        if len(values) < 2:
            return 0.0
        mean = sum(values) / float(len(values))
        return sum((value - mean) ** 2 for value in values) / float(len(values) - 1)

    def _quantile(self, sorted_values, q):
        values = list(sorted_values or [])
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        q = max(0.0, min(1.0, float(q)))
        pos = q * (len(values) - 1)
        lower = int(pos)
        upper = min(lower + 1, len(values) - 1)
        fraction = pos - lower
        return float(values[lower]) * (1.0 - fraction) + float(values[upper]) * fraction

    def _clade_key(self, node):
        return "|".join(sorted(
            str(getattr(leaf, "name", "") or "").strip()
            for leaf in self._iter_leaves(node)
            if str(getattr(leaf, "name", "") or "").strip()
        ))

    def _iter_leaves(self, node):
        if hasattr(node, "iter_leaves"):
            return list(node.iter_leaves())
        return [item for item in self._traverse(node) if self._is_leaf(item)]

    def _traverse(self, node):
        if hasattr(node, "traverse"):
            try:
                return list(node.traverse("preorder"))
            except TypeError:
                return list(node.traverse())
        output = []
        stack = [node]
        while stack:
            current = stack.pop()
            output.append(current)
            stack.extend(reversed(self._children(current)))
        return output

    def _children(self, node):
        return list(getattr(node, "children", []) or [])

    def _is_leaf(self, node):
        if hasattr(node, "is_leaf"):
            try:
                return bool(node.is_leaf())
            except TypeError:
                pass
        return len(self._children(node)) == 0

    def _bounded_seed(self, value):
        value = int(value or 0)
        value = value % 2147483647
        return value if value > 0 else 1

    def _age_offset(self, config):
        try:
            value = float(getattr(config, "continuous_dtt_age_offset", 0.0) or 0.0)
        except Exception:
            value = 0.0
        return value if math.isfinite(value) else 0.0
