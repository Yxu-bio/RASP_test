# Spatial and literature reference data

This document records the provenance and intended use of the literature-derived
datasets under `data/`. The canonical directory layout is described in
`data/README.md`. Large archives are not fully downloaded unless noted.

## Ready-to-test Phase 1 files

### 1. Ponerinae ants, Dore et al. 2025
Source repository: https://github.com/MaelDore/Ponerinae_Historical_Biogeography
Article: https://www.nature.com/articles/s41467-025-63709-3

Files:
- `benchmarks/dore_ponerinae/ponerinae_occurrences_subset_1000.csv`
  - Direct input for Spatial Data Manager -> Load Occurrences CSV.
  - Columns: taxon, latitude, longitude, country, source, occurrence_id, country_code, status.
- `benchmarks/dore_ponerinae/ponerinae_occurrences_subset_5000.csv`
  - Larger stress-test subset.
- `benchmarks/dore_ponerinae/ponerinae_occurrences_full_149k.csv`
  - Full extracted occurrence CSV from `Biogeographic_database_Ponerinae_cleaned.xlsx`.
  - The benchmark script records import, encoding and export timings for the
    current machine and commit; no fixed runtime is claimed in this catalog.
- `spatial/base_layers/world_countries_simplified.geojson`
  - Direct input for Spatial Data Manager -> Load Area GeoJSON.
  - Simplified country polygons from https://github.com/johan/world.geo.json.
  - Area codes will be country names because the GeoJSON exposes `properties.name`.
- `benchmarks/dore_ponerinae/Ponerinae_7_bioregions.geojson`
  - Direct input for Spatial Data Manager -> Load Area GeoJSON when testing the
    seven Dore et al. Ponerinae bioregions.
  - This is an approximate rule-based reference asset, not an official
    author-provided polygon boundary dataset.
  - Area codes match the reconstruction matrix columns: Afrotropics,
    Australasia, Indomalaya, Nearctic, Neotropics, Eastern Palearctic, and
    Western Palearctic.
  - Built from Dore's `Countries_NE_sf_metadata.xlsx` and Natural Earth map
    subunits/admin1 polygons. Cross-region cases follow the Dore curation
    script where possible: Indonesia longitude 125.5, Mexico latitude 22,
    China latitude 33, Russia/India/Pakistan admin1 splits, and selected
    overseas subunits.
  - Use it for RASP spatial workflow testing and study-specific approximate
    coding. Do not present it as the paper's true bioregion boundary map.
  - Build notes are written to
    `benchmarks/dore_ponerinae/Ponerinae_7_bioregions_build_notes.csv`.
- `tools/build_ponerinae_bioregions_geojson.py`
  - Rebuilds `Ponerinae_7_bioregions.geojson` from online source data.
  - This is a reference-data builder; it is not required at application runtime.
- `tools/build_region_geojson.py`
  - Generic config-driven builder for study-specific region GeoJSON files.
  - Combines a base GeoJSON, a mapping CSV, and optional split/override rules
    into one `MultiPolygon` feature per analysis area.
  - See `fixtures/region_builder/` for a minimal demo plus Dore and Kawahara
    literature-derived rule templates.
- `benchmarks/dore_ponerinae/taxa_bioregions_7areas_matrix.csv`
  - Direct input for RASP matrix import, not Spatial Data Manager occurrence encoding.
  - Useful to test tree/matrix taxon matching and downstream reconstruction methods.
- `benchmarks/dore_ponerinae/taxa_bioregions_7areas_area_mapping.csv`
  - Label/color metadata for the seven bioregions in the paper. This does not contain polygons.
- `benchmarks/dore_ponerinae/Ponerinae_MCC_phylogeny_789t.tree`
  - Reference tree from the same repository.
- Service smoke and full-data benchmark outputs are intentionally written under `runs/` and are not committed.

Suggested manual test:
1. Open `Spatial Data -> Spatial Data Manager`.
2. Load `data/benchmarks/dore_ponerinae/ponerinae_occurrences_subset_1000.csv`.
3. Load `data/spatial/base_layers/world_countries_simplified.geojson`.
4. Encode Matrix with min records = 1.
5. Inspect Encoding audit for matched/multi_area/unmatched rows.
6. Export encoded matrix, audit, and taxon matching report.

### 2. Kawahara et al. 2023 butterflies
Article: https://www.nature.com/articles/s41559-023-02041-9
Figshare dataset: https://springernature.figshare.com/articles/dataset/A_global_phylogeny_of_butterflies_reveals_their_evolutionary_history_ancestral_host_plants_and_biogeographic_origins/21774899

Files:
- `benchmarks/kawahara_butterflies/Tables.S1-S52.xlsx`
  - Original downloaded supplementary table workbook.
- `benchmarks/kawahara_butterflies/kawahara_butterfly_country_records_S5.csv`
  - Extracted from Table S5: TipName, Species, Country_ISO3.
  - This is country-level range evidence, not lat/lon occurrence input. Use it as a reference for later country-to-area mapping logic.
- `fixtures/region_builder/kawahara_7_bioregion_mapping.csv`
  - Extracted from Table S27: ISO to 7-bioregion area assignment.
- `fixtures/region_builder/kawahara_7_bioregion_rules.json`
  - Example config for building an approximate Kawahara 7-bioregion GeoJSON
    from country/subunit polygons.
  - Multi-region entries in Table S27 are handled with coarse split/admin1
    rules; this is not an official author-provided polygon boundary dataset.

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
