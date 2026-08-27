"""Build an approximate Dore et al. 2025 Ponerinae 7-bioregion GeoJSON.

This is a reproducible reference-data builder, not an application runtime
dependency.  It combines the country/subunit bioregion metadata from the
Dore et al. repository with Natural Earth map-subunit/admin1 polygons, then
applies the special split rules documented in the Dore curation script.

The output is a rule-based reference asset for RASP spatial workflow testing.
It is not an official author-provided bioregion boundary file.
"""

import argparse
import io
import json
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


DORE_METADATA_URL = (
    "https://raw.githubusercontent.com/MaelDore/"
    "Ponerinae_Historical_Biogeography/main/input_data/"
    "Biogeographic_data/Countries_NE_sf_metadata.xlsx"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
NE_SUBUNITS_PATH = (
    REPO_ROOT
    / "resources"
    / "spatial_base_layers"
    / "natural_earth"
    / "ne_50m_admin_0_map_subunits.geojson"
)
NE_ADMIN1_PATH = (
    REPO_ROOT
    / "resources"
    / "spatial_base_layers"
    / "natural_earth"
    / "ne_10m_admin_1_states_provinces.geojson"
)

DEFAULT_OUTPUT = (
    Path("data")
    / "benchmarks"
    / "dore_ponerinae"
    / "Ponerinae_7_bioregions.geojson"
)
DEFAULT_NOTES_OUTPUT = (
    Path("data")
    / "benchmarks"
    / "dore_ponerinae"
    / "Ponerinae_7_bioregions_build_notes.csv"
)

AREA_ORDER = [
    "Afrotropics",
    "Australasia",
    "Indomalaya",
    "Nearctic",
    "Neotropics",
    "Eastern Palearctic",
    "Western Palearctic",
]

AREA_COLORS = {
    "Afrotropics": "#8dd3c7",
    "Australasia": "#ffffb3",
    "Indomalaya": "#bebada",
    "Nearctic": "#fb8072",
    "Neotropics": "#80b1d3",
    "Eastern Palearctic": "#fdb462",
    "Western Palearctic": "#b3de69",
}

SPECIAL_ISO = {"IDN", "MEX", "CHN", "USA", "RUS", "IND", "PAK", "JPN", "FRA", "NLD"}
ADMIN1_SPLIT_ISO = {"RUS", "IND", "PAK"}
IGNORE_ISO = {"ATA", "HMD", "SGS"}

RUSSIA_EASTERN_ADM1 = {
    "Altai Krai",
    "Altay",
    "Altai Republic",
    "Gorno-Altay",
    "Amur Oblast",
    "Amur",
    "Buryatia",
    "Republic of Buryatia",
    "Buryat",
    "Chelyabinsk Oblast",
    "Chelyabinsk",
    "Chukotka Autonomous Okrug",
    "Chukchi Autonomous Okrug",
    "Irkutsk Oblast",
    "Irkutsk",
    "Jewish Autonomous Oblast",
    "Kamchatka Krai",
    "Kamchatka",
    "Kemerovo Oblast",
    "Kemerovo",
    "Khabarovsk Krai",
    "Khabarovsk",
    "Khakassia",
    "Republic of Khakassia",
    "Khakass",
    "Khanty-Mansiysk Autonomous Okrug ? Ugra",
    "Khanty-Mansiy",
    "Krasnoyarsk Krai",
    "Krasnoyarsk",
    "Kurgan Oblast",
    "Kurgan",
    "Magadan Oblast",
    "Magadan",
    "Novosibirsk Oblast",
    "Novosibirsk",
    "Omsk Oblast",
    "Omsk",
    "Primorsky Krai",
    "Primorskiy Kray",
    "Primorsky",
    "Sakha Republic",
    "Sakha",
    "Sakhalin Oblast",
    "Sakhalin",
    "Sverdlovsk Oblast",
    "Sverdlovsk",
    "Tomsk Oblast",
    "Tomsk",
    "Tuva",
    "Tyumen Oblast",
    "Tyumen",
    "Yamalo-Nenets Autonomous Okrug",
    "Yamal-Nenets",
    "Zabaykalsky Krai",
    "Transbaikal",
}

INDIA_EASTERN_PALEARCTIC_ADM1 = {
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Ladakh",
}

PAKISTAN_EASTERN_PALEARCTIC_ADM1 = {
    "Azad Kashmir",
    "Gilgit-Baltistan",
    "Northern Areas",
}

JAPAN_INDOMALAYA_SUBUNITS = {
    "Nanseishoto",
    "Nansei-shoto",
}

FRANCE_NEOTROPICS = {
    "French Guiana",
    "Guadeloupe",
    "Martinique",
    "Saint Martin",
    "Saint Barthelemy",
    "St-Martin",
    "St-Barthélemy",
}
FRANCE_AFROTROPICS = {
    "Mayotte",
    "Réunion",
    "Reunion",
    "French Southern and Antarctic Lands",
    "Fr. S. Antarctic Lands",
}
NETHERLANDS_NEOTROPICS = {
    "Aruba",
    "Caribbean Netherlands",
}
USA_AUSTRALASIA = {
    "Hawaii",
    "Guam",
    "Northern Mariana Islands",
    "American Samoa",
}
USA_NEOTROPICS = {
    "Puerto Rico",
    "United States Virgin Islands",
}

XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "RASP5-reference-builder"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _xlsx_first_sheet_rows(raw_bytes):
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", XLSX_NS):
                shared_strings.append("".join((t.text or "") for t in item.findall(".//a:t", XLSX_NS)))

        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in root.findall(".//a:sheetData/a:row", XLSX_NS):
            values = []
            for cell in row.findall("a:c", XLSX_NS):
                ref = cell.attrib.get("r", "A1")
                col = 0
                for ch in "".join(ch for ch in ref if ch.isalpha()):
                    col = col * 26 + ord(ch.upper()) - 64
                col -= 1
                while len(values) <= col:
                    values.append("")
                value_node = cell.find("a:v", XLSX_NS)
                if cell.attrib.get("t") == "s":
                    if value_node is not None and value_node.text:
                        values[col] = shared_strings[int(value_node.text)]
                elif value_node is not None and value_node.text:
                    values[col] = value_node.text
            rows.append(values)
        return rows


def _read_dore_metadata():
    rows = _xlsx_first_sheet_rows(_download(DORE_METADATA_URL))
    header = rows[0]
    records = []
    for row in rows[1:]:
        padded = row + [""] * (len(header) - len(row))
        record = dict((header[i], padded[i].strip()) for i in range(len(header)))
        records.append(record)
    return records


def _geometry_to_polygons(geometry):
    if not geometry:
        return []
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
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


def _inside(point, axis, op, threshold):
    value = point[0] if axis == "lon" else point[1]
    if op == "<":
        return value <= threshold
    if op == ">=":
        return value >= threshold
    raise ValueError("Unsupported clip operator: %s" % op)


def _intersection(a, b, axis, threshold):
    av = a[0] if axis == "lon" else a[1]
    bv = b[0] if axis == "lon" else b[1]
    if abs(bv - av) < 1e-12:
        return [threshold if axis == "lon" else b[0], threshold if axis == "lat" else b[1]]
    t = (threshold - av) / (bv - av)
    lon = a[0] + (b[0] - a[0]) * t
    lat = a[1] + (b[1] - a[1]) * t
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


def _rounded_polygons(geometry):
    polygons = []
    for polygon in _geometry_to_polygons(geometry):
        rounded_polygon = []
        for ring in polygon:
            closed = _close_ring(_normalise_ring(ring))
            if closed:
                rounded_polygon.append(closed)
        if rounded_polygon:
            polygons.append(rounded_polygon)
    return polygons


def _feature_names(properties):
    return {
        str(properties.get(key) or "").strip()
        for key in ["SUBUNIT", "NAME", "NAME_LONG", "ADMIN", "SOVEREIGNT", "GEOUNIT"]
        if str(properties.get(key) or "").strip()
    }


def _feature_iso(properties):
    for key in ["ISO_A3", "ADM0_A3", "GU_A3", "SU_A3", "SOV_A3"]:
        value = str(properties.get(key) or "").strip()
        if value and value != "-99":
            return value
    return str(properties.get("ADM0_A3") or properties.get("SOV_A3") or "").strip()


def _metadata_region(properties, metadata_by_subunit, metadata_by_iso):
    names = _feature_names(properties)
    for name in names:
        record = metadata_by_subunit.get(name)
        if record and record.get("Bioregion_7_PaleA"):
            return record["Bioregion_7_PaleA"]
    for key in ["ISO_A3", "ADM0_A3", "GU_A3", "SU_A3", "SOV_A3"]:
        value = str(properties.get(key) or "").strip()
        if value and value != "-99":
            record = metadata_by_iso.get(value)
            if record and record.get("Bioregion_7_PaleA"):
                return record["Bioregion_7_PaleA"]
    return ""


def _add_polygons(groups, notes, region, polygons, source_name, rule):
    if region not in AREA_ORDER or not polygons:
        return
    groups[region].extend(polygons)
    notes.append((source_name, region, rule, len(polygons)))


def _add_regular_subunit(groups, notes, feature, metadata_by_subunit, metadata_by_iso):
    properties = feature.get("properties") or {}
    region = _metadata_region(properties, metadata_by_subunit, metadata_by_iso)
    if region not in AREA_ORDER:
        return False
    source_name = str(properties.get("SUBUNIT") or properties.get("NAME") or region)
    _add_polygons(groups, notes, region, _rounded_polygons(feature.get("geometry")), source_name, "Dore country/subunit metadata")
    return True


def _add_special_admin0(groups, notes, feature):
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry")
    subunit = str(properties.get("SUBUNIT") or properties.get("NAME") or "")
    name = str(properties.get("NAME") or "")
    adm0 = str(properties.get("ADM0_A3") or properties.get("SOV_A3") or "")
    names = _feature_names(properties)

    if names & FRANCE_AFROTROPICS:
        _add_polygons(groups, notes, "Afrotropics", _rounded_polygons(geometry), subunit, "Dore TAAF/Europa Island special case")
        return True
    if adm0 == "IDN":
        _add_polygons(groups, notes, "Indomalaya", _clip_geometry(geometry, [("lon", "<", 125.5)]), subunit, "Dore split: Indonesia longitude < 125.5")
        _add_polygons(groups, notes, "Australasia", _clip_geometry(geometry, [("lon", ">=", 125.5)]), subunit, "Dore split: Indonesia longitude >= 125.5")
        return True
    if adm0 == "MEX":
        _add_polygons(groups, notes, "Neotropics", _clip_geometry(geometry, [("lat", "<", 22.0)]), subunit, "Dore split: Mexico latitude < 22")
        _add_polygons(groups, notes, "Nearctic", _clip_geometry(geometry, [("lat", ">=", 22.0)]), subunit, "Dore split: Mexico latitude >= 22")
        return True
    if adm0 == "CHN":
        _add_polygons(groups, notes, "Indomalaya", _clip_geometry(geometry, [("lat", "<", 33.0)]), subunit, "Dore split: China latitude < 33")
        _add_polygons(groups, notes, "Eastern Palearctic", _clip_geometry(geometry, [("lat", ">=", 33.0)]), subunit, "Dore split: China latitude >= 33, then 7-PaleA Eastern")
        return True
    if adm0 == "USA":
        if names & USA_AUSTRALASIA:
            _add_polygons(groups, notes, "Australasia", _rounded_polygons(geometry), subunit, "Dore USA/Hawaii special case; NE subunit")
        elif names & USA_NEOTROPICS:
            _add_polygons(groups, notes, "Neotropics", _rounded_polygons(geometry), subunit, "US Caribbean subunit")
        else:
            _add_polygons(groups, notes, "Nearctic", _rounded_polygons(geometry), subunit, "Dore USA special case; non-Hawaii subunit")
        return True
    if adm0 == "FRA":
        if names & FRANCE_NEOTROPICS:
            _add_polygons(groups, notes, "Neotropics", _rounded_polygons(geometry), subunit, "Dore France overseas special case")
        elif names & FRANCE_AFROTROPICS:
            _add_polygons(groups, notes, "Afrotropics", _rounded_polygons(geometry), subunit, "Dore France overseas special case")
        else:
            _add_polygons(groups, notes, "Western Palearctic", _rounded_polygons(geometry), subunit, "Dore 7-PaleA France mainland -> Western Palearctic")
        return True
    if adm0 == "NLD":
        if names & NETHERLANDS_NEOTROPICS:
            _add_polygons(groups, notes, "Neotropics", _rounded_polygons(geometry), subunit, "Netherlands Caribbean subunit")
        else:
            _add_polygons(groups, notes, "Western Palearctic", _rounded_polygons(geometry), subunit, "Dore 7-PaleA Netherlands mainland -> Western Palearctic")
        return True
    if adm0 == "JPN":
        if names & JAPAN_INDOMALAYA_SUBUNITS:
            _add_polygons(groups, notes, "Indomalaya", _rounded_polygons(geometry), subunit, "Japan Nanseishoto approximation")
        else:
            _add_polygons(groups, notes, "Eastern Palearctic", _rounded_polygons(geometry), subunit, "Dore 7-PaleA Japan Palearctic entries -> Eastern")
        return True
    return False


def _add_admin1_splits(groups, notes, admin1_geojson):
    for feature in admin1_geojson.get("features", []):
        properties = feature.get("properties") or {}
        adm0 = str(properties.get("adm0_a3") or "")
        if adm0 not in ADMIN1_SPLIT_ISO:
            continue
        name = str(properties.get("name_en") or properties.get("name") or "")
        names = {
            str(properties.get(key) or "").strip()
            for key in ["name_en", "name", "gn_name"]
            if str(properties.get(key) or "").strip()
        }
        if adm0 == "RUS":
            region = "Eastern Palearctic" if names & RUSSIA_EASTERN_ADM1 else "Western Palearctic"
            rule = "Dore 7-PaleA Russia adm1 split"
        elif adm0 == "IND":
            region = "Eastern Palearctic" if names & INDIA_EASTERN_PALEARCTIC_ADM1 else "Indomalaya"
            rule = "Dore India Palearctic adm1 -> Eastern; other adm1 -> Indomalaya approximation"
        elif adm0 == "PAK":
            region = "Eastern Palearctic" if names & PAKISTAN_EASTERN_PALEARCTIC_ADM1 else "Indomalaya"
            rule = "Dore Pakistan Palearctic adm1 -> Eastern; other adm1 -> Indomalaya approximation"
        else:
            continue
        _add_polygons(groups, notes, region, _rounded_polygons(feature.get("geometry")), name, rule)


def _build_feature(region, polygons):
    return {
        "type": "Feature",
        "properties": {
            "area_code": region,
            "name": region,
            "display_name": region,
            "color": AREA_COLORS[region],
            "group": "Dore_2025_Ponerinae_7_bioregions",
            "source": "Dore_2025_Ponerinae + Natural Earth",
            "crs": "EPSG:4326",
            "boundary_kind": "approximate_rule_based_reference",
            "official_author_boundary": False,
            "build": "Approximate grouped Natural Earth polygons with Dore occurrence-assignment special split rules; no topology union required for point-in-polygon encoding.",
            "build_notes": "Reference asset for testing RASP spatial workflows. Dore et al. assigned occurrences with country/subunit metadata and special rules; this file spatializes those rules and should not be treated as an official paper boundary map.",
        },
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": polygons,
        },
    }


