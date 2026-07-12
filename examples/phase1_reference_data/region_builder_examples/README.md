# Region Builder Examples

This folder contains small examples for the generic RASP5 Region GeoJSON
builder:

```powershell
python tools\build_region_geojson.py `
  --config examples\phase1_reference_data\region_builder_examples\simple_region_rules.json `
  --output runs\region_builder\simple_region_demo.geojson `
  --notes-output runs\region_builder\simple_region_demo_notes.csv `
  --unassigned-output runs\region_builder\simple_region_demo_unassigned.csv
```

The demo uses the existing simplified country GeoJSON and a small mapping table.
It is intentionally artificial.  Its purpose is to demonstrate the workflow:

1. Map base polygon properties to study areas.
2. Override selected features with explicit rules.
3. Split a polygon by latitude or longitude when a study uses a coarse custom
   boundary.
4. Export one `MultiPolygon` feature per analysis area.

For real studies, use the author's area definitions, a standard biogeographic
template, or a study-specific mapping/rule file.  Coarse rules such as
`lat >= 33` should be labelled as approximate rule-based boundaries.

The GUI version exposes this as a two-step idea: choose a base boundary layer
such as the built-in Natural Earth country/subunit layer, then map those source
features into the study-specific analysis areas.  The base layer is not the
final region set; it is the administrative/geographic database used to build
the final GeoJSON.

## Dore et al. Ponerinae 7-region example

This config uses Dore's country metadata table plus Natural Earth map subunits
and admin1 polygons:

```powershell
python tools\build_region_geojson.py `
  --config examples\phase1_reference_data\region_builder_examples\dore_ponerinae_7_palea_rules.json `
  --output runs\region_builder\dore_ponerinae_7_palea_generic.geojson `
  --notes-output runs\region_builder\dore_ponerinae_7_palea_generic_notes.csv `
  --unassigned-output runs\region_builder\dore_ponerinae_7_palea_generic_unassigned.csv
```

The Dore example follows the source workflow where possible, including coarse
cross-region rules for Indonesia, Mexico, China, Russia, India, Pakistan, and
selected overseas subunits.  It is useful for workflow testing and approximate
study-specific coding, but it is not an official polygon file from the authors.

## Kawahara et al. butterfly 7-region example

This config uses Kawahara Table S27's country ISO to 7-bioregion scoring:

```powershell
python tools\build_region_geojson.py `
  --config examples\phase1_reference_data\region_builder_examples\kawahara_7_bioregion_rules.json `
  --output runs\region_builder\kawahara_7_bioregion_generic.geojson `
  --notes-output runs\region_builder\kawahara_7_bioregion_generic_notes.csv `
  --unassigned-output runs\region_builder\kawahara_7_bioregion_generic_unassigned.csv
```

Most countries are assigned directly from ISO codes.  China, Indonesia, Mexico,
and Russia are multi-region entries in Table S27, so the example uses coarse
split/admin1 rules instead of creating mixed area labels.  Small countries,
dependencies, and disputed subunits that are absent from S27 are handled as
explicit rule-file cases.
