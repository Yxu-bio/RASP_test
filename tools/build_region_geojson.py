"""Build study-specific area GeoJSON from base polygons and rules.

This is a generic reference-data builder for RASP spatial workflows.  It turns
country/admin/ecoregion polygons plus a mapping table and optional rules into a
GeoJSON where each output feature is one analysis area.

Typical usage:

    python tools/build_region_geojson.py ^
      --config examples/phase1_reference_data/region_builder_examples/demo_rules.json ^
      --output runs/region_builder/demo_regions.geojson

The builder intentionally avoids GIS-heavy dependencies.  It groups polygons as
MultiPolygon features and supports simple latitude/longitude clipping for coarse
study-specific rules.  It does not perform a topological dissolve.
"""

import argparse
import csv
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path


DEFAULT_COLORS = [
    "#4C78A8",
    "#F58518",
    "#54A24B",
    "#E45756",
    "#72B7B2",
    "#B279A2",
    "#FF9DA6",
    "#9D755D",
    "#BAB0AC",
    "#59A14F",
    "#EDC948",
    "#AF7AA1",
]


def _is_url(value):
    text = str(value or "")
    return text.startswith("http://") or text.startswith("https://")


def _read_bytes(path_or_url, base_dir=None):
    value = str(path_or_url or "").strip()
    if not value:
        raise ValueError("Missing path or URL.")
    if _is_url(value):
        request = urllib.request.Request(value, headers={"User-Agent": "RASP5-region-builder"})
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()
    path = Path(value)
    if not path.is_absolute() and base_dir is not None:
        path = Path(base_dir) / path
    return path.read_bytes()


def _read_text(path_or_url, base_dir=None):
    return _read_bytes(path_or_url, base_dir=base_dir).decode("utf-8-sig")


def _load_json(path_or_url, base_dir=None):
    return json.loads(_read_text(path_or_url, base_dir=base_dir))


def _load_csv_rows(path_or_url, base_dir=None):
    text = _read_text(path_or_url, base_dir=base_dir)
    rows = []
    for row in csv.DictReader(text.splitlines()):
        rows.append(dict((str(k or "").strip(), str(v or "").strip()) for k, v in row.items()))
    return rows


def _geometry_to_polygons(geometry):
    geometry_type = str((geometry or {}).get("type") or "")
    coordinates = (geometry or {}).get("coordinates") or []
    if geometry_type == "Polygon":
        return [coordinates]
    if geometry_type == "MultiPolygon":
        return list(coordinates)
    return []


def _normalise_ring(ring):
    points = []
    for point in ring or []:
        if len(point) >= 2:
            points.append([float(point[0]), float(point[1])])
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    return points


def _close_ring(points):
    if len(points) < 3:
        return None
    rounded = [[round(float(x), 6), round(float(y), 6)] for x, y in points]
    if rounded[0] != rounded[-1]:
        rounded.append(list(rounded[0]))
    if len(rounded) < 4:
        return None
    return rounded


def _rounded_polygons(geometry):
    polygons = []
    for polygon in _geometry_to_polygons(geometry):
        out_polygon = []
        for ring in polygon or []:
            closed = _close_ring(_normalise_ring(ring))
            if closed:
                out_polygon.append(closed)
        if out_polygon:
            polygons.append(out_polygon)
    return polygons


def _inside(point, axis, op, threshold):
    value = point[0] if axis == "lon" else point[1]
    if op in ("<", "lt", "less"):
        return value <= threshold
    if op in (">=", "gte", "greater_equal"):
        return value >= threshold
    raise ValueError("Unsupported clip operator: %s" % op)


def _intersection(a, b, axis, threshold):
    av = a[0] if axis == "lon" else a[1]
    bv = b[0] if axis == "lon" else b[1]
    if abs(bv - av) < 1e-12:
        return [threshold if axis == "lon" else b[0], threshold if axis == "lat" else b[1]]
    ratio = (threshold - av) / (bv - av)
    lon = a[0] + (b[0] - a[0]) * ratio
    lat = a[1] + (b[1] - a[1]) * ratio
    if axis == "lon":
        lon = threshold
    else:
        lat = threshold
    return [lon, lat]