def build_ponerinae_geojson():
    metadata = _read_dore_metadata()
    metadata_by_subunit = dict((r.get("SUBUNIT", ""), r) for r in metadata if r.get("SUBUNIT"))
    metadata_by_iso = {}
    for record in metadata:
        iso = record.get("ISO_A3")
        if iso and iso not in metadata_by_iso:
            metadata_by_iso[iso] = record

    subunits = _read_json(NE_SUBUNITS_PATH)
    admin1 = _read_json(NE_ADMIN1_PATH)
    groups = defaultdict(list)
    notes = []
    unmatched = []

    for feature in subunits.get("features", []):
        properties = feature.get("properties") or {}
        adm0 = str(properties.get("ADM0_A3") or properties.get("SOV_A3") or "")
        if adm0 in ADMIN1_SPLIT_ISO:
            continue
        if _add_special_admin0(groups, notes, feature):
            continue
        if _add_regular_subunit(groups, notes, feature, metadata_by_subunit, metadata_by_iso):
            continue
        name = str(properties.get("SUBUNIT") or properties.get("NAME") or "")
        iso = _feature_iso(properties)
        if name and iso not in IGNORE_ISO:
            unmatched.append((name, iso))

    _add_admin1_splits(groups, notes, admin1)

    features = []
    for region in AREA_ORDER:
        polygons = groups.get(region, [])
        if not polygons:
            raise RuntimeError("No polygons were generated for %s" % region)
        features.append(_build_feature(region, polygons))

    collection = {
        "type": "FeatureCollection",
        "name": "Ponerinae_7_bioregions",
        "metadata": {
            "description": "Approximate rule-based seven-bioregion GeoJSON for Dore et al. 2025 Ponerinae spatial testing.",
            "boundary_kind": "approximate_rule_based_reference",
            "official_author_boundary": False,
            "usage_note": "Use for RASP point-in-polygon workflow testing and study-specific approximate coding. Do not cite or present as an official Dore et al. polygon boundary dataset.",
            "dore_metadata_url": DORE_METADATA_URL,
            "natural_earth_subunits_path": str(NE_SUBUNITS_PATH),
            "natural_earth_admin1_path": str(NE_ADMIN1_PATH),
            "special_rules": [
                "Indonesia split at 125.5E longitude.",
                "Mexico split at 22N latitude.",
                "China split at 33N latitude; northern part assigned Eastern Palearctic.",
                "Russia split by Natural Earth admin1 using Dore eastern-adm1 list.",
                "India and Pakistan split by Natural Earth admin1 using Dore-commented Palearctic admin1 lists.",
                "Japan main islands assigned Eastern Palearctic; Nanseishoto assigned Indomalaya approximation.",
                "France, Netherlands, and USA overseas subunits handled separately.",
            ],
        },
        "features": features,
    }
    return collection, notes, unmatched


