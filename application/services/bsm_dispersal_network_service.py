import csv
import json
from collections import defaultdict
from pathlib import Path


class BSMDispersalNetworkService:
    """Aggregate BioGeoBEARS BSM events into an area-to-area network.

    This service is intentionally independent from the BSM event table parser.
    It reads the raw exported event rows when available so we can keep old event
    table behavior stable while adding map/network summaries.
    """

    ANAGENETIC_TYPES = set(["d", "a"])
    FOUNDER_EVENT = "founder (j)"
    KNOWN_AREA_ALIASES = {
        "A": "Afrotropics",
        "U": "Australasia",
        "I": "Indomalaya",
        "R": "Nearctic",
        "N": "Neotropics",
        "E": "Eastern Palearctic",
        "W": "Western Palearctic",
    }

    def build_network(
        self,
        result,
        areas=None,
        range_matrix=None,
        min_mean_per_map=5.0,
        include_anagenetic=True,
        include_founder=True,
    ):
        area_rows = list(areas or [])
        area_codes = self._area_codes(area_rows, range_matrix, result)
        area_metadata = self._area_metadata(area_rows)
        nummaps = self._nummaps(result)
        if nummaps <= 0:
            nummaps = 1

        precomputed_edges = list(getattr(result, "precomputed_bsm_network_edges", []) or [])
        if precomputed_edges:
            edge_rows = self._edge_rows_from_precomputed(precomputed_edges, area_codes, area_metadata, nummaps)
            area_codes = self._unique_preserve_order(
                list(area_codes or [])
                + [str(row.get("source_area", "") or "") for row in edge_rows]
                + [str(row.get("target_area", "") or "") for row in edge_rows]
            )
            node_rows = self._node_rows(area_codes, area_metadata, range_matrix, edge_rows)
            node_rows = self._merge_precomputed_node_rows(
                node_rows,
                list(getattr(result, "precomputed_bsm_node_rows", []) or []),
            )
            threshold = self._safe_float(min_mean_per_map, 0.0)
            display_edges = [
                row for row in edge_rows
                if float(row.get("mean_per_map", 0.0)) >= threshold
            ]
            warnings = list(getattr(result, "parse_warnings", []) or [])
            if not area_metadata:
                warnings.append("No spatial area metadata was supplied; using schematic network layout.")
            return {
                "nummaps": nummaps,
                "min_mean_per_map": threshold,
                "edge_rows": edge_rows,
                "display_edge_rows": display_edges,
                "node_rows": node_rows,
                "area_codes": area_codes,
                "warnings": warnings,
                "include_anagenetic": bool(include_anagenetic),
                "include_founder": bool(include_founder),
                "edge_geojson": self.edge_geojson(display_edges),
                "node_geojson": self.node_geojson(node_rows),
            }

        edge_acc = {}
        if include_anagenetic:
            for row in self._raw_rows(result, "anagenetic"):
                event_type = self._clean(row.get("event_type") or row.get("clado_event_type"))
                if event_type not in self.ANAGENETIC_TYPES:
                    continue
                target = self._clean(row.get("dispersal_to") or row.get("new_area_num_1based"))
                source_range = self._clean(row.get("current_rangetxt") or row.get("sampled_states_AT_brbots"))
                self._add_split_source_edge(edge_acc, source_range, target, area_codes, "anagenetic")

        if include_founder:
            for row in self._raw_rows(result, "cladogenetic"):
                event_type = self._clean(row.get("clado_event_type") or row.get("event_type"))
                if event_type != self.FOUNDER_EVENT:
                    continue
                target = self._clean(row.get("clado_dispersal_to") or row.get("dispersal_to"))
                text = self._clean(row.get("clado_event_txt") or row.get("event_txt"))
                source_range = text.split("->", 1)[0].strip() if "->" in text else ""
                if not source_range:
                    source_range = self._clean(row.get("sampled_states_AT_brbots"))
                self._add_split_source_edge(edge_acc, source_range, target, area_codes, "founder")

        edge_rows = []
        for key in sorted(edge_acc.keys()):
            row = edge_acc[key]
            total = float(row.get("anagenetic_count", 0.0)) + float(row.get("founder_count", 0.0))
            mean = total / float(nummaps)
            source = row["source_area"]
            target = row["target_area"]
            source_meta = area_metadata.get(source, {})
            target_meta = area_metadata.get(target, {})
            edge_rows.append({
                "source_area": source,
                "target_area": target,
                "source_name": source_meta.get("display_name") or source,
                "target_name": target_meta.get("display_name") or target,
                "anagenetic_count": row.get("anagenetic_count", 0.0),
                "founder_count": row.get("founder_count", 0.0),
                "total_count": total,
                "mean_per_map": mean,
                "source_lon": source_meta.get("centroid_lon", ""),
                "source_lat": source_meta.get("centroid_lat", ""),
                "target_lon": target_meta.get("centroid_lon", ""),
                "target_lat": target_meta.get("centroid_lat", ""),
            })
        edge_rows.sort(key=lambda row: (-float(row.get("total_count", 0.0)), row.get("source_area", ""), row.get("target_area", "")))

        node_rows = self._node_rows(area_codes, area_metadata, range_matrix, edge_rows)
        threshold = self._safe_float(min_mean_per_map, 0.0)
        display_edges = [
            row for row in edge_rows
            if float(row.get("mean_per_map", 0.0)) >= threshold
        ]
        warnings = []
        missing_centroids = [
            code for code in area_codes
            if code in area_metadata and (
                area_metadata[code].get("centroid_lon") in ("", None)
                or area_metadata[code].get("centroid_lat") in ("", None)
            )
        ]
        if missing_centroids:
            warnings.append("Some areas do not have usable centroids: %s" % ", ".join(missing_centroids[:12]))
        if not area_metadata:
            warnings.append("No spatial area metadata was supplied; network tables can be exported but map coordinates are unavailable.")

        return {
            "nummaps": nummaps,
            "min_mean_per_map": threshold,
            "edge_rows": edge_rows,
            "display_edge_rows": display_edges,
            "node_rows": node_rows,
            "area_codes": area_codes,
            "warnings": warnings,
            "include_anagenetic": bool(include_anagenetic),
            "include_founder": bool(include_founder),
            "edge_geojson": self.edge_geojson(display_edges),
            "node_geojson": self.node_geojson(node_rows),
        }

    def _edge_rows_from_precomputed(self, rows, area_codes, area_metadata, nummaps):
        output = []
        for row in list(rows or []):
            source = self._clean(row.get("source_area") or row.get("from") or row.get("source") or "")
            target = self._clean(row.get("target_area") or row.get("to") or row.get("target") or "")
            if not source or not target:
                continue
            source_meta = area_metadata.get(source, {})
            target_meta = area_metadata.get(target, {})
            ana_count = self._safe_float(row.get("anagenetic_count") or row.get("ana_count"), 0.0)
            founder_count = self._safe_float(row.get("founder_count") or row.get("clado_count"), 0.0)
            total = self._safe_float(row.get("total_count"), ana_count + founder_count)
            mean = self._safe_float(row.get("mean_per_map"), None)
            if mean is None:
                mean = total / float(nummaps or 1)
            output.append({
                "source_area": source,
                "target_area": target,
                "source_name": source_meta.get("display_name") or row.get("source_name") or row.get("from_name") or source,
                "target_name": target_meta.get("display_name") or row.get("target_name") or row.get("to_name") or target,
                "anagenetic_count": ana_count,
                "founder_count": founder_count,
                "total_count": total,
                "mean_per_map": mean,
                "source_lon": source_meta.get("centroid_lon", ""),
                "source_lat": source_meta.get("centroid_lat", ""),
                "target_lon": target_meta.get("centroid_lon", ""),
                "target_lat": target_meta.get("centroid_lat", ""),
            })
        output.sort(key=lambda item: (-float(item.get("total_count", 0.0)), item.get("source_area", ""), item.get("target_area", "")))
        return output

    def _merge_precomputed_node_rows(self, node_rows, precomputed_rows):
        if not precomputed_rows:
            return node_rows
        by_code = {str(row.get("area_code", "") or ""): dict(row) for row in list(node_rows or [])}
        for row in list(precomputed_rows or []):
            code = self._clean(row.get("area_code") or row.get("area") or "")
            if not code:
                continue
            current = by_code.get(code, {"area_code": code})
            if row.get("name") and not current.get("display_name"):
                current["display_name"] = row.get("name")
            if row.get("display_name"):
                current["display_name"] = row.get("display_name")
            if row.get("richness") not in ("", None):
                current["richness"] = self._safe_float(row.get("richness"), current.get("richness", 0.0))
            by_code[code] = current
        return list(by_code.values())

    def write_edges_csv(self, network, file_path):
        return self._write_csv(network.get("edge_rows", []), file_path)

    def write_display_edges_csv(self, network, file_path):
        return self._write_csv(network.get("display_edge_rows", []), file_path)

    def write_nodes_csv(self, network, file_path):
        return self._write_csv(network.get("node_rows", []), file_path)

    def write_geojson(self, network, file_path):
        features = []
        features.extend(network.get("edge_geojson", {}).get("features", []) or [])
        features.extend(network.get("node_geojson", {}).get("features", []) or [])
        payload = {
            "type": "FeatureCollection",
            "name": "bsm_dispersal_network",
            "features": features,
        }
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def edge_geojson(self, edge_rows):
        features = []
        for row in list(edge_rows or []):
            source_lon = self._safe_float(row.get("source_lon"), None)
            source_lat = self._safe_float(row.get("source_lat"), None)
            target_lon = self._safe_float(row.get("target_lon"), None)
            target_lat = self._safe_float(row.get("target_lat"), None)
            if None in (source_lon, source_lat, target_lon, target_lat):
                continue
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[source_lon, source_lat], [target_lon, target_lat]],
                },
                "properties": {
                    "feature_type": "bsm_dispersal_edge",
                    "source_area": row.get("source_area", ""),
                    "target_area": row.get("target_area", ""),
                    "source_name": row.get("source_name", ""),
                    "target_name": row.get("target_name", ""),
                    "anagenetic_count": row.get("anagenetic_count", 0.0),
                    "founder_count": row.get("founder_count", 0.0),
                    "total_count": row.get("total_count", 0.0),
                    "mean_per_map": row.get("mean_per_map", 0.0),
                },
            })
        return {"type": "FeatureCollection", "features": features}

    def node_geojson(self, node_rows):
        features = []
        for row in list(node_rows or []):
            lon = self._safe_float(row.get("centroid_lon"), None)
            lat = self._safe_float(row.get("centroid_lat"), None)
            if None in (lon, lat):
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "feature_type": "bsm_dispersal_node",
                    "area_code": row.get("area_code", ""),
                    "display_name": row.get("display_name", ""),
                    "richness": row.get("richness", 0.0),
                    "incoming_mean_per_map": row.get("incoming_mean_per_map", 0.0),
                    "outgoing_mean_per_map": row.get("outgoing_mean_per_map", 0.0),
                },
            })
        return {"type": "FeatureCollection", "features": features}

    def _write_csv(self, rows, file_path):
        rows = list(rows or [])
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = []
        for row in rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict((key, row.get(key, "")) for key in headers))
        return path

    def _raw_rows(self, result, name):
        raw_tables = dict(getattr(result, "raw_tables", {}) or {})
        return list(raw_tables.get(name, []) or [])

    def _nummaps(self, result):
        summary = dict(getattr(result, "summary", {}) or {})
        value = self._safe_int(summary.get("nummaps"), 0)
        if value > 0:
            return value
        sample_ids = set()
        for name in ("anagenetic", "cladogenetic"):
            for row in self._raw_rows(result, name):
                sample_id = self._clean(row.get("sample_id") or row.get("trynum"))
                if sample_id:
                    sample_ids.add(sample_id)
        return len(sample_ids) or 1

    def _add_split_source_edge(self, edge_acc, source_range, target, area_codes, event_kind):
        target = self._normalize_area_code(target, area_codes)
        if not target:
            return
        sources = self._split_range_label(source_range, area_codes)
        if not sources:
            return
        weight = 1.0 / float(len(sources))
        count_key = "founder_count" if event_kind == "founder" else "anagenetic_count"
        for source in sources:
            if source == target:
                continue
            key = (source, target)
            if key not in edge_acc:
                edge_acc[key] = {
                    "source_area": source,
                    "target_area": target,
                    "anagenetic_count": 0.0,
                    "founder_count": 0.0,
                }
            edge_acc[key][count_key] += weight

    def _split_range_label(self, value, area_codes):
        text = self._clean(value)
        if not text:
            return []
        if text in ("_", "/", "null", "NULL"):
            return []
        codes = [str(code) for code in list(area_codes or []) if str(code)]
        if not codes:
            return []
        normalized = text
        for token in ["{", "}", "[", "]", "(", ")", "\"", "'", "|", ";", ":", ">", "<"]:
            normalized = normalized.replace(token, " ")
        for token in [",", "+", "&", "/", "\\", "-"]:
            normalized = normalized.replace(token, " ")
        parts = [part.strip() for part in normalized.split() if part.strip()]
        if parts:
            matched = [self._normalize_area_code(part, codes) for part in parts]
            matched = [part for part in matched if part]
            if matched:
                return self._unique_preserve_order(matched)

        compact = "".join(ch for ch in text if not ch.isspace() and ch not in "{}[](),'\"")
        if all(len(code) == 1 for code in codes):
            return self._unique_preserve_order([ch for ch in compact if ch in codes])

        remaining = compact
        matched = []
        for code in sorted(codes, key=len, reverse=True):
            if code and code in remaining:
                matched.append(code)
                remaining = remaining.replace(code, " ")
        return self._unique_preserve_order(matched)

    def _normalize_area_code(self, value, area_codes):
        text = self._clean(value)
        if not text:
            return ""
        for code in list(area_codes or []):
            if text == str(code):
                return str(code)
        # BioGeoBEARS may store numeric one-based area ids in some fields.
        idx = self._safe_int(text, 0)
        if idx > 0 and idx <= len(area_codes):
            return str(area_codes[idx - 1])
        return ""

    def _area_codes(self, areas, range_matrix, result):
        matrix_codes = []
        for column in list(getattr(range_matrix, "state_columns", []) or []):
            code = self._clean(column)
            if code and code not in matrix_codes:
                matrix_codes.append(code)

        event_codes = []
        for name in ("anagenetic", "cladogenetic"):
            for row in self._raw_rows(result, name)[:2000]:
                for key in ("current_rangetxt", "new_rangetxt", "dispersal_to", "clado_dispersal_to", "clado_event_txt"):
                    for code in self._extract_event_area_codes(row.get(key)):
                        if code and code not in event_codes:
                            event_codes.append(code)

        spatial_codes = []
        for area in list(areas or []):
            code = self._clean(getattr(area, "area_code", ""))
            if code and code not in spatial_codes:
                spatial_codes.append(code)

        # BSM events are encoded in model-area codes. When a range matrix exists,
        # its columns are the authoritative model codes; spatial layers are only
        # used for centroids/display names. This avoids mixing short model codes
        # such as A/U/I/R/N/E/W with full GeoJSON names.
        if event_codes and matrix_codes:
            if all(len(code) == 1 for code in event_codes) and not all(code in matrix_codes for code in event_codes):
                if self._looks_like_model_area_codes(matrix_codes):
                    return self._unique_preserve_order(matrix_codes)
                return self._unique_preserve_order(event_codes)
            return self._unique_preserve_order(matrix_codes + [code for code in event_codes if code in matrix_codes])
        if matrix_codes:
            return self._unique_preserve_order(matrix_codes + event_codes)
        if event_codes:
            return self._unique_preserve_order(event_codes + spatial_codes)
        return spatial_codes

    def _looks_like_model_area_codes(self, codes):
        values = [self._clean(code) for code in list(codes or []) if self._clean(code)]
        if not values:
            return False
        for code in values:
            if len(code) > 6:
                return False
            if any(ch.isspace() for ch in code):
                return False
            if not all(ch.isalnum() or ch in ("_", "-") for ch in code):
                return False
        return True

    def _extract_event_area_codes(self, value):
        text = self._clean(value)
        if not text:
            return []
        if text in ("_", "/", "-", "none"):
            return []
        normalized = text
        for token in ["{", "}", "[", "]", "(", ")", "\"", "'", "|", ";", ":", ">", "<"]:
            normalized = normalized.replace(token, " ")
        for token in [",", "+", "&", "/", "\\", "-"]:
            normalized = normalized.replace(token, " ")
        codes = []
        for part in [part.strip() for part in normalized.split() if part.strip()]:
            if part.lower() in ("na", "nan", "null", "none", "founder"):
                continue
            if not any(ch.isalpha() for ch in part):
                continue
            if part.isupper() and len(part) > 1:
                for char in part:
                    if char.isalpha() and char not in codes:
                        codes.append(char)
            elif part not in codes:
                codes.append(part)
        return codes

    def _area_metadata(self, areas):
        metadata = {}
        for area in list(areas or []):
            code = self._clean(getattr(area, "area_code", ""))
            if not code:
                continue
            metadata[code] = {
                "area_code": code,
                "display_name": self._clean(getattr(area, "display_name", "")) or code,
                "color": self._clean(getattr(area, "color", "")),
                "centroid_lon": getattr(area, "centroid_lon", None),
                "centroid_lat": getattr(area, "centroid_lat", None),
            }
        self._add_known_area_aliases(metadata)
        return metadata

    def _add_known_area_aliases(self, metadata):
        if not metadata:
            return
        by_name = {}
        for code, meta in list(metadata.items()):
            candidates = [
                code,
                meta.get("display_name", ""),
            ]
            for candidate in candidates:
                norm = self._normalize_name(candidate)
                if norm and norm not in by_name:
                    by_name[norm] = meta
        for alias, display_name in self.KNOWN_AREA_ALIASES.items():
            if alias in metadata:
                continue
            meta = by_name.get(self._normalize_name(display_name))
            if not meta:
                continue
            alias_meta = dict(meta)
            alias_meta["area_code"] = alias
            alias_meta["display_name"] = meta.get("display_name") or display_name
            metadata[alias] = alias_meta

    def _normalize_name(self, value):
        text = self._clean(value).lower()
        return "".join(ch for ch in text if ch.isalnum())

    def _node_rows(self, area_codes, area_metadata, range_matrix, edge_rows):
        richness = defaultdict(float)
        columns = [str(col) for col in list(getattr(range_matrix, "state_columns", []) or []) if str(col)]
        for row in list(getattr(range_matrix, "rows", []) or []):
            present = []
            for col in columns:
                if self._truthy_range_value(row.get(col)):
                    code = self._resolve_column_area_code(col, area_codes, area_metadata)
                    if code:
                        present.append(code)
            if present:
                weight = 1.0 / float(len(present))
                for col in present:
                    richness[col] += weight

        incoming = defaultdict(float)
        outgoing = defaultdict(float)
        for edge in list(edge_rows or []):
            source = str(edge.get("source_area", "") or "")
            target = str(edge.get("target_area", "") or "")
            mean = float(edge.get("mean_per_map", 0.0) or 0.0)
            outgoing[source] += mean
            incoming[target] += mean

        rows = []
        for code in list(area_codes or []):
            meta = area_metadata.get(code, {})
            rows.append({
                "area_code": code,
                "display_name": meta.get("display_name") or code,
                "richness": richness.get(code, 0.0),
                "incoming_mean_per_map": incoming.get(code, 0.0),
                "outgoing_mean_per_map": outgoing.get(code, 0.0),
                "centroid_lon": meta.get("centroid_lon", ""),
                "centroid_lat": meta.get("centroid_lat", ""),
                "color": meta.get("color", ""),
            })
        return rows

    def _resolve_column_area_code(self, column, area_codes, area_metadata):
        text = self._clean(column)
        codes = [str(code) for code in list(area_codes or []) if str(code)]
        if text in codes:
            return text
        norm = self._normalize_name(text)
        for code in codes:
            meta = area_metadata.get(code, {})
            candidates = [code, meta.get("display_name", "")]
            for candidate in candidates:
                if norm and norm == self._normalize_name(candidate):
                    return code
        return text if text in codes else ""

    def _truthy_range_value(self, value):
        text = str(value or "").strip().lower()
        return text in ("1", "true", "t", "yes", "y", "present")

    def _clean(self, value):
        if value is None:
            return ""
        text = str(value).strip()
        if text in ("NA", "<NA>", "NaN", "nan", "NULL", "None"):
            return ""
        return text

    def _safe_float(self, value, default):
        try:
            text = str(value).strip()
            if text == "":
                return default
            return float(text)
        except Exception:
            return default

    def _safe_int(self, value, default):
        try:
            text = str(value).strip()
            if text == "":
                return default
            return int(float(text))
        except Exception:
            return default

    def _unique_preserve_order(self, values):
        seen = set()
        out = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            out.append(value)
        return out
