from pathlib import Path

from domain.models.diva_dataset import DivaDataset


class DivaBatchExporter:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, dataset: DivaDataset, filename: str = None, config=None) -> Path:
        if filename is None:
            filename = f"{dataset.tree_name}_{dataset.distribution_name}.diva.txt"
        out_file = self.output_dir / filename

        if out_file.exists():
            raise FileExistsError(f"DIVA output file already exists: {out_file}")

        lines = []

        exclude_command = self._build_exclude_command(config)
        if exclude_command:
            lines.append(exclude_command)

        lines.append(f"tree {dataset.tree_name} {dataset.numeric_newick}")

        dist_str = " ".join(dataset.distributions)
        lines.append(f"distribution +{dataset.distribution_name} {dist_str};")

        fossil_command = self._build_fossil_command(config)
        if fossil_command:
            lines.append(fossil_command)

        lines.append(self._build_optimize_command(dataset, config))
        lines.append("return;")

        content = "\n".join(lines)
        out_file.write_text(content, encoding="utf-8")
        return out_file

    def _build_exclude_command(self, config) -> str:
        if config is None or not hasattr(config, "to_diva_exclude_command"):
            return ""
        return str(config.to_diva_exclude_command() or "").strip()

    def _build_fossil_command(self, config) -> str:
        if config is None or not hasattr(config, "to_diva_fossil_command"):
            return ""
        return str(config.to_diva_fossil_command() or "").strip()

    def _build_optimize_command(self, dataset: DivaDataset, config) -> str:
        if config is not None and hasattr(config, "to_diva_optimize_command"):
            return config.to_diva_optimize_command(taxon_count=len(dataset.taxa_order))
        return "optimize;"
