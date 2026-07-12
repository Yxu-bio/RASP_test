import csv
import json
from collections import defaultdict
from pathlib import Path

from application.services.taxon_match_service import TaxonMatchService
from domain.models.spatial_data import (
    AreaSpatialRecord,
    EncodedOccurrenceAuditRow,
    OccurrenceRecord,
    SpatialDataProject,
    SpatialQAIssue,
)
from domain.models.state_matrix import StateMatrix


class SpatialDataService:
    PROJECT_FORMAT = "rasp5_spatial_data_project"
    PROJECT_VERSION = 1
    TAXON_FIELDS = ["taxon", "name", "species", "scientificname", "scientific_name"]
    LATITUDE_FIELDS = ["latitude", "lat", "decimallatitude", "decimal_latitude"]
    LONGITUDE_FIELDS = ["longitude", "lon", "lng", "decimallongitude", "decimal_longitude"]
    AREA_CODE_FIELDS = ["area_code", "area", "code", "id", "name", "label"]
    AREA_GROUP_FIELDS = ["group", "area_group", "region", "bioregion", "category"]
    AREA_COLOR_PALETTE = [
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

    def import_occurrences_csv(self, file_path: str, progress_callback=None, cancel_callback=None):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError("Occurrence file does not exist: %s" % file_path)
        delimiter = self._detect_delimiter(path)
        total_rows = self._count_data_rows(path) if progress_callback is not None else 0
        progress_step = max(1, total_rows // 100) if total_rows else 1
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise ValueError("Occurrence file has no header row.")
            field_map = self._build_field_map(reader.fieldnames)
            taxon_field = self._find_field(field_map, self.TAXON_FIELDS)
            lat_field = self._find_field(field_map, self.LATITUDE_FIELDS)
            lon_field = self._find_field(field_map, self.LONGITUDE_FIELDS)
            missing = []
            if not taxon_field:
                missing.append("taxon")
            if not lat_field:
                missing.append("latitude")
            if not lon_field:
                missing.append("longitude")
            if missing:
                raise ValueError("Occurrence file is missing required fields: %s." % ", ".join(missing))

            records = []
            issues = []
            seen_points = set()
            duplicate_warning_count = 0
            duplicate_warning_limit = 100
            for row_index, row in enumerate(reader, start=2):
                done = row_index - 1
                if cancel_callback is not None and cancel_callback():
                    raise RuntimeError("Occurrence import was cancelled.")
                clean = dict((str(k or "").strip(), str(v or "").strip()) for k, v in dict(row or {}).items())
                taxon = clean.get(taxon_field, "").strip()
                lat_text = clean.get(lat_field, "").strip()
                lon_text = clean.get(lon_field, "").strip()
                if not taxon:
                    issues.append(SpatialQAIssue("error", "missing_taxon", "Missing taxon name.", row=row_index))
                    continue
                try:
                    lat = float(lat_text)
                    lon = float(lon_text)
                except Exception:
                    issues.append(SpatialQAIssue("error", "invalid_coordinate", "Invalid latitude/longitude.", row=row_index, taxon=taxon))
                    continue
                if lat < -90.0 or lat > 90.0 or lon < -180.0 or lon > 180.0:
                    issues.append(SpatialQAIssue("error", "coordinate_out_of_range", "Coordinate is outside WGS84 bounds.", row=row_index, taxon=taxon))
                    continue
                if abs(lat) < 1e-12 and abs(lon) < 1e-12:
                    issues.append(SpatialQAIssue("warning", "zero_zero_coordinate", "Coordinate is exactly 0,0; verify that this is not a missing-coordinate placeholder.", row=row_index, taxon=taxon))
                point_key = (taxon, round(lat, 6), round(lon, 6))
                if point_key in seen_points and duplicate_warning_count < duplicate_warning_limit:
                    issues.append(SpatialQAIssue("warning", "duplicate_taxon_coordinate", "Duplicate taxon coordinate rounded to 6 decimals.", row=row_index, taxon=taxon))
                    duplicate_warning_count += 1
                seen_points.add(point_key)
                records.append(
                    OccurrenceRecord(
                        taxon=taxon,
                        latitude=lat,
                        longitude=lon,
                        row_index=row_index,
                        country=self._value_by_alias(clean, ["country"]),
                        locality=self._value_by_alias(clean, ["locality", "location"]),
                        year=self._value_by_alias(clean, ["year"]),
                        source=self._value_by_alias(clean, ["source", "dataset"]),
                        uncertainty_m=self._value_by_alias(clean, ["uncertainty_m", "coordinateuncertaintyinmeters"]),
                        raw=clean,
                    )
                )
                if progress_callback is not None and (done == 1 or done == total_rows or done % progress_step == 0):
                    total = total_rows or done
                    progress_callback(done, total, "Loaded occurrence %d/%d" % (done, total))
        return records, issues

    def import_area_geojson(self, file_path: str, progress_callback=None, cancel_callback=None):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError("GeoJSON file does not exist: %s" % file_path)
        if progress_callback is not None:
            progress_callback(0, 100, "Reading area GeoJSON ...")
        if cancel_callback is not None and cancel_callback():
            raise RuntimeError("Area import cancelled.")
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if progress_callback is not None:
            progress_callback(5, 100, "Parsing area polygons ...")
        if cancel_callback is not None and cancel_callback():
            raise RuntimeError("Area import cancelled.")
        crs = self._geojson_crs(payload)
        features = self._geojson_features(payload)
        if not features:
            raise ValueError("GeoJSON does not contain any polygon features.")

        areas = []
        issues = []
        if self._normalize_crs(crs) not in ("epsg:4326", "crs84", "urn:ogc:def:crs:ogc:1.3:crs84"):
            issues.append(
                SpatialQAIssue(
                    "warning",
                    "non_wgs84_crs",
                    "GeoJSON CRS is '%s'. Phase 1 assumes WGS84 longitude/latitude coordinates." % crs,
                )
            )
        used_codes = set()
        total_features = len(features)
        progress_step = max(1, total_features // 100) if total_features else 1
        for index, feature in enumerate(features, start=1):
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError("Area import cancelled.")
            geometry = dict(feature.get("geometry") or {})
            geometry_type = str(geometry.get("type", "") or "")
            if geometry_type not in ("Polygon", "MultiPolygon"):
                issues.append(SpatialQAIssue("warning", "unsupported_geometry", "Skipped non-polygon feature: %s." % geometry_type, row=index))
                if progress_callback is not None and (index == 1 or index == total_features or index % progress_step == 0):
                    progress_callback(index, total_features, "Parsed area feature %d/%d" % (index, total_features))
                continue
            if not list(self._geometry_points(geometry)):
                issues.append(SpatialQAIssue("error", "empty_geometry", "Skipped empty polygon geometry.", row=index))
                if progress_callback is not None and (index == 1 or index == total_features or index % progress_step == 0):
                    progress_callback(index, total_features, "Parsed area feature %d/%d" % (index, total_features))
                continue
            properties = dict(feature.get("properties") or {})
            area_code = self._area_code_from_feature(feature, properties, index)
            if area_code in used_codes:
                issues.append(SpatialQAIssue("error", "duplicate_area_code", "Duplicate area code: %s." % area_code, row=index))
                if progress_callback is not None and (index == 1 or index == total_features or index % progress_step == 0):
                    progress_callback(index, total_features, "Parsed area feature %d/%d" % (index, total_features))
                continue
            used_codes.add(area_code)
            centroid_lon, centroid_lat = self._geometry_centroid(geometry)
            areas.append(
                AreaSpatialRecord(
                    area_code=area_code,
                    geometry_id=str(feature.get("id", "") or area_code),
                    display_name=str(properties.get("display_name", "") or properties.get("name", "") or area_code),
                    color=str(properties.get("color", "") or ""),
                    group=str(self._value_by_alias(properties, self.AREA_GROUP_FIELDS) or ""),
                    centroid_lon=centroid_lon,
                    centroid_lat=centroid_lat,
                    source=str(path),
                    crs=crs,
                    geometry=geometry,
                    properties=properties,
                )
            )
            if progress_callback is not None and (index == 1 or index == total_features or index % progress_step == 0):
                progress_callback(index, total_features, "Parsed area feature %d/%d" % (index, total_features))
        if not areas:
            raise ValueError("GeoJSON did not yield any usable polygon or multipolygon areas.")
        if progress_callback is not None:
            progress_callback(total_features, total_features, "Area GeoJSON parsed")
        return areas, issues

    def build_project(self, occurrences=None, areas=None, occurrence_source_path="", area_source_path="", qa_issues=None):
        return SpatialDataProject(
            occurrences=list(occurrences or []),
            areas=list(areas or []),
            occurrence_source_path=str(occurrence_source_path or ""),
            area_source_path=str(area_source_path or ""),
            qa_issues=list(qa_issues or []),
        )

    def validate_area_mapping(self, areas):
        issues = []
        seen = set()
        for index, area in enumerate(list(areas or []), start=1):
            code = str(getattr(area, "area_code", "") or "").strip()
            if not code:
                issues.append(SpatialQAIssue("error", "empty_area_code", "Area code cannot be empty.", row=index))
                continue
            if code in seen:
                issues.append(SpatialQAIssue("error", "duplicate_area_code", "Duplicate area code: %s." % code, row=index))
            seen.add(code)
            color = str(getattr(area, "color", "") or "").strip()
            if color and not self._is_valid_color(color):
                issues.append(SpatialQAIssue("warning", "invalid_area_color", "Area color should be a #RRGGBB value: %s." % color, row=index))
        return issues

    def read_area_mapping_csv(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError("Area mapping file does not exist: %s" % file_path)
        delimiter = self._detect_delimiter(path)
        rows = []
        issues = []
        seen = set()
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise ValueError("Area mapping file has no header row.")
            field_map = self._build_field_map(reader.fieldnames)
            code_field = self._find_field(field_map, self.AREA_CODE_FIELDS)
            if not code_field:
                raise ValueError("Area mapping file must contain an area_code/area/code/id/name/label column.")
            display_field = self._find_field(field_map, ["display_name", "display", "name", "label"])
            color_field = self._find_field(field_map, ["color", "colour", "hex", "hex_color"])
            group_field = self._find_field(field_map, self.AREA_GROUP_FIELDS)
            for row_index, row in enumerate(reader, start=2):
                clean = dict((str(k or "").strip(), str(v or "").strip()) for k, v in dict(row or {}).items())
                area_code = clean.get(code_field, "").strip()
                if not area_code:
                    issues.append(SpatialQAIssue("error", "empty_area_code", "Area metadata row has empty area code.", row=row_index))
                    continue
                if area_code in seen:
                    issues.append(SpatialQAIssue("error", "duplicate_area_code", "Duplicate area metadata code: %s." % area_code, row=row_index))
                    continue
                seen.add(area_code)
                color = clean.get(color_field, "").strip() if color_field else ""
                if color and not self._is_valid_color(color):
                    issues.append(SpatialQAIssue("warning", "invalid_area_color", "Area color is not a valid #RRGGBB value: %s." % color, row=row_index))
                rows.append({
                    "area_code": area_code,
                    "display_name": clean.get(display_field, "").strip() if display_field else "",
                    "color": color,
                    "group": clean.get(group_field, "").strip() if group_field else "",
                })
        return rows, issues

    def apply_area_metadata(self, areas, metadata_rows):
        area_list = list(areas or [])
        row_list = list(metadata_rows or [])
        by_code = dict((str(area.area_code), area) for area in area_list)
        updated = 0
        missing = []
        metadata_codes = set()
        for row in row_list:
            code = str(row.get("area_code", "") or "").strip()
            if code:
                metadata_codes.add(code)
            area = by_code.get(code)
            if area is None:
                missing.append(code)
                continue
            display_name = str(row.get("display_name", "") or "").strip()
            color = str(row.get("color", "") or "").strip()
            group = str(row.get("group", "") or "").strip()
            if display_name:
                area.display_name = display_name
            if color:
                area.color = color
            if group:
                area.group = group
            updated += 1
        not_in_metadata = [
            str(area.area_code)
            for area in area_list
            if str(area.area_code) not in metadata_codes
        ]
        return {
            "updated": updated,
            "metadata_without_area": sorted(missing),
            "areas_without_metadata": sorted(not_in_metadata),
        }

    def assign_default_area_colors(self, areas, overwrite=False):
        area_list = list(areas or [])
        for index, area in enumerate(area_list):
            if overwrite or not str(getattr(area, "color", "") or "").strip():
                area.color = self.AREA_COLOR_PALETTE[index % len(self.AREA_COLOR_PALETTE)]
        return len(area_list)

    def encode_occurrences_to_matrix(
        self,
        occurrences,
        areas,
        min_records_per_taxon_area=1,
        source_path="spatial://encoded_occurrences",
        progress_callback=None,
        cancel_callback=None,
    ):
        occurrence_list = list(occurrences or [])
        area_list = list(areas or [])
        threshold = max(1, int(min_records_per_taxon_area or 1))
        if not occurrence_list:
            raise ValueError("No occurrences have been loaded.")
        if not area_list:
            raise ValueError("No area polygons have been loaded.")
        area_issues = [issue for issue in self.validate_area_mapping(area_list) if issue.level == "error"]
        if area_issues:
            raise ValueError("; ".join(issue.message for issue in area_issues[:5]))

        area_codes = [area.area_code for area in area_list]
        prepared_areas = [
            (area, self._prepare_geometry_for_point_lookup(area.geometry))
            for area in area_list
        ]
        counts = defaultdict(lambda: defaultdict(int))
        audit_rows = []
        total = len(occurrence_list)
        progress_step = max(1, total // 100) if total else 1
        for index, occurrence in enumerate(occurrence_list, start=1):
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError("Encoding was cancelled.")
            matched = []
            lon = float(occurrence.longitude)
            lat = float(occurrence.latitude)
            for area, prepared_geometry in prepared_areas:
                if self._point_in_prepared_geometry(lon, lat, prepared_geometry):
                    matched.append(area.area_code)
                    counts[occurrence.taxon][area.area_code] += 1
            status = "matched" if matched else "unmatched"
            if len(matched) > 1:
                status = "multi_area"
            audit_rows.append(
                EncodedOccurrenceAuditRow(
                    row_index=int(occurrence.row_index),
                    taxon=occurrence.taxon,
                    longitude=float(occurrence.longitude),
                    latitude=float(occurrence.latitude),
                    matched_areas=matched,
                    status=status,
                )
            )
            if progress_callback is not None and (index == 1 or index == total or index % progress_step == 0):
                progress_callback(index, total, "Encoded occurrence %d/%d" % (index, total))

        taxa = sorted(counts.keys())
        for occurrence in occurrence_list:
            if occurrence.taxon not in taxa:
                taxa.append(occurrence.taxon)
        rows = []
        ids = []
        for index, taxon in enumerate(sorted(taxa), start=1):
            row = {"ID": str(index), "Name": taxon}
            for area_code in area_codes:
                row[area_code] = "1" if int(counts[taxon].get(area_code, 0)) >= threshold else "0"
            rows.append(row)
            ids.append(str(index))

        matrix = StateMatrix(
            ids=ids,
            taxa_names=[row["Name"] for row in rows],
            state_columns=area_codes,
            rows=rows,
            source_path=str(source_path or "spatial://encoded_occurrences"),
        )
        return matrix, audit_rows

    def build_encoding_diagnostics(self, occurrences=None, areas=None, matrix=None, audit_rows=None):
        occurrence_list = list(occurrences or [])
        area_list = list(areas or [])
        audit_list = list(audit_rows or [])
        status_counts = defaultdict(int)
        area_occurrence_counts = defaultdict(int)
        area_taxa = defaultdict(set)
        taxon_statuses = defaultdict(lambda: defaultdict(int))
        taxon_areas = defaultdict(set)

        for audit in audit_list:
            taxon = str(getattr(audit, "taxon", "") or "")
            status = str(getattr(audit, "status", "") or "")
            if status:
                status_counts[status] += 1
                taxon_statuses[taxon][status] += 1
            for area in list(getattr(audit, "matched_areas", []) or []):
                area_name = str(area or "")
                if not area_name:
                    continue
                area_occurrence_counts[area_name] += 1
                area_taxa[area_name].add(taxon)
                taxon_areas[taxon].add(area_name)

        all_area_codes = [
            str(getattr(area, "area_code", "") or "")
            for area in area_list
            if str(getattr(area, "area_code", "") or "")
        ]
        if matrix is not None:
            all_area_codes = [
                str(col or "")
                for col in list(getattr(matrix, "state_columns", []) or [])
                if str(col or "")
            ] or all_area_codes

        empty_areas = [area for area in all_area_codes if int(area_occurrence_counts.get(area, 0)) == 0]
        taxa_all_outside = []
        taxa_multi_area_points = []
        for taxon, statuses in taxon_statuses.items():
            total = sum(int(value) for value in statuses.values())
            if total and int(statuses.get("unmatched", 0)) == total:
                taxa_all_outside.append(taxon)
            if int(statuses.get("multi_area", 0)) > 0:
                taxa_multi_area_points.append(taxon)

        matrix_empty_range_taxa = []
        threshold_filtered_taxa = []
        if matrix is not None:
            columns = [
                str(col or "")
                for col in list(getattr(matrix, "state_columns", []) or [])
                if str(col or "")
            ]
            for row in list(getattr(matrix, "rows", []) or []):
                taxon = str(row.get("Name", "") or "")
                bits = [str(row.get(column, "") or "") for column in columns]
                if columns and "1" not in bits:
                    matrix_empty_range_taxa.append(taxon)
                    if taxon_areas.get(taxon):
                        threshold_filtered_taxa.append(taxon)

        return {
            "occurrence_count": len(occurrence_list),
            "unique_occurrence_taxa": len(set(str(getattr(row, "taxon", "") or "") for row in occurrence_list if str(getattr(row, "taxon", "") or ""))),
            "area_count": len(all_area_codes),
            "audit_count": len(audit_list),
            "status_counts": dict(status_counts),
            "area_occurrence_counts": dict((area, int(area_occurrence_counts.get(area, 0))) for area in all_area_codes),
            "area_taxon_counts": dict((area, len(area_taxa.get(area, set()))) for area in all_area_codes),
            "empty_areas": sorted(empty_areas),
            "taxa_all_outside_polygons": sorted(taxa_all_outside),
            "taxa_with_multi_area_points": sorted(taxa_multi_area_points),
            "matrix_empty_range_taxa": sorted(matrix_empty_range_taxa),
            "threshold_filtered_empty_taxa": sorted(threshold_filtered_taxa),
        }

    def write_state_matrix_csv(self, matrix, file_path: str):
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = ["ID", "Name"] + list(getattr(matrix, "state_columns", []) or [])
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in list(getattr(matrix, "rows", []) or []):
                writer.writerow(dict((header, row.get(header, "")) for header in headers))
        return path

    def write_area_mapping_csv(self, areas, file_path: str):
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = [
            "area_code",
            "geometry_id",
            "display_name",
            "color",
            "group",
            "centroid_lon",
            "centroid_lat",
            "source",
            "crs",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for area in list(areas or []):
                writer.writerow({
                    "area_code": area.area_code,
                    "geometry_id": area.geometry_id,
                    "display_name": area.display_name,
                    "color": area.color,
                    "group": getattr(area, "group", ""),
                    "centroid_lon": "" if area.centroid_lon is None else area.centroid_lon,
                    "centroid_lat": "" if area.centroid_lat is None else area.centroid_lat,
                    "source": area.source,
                    "crs": area.crs,
                })
        return path

    def build_taxon_matching_rows(self, tree_taxa=None, matrix_taxa=None, occurrence_taxa=None):
        tree_set = set(str(x) for x in list(tree_taxa or []) if str(x).strip())
        matrix_set = set(str(x) for x in list(matrix_taxa or []) if str(x).strip())
        occurrence_set = set(str(x) for x in list(occurrence_taxa or []) if str(x).strip())
        names = sorted(tree_set | matrix_set | occurrence_set)
        return [
            {
                "taxon": name,
                "in_tree": "1" if name in tree_set else "0",
                "in_active_matrix": "1" if name in matrix_set else "0",
                "in_occurrences": "1" if name in occurrence_set else "0",
            }
            for name in names
        ]

    def write_taxon_matching_csv(self, tree_taxa, matrix_taxa, occurrence_taxa, file_path: str):
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = ["taxon", "in_tree", "in_active_matrix", "in_occurrences"]
        rows = self.build_taxon_matching_rows(tree_taxa, matrix_taxa, occurrence_taxa)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def build_taxon_mapping_rows(self, tree_taxa=None, matrix_taxa=None, occurrence_taxa=None, mode=TaxonMatchService.MATCH_NORMALIZED_PREFIX):
        matcher = TaxonMatchService()
        tree_names = matcher.unique_names(tree_taxa)
        matrix_names = matcher.unique_names(matrix_taxa)
        occurrence_names = matcher.unique_names(occurrence_taxa)

        if matrix_names:
            target_names = matrix_names
            target_type = "active_matrix"
        elif tree_names:
            target_names = tree_names
            target_type = "tree"
        else:
            target_names = occurrence_names
            target_type = "occurrences"

        rows = []
        for source_type, names in [
            ("tree", tree_names),
            ("active_matrix", matrix_names),
            ("occurrences", occurrence_names),
        ]:
            rows.extend(
                matcher.build_mapping_rows(
                    source_taxa=names,
                    target_taxa=target_names,
                    source_type=source_type,
                    target_type=target_type,
                    mode=mode,
                )
            )
        return rows

    def write_taxon_mapping_csv(self, tree_taxa, matrix_taxa, occurrence_taxa, file_path: str, mode=TaxonMatchService.MATCH_NORMALIZED_PREFIX):
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = [
            "source_type",
            "source_taxon",
            "target_type",
            "matched_taxon",
            "match_status",
            "match_rule",
            "candidates",
        ]
        rows = self.build_taxon_mapping_rows(tree_taxa, matrix_taxa, occurrence_taxa, mode=mode)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict((header, row.get(header, "")) for header in headers))
        return path

    def write_encoding_audit_csv(self, audit_rows, file_path: str):
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = ["row_index", "taxon", "longitude", "latitude", "matched_areas", "status", "coordinate_status"]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in list(audit_rows or []):
                status = str(row.status or "")
                writer.writerow({
                    "row_index": row.row_index,
                    "taxon": row.taxon,
                    "longitude": row.longitude,
                    "latitude": row.latitude,
                    "matched_areas": ",".join(list(row.matched_areas or [])),
                    "status": status,
                    "coordinate_status": self._coordinate_status_label(status),
                })
        return path

    def save_project_json(self, project, file_path: str):
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.project_to_dict(project), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def load_project_json(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError("Spatial project file does not exist: %s" % file_path)
        return self.project_from_dict(json.loads(path.read_text(encoding="utf-8-sig")))

    def project_to_dict(self, project):
        matrix = getattr(project, "encoded_matrix", None)
        matrix_payload = None
        if matrix is not None:
            matrix_payload = {
                "ids": list(getattr(matrix, "ids", []) or []),
                "taxa_names": list(getattr(matrix, "taxa_names", []) or []),
                "state_columns": list(getattr(matrix, "state_columns", []) or []),
                "rows": [dict(row) for row in list(getattr(matrix, "rows", []) or [])],
                "source_path": str(getattr(matrix, "source_path", "") or ""),
            }
        return {
            "format": self.PROJECT_FORMAT,
            "version": self.PROJECT_VERSION,
            "occurrence_source_path": str(getattr(project, "occurrence_source_path", "") or ""),
            "area_source_path": str(getattr(project, "area_source_path", "") or ""),
            "occurrences": [self._occurrence_to_dict(row) for row in list(getattr(project, "occurrences", []) or [])],
            "areas": [self._area_to_dict(row) for row in list(getattr(project, "areas", []) or [])],
            "qa_issues": [self._issue_to_dict(row) for row in list(getattr(project, "qa_issues", []) or [])],
            "encoded_matrix": matrix_payload,
            "encoded_audit_rows": [self._audit_to_dict(row) for row in list(getattr(project, "encoded_audit_rows", []) or [])],
        }

    def project_from_dict(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Spatial project JSON must contain an object.")
        fmt = str(payload.get("format", "") or "")
        if fmt and fmt != self.PROJECT_FORMAT:
            raise ValueError("Unsupported spatial project format: %s" % fmt)
        matrix_payload = payload.get("encoded_matrix")
        matrix = None
        if isinstance(matrix_payload, dict):
            matrix = StateMatrix(
                ids=[str(x) for x in list(matrix_payload.get("ids", []) or [])],
                taxa_names=[str(x) for x in list(matrix_payload.get("taxa_names", []) or [])],
                state_columns=[str(x) for x in list(matrix_payload.get("state_columns", []) or [])],
                rows=[dict(row) for row in list(matrix_payload.get("rows", []) or []) if isinstance(row, dict)],
                source_path=str(matrix_payload.get("source_path", "") or ""),
            )
        return SpatialDataProject(
            occurrences=[self._occurrence_from_dict(row) for row in list(payload.get("occurrences", []) or []) if isinstance(row, dict)],
            areas=[self._area_from_dict(row) for row in list(payload.get("areas", []) or []) if isinstance(row, dict)],
            occurrence_source_path=str(payload.get("occurrence_source_path", "") or ""),
            area_source_path=str(payload.get("area_source_path", "") or ""),
            qa_issues=[self._issue_from_dict(row) for row in list(payload.get("qa_issues", []) or []) if isinstance(row, dict)],
            encoded_matrix=matrix,
            encoded_audit_rows=[self._audit_from_dict(row) for row in list(payload.get("encoded_audit_rows", []) or []) if isinstance(row, dict)],
        )

    def summarize_taxon_matching(self, tree_taxa=None, matrix_taxa=None, occurrence_taxa=None):
        tree_set = set(str(x) for x in list(tree_taxa or []) if str(x).strip())
        matrix_set = set(str(x) for x in list(matrix_taxa or []) if str(x).strip())
        occurrence_set = set(str(x) for x in list(occurrence_taxa or []) if str(x).strip())
        all_sets = [s for s in [tree_set, matrix_set, occurrence_set] if s]
        matched_all = set.intersection(*all_sets) if all_sets else set()
        return {
            "tree_count": len(tree_set),
            "matrix_count": len(matrix_set),
            "occurrence_count": len(occurrence_set),
            "matched_all": sorted(matched_all),
            "only_tree": sorted(tree_set - matrix_set - occurrence_set),
            "only_matrix": sorted(matrix_set - tree_set - occurrence_set),
            "only_occurrence": sorted(occurrence_set - tree_set - matrix_set),
            "tree_not_occurrence": sorted(tree_set - occurrence_set) if occurrence_set else [],
            "occurrence_not_tree": sorted(occurrence_set - tree_set) if tree_set else [],
        }

    def summarize_taxon_mapping(self, tree_taxa=None, matrix_taxa=None, occurrence_taxa=None, mode=TaxonMatchService.MATCH_NORMALIZED_PREFIX):
        matcher = TaxonMatchService()
        tree_names = matcher.unique_names(tree_taxa)
        matrix_names = matcher.unique_names(matrix_taxa)
        occurrence_names = matcher.unique_names(occurrence_taxa)
        rows = self.build_taxon_mapping_rows(
            tree_taxa=tree_names,
            matrix_taxa=matrix_names,
            occurrence_taxa=occurrence_names,
            mode=mode,
        )
        target_source = rows[0]["target_type"] if rows else ("active_matrix" if matrix_names else ("tree" if tree_names else "occurrences"))
        status_counts = matcher.count_statuses(rows)

        def source_rows(source_type):
            return [row for row in rows if row.get("source_type") == source_type]

        def matched(rows_for_source):
            return [row for row in rows_for_source if row.get("match_status") in TaxonMatchService.MATCHED_STATUSES]

        def with_status(rows_for_source, status):
            return [row for row in rows_for_source if row.get("match_status") == status]

        tree_rows = source_rows("tree")
        matrix_rows = source_rows("active_matrix")
        occurrence_rows = source_rows("occurrences")
        return {
            "mode": mode,
            "target_source": target_source,
            "tree_count": len(tree_names),
            "matrix_count": len(matrix_names),
            "occurrence_count": len(occurrence_names),
            "rows": rows,
            "status_counts": status_counts,
            "tree_matched_to_target": len(matched(tree_rows)),
            "matrix_matched_to_target": len(matched(matrix_rows)),
            "occurrence_matched_to_target": len(matched(occurrence_rows)),
            "tree_unmatched": with_status(tree_rows, "unmatched"),
            "tree_ambiguous": with_status(tree_rows, "ambiguous"),
            "occurrence_unmatched": with_status(occurrence_rows, "unmatched"),
            "occurrence_ambiguous": with_status(occurrence_rows, "ambiguous"),
            "matrix_unmatched": with_status(matrix_rows, "unmatched"),
            "matrix_ambiguous": with_status(matrix_rows, "ambiguous"),
        }

    def _detect_delimiter(self, path: Path) -> str:
        sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:4096]
        if "\t" in sample and sample.count("\t") >= sample.count(","):
            return "\t"
        return ","

    def _count_data_rows(self, path: Path) -> int:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            total_lines = sum(1 for _line in handle)
        return max(0, total_lines - 1)

    def _build_field_map(self, fieldnames):
        return dict((self._normalize_field(name), str(name or "").strip()) for name in list(fieldnames or []))

    def _find_field(self, field_map, aliases):
        for alias in aliases:
            hit = field_map.get(self._normalize_field(alias))
            if hit:
                return hit
        return ""

    def _value_by_alias(self, row, aliases):
        field_map = self._build_field_map(row.keys())
        field = self._find_field(field_map, aliases)
        return row.get(field, "") if field else ""

    def _coordinate_status_label(self, status):
        value = str(status or "").strip()
        if value == "unmatched":
            return "outside_all_polygons"
        if value == "matched":
            return "inside_one_polygon"
        if value == "multi_area":
            return "inside_multiple_polygons"
        return value or "unknown"

    def _normalize_field(self, value):
        return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch == "_")

    def _normalize_crs(self, value):
        return str(value or "").strip().lower()

    def _is_valid_color(self, value):
        text = str(value or "").strip()
        if not text:
            return True
        if len(text) != 7 or not text.startswith("#"):
            return False
        try:
            int(text[1:], 16)
            return True
        except Exception:
            return False

    def _geojson_features(self, payload):
        if not isinstance(payload, dict):
            return []
        if payload.get("type") == "FeatureCollection":
            return list(payload.get("features", []) or [])
        if payload.get("type") == "Feature":
            return [payload]
        if payload.get("type") in ("Polygon", "MultiPolygon"):
            return [{"type": "Feature", "properties": {}, "geometry": payload}]
        return []

    def _geojson_crs(self, payload):
        crs = payload.get("crs") if isinstance(payload, dict) else None
        if isinstance(crs, dict):
            props = crs.get("properties") or {}
            name = props.get("name")
            if name:
                return str(name)
        return "EPSG:4326"

    def _area_code_from_feature(self, feature, properties, index):
        field_map = self._build_field_map(properties.keys())
        field = self._find_field(field_map, self.AREA_CODE_FIELDS)
        if field:
            value = str(properties.get(field, "") or "").strip()
            if value:
                return value
        feature_id = str(feature.get("id", "") or "").strip()
        if feature_id:
            return feature_id
        return "Area%d" % int(index)

    def _geometry_centroid(self, geometry):
        points = list(self._geometry_points(geometry))
        if not points:
            return None, None
        lon = sum(point[0] for point in points) / float(len(points))
        lat = sum(point[1] for point in points) / float(len(points))
        return lon, lat

    def _geometry_points(self, geometry):
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon":
            polygons = [coordinates]
        elif geometry_type == "MultiPolygon":
            polygons = coordinates
        else:
            polygons = []
        for polygon in polygons:
            for ring in list(polygon or []):
                for point in list(ring or []):
                    if len(point) >= 2:
                        yield float(point[0]), float(point[1])

    def _point_in_geometry(self, lon, lat, geometry):
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon":
            return self._point_in_polygon(lon, lat, coordinates)
        if geometry_type == "MultiPolygon":
            return any(self._point_in_polygon(lon, lat, polygon) for polygon in list(coordinates or []))
        return False

    def _prepare_geometry_for_point_lookup(self, geometry):
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon":
            polygons = [coordinates]
        elif geometry_type == "MultiPolygon":
            polygons = list(coordinates or [])
        else:
            polygons = []

        prepared_polygons = []
        area_bbox = None
        for polygon in polygons:
            bbox = self._polygon_bbox(polygon)
            if bbox is None:
                continue
            prepared_polygons.append({
                "bbox": bbox,
                "polygon": polygon,
            })
            area_bbox = self._merge_bbox(area_bbox, bbox)
        return {
            "bbox": area_bbox,
            "polygons": prepared_polygons,
        }

    def _point_in_prepared_geometry(self, lon, lat, prepared_geometry):
        if not prepared_geometry:
            return False
        bbox = prepared_geometry.get("bbox")
        if not self._bbox_contains(bbox, lon, lat):
            return False
        for prepared_polygon in list(prepared_geometry.get("polygons") or []):
            if not self._bbox_contains(prepared_polygon.get("bbox"), lon, lat):
                continue
            if self._point_in_polygon(lon, lat, prepared_polygon.get("polygon") or []):
                return True
        return False

    def _polygon_bbox(self, polygon):
        min_lon = None
        min_lat = None
        max_lon = None
        max_lat = None
        for ring in list(polygon or []):
            for point in list(ring or []):
                if len(point) < 2:
                    continue
                lon = float(point[0])
                lat = float(point[1])
                min_lon = lon if min_lon is None else min(min_lon, lon)
                max_lon = lon if max_lon is None else max(max_lon, lon)
                min_lat = lat if min_lat is None else min(min_lat, lat)
                max_lat = lat if max_lat is None else max(max_lat, lat)
        if min_lon is None:
            return None
        return (min_lon, min_lat, max_lon, max_lat)

    def _merge_bbox(self, bbox_a, bbox_b):
        if bbox_a is None:
            return bbox_b
        if bbox_b is None:
            return bbox_a
        return (
            min(float(bbox_a[0]), float(bbox_b[0])),
            min(float(bbox_a[1]), float(bbox_b[1])),
            max(float(bbox_a[2]), float(bbox_b[2])),
            max(float(bbox_a[3]), float(bbox_b[3])),
        )

    def _bbox_contains(self, bbox, lon, lat):
        if bbox is None:
            return False
        x = float(lon)
        y = float(lat)
        return (
            float(bbox[0]) <= x <= float(bbox[2])
            and float(bbox[1]) <= y <= float(bbox[3])
        )

    def _point_in_polygon(self, lon, lat, polygon):
        rings = list(polygon or [])
        if not rings:
            return False
        if not self._point_in_ring(lon, lat, rings[0]):
            return False
        for hole in rings[1:]:
            if self._point_in_ring(lon, lat, hole):
                return False
        return True

    def _point_in_ring(self, lon, lat, ring):
        points = [(float(p[0]), float(p[1])) for p in list(ring or []) if len(p) >= 2]
        if len(points) < 3:
            return False
        inside = False
        x = float(lon)
        y = float(lat)
        j = len(points) - 1
        for i in range(len(points)):
            xi, yi = points[i]
            xj, yj = points[j]
            intersects = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-300) + xi
            )
            if intersects:
                inside = not inside
            j = i
        return inside

    def _occurrence_to_dict(self, record):
        return {
            "taxon": record.taxon,
            "latitude": record.latitude,
            "longitude": record.longitude,
            "row_index": record.row_index,
            "country": record.country,
            "locality": record.locality,
            "year": record.year,
            "source": record.source,
            "uncertainty_m": record.uncertainty_m,
            "raw": dict(record.raw or {}),
        }

    def _occurrence_from_dict(self, data):
        return OccurrenceRecord(
            taxon=str(data.get("taxon", "") or ""),
            latitude=float(data.get("latitude", 0.0) or 0.0),
            longitude=float(data.get("longitude", 0.0) or 0.0),
            row_index=int(data.get("row_index", 0) or 0),
            country=str(data.get("country", "") or ""),
            locality=str(data.get("locality", "") or ""),
            year=str(data.get("year", "") or ""),
            source=str(data.get("source", "") or ""),
            uncertainty_m=str(data.get("uncertainty_m", "") or ""),
            raw=dict(data.get("raw", {}) or {}),
        )

    def _area_to_dict(self, record):
        return {
            "area_code": record.area_code,
            "geometry_id": record.geometry_id,
            "display_name": record.display_name,
            "color": record.color,
            "group": getattr(record, "group", ""),
            "centroid_lon": record.centroid_lon,
            "centroid_lat": record.centroid_lat,
            "source": record.source,
            "crs": record.crs,
            "geometry": dict(record.geometry or {}),
            "properties": dict(record.properties or {}),
        }

    def _area_from_dict(self, data):
        lon = data.get("centroid_lon")
        lat = data.get("centroid_lat")
        return AreaSpatialRecord(
            area_code=str(data.get("area_code", "") or ""),
            geometry_id=str(data.get("geometry_id", "") or ""),
            display_name=str(data.get("display_name", "") or ""),
            color=str(data.get("color", "") or ""),
            group=str(data.get("group", "") or ""),
            centroid_lon=None if lon is None or lon == "" else float(lon),
            centroid_lat=None if lat is None or lat == "" else float(lat),
            source=str(data.get("source", "") or ""),
            crs=str(data.get("crs", "EPSG:4326") or "EPSG:4326"),
            geometry=dict(data.get("geometry", {}) or {}),
            properties=dict(data.get("properties", {}) or {}),
        )

    def _issue_to_dict(self, issue):
        return {
            "level": issue.level,
            "code": issue.code,
            "message": issue.message,
            "row": issue.row,
            "taxon": issue.taxon,
        }

    def _issue_from_dict(self, data):
        row = data.get("row")
        return SpatialQAIssue(
            level=str(data.get("level", "") or ""),
            code=str(data.get("code", "") or ""),
            message=str(data.get("message", "") or ""),
            row=None if row is None or row == "" else int(row),
            taxon=str(data.get("taxon", "") or ""),
        )

    def _audit_to_dict(self, row):
        return {
            "row_index": row.row_index,
            "taxon": row.taxon,
            "longitude": row.longitude,
            "latitude": row.latitude,
            "matched_areas": list(row.matched_areas or []),
            "status": row.status,
        }

    def _audit_from_dict(self, data):
        return EncodedOccurrenceAuditRow(
            row_index=int(data.get("row_index", 0) or 0),
            taxon=str(data.get("taxon", "") or ""),
            longitude=float(data.get("longitude", 0.0) or 0.0),
            latitude=float(data.get("latitude", 0.0) or 0.0),
            matched_areas=[str(x) for x in list(data.get("matched_areas", []) or [])],
            status=str(data.get("status", "unmatched") or "unmatched"),
        )
