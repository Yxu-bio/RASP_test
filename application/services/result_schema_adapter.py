from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional
from domain.models.dec_result import DECResult
from domain.models.sdec_result import SDECResult
from domain.models.biogeobears_result import BioGeoBEARSResult
from domain.models.continuous_trait_result import ContinuousTraitResult


@dataclass
class NodePayloadSchema:
    method_name: str
    clade_key: str
    display_node_id: str = ""
    display_id_source: str = ""
    node_kind: str = "internal"
    node_name: str = ""

    state_labels: List[str] = field(default_factory=list)
    state_text: str = ""
    state_summary: str = ""
    support_summary: str = ""
    ambiguity_count: int = 0

    supporting_tree_count: int = 0
    total_tree_count: int = 0
    state_counts: Dict[str, float] = field(default_factory=dict)
    state_supports: Dict[str, float] = field(default_factory=dict)

    event_summary: str = "不适用"
    time_summary: str = "暂不实现"
    interpretation_note: str = ""

    raw_method_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MethodSummarySchema:
    method_name: str
    method_type: str
    input_tree_count: int = 1
    effective_tree_count: int = 1
    is_tree_set: bool = False
    has_event_model: bool = False
    has_time_model: bool = False
    display_id_source: str = ""
    result_semantics_note: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class StandardResultSchema:
    method_summary: MethodSummarySchema
    state_order: List[str] = field(default_factory=list)
    state_colors: Dict[str, str] = field(default_factory=dict)
    node_payloads: Dict[str, NodePayloadSchema] = field(default_factory=dict)


class BaseResultSchemaAdapter:
    method_name = ""
    method_type = ""

    def __init__(self, result):
        self.result = result

    def build_method_summary(self):
        raise NotImplementedError

    def build_node_payload(self, clade_key, node_name=""):
        raise NotImplementedError

    def iter_node_payloads(self):
        payloads = []
        node_results = getattr(self.result, "node_results", {}) or {}
        for clade_key in sorted(node_results.keys()):
            payload = self.build_node_payload(str(clade_key))
            if payload is not None:
                payloads.append(payload)
        return payloads

    def to_standard_result(self, result=None, method_name=""):
        if result is not None:
            self.result = result

        method_summary = self.build_method_summary()
        if method_name:
            method_summary.method_name = str(method_name)

        node_payloads = {}
        for payload in self.iter_node_payloads():
            if method_name:
                payload.method_name = str(method_name)
            node_payloads[payload.clade_key] = payload

        return StandardResultSchema(
            method_summary=method_summary,
            state_order=list(getattr(self.result, "state_order", []) or []),
            state_colors=dict(getattr(self.result, "state_colors", {}) or {}),
            node_payloads=node_payloads,
        )

    @staticmethod
    def _stringify_states(states):
        clean = [str(x).strip() for x in states if str(x).strip()]
        return " ".join(clean) if clean else "无"

    @staticmethod
    def _to_raw_payload(node_result):
        if node_result is None:
            return {}

        if is_dataclass(node_result):
            return asdict(node_result)

        if hasattr(node_result, "__dict__"):
            data = {}
            for key, value in vars(node_result).items():
                if key.startswith("_"):
                    continue
                data[key] = value
            return data

        return {"value": str(node_result)}

    @staticmethod
    def _safe_text(value):
        text = str(value or "").strip()
        return text if text else ""

class ResultSchemaAdapterFactory:
    @staticmethod
    def create(result):
        class_name = type(result).__name__
        if class_name == "DivaResult":
            return DivaResultSchemaAdapter(result)
        if class_name == "SDivaResult":
            return SDivaResultSchemaAdapter(result)
        if class_name == "DECResult":
            return DECResultSchemaAdapter(result)
        if class_name == "SDECResult":
            return SDECResultSchemaAdapter(result)
        if class_name == "BioGeoBEARSResult":
            return BioGeoBEARSResultSchemaAdapter(result)
        if class_name == "ContinuousTraitResult":
            return ContinuousTraitResultSchemaAdapter(result)
        raise TypeError("暂不支持的结果类型: %s" % class_name)