def _clip_ring(points, axis, op, threshold):
    if len(points) < 3:
        return []
    output = list(points)
    clipped = []
    previous = output[-1]
    previous_inside = _inside(previous, axis, op, threshold)
    for current in output:
        current_inside = _inside(current, axis, op, threshold)
        if current_inside:
            if not previous_inside:
                clipped.append(_intersection(previous, current, axis, threshold))
            clipped.append(current)
        elif previous_inside:
            clipped.append(_intersection(previous, current, axis, threshold))
        previous = current
        previous_inside = current_inside
    return clipped


def _clip_polygon(polygon, constraints):
    clipped_rings = []
    for ring in polygon or []:
        points = _normalise_ring(ring)
        for axis, op, threshold in constraints:
            points = _clip_ring(points, axis, op, float(threshold))
            if len(points) < 3:
                break
        closed = _close_ring(points)
        if closed:
            clipped_rings.append(closed)
    if not clipped_rings:
        return None
    return clipped_rings


def _clip_geometry(geometry, constraints):
    clipped = []
    for polygon in _geometry_to_polygons(geometry):
        clipped_polygon = _clip_polygon(polygon, constraints)
        if clipped_polygon:
            clipped.append(clipped_polygon)
    return clipped


def _property_values(properties, fields):
    out = []
    for field in fields or []:
        value = str((properties or {}).get(field, "") or "").strip()
        if value:
            out.append(value)
    return out


def _selector_matches(properties, selector):
    selector = dict(selector or {})
    if not selector:
        return True
    if "all" in selector:
        return all(_selector_matches(properties, item) for item in selector.get("all") or [])
    if "any" in selector:
        return any(_selector_matches(properties, item) for item in selector.get("any") or [])

    fields = selector.get("fields")
    if fields is None:
        field = selector.get("field")
        fields = [field] if field else []
    values = _property_values(properties, fields)

    if "equals" in selector:
        target = str(selector.get("equals") or "").strip()
        return any(value == target for value in values)
    if "in" in selector:
        targets = set(str(value).strip() for value in selector.get("in") or [])
        return any(value in targets for value in values)
    if "contains" in selector:
        target = str(selector.get("contains") or "").strip()
        return any(target in value for value in values)
    if "regex" in selector:
        pattern = re.compile(str(selector.get("regex") or ""))
        return any(pattern.search(value) for value in values)
    if "not" in selector:
        return not _selector_matches(properties, selector.get("not") or {})
    return bool(values)


def _feature_name(feature, fields=None):
    properties = dict((feature or {}).get("properties") or {})
    for field in fields or ["SUBUNIT", "NAME", "name", "NAME_LONG", "ADMIN", "SOVEREIGNT", "id"]:
        value = str(properties.get(field, "") or "").strip()
        if value:
            return value
    return str((feature or {}).get("id", "") or "").strip() or "feature"


def _load_mapping(config, config_dir):
    mapping_config = dict(config.get("base_mapping") or {})
    mapping_file = mapping_config.get("mapping_file") or config.get("mapping_csv")
    if not mapping_file:
        return {}, mapping_config
    rows = _load_csv_rows(mapping_file, base_dir=config_dir)
    value_field = mapping_config.get("value_field", "match_value")
    area_field = mapping_config.get("area_field", "area_code")
    mapping = {}
    for row in rows:
        area = str(row.get(area_field, "") or "").strip()
        if not area:
            continue
        values = []
        if row.get(value_field):
            values.append(row.get(value_field))
        for field in mapping_config.get("row_value_fields") or []:
            if row.get(field):
                values.append(row.get(field))
        for value in values:
            value = str(value or "").strip()
            if value:
                mapping[value] = area
    return mapping, mapping_config