def write_notes(path, notes, unmatched):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("source_name,area_code,rule,polygon_count\n")
        for source_name, region, rule, count in notes:
            safe = [
                str(source_name).replace('"', '""'),
                str(region).replace('"', '""'),
                str(rule).replace('"', '""'),
                str(count),
            ]
            handle.write('"%s","%s","%s",%s\n' % tuple(safe))
        if unmatched:
            handle.write("\n# unmatched_subunit,iso\n")
            for name, iso in unmatched:
                handle.write('"%s","%s"\n' % (str(name).replace('"', '""'), str(iso).replace('"', '""')))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output GeoJSON path.")
    parser.add_argument("--notes-output", default=str(DEFAULT_NOTES_OUTPUT), help="Output build notes CSV path.")
    args = parser.parse_args(argv)

    output = Path(args.output)
    notes_output = Path(args.notes_output)
    collection, notes, unmatched = build_ponerinae_geojson()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_notes(notes_output, notes, unmatched)
    print("wrote", output)
    print("features", len(collection.get("features", [])))
    for feature in collection.get("features", []):
        print(
            feature["properties"]["area_code"],
            len(feature["geometry"]["coordinates"]),
            "polygons",
        )
    if unmatched:
        print("unmatched subunits:", len(unmatched), file=sys.stderr)
        for name, iso in unmatched[:30]:
            print("  %s (%s)" % (name, iso), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