class DivaResultSchemaAdapter(BaseResultSchemaAdapter):
    method_name = "DIVA"
    method_type = "single_tree_ancestral_area"

    def build_method_summary(self):
        warnings = list(getattr(self.result, "parse_warnings", []) or [])
        return MethodSummarySchema(
            method_name=self.method_name,
            method_type=self.method_type,
            input_tree_count=1,
            effective_tree_count=1,
            is_tree_set=False,
            has_event_model=False,
            has_time_model=False,
            display_id_source="diva_native_node_id",
            result_semantics_note=(
                "DIVA 的内部节点结果表示最优状态集合。若一个节点存在多个状态，"
                "饼图仅表示等优并列，不表示统计概率。"
            ),
            warnings=warnings,
        )

    def build_node_payload(self, clade_key, node_name=""):
        node_result = self.result.get_node_result(clade_key)
        if node_result is None:
            return None

        state_labels = [
            str(x).strip()
            for x in list(getattr(node_result, "states", []) or [])
            if str(x).strip()
        ]
        state_text = self._stringify_states(state_labels)
        ambiguity_count = len(state_labels)

        return NodePayloadSchema(
            method_name=self.method_name,
            clade_key=clade_key,
            display_node_id=self._safe_text(getattr(node_result, "diva_node_id", "")),
            display_id_source="diva_native_node_id",
            node_kind="internal",
            node_name=node_name,
            state_labels=state_labels,
            state_text=state_text,
            state_summary=state_text,
            support_summary="等优状态数: %s" % ambiguity_count,
            ambiguity_count=ambiguity_count,
            supporting_tree_count=1,
            total_tree_count=1,
            state_counts={},
            state_supports={},
            event_summary="DIVA 当前结果不包含事件模型。",
            time_summary="Time 页暂不实现。",
            interpretation_note="多个状态表示等优重建，不表示概率。",
            raw_method_payload=self._to_raw_payload(node_result),
        )

class SDivaResultSchemaAdapter(BaseResultSchemaAdapter):
    method_name = "S-DIVA"
    method_type = "tree_set_ancestral_area"

    def build_method_summary(self):
        total = int(getattr(self.result, "tree_count_total", 0) or 0)
        warnings = list(getattr(self.result, "parse_warnings", []) or [])
        return MethodSummarySchema(
            method_name=self.method_name,
            method_type=self.method_type,
            input_tree_count=total,
            effective_tree_count=total,
            is_tree_set=True,
            has_event_model=False,
            has_time_model=False,
            display_id_source="reference_tree_diva_node_id",
            result_semantics_note=(
                "S-DIVA 在树集合上聚合 clade 状态支持；同一棵树在同一 clade 上"
                "存在多个等优状态时，按等权分摊该树的 1 份权重。"
            ),
            warnings=warnings,
        )

    def build_node_payload(self, clade_key, node_name=""):
        node_result = self.result.get_node_result(clade_key)
        if node_result is None:
            return None

        state_labels = [
            str(x).strip()
            for x in list(getattr(node_result, "states", []) or [])
            if str(x).strip()
        ]
        state_counts = {
            str(k): float(v)
            for k, v in dict(getattr(node_result, "state_counts", {}) or {}).items()
        }
        state_supports = {
            str(k): float(v)
            for k, v in dict(getattr(node_result, "state_supports", {}) or {}).items()
        }

        summary_parts = []
        for state in state_labels:
            percent = float(state_supports.get(state, 0.0))
            summary_parts.append("%s(%.1f%%)" % (state, percent))
        state_text = " ".join(summary_parts) if summary_parts else "无"

        ref_map = dict(getattr(self.result, "reference_diva_node_ids", {}) or {})
        display_node_id = self._safe_text(ref_map.get(clade_key, ""))

        supporting_tree_count = int(getattr(node_result, "supporting_tree_count", 0) or 0)
        total_tree_count = int(getattr(node_result, "total_tree_count", 0) or 0)

        return NodePayloadSchema(
            method_name=self.method_name,
            clade_key=clade_key,
            display_node_id=display_node_id,
            display_id_source="reference_tree_diva_node_id",
            node_kind="internal",
            node_name=node_name,
            state_labels=state_labels,
            state_text=state_text,
            state_summary=state_text,
            support_summary="支持树数: %s / %s" % (supporting_tree_count, total_tree_count),
            ambiguity_count=len(state_labels),
            supporting_tree_count=supporting_tree_count,
            total_tree_count=total_tree_count,
            state_counts=state_counts,
            state_supports=state_supports,
            event_summary="S-DIVA 当前结果不包含事件模型。",
            time_summary="Time 页暂不实现。",
            interpretation_note="比例表示聚合支持，不是单树概率。",
            raw_method_payload=self._to_raw_payload(node_result),
        )