def _mapping_area(feature, mapping, mapping_config):
    if not mapping:
        return ""
    fields = mapping_config.get("feature_fields") or ["ISO_A3", "ADM0_A3", "SUBUNIT", "NAME", "name"]
    properties = dict((feature or {}).get("properties") or {})
    for value in _property_values(properties, fields):
        if value in mapping:
            return mapping[value]
    return ""


def _add_polygons(groups, notes, source_id, source_name, area, polygons, rule_name):
    if not area or not polygons:
        return
    groups[area].extend(polygons)
    notes.append(
        {
            "source_id": source_id,
            "source_name": source_name,
            "area_code": area,
            "rule": rule_name,
            "polygon_count": len(polygons),
        }
    )


def _rule_area_by_value(rule, properties):
    fields = rule.get("value_fields")
    if fields is None:
        field = rule.get("value_field")
        fields = [field] if field else []
    values = set(_property_values(properties, fields))
    for area, candidates in dict(rule.get("areas") or {}).items():
        if values & set(str(value).strip() for value in candidates or []):
            return area
    return str(rule.get("default_area", "") or "").strip()


def _apply_rule(groups, notes, source_id, feature, rule):
    rule_type = str(rule.get("type") or "").strip().lower()
    properties = dict((feature or {}).get("properties") or {})
    if not _selector_matches(properties, rule.get("selector") or {}):
        return False
    rule_name = str(rule.get("name") or rule_type or "rule")
    source_name = _feature_name(feature, rule.get("name_fields"))
    geometry = feature.get("geometry") or {}

    if rule_type == "ignore":
        notes.append(
            {
                "source_id": source_id,
                "source_name": source_name,
                "area_code": "",
                "rule": rule_name,
                "polygon_count": 0,
            }
        )
        return True
    if rule_type == "assign":
        area = str(rule.get("area") or "").strip()
        _add_polygons(groups, notes, source_id, source_name, area, _rounded_polygons(geometry), rule_name)
        return True
    if rule_type == "assign_by_values":
        area = _rule_area_by_value(rule, properties)
        _add_polygons(groups, notes, source_id, source_name, area, _rounded_polygons(geometry), rule_name)
        return True
    if rule_type == "split":
        axis = str(rule.get("axis") or "").strip().lower()
        if axis not in ("lat", "lon"):
            raise ValueError("Split rule '%s' must use axis lat or lon." % rule_name)
        threshold = float(rule.get("threshold"))
        less_area = str(rule.get("less_area") or rule.get("below_area") or "").strip()
        greater_area = str(rule.get("greater_equal_area") or rule.get("above_or_equal_area") or "").strip()
        _add_polygons(
            groups,
            notes,
            source_id,
            source_name,
            less_area,
            _clip_geometry(geometry, [(axis, "<", threshold)]),
            rule_name + " (< %s)" % threshold,
        )
        _add_polygons(
            groups,
            notes,
            source_id,
            source_name,
            greater_area,
            _clip_geometry(geometry, [(axis, ">=", threshold)]),
            rule_name + " (>= %s)" % threshold,
        )
        return True
    raise ValueError("Unsupported rule type '%s' in rule '%s'." % (rule_type, rule_name))


def _source_path_for(source_config):
    return source_config.get("path") or source_config.get("url") or source_config.get("geojson")


def _load_sources(config, config_dir):
    sources = {
        "base": _load_json(config.get("base_geojson") or config.get("base_url"), base_dir=config_dir)
    }
    for source_id, source_config in dict(config.get("sources") or {}).items():
        sources[source_id] = _load_json(_source_path_for(dict(source_config or {})), base_dir=config_dir)
    return sources


def _area_metadata(config, area_order):
    configured = dict(config.get("area_metadata") or {})
    out = {}
    for index, area in enumerate(area_order):
        meta = dict(configured.get(area) or {})
        meta.setdefault("display_name", area)
        meta.setdefault("color", DEFAULT_COLORS[index % len(DEFAULT_COLORS)])
        out[area] = meta
    return out


