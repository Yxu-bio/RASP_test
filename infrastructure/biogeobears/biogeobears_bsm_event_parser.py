import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from domain.models.biogeobears_event_result import (
    BioGeoBEARSEventRecord,
    BioGeoBEARSEventResult,
)


class BioGeoBEARSBSMEventParser:
    def parse(self, *, output_json_path, bsm_dir):
        output_json_path = Path(output_json_path)
        bsm_path = Path(bsm_dir)

        result = BioGeoBEARSEventResult(
            source_output_json_path=str(output_json_path),
            source_run_directory=str(output_json_path.parent),
        )

        if output_json_path.exists():
            try:
                payload = json.loads(output_json_path.read_text(encoding="utf-8"))
                attrs = dict(payload.get("attributes", {}) or {})
                result.source_model_name = self._format_model_name(attrs)
            except Exception as exc:
                result.parse_warnings.append("Could not read BioGeoBEARS output JSON: %s" % exc)

        summary_path = bsm_path / "bsm_summary.json"
        ana_path = bsm_path / "bsm_ana_events.csv"
        clado_path = bsm_path / "bsm_clado_events.csv"

        result.summary = {"enabled": True, "directory": str(bsm_path)}
        if summary_path.exists():
            try:
                result.summary.update(json.loads(summary_path.read_text(encoding="utf-8")))
            except Exception as exc:
                result.parse_warnings.append("Could not read BSM summary JSON: %s" % exc)

        raw_tables = {}
        events = []
        for scope, path in (("anagenetic", ana_path), ("cladogenetic", clado_path)):
            rows = self._read_csv_dicts(path)
            if rows:
                raw_tables[scope] = rows
            for row in rows:
                event = self._row_to_event(scope, row)
                if event is not None:
                    events.append(event)

        result.raw_tables = raw_tables
        result.events = events
        result.event_type_counts = dict(Counter(self._event_count_key(event) for event in events))
        result.route_counts = dict(Counter(self._event_route_key(event) for event in events if self._event_route_key(event)))
        result.time_series = self._build_time_series(events)
        self._attach_text(result)
        return result

    def _format_model_name(self, attrs):
        model_name = str(attrs.get("model_name", "BioGeoBEARS") or "BioGeoBEARS")
        pretty = {
            "DEC": "DEC",
            "DECJ": "DEC+J",
            "DIVALIKE": "DIVALIKE",
            "DIVALIKEJ": "DIVALIKE+J",
            "BAYAREALIKE": "BAYAREALIKE",
            "BAYAREALIKEJ": "BAYAREALIKE+J",
        }.get(model_name, model_name)
        if not self._safe_bool(attrs.get("include_null_range", True)):
            pretty = "%s (no null range)" % pretty
        return "BioGeoBEARS-" + pretty

    def _read_csv_dicts(self, path):
        path = Path(path)
        if not path.exists():
            return []
        rows = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    rows.append({str(k): self._clean_csv_value(v) for k, v in dict(row).items()})
        except Exception:
            return []
        return rows

    def _row_to_event(self, scope, row):
        if scope == "anagenetic":
            event_type = self._first_text(row, ["event_type", "clado_event_type"])
            event_text = self._first_text(row, ["event_txt", "clado_event_txt"])
            source_range = self._first_text(row, ["current_rangetxt", "sampled_states_AT_brbots"])
            target_range = self._first_text(row, ["new_rangetxt", "sampled_states_AT_nodes"])
            time_value = self._first_float(row, ["abs_event_time", "time_bp", "SUBtime_bp", "event_time"])
        else:
            event_type = self._first_text(row, ["clado_event_type", "event_type"])
            event_text = self._first_text(row, ["clado_event_txt", "event_txt"])
            source_range = self._first_text(row, ["sampled_states_AT_brbots", "ancestor"])
            target_range = self._first_text(row, ["sampled_states_AT_nodes", "samp_LEFT_dcorner", "samp_RIGHT_dcorner"])
            time_value = self._first_float(row, ["time_bp", "SUBtime_bp", "abs_event_time", "event_time"])

        if not event_type and not event_text:
            return None
        if self._is_empty_event_text(event_type) and self._is_empty_event_text(event_text):
            return None

        return BioGeoBEARSEventRecord(
            event_scope=scope,
            sample_id=self._first_text(row, ["sample_id", "trynum"]),
            event_type=event_type,
            event_text=event_text,
            time=time_value,
            node=self._first_text(row, ["node", "SUBnode", "nodenum_at_top_of_branch"]),
            branch=self._first_text(row, ["parent_br", "SUBparent_br"]),
            source_range=source_range,
            target_range=target_range,
            dispersal_to=self._first_text(row, ["dispersal_to", "clado_dispersal_to"]),
            extirpation_from=self._first_text(row, ["extirpation_from"]),
            raw=dict(row),
        )

    def _build_time_series(self, events):
        buckets = defaultdict(lambda: Counter())
        for event in events:
            if event.time is None:
                continue
            time_key = round(float(event.time), 6)
            buckets[time_key][self._event_count_key(event)] += 1
            buckets[time_key]["total"] += 1

        rows = []
        for time_key in sorted(buckets.keys()):
            counter = buckets[time_key]
            row = {"time": time_key}
            for key, value in sorted(counter.items()):
                row[key] = int(value)
            rows.append(row)
        return rows

    def _attach_text(self, result):
        lines = [
            "BioGeoBEARS BSM event summary",
            "",
            "Source model: %s" % result.source_model_name,
            "Stochastic-map events: %d" % len(result.events),
        ]
        for key, value in sorted(dict(result.event_type_counts).items()):
            lines.append("  %s: %s" % (key, value))
        if result.route_counts:
            lines.append("")
            lines.append("Top event routes")
            for route, value in sorted(result.route_counts.items(), key=lambda x: (-int(x[1]), x[0]))[:20]:
                lines.append("  %s: %s" % (route, value))
        result.information_text = "\n".join(lines)

        time_lines = ["BioGeoBEARS BSM event-through-time table", "Time\tTotal\tEvent counts"]
        for row in list(result.time_series or [])[:500]:
            time_value = row.get("time", "")
            total = row.get("total", 0)
            parts = [
                "%s=%s" % (key, value)
                for key, value in sorted(row.items())
                if key not in ("time", "total")
            ]
            time_lines.append("%s\t%s\t%s" % (time_value, total, "; ".join(parts)))
        if len(result.time_series or []) > 500:
            time_lines.append("... truncated to first 500 time rows")
        result.time_summary_text = "\n".join(time_lines)

    def _safe_bool(self, value):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("0", "false", "f", "no", "n", "exclude"):
            return False
        if text in ("1", "true", "t", "yes", "y", "include"):
            return True
        return bool(value)

    def _clean_csv_value(self, value):
        if value is None:
            return ""
        text = str(value).strip()
        if text in ("NA", "<NA>", "NaN", "nan", "NULL"):
            return ""
        return text

    def _first_text(self, row, keys):
        for key in keys:
            value = self._clean_csv_value(row.get(key, ""))
            if value:
                return value
        return ""

    def _first_float(self, row, keys):
        for key in keys:
            value = self._clean_csv_value(row.get(key, ""))
            if not value:
                continue
            try:
                return float(value)
            except Exception:
                continue
        return None

    def _is_empty_event_text(self, value):
        text = str(value or "").strip().lower()
        return text in ("", "none", "na", "<na>", "nan", "null")

    def _event_count_key(self, event):
        event_type = str(getattr(event, "event_type", "") or "").strip()
        scope = str(getattr(event, "event_scope", "") or "").strip()
        if event_type:
            return "%s:%s" % (scope, event_type)
        return scope or "event"

    def _event_route_key(self, event):
        text = str(getattr(event, "event_text", "") or "").strip()
        if text and not self._is_empty_event_text(text):
            return text
        source = str(getattr(event, "source_range", "") or "").strip()
        target = str(getattr(event, "target_range", "") or "").strip()
        if source or target:
            return "%s->%s" % (source or "?", target or "?")
        return ""
