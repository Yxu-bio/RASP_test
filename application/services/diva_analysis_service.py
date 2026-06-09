from datetime import datetime
from pathlib import Path

from application.services.diva_dataset_builder import DivaDatasetBuilder
from domain.models.diva_result import DivaRunArtifacts
from infrastructure.diva.diva_batch_exporter import DivaBatchExporter
from infrastructure.diva.diva_output_parser import DivaOutputParser
from infrastructure.diva.diva_runner import DivaRunner


class DivaAnalysisService:
    def __init__(self, project_root: str = None) -> None:
        if project_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent
        self.project_root = Path(project_root)

        self.dataset_builder = DivaDatasetBuilder()
        self.output_parser = DivaOutputParser()
        self.diva_exe_path = self.project_root / "engines" / "diva" / "DIVA.exe"

    def run(
        self,
        tree,
        matrix,
        tree_name: str = "t1",
        distribution_name: str = "d1",
        config=None,
        timeout_seconds: int = 120,
    ):
        dataset = self.dataset_builder.build(
            tree=tree,
            matrix=matrix,
            tree_name=tree_name,
            distribution_name=distribution_name,
        )

        run_dir = self._make_run_dir(tree_name, distribution_name)

        exporter = DivaBatchExporter(str(run_dir))
        batch_path = exporter.export(dataset, config=config)

        runner = DivaRunner(str(self.diva_exe_path))
        runner_result = runner.run(
            str(batch_path),
            wrapper_name=f"{batch_path.stem}.wrapper.txt",
            log_name=f"{batch_path.stem}.console.log",
            timeout_seconds=timeout_seconds,
        )

        wrapper_file = runner_result["wrapper_file"]
        console_log = runner_result["console_log"]

        result = self.output_parser.parse_log_file(console_log, dataset)
        self._attach_pie_chart_data(result)

        result.artifacts = DivaRunArtifacts(
            run_dir=str(run_dir),
            batch_file=str(batch_path),
            wrapper_file=wrapper_file,
            console_log=console_log,
            extra_files=[],
            return_code=runner_result["return_code"],
        )

        self._write_run_manifest(result)
        return result

    def _make_run_dir(self, tree_name: str, distribution_name: str) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = self.project_root / "runs" / "diva" / f"{stamp}_{tree_name}_{distribution_name}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _write_run_manifest(self, result) -> None:
        run_dir = Path(result.artifacts.run_dir)
        dataset = result.dataset

        lines = [
            f"tree_name={dataset.tree_name}",
            f"distribution_name={dataset.distribution_name}",
            f"source_matrix_path={dataset.source_matrix_path}",
            f"return_code={result.artifacts.return_code}",
            f"batch_file={result.artifacts.batch_file}",
            f"wrapper_file={result.artifacts.wrapper_file}",
            f"console_log={result.artifacts.console_log}",
            f"parsed_nodes={len(result.node_results)}",
            f"numeric_newick={dataset.numeric_newick}",
            "taxa_order=" + ",".join(dataset.taxa_order),
            "state_order=" + ",".join(result.state_order),
        ]

        if result.artifacts.extra_files:
            lines.append("extra_files=" + ",".join(result.artifacts.extra_files))

        if result.parse_warnings:
            lines.append("parse_warnings=")
            lines.extend(result.parse_warnings)

        (run_dir / "run_info.txt").write_text("\n".join(lines), encoding="utf-8")

    def _attach_pie_chart_data(self, result) -> None:
        state_order = self._infer_state_order(result)
        state_colors = self._build_state_color_map(state_order)

        result.state_order = state_order
        result.state_colors = state_colors

        for node_result in result.node_results.values():
            states = []
            for state in node_result.states:
                s = str(state).strip()
                if s and s not in states:
                    states.append(s)

            if not states:
                continue

            node_result.pie_labels = states
            node_result.pie_percents = self._equal_percents(len(states))
            node_result.pie_colors = [state_colors[s] for s in states]

    def _infer_state_order(self, result) -> list:
        states = []
        seen = set()

        # 先纳入叶节点原始分布状态
        for dist in result.dataset.distributions:
            s = str(dist).strip()
            if s and s not in seen:
                seen.add(s)
                states.append(s)

        # 再纳入内部节点 DIVA 最优状态
        for node_result in result.node_results.values():
            for state in node_result.states:
                s = str(state).strip()
                if s and s not in seen:
                    seen.add(s)
                    states.append(s)

        states.sort(key=lambda x: (len(x), x))
        return states

    def _build_state_color_map(self, state_order: list) -> dict:
        palette = [
            "#e41a1c",
            "#377eb8",
            "#4daf4a",
            "#984ea3",
            "#ff7f00",
            "#ffff33",
            "#a65628",
            "#f781bf",
            "#999999",
            "#66c2a5",
            "#fc8d62",
            "#8da0cb",
            "#e78ac3",
            "#a6d854",
            "#ffd92f",
            "#1b9e77",
            "#d95f02",
            "#7570b3",
            "#e7298a",
            "#66a61e",
        ]
        return {
            state: palette[i % len(palette)]
            for i, state in enumerate(state_order)
        }

    def _equal_percents(self, n: int) -> list:
        if n <= 0:
            return []

        base = round(100.0 / n, 6)
        values = [base] * n
        values[-1] += 100.0 - sum(values)
        return values