class DECResultSchemaAdapter(BaseResultSchemaAdapter):
    method_name = "DEC"
    method_type = "single_tree_range_evolution"

    def build_method_summary(self):
        warnings = list(getattr(self.result, "parse_warnings", []) or [])
        result_note = str(getattr(self.result, "result_note", "") or "").strip()

        semantics_note = (
            "DEC 结果表示祖先分布范围及事件解释。"
            "当前窄版接入先统一节点状态、事件摘要和显示编号，"
            "不在这一层展开完整事件时序。"
        )
        if result_note:
            semantics_note = semantics_note + " " + result_note

        return MethodSummarySchema(
            method_name=self.method_name,
            method_type=self.method_type,
            input_tree_count=1,
            effective_tree_count=1,
            is_tree_set=False,
            has_event_model=True,
            has_time_model=False,
            display_id_source="reference_node_id",
            result_semantics_note=semantics_note,
            warnings=warnings,
        )

    def build_node_payload(self, clade_key, node_name=""):
        node_result = self.result.get_node_result(clade_key)
        if node_result is None:
            return None

        state_labels = [
            str(x).strip()
            for x in list(getattr(node_result, "states", []) or [])
            if str(x).strip()
        ]
        state_text = self._stringify_states(state_labels)

        event_counts = {
            str(k): float(v)
            for k, v in dict(getattr(node_result, "event_counts", {}) or {}).items()
        }
        event_supports = {
            str(k): float(v)
            for k, v in dict(getattr(node_result, "event_supports", {}) or {}).items()
        }

        ref_map = dict(getattr(self.result, "reference_node_ids", {}) or {})
        display_node_id = self._safe_text(
            getattr(node_result, "display_node_id", "") or ref_map.get(clade_key, "")
        )

        event_summary = str(getattr(node_result, "event_summary", "") or "").strip()
        if not event_summary and event_supports:
            parts = []
            for event_name, value in event_supports.items():
                parts.append("%s(%.1f%%)" % (event_name, float(value)))
            event_summary = " ".join(parts)

        return NodePayloadSchema(
            method_name=self.method_name,
            clade_key=clade_key,
            display_node_id=display_node_id,
            display_id_source="reference_node_id",
            node_kind="internal",
            node_name=node_name,
            state_labels=state_labels,
            state_text=state_text,
            state_summary=state_text,
            support_summary=event_summary or "无事件摘要",
            ambiguity_count=len(state_labels),
            supporting_tree_count=1,
            total_tree_count=1,
            state_counts={},
            state_supports={},
            event_summary=event_summary or "当前节点无事件摘要。",
            time_summary="Time 页暂不实现。",
            interpretation_note="DEC 窄版结果：统一展示分布状态与事件摘要。",
            raw_method_payload=self._to_raw_payload(node_result),
        )

class SDECResultSchemaAdapter(BaseResultSchemaAdapter):
    method_name = "S-DEC"
    method_type = "statistical_dec"

    def build_method_summary(self):
        warnings = list(getattr(self.result, "parse_warnings", []) or [])
        result_note = str(getattr(self.result, "result_note", "") or "").strip()

        semantics_note = (
            "S-DEC follows old RASP-style tree-set aggregation: per-tree DEC results "
            "are converted to intermediate RASP DEC records and then combined on "
            "matching reference-tree clades."
        )
        if result_note:
            semantics_note = semantics_note + " " + result_note

        return MethodSummarySchema(
            method_name=self.method_name,
            method_type=self.method_type,
            input_tree_count=int(getattr(self.result, "input_tree_count", 0) or 0),
            effective_tree_count=int(getattr(self.result, "effective_tree_count", 0) or 0),
            is_tree_set=True,
            has_event_model=False,
            has_time_model=False,
            display_id_source="reference_node_id",
            result_semantics_note=semantics_note,
            warnings=warnings,
        )

    def build_node_payload(self, clade_key, node_name=""):
        node_result = self.result.get_node_result(clade_key)
        if node_result is None:
            return None

        state_labels = list(getattr(node_result, "states", []) or [])
        state_text = self._stringify_states(state_labels)

        state_supports = dict(getattr(node_result, "state_supports", {}) or {})
        support_summary = self._format_state_supports(state_supports)

        return NodePayloadSchema(
            method_name=self.method_name,
            clade_key=clade_key,
            display_node_id=self._safe_text(getattr(node_result, "display_node_id", "")),
            display_id_source="reference_node_id",
            node_kind="internal",
            node_name=node_name,
            state_labels=state_labels,
            state_text=state_text,
            state_summary=state_text,
            support_summary=support_summary,
            ambiguity_count=len(state_labels),
            supporting_tree_count=int(getattr(node_result, "supporting_tree_count", 0) or 0),
            total_tree_count=int(getattr(node_result, "total_tree_count", 0) or 0),
            state_counts={},
            state_supports=state_supports,
            event_summary=str(getattr(node_result, "event_summary", "") or ""),
            time_summary="Time 页暂不实现。",
            interpretation_note="S-DEC probabilities are aggregated from per-tree DEC results.",
            raw_method_payload=self._to_raw_payload(node_result),
        )

    def _format_state_supports(self, state_supports):
        if not state_supports:
            return "无状态支持"
        items = sorted(state_supports.items(), key=lambda x: (-float(x[1]), x[0]))
        return " ".join(f"{k}({float(v):.1f}%)" for k, v in items[:5])


