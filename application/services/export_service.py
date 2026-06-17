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

    NODE_SUMMARY_CSV_FIELDNAMES = [
        "method",
        "method_name",
        "node_id",
        "display_node_id",
        "display_id_source",
        "clade_key",
        "node_kind",
        "node_name",
        "node_age",
        "rank",
        "state_rank",
        "state",
        "probability",
        "probability_percent",
        "count",
        "support_basis",
        "top_state",
        "top_prob",
        "top_probability_percent",
        "state_summary",
        "supporting_tree_count",
        "total_tree_count",
        "support_summary",
        "event_summary",
        "time_summary",
        "interpretation_note",
        "source_result_path",
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

    def export_node_summary_csv(self, result, file_path: str, method_name: str = "") -> None:
        if result is None:
            raise ValueError("No result is available for export")

        standard_result = self._adapt_result(result, method_name=method_name)
        payloads = list(standard_result.node_payloads.values())
        payloads.sort(key=self._node_sort_key)

        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.NODE_SUMMARY_CSV_FIELDNAMES)
            writer.writeheader()
            for payload in payloads:
                state_rows = self._state_rows_for_payload(payload, standard_result.state_order)
                if not state_rows:
                    state_rows = [("", "", "", "none")]
                top_state, top_probability = self._top_state_from_rows(state_rows)
                node_age = self._node_age_from_payload(payload)
                source_result_path = str(getattr(result, "source_run_directory", "") or getattr(result, "run_directory", "") or "")
                for rank, (state, probability, count, basis) in enumerate(state_rows, start=1):
                    writer.writerow({
                        "method": payload.method_name,
                        "method_name": payload.method_name,
                        "node_id": payload.display_node_id,
                        "display_node_id": payload.display_node_id,
                        "display_id_source": payload.display_id_source,
                        "clade_key": payload.clade_key,
                        "node_kind": payload.node_kind,
                        "node_name": payload.node_name,
                        "node_age": node_age,
                        "rank": rank,
                        "state_rank": rank,
                        "state": state,
                        "probability": probability,
                        "probability_percent": probability,
                        "count": count,
                        "support_basis": basis,
                        "top_state": top_state,
                        "top_prob": top_probability,
                        "top_probability_percent": top_probability,
                        "state_summary": payload.state_summary,
                        "supporting_tree_count": payload.supporting_tree_count,
                        "total_tree_count": payload.total_tree_count,
                        "support_summary": payload.support_summary,
                        "event_summary": payload.event_summary,
                        "time_summary": payload.time_summary,
                        "interpretation_note": payload.interpretation_note,
                        "source_result_path": source_result_path,
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

    def _state_rows_for_payload(self, payload, state_order) -> list:
        supports = {
            str(key): float(value)
            for key, value in dict(getattr(payload, "state_supports", {}) or {}).items()
            if str(key).strip()
        }
        counts = {
            str(key): float(value)
            for key, value in dict(getattr(payload, "state_counts", {}) or {}).items()
            if str(key).strip()
        }

        if supports:
            rows = []
            for state in self._ordered_states(supports.keys(), state_order):
                rows.append((state, self._format_float(supports.get(state, 0.0)), "", "state_supports"))
            rows.sort(key=lambda row: (-self._safe_float(row[1]), row[0]))
            return rows

        if counts:
            total = sum(float(value) for value in counts.values())
            rows = []
            for state in self._ordered_states(counts.keys(), state_order):
                value = float(counts.get(state, 0.0))
                percent = (100.0 * value / total) if total > 0.0 else 0.0
                rows.append((state, self._format_float(percent), self._format_float(value), "state_counts"))
            rows.sort(key=lambda row: (-self._safe_float(row[1]), row[0]))
            return rows

        labels = [
            str(value).strip()
            for value in list(getattr(payload, "state_labels", []) or [])
            if str(value).strip()
        ]
        return [(state, "", "", "state_labels_only") for state in self._ordered_states(labels, state_order)]

    def _ordered_states(self, states, state_order) -> list:
        available = {str(state).strip() for state in states if str(state).strip()}
        ordered = []
        for state in list(state_order or []):
            text = str(state).strip()
            if text and text in available and text not in ordered:
                ordered.append(text)
        for state in sorted(available):
            if state not in ordered:
                ordered.append(state)
        return ordered

    def _top_state_from_rows(self, state_rows) -> tuple:
        numeric_rows = [
            (state, self._safe_float(probability))
            for state, probability, _count, _basis in list(state_rows or [])
            if str(state).strip() and str(probability).strip()
        ]
        if numeric_rows:
            numeric_rows.sort(key=lambda item: (-float(item[1]), item[0]))
            return numeric_rows[0][0], self._format_float(numeric_rows[0][1])
        labels = [
            str(state).strip()
            for state, _probability, _count, _basis in list(state_rows or [])
            if str(state).strip()
        ]
        return (labels[0], "") if labels else ("", "")

    def _node_age_from_payload(self, payload) -> str:
        raw = dict(getattr(payload, "raw_method_payload", {}) or {})
        for key in ("node_age", "age", "height", "time"):
            if key in raw and str(raw.get(key, "")).strip():
                return self._format_float(raw.get(key))
        return ""

    @staticmethod
    def _safe_int(value):
        text = str(value or "").strip()
        if text.isdigit():
            return int(text)
        return None

    @staticmethod
    def _safe_float(value) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    @staticmethod
    def _format_float(value) -> str:
        try:
            return "%.10g" % float(value)
        except Exception:
            return ""

    @staticmethod
    def _json_dumps(value) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
