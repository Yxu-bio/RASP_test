# Spatial Base Layers

These files are built-in base boundary layers for the RASP5 Region GeoJSON
Builder.  They are not final analysis areas.  They are source boundary
databases that can be mapped or split into study-specific regions.

## Natural Earth

- `natural_earth/ne_50m_admin_0_map_subunits.geojson`
  - Country, territory, dependency, and disputed map subunit polygons.
  - Useful when occurrence/range records are coded by country names, ISO codes,
    territories, or overseas dependencies.
- `natural_earth/ne_10m_admin_1_states_provinces.geojson`
  - First-level administrative units.
  - Useful when a country is split across multiple bioregions and the split can
    be approximated by provinces/states.

The Region GeoJSON Builder converts these base layers into analysis-ready area
GeoJSON files by applying a mapping CSV and optional rules.