class ContinuousTraitResultSchemaAdapter(BaseResultSchemaAdapter):
    method_name = "BayesTraits Continuous ASR"
    method_type = "continuous_trait_asr"

    def build_method_summary(self):
        warnings = list(getattr(self.result, "parse_warnings", []) or [])
        return MethodSummarySchema(
            method_name=str(getattr(self.result, "model_name", "") or self.method_name),
            method_type=self.method_type,
            input_tree_count=int(getattr(self.result, "input_tree_count", 1) or 1),
            effective_tree_count=int(getattr(self.result, "effective_tree_count", 1) or 1),
            is_tree_set=False,
            has_event_model=False,
            has_time_model=False,
            display_id_source="reference_node_id",
            result_semantics_note=(
                "Continuous ASR shows posterior summaries of BayesTraits unknown internal-node values. "
                "Branches are visualized by interpolating parent and child node/tip values."
            ),
            warnings=warnings,
        )

    def build_node_payload(self, clade_key, node_name=""):
        node_result = self.result.get_node_result(clade_key)
        if node_result is None:
            return None

        raw = self._to_raw_payload(node_result)
        method_payload = raw.get("raw_method_payload", {})
        if isinstance(method_payload, dict):
            for key, value in method_payload.items():
                raw.setdefault(key, value)
        raw["continuous"] = True
        raw["trait_transform"] = str(getattr(self.result, "trait_transform", "none") or "none")
        raw["trait_display_scale"] = str(getattr(self.result, "trait_display_scale", "analysis") or "analysis")
        raw["trait_plot_scale"] = str(getattr(self.result, "trait_plot_scale", "analysis") or "analysis")
        raw["trait_scale"] = str(
            dict(getattr(self.result, "model_statistics", {}) or {}).get("trait_scale", "")
            or getattr(self.result, "trait_transform", "none")
            or "none"
        )
        if raw["trait_display_scale"] == "original" and raw["trait_transform"] != "none":
            raw["display_scale"] = "Original scale (back-transformed)"
            raw["display_mean"] = raw.get("original_mean", raw.get("display_mean", raw.get("mean", 0.0)))
            raw["display_median"] = raw.get("original_median", raw.get("display_median", raw.get("median", 0.0)))
            raw["display_lower95"] = raw.get("original_lower95", raw.get("display_lower95", raw.get("lower95", 0.0)))
            raw["display_upper95"] = raw.get("original_upper95", raw.get("display_upper95", raw.get("upper95", 0.0)))
        else:
            raw["display_scale"] = raw["trait_scale"]
            raw["display_mean"] = raw.get("analysis_mean", raw.get("mean", 0.0))
            raw["display_median"] = raw.get("analysis_median", raw.get("median", 0.0))
            raw["display_lower95"] = raw.get("analysis_lower95", raw.get("lower95", 0.0))
            raw["display_upper95"] = raw.get("analysis_upper95", raw.get("upper95", 0.0))
        raw["plot_scale"] = str(
            dict(getattr(self.result, "model_statistics", {}) or {}).get("plot_scale", "")
            or raw.get("plot_scale", "")
            or raw["trait_scale"]
        )
        display_mean = float(raw.get("display_mean", getattr(node_result, "mean", 0.0)) or 0.0)
        display_median = float(raw.get("display_median", getattr(node_result, "median", 0.0)) or 0.0)
        display_lower95 = float(raw.get("display_lower95", getattr(node_result, "lower95", 0.0)) or 0.0)
        display_upper95 = float(raw.get("display_upper95", getattr(node_result, "upper95", 0.0)) or 0.0)
        summary = "mean %.4g, median %.4g, 95%% CI [%.4g, %.4g]" % (
            display_mean,
            display_median,
            display_lower95,
            display_upper95,
        )

        return NodePayloadSchema(
            method_name=str(getattr(self.result, "model_name", "") or self.method_name),
            clade_key=clade_key,
            display_node_id=self._safe_text(getattr(node_result, "display_node_id", "")),
            display_id_source="reference_node_id",
            node_kind="internal",
            node_name=node_name,
            state_labels=[],
            state_text=summary,
            state_summary=summary,
            support_summary="samples: %s" % int(getattr(node_result, "sample_count", 0) or 0),
            ambiguity_count=0,
            supporting_tree_count=int(getattr(node_result, "sample_count", 0) or 0),
            total_tree_count=int(getattr(node_result, "sample_count", 0) or 0),
            state_counts={},
            state_supports={},
            event_summary="Continuous trait posterior summary",
            time_summary="Time not applicable",
            interpretation_note=(
                "Node color and branch gradient use the posterior mean continuous trait value "
                "on the configured trait scale."
            ),
            raw_method_payload=raw,
        )

