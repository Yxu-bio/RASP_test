# Phase 1 reference data collected from discussed literature

This folder contains lightweight reference datasets for manual testing of RASP5 Phase 1 spatial-data workflows. Large archives are not fully downloaded unless noted.

## Ready-to-test Phase 1 files

### 1. Ponerinae ants, Dore et al. 2025
Source repository: https://github.com/MaelDore/Ponerinae_Historical_Biogeography
Article: https://www.nature.com/articles/s41467-025-63709-3

Files:
- `Dore_2025_Ponerinae/ponerinae_occurrences_subset_1000.csv`
  - Direct input for Spatial Data Manager -> Load Occurrences CSV.
  - Columns: taxon, latitude, longitude, country, source, occurrence_id, country_code, status.
- `Dore_2025_Ponerinae/ponerinae_occurrences_subset_5000.csv`
  - Larger stress-test subset.
- `Dore_2025_Ponerinae/ponerinae_occurrences_full_149k.csv`
  - Full extracted occurrence CSV from `Biogeographic_database_Ponerinae_cleaned.xlsx`.
  - Service benchmark after bounding-box prefilter optimization: 149,541 occurrence points against 180 country polygons encoded in about 18.1 seconds on the current test machine.
- `general_world_polygons/world_countries_simplified.geojson`
  - Direct input for Spatial Data Manager -> Load Area GeoJSON.
  - Simplified country polygons from https://github.com/johan/world.geo.json.
  - Area codes will be country names because the GeoJSON exposes `properties.name`.
- `Dore_2025_Ponerinae/taxa_bioregions_7areas_matrix.csv`
  - Direct input for RASP matrix import, not Spatial Data Manager occurrence encoding.
  - Useful to test tree/matrix taxon matching and downstream reconstruction methods.
- `Dore_2025_Ponerinae/taxa_bioregions_7areas_area_mapping.csv`
  - Label/color metadata for the seven bioregions in the paper. This does not contain polygons.
- `Dore_2025_Ponerinae/Ponerinae_MCC_phylogeny_789t.tree`
  - Reference tree from the same repository.
- Service smoke and full-data benchmark outputs are intentionally written under `runs/` and are not committed.

Suggested manual test:
1. Open `Spatial Data -> Spatial Data Manager`.
2. Load `Dore_2025_Ponerinae/ponerinae_occurrences_subset_1000.csv`.
3. Load `general_world_polygons/world_countries_simplified.geojson`.
4. Encode Matrix with min records = 1.
5. Inspect Encoding audit for matched/multi_area/unmatched rows.
6. Export encoded matrix, audit, and taxon matching report.

### 2. Kawahara et al. 2023 butterflies
Article: https://www.nature.com/articles/s41559-023-02041-9
Figshare dataset: https://springernature.figshare.com/articles/dataset/A_global_phylogeny_of_butterflies_reveals_their_evolutionary_history_ancestral_host_plants_and_biogeographic_origins/21774899

Files:
- `Kawahara_2023_figshare/Tables.S1-S52.xlsx`
  - Original downloaded supplementary table workbook.
- `Kawahara_2023_figshare/kawahara_butterfly_country_records_S5.csv`
  - Extracted from Table S5: TipName, Species, Country_ISO3.
  - This is country-level range evidence, not lat/lon occurrence input. Use it as a reference for later country-to-area mapping logic.

Not downloaded by default:
- `Data_S1-S28.zip` is about 1.4 GB. Download from Figshare only if needed.

### 3. Butterfly phyloregionalization, Dryad
Dryad dataset: https://datadryad.org/dataset/doi:10.5061/dryad.w3r2280zf

Not downloaded by default:
- `Butterfly_Phyloregionalization.zip` is about 4.48 GB. It likely contains the full regionalization GIS outputs, but it is too large for routine development pulls.
- Dryad's file download endpoint returned authorization/forbidden responses during this collection pass, so no local Dryad files are included yet.

## Notes

- Phase 1 currently supports CSV/TSV occurrences with taxon/latitude/longitude and GeoJSON Polygon/MultiPolygon areas.
- The Dore occurrence + simplified country GeoJSON pair is the most direct manual test for point-in-polygon encoding.
- The Dore 7-region matrix is better for validating regular RASP reconstruction inputs, not coordinate-to-area encoding.
- Kawahara S5 is country-range evidence; it is useful for designing future country-code-to-polygon or country-code-to-bioregion workflows.
