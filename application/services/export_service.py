import csv
import json
from dataclasses import asdict

from application.services.continuous_trait_figure_exporter import ContinuousTraitPublicationFigureExporter
from application.services.result_schema_adapter import ResultSchemaAdapterFactory


class ExportService:
    RESULT_CSV_FIELDNAMES = [
        "method_name",
        "clade_key",
        "display_node_id",
        "display_id_source",
        "node_kind",
        "state_labels",
        "state_text",
        "state_summary",
        "ambiguity_count",
        "supporting_tree_count",
        "total_tree_count",
        "support_summary",
        "state_counts_json",
        "state_supports_json",
        "event_summary",
        "time_summary",
        "interpretation_note",
        "raw_method_payload_json",
    ]

    def export_tree_png(self, renderer, file_path: str) -> None:
        if renderer is None:
            raise ValueError("当前没有可导出的结果")
        renderer.export_tree_png(file_path)

    def export_tree_svg(self, renderer, file_path: str) -> None:
        if renderer is None:
            raise ValueError("当前没有可导出的结果")
        renderer.export_tree_svg(file_path)

    def export_tree_pdf(self, renderer, file_path: str) -> None:
        if renderer is None:
            raise ValueError("当前没有可导出的结果")
        renderer.export_tree_pdf(file_path)

    def export_continuous_publication_figure(self, result, file_path: str, method_name: str = "") -> None:
        exporter = ContinuousTraitPublicationFigureExporter()
        exporter.export(result, file_path, method_name=method_name)

    def export_result_csv(self, result, file_path: str, method_name: str = "") -> None:
        if result is None:
            raise ValueError("当前没有可导出的结果")

        standard_result = self._adapt_result(result, method_name=method_name)

        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.RESULT_CSV_FIELDNAMES)
            writer.writeheader()

            payloads = list(standard_result.node_payloads.values())
            payloads.sort(key=self._node_sort_key)

            for payload in payloads:
                writer.writerow({
                    "method_name": payload.method_name,
                    "clade_key": payload.clade_key,
                    "display_node_id": payload.display_node_id,
                    "display_id_source": payload.display_id_source,
                    "node_kind": payload.node_kind,
                    "state_labels": " ".join(payload.state_labels),
                    "state_text": payload.state_text,
                    "state_summary": payload.state_summary,
                    "ambiguity_count": payload.ambiguity_count,
                    "supporting_tree_count": payload.supporting_tree_count,
                    "total_tree_count": payload.total_tree_count,
                    "support_summary": payload.support_summary,
                    "state_counts_json": self._json_dumps(payload.state_counts),
                    "state_supports_json": self._json_dumps(payload.state_supports),
                    "event_summary": payload.event_summary,
                    "time_summary": payload.time_summary,
                    "interpretation_note": payload.interpretation_note,
                    "raw_method_payload_json": self._json_dumps(payload.raw_method_payload),
                })

    def export_result_summary_json(self, result, file_path: str, method_name: str = "") -> None:
        if result is None:
            raise ValueError("当前没有可导出的结果")

        standard_result = self._adapt_result(result, method_name=method_name)
        data = {
            "method_summary": asdict(standard_result.method_summary),
            "state_order": list(standard_result.state_order),
            "state_colors": dict(standard_result.state_colors),
            "node_count": len(standard_result.node_payloads),
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def export_diva_result_csv(self, result, file_path: str) -> None:
        self.export_result_csv(result, file_path, method_name="DIVA")

    def export_sdiva_result_csv(self, result, file_path: str) -> None:
        self.export_result_csv(result, file_path, method_name="S-DIVA")

    def _adapt_result(self, result, method_name: str = ""):
        adapter = ResultSchemaAdapterFactory.create(result)
        return adapter.to_standard_result(result, method_name=method_name)

    def _node_sort_key(self, payload) -> tuple:
        numeric_id = self._safe_int(payload.display_node_id)
        if numeric_id is not None:
            return (0, numeric_id, payload.clade_key)
        return (1, 10 ** 9, payload.clade_key)

    @staticmethod
    def _safe_int(value):
        text = str(value or "").strip()
        if text.isdigit():
            return int(text)
        return None

    @staticmethod
    def _json_dumps(value) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