class BioGeoBEARSResultSchemaAdapter(BaseResultSchemaAdapter):
    method_name = "BioGeoBEARS"
    method_type = "biogeobears"

    def build_method_summary(self):
        warnings = list(getattr(self.result, "parse_warnings", []) or [])
        result_note = str(getattr(self.result, "result_note", "") or "").strip()
        actual_name = str(getattr(self.result, "model_name", "") or "BioGeoBEARS")

        semantics_note = (
            "BioGeoBEARS 第一版通过外部 Rscript 调用 BioGeoBEARS，"
            "当前接入单树 DEC / DEC+J，并读取节点祖先状态概率。"
        )
        if actual_name.startswith("BayesTraits"):
            semantics_note = (
                "BayesTraits MultiState 通过外部 BayesTraitsV5.exe 运行，"
                "当前节点显示的是性状祖先状态概率。"
            )
        elif actual_name.startswith("BBM"):
            semantics_note = (
                "BBM 通过 MrBayes restriction-data 运行，"
                "当前节点显示的是区域存在/缺失边际概率组合后的范围概率。"
            )
        elif actual_name.startswith("BayArea"):
            semantics_note = (
                "BayArea 通过外部 BayArea runner 运行，"
                "当前节点显示的是 BayArea 后验祖先范围概率。"
            )
        if result_note:
            semantics_note = semantics_note + " " + result_note

        return MethodSummarySchema(
            method_name=actual_name,
            method_type=self.method_type,
            input_tree_count=int(getattr(self.result, "input_tree_count", 1) or 1),
            effective_tree_count=int(getattr(self.result, "effective_tree_count", 1) or 1),
            is_tree_set=False,
            has_event_model=False,
            has_time_model=False,
            display_id_source="reference_node_id",
            result_semantics_note=semantics_note,
            warnings=warnings,
        )

    def build_node_payload(self, clade_key, node_name=""):
        node_result = self.result.get_node_result(clade_key)
        if node_result is None:
            return None

        state_labels = list(getattr(node_result, "states", []) or [])
        state_text = self._stringify_states(state_labels)

        state_supports = dict(getattr(node_result, "state_supports", {}) or {})
        support_summary = self._format_state_supports(state_supports)

        return NodePayloadSchema(
            method_name=str(getattr(self.result, "model_name", "") or "BioGeoBEARS"),
            clade_key=clade_key,
            display_node_id=self._safe_text(getattr(node_result, "display_node_id", "")),
            display_id_source="reference_node_id",
            node_kind="internal",
            node_name=node_name,
            state_labels=state_labels,
            state_text=state_text,
            state_summary=state_text,
            support_summary=support_summary,
            ambiguity_count=len(state_labels),
            supporting_tree_count=int(getattr(node_result, "supporting_tree_count", 1) or 1),
            total_tree_count=int(getattr(node_result, "total_tree_count", 1) or 1),
            state_counts={},
            state_supports=state_supports,
            event_summary=str(getattr(node_result, "event_summary", "") or ""),
            time_summary="Time 页暂不实现。",
            interpretation_note=(
                "当前节点显示的是 BayesTraits 的性状祖先状态概率。"
                if str(getattr(self.result, "model_name", "") or "").startswith("BayesTraits")
                else "当前节点显示的是 BioGeoBEARS 的祖先状态概率。"
            ),
            raw_method_payload=self._to_raw_payload(node_result),
        )

    def _format_state_supports(self, state_supports):
        if not state_supports:
            return "无状态支持"
        items = sorted(state_supports.items(), key=lambda x: (-float(x[1]), x[0]))
        return " ".join(f"{k}({float(v):.1f}%)" for k, v in items[:5])