def build_regions(config, config_dir=None):
    sources = _load_sources(config, config_dir)
    mapping, mapping_config = _load_mapping(config, config_dir)
    groups = defaultdict(list)
    notes = []
    unassigned = []
    rules = [dict(rule or {}) for rule in config.get("rules") or []]

    base_rules = [rule for rule in rules if str(rule.get("source", "base") or "base") == "base"]
    for feature in sources["base"].get("features", []):
        handled = False
        for rule in base_rules:
            if _apply_rule(groups, notes, "base", feature, rule):
                handled = True
                break
        if handled:
            continue
        area = _mapping_area(feature, mapping, mapping_config)
        if area:
            _add_polygons(groups, notes, "base", _feature_name(feature), area, _rounded_polygons(feature.get("geometry")), "base mapping")
        else:
            unassigned.append(
                {
                    "source_id": "base",
                    "source_name": _feature_name(feature),
                    "properties": dict(feature.get("properties") or {}),
                }
            )

    for source_id, source in sources.items():
        if source_id == "base":
            continue
        source_rules = [rule for rule in rules if str(rule.get("source", "") or "") == source_id]
        for rule in source_rules:
            for feature in source.get("features", []):
                _apply_rule(groups, notes, source_id, feature, rule)

    area_order = list(config.get("area_order") or [])
    for area in sorted(groups):
        if area not in area_order:
            area_order.append(area)
    metadata = _area_metadata(config, area_order)
    features = []
    for area in area_order:
        polygons = list(groups.get(area) or [])
        if not polygons:
            continue
        meta = metadata.get(area, {})
        properties = {
            "area_code": area,
            "name": str(meta.get("display_name") or area),
            "display_name": str(meta.get("display_name") or area),
            "color": str(meta.get("color") or ""),
            "group": str(config.get("group") or config.get("name") or "custom_regions"),
            "source": str(config.get("source") or ""),
            "boundary_kind": str(config.get("boundary_kind") or "rule_based_reference"),
            "official_author_boundary": bool(config.get("official_author_boundary", False)),
            "build_notes": str(config.get("build_notes") or "Built by RASP5 generic Region GeoJSON builder."),
        }
        for key, value in dict(meta.get("properties") or {}).items():
            properties[key] = value
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": polygons,
                },
            }
        )
    collection = {
        "type": "FeatureCollection",
        "name": str(config.get("name") or "study_regions"),
        "metadata": {
            "schema": "rasp5_region_builder.v1",
            "boundary_kind": str(config.get("boundary_kind") or "rule_based_reference"),
            "official_author_boundary": bool(config.get("official_author_boundary", False)),
            "build_notes": str(config.get("build_notes") or "Built by RASP5 generic Region GeoJSON builder."),
        },
        "features": features,
    }
    return collection, notes, unassigned


def _write_notes(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["source_id", "source_name", "area_code", "rule", "polygon_count"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict((field, row.get(field, "")) for field in fieldnames))


def _write_unassigned(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["source_id", "source_name", "properties_json"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source_id": row.get("source_id", ""),
                    "source_name": row.get("source_name", ""),
                    "properties_json": json.dumps(row.get("properties") or {}, ensure_ascii=False, sort_keys=True),
                }
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Region builder JSON config.")
    parser.add_argument("--output", required=True, help="Output area GeoJSON.")
    parser.add_argument("--notes-output", default="", help="Optional build notes CSV.")
    parser.add_argument("--unassigned-output", default="", help="Optional unassigned features CSV.")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    collection, notes, unassigned = build_regions(config, config_dir=config_path.parent)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if args.notes_output:
        _write_notes(args.notes_output, notes)
    if args.unassigned_output:
        _write_unassigned(args.unassigned_output, unassigned)

    print("wrote", output)
    print("features", len(collection.get("features") or []))
    for feature in collection.get("features") or []:
        print(feature["properties"]["area_code"], len(feature["geometry"]["coordinates"]), "polygons")
    if unassigned:
        print("unassigned features:", len(unassigned), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
