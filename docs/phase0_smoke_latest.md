# Phase 0 Smoke Test Latest

- Started: `2026-08-27T20:11:45`
- Finished: `2026-08-27T20:12:18`
- Run root: `E:\RASP\runs\phase0_smoke\20260827_201145`
- Data dir: `E:\RASP\data\benchmarks\psychotria`
- Tree set sample size: `25`

## Tasks

### P0-001 preflight range analysis

- Status: `ok`
- Elapsed seconds: `0.001`
- ok: `True`
- issue_count: `0`
- warnings: `[]`

### P0-004/P0-005 DIVA node result and export

- Status: `ok`
- Elapsed seconds: `0.074`
- class: `DivaResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: `E:\RASP\runs\diva\20260827_201145_890686_Psychotria_distribution`
- has_information: `True`
- has_time_data: `True`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260827_201145\diva_node_summary.csv`
- node_summary_rows: `31`

### P0-004/P0-005 S-DIVA sampled node result and export

- Status: `ok`
- Elapsed seconds: `0.563`
- class: `SDivaResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: `E:\RASP\runs\sdiva\legacy_sdiva_20260827_201145_969161`
- has_information: `True`
- has_time_data: `True`
- input_tree_count: `25`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260827_201145\s-diva_node_summary.csv`
- node_summary_rows: `270`

### P0-004/P0-005 DEC node result and export

- Status: `ok`
- Elapsed seconds: `0.157`
- class: `DECResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: `E:\RASP\runs\phase0_smoke\20260827_201145\dec\phase0_dec`
- has_information: `True`
- has_time_data: `True`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260827_201145\dec_node_summary.csv`
- node_summary_rows: `140`

### P0-004/P0-005 S-DEC sampled node result and export

- Status: `ok`
- Elapsed seconds: `2.232`
- class: `SDECResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: `E:\RASP\runs\sdec\sdec_20260827_201146_693380`
- has_information: `True`
- has_time_data: `True`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260827_201145\s-dec_node_summary.csv`
- node_summary_rows: `163`

### P0-002/P0-004/P0-005 BioGeoBEARS DEC result and export

- Status: `ok`
- Elapsed seconds: `6.63`
- class: `BioGeoBEARSResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: `E:\RASP\runs\phase0_smoke\20260827_201145\biogeobears\phase0_bgb_dec`
- has_information: `True`
- has_time_data: `True`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260827_201145\biogeobears-dec_node_summary.csv`
- node_summary_rows: `270`

### P0-003 BioGeoBEARS model test six models

- Status: `ok`
- Elapsed seconds: `17.0`
- class: `BioGeoBEARSModelTestResult`
- effective_model_count: `6`
- failed_model_count: `0`
- best_model_name: `DECJ`
- criterion_used: `AICc`
- teststable_path: `E:\RASP\runs\phase0_smoke\20260827_201145\biogeobears\phase0_bgb_model_test_batch\teststable.txt`
- rows: `[{"model": "DEC", "success": true, "aicc": 73.831361528575, "weight": 2.149093978372951e-06, "error": ""}, {"model": "DECJ", "success": true, "aicc": 49.4951767183824, "weight": 0.41380029326767426, "error": ""}, {"model": "DIVALIKE", "success": true, "aicc": 71.0466610374798, "weight": 8.648592521812276e-06, "error": ""}, {"model": "DIVALIKEJ", "success": true, "aicc": 49.7724184238102, "weight": 0.3602371704420458, "error": ""}, {"model": "BAYAREALIKE", "success": true, "aicc": 85.4012617942632, "weight": 6.605162194894386e-09, "error": ""}, {"model": "BAYAREALIKEJ", "success": true, "aicc":`

### P0-006/P0-007/P0-008/P0-009 BioGeoBEARS BSM events

- Status: `ok`
- Elapsed seconds: `6.207`
- class: `BioGeoBEARSEventResult`
- event_count: `128`
- raw_tables: `{"anagenetic": 38, "cladogenetic": 185}`
- summary: `{"enabled": true, "directory": "E:\\RASP\\runs\\phase0_smoke\\20260827_201145\\biogeobears\\phase0_bgb_bsm\\bsm", "source_treefile": "E:\\RASP\\runs\\phase0_smoke\\20260827_201145\\biogeobears\\phase0_bgb_bsm\\input_tree.nwk", "source_tip_count": 19, "source_internal_node_count": 18, "nummaps": 5, "seed": 12345, "maxnum_maps_to_try": 5, "maxtries_per_branch": 40000, "clado_rows": 185, "ana_rows": 38, "state_labels": ["/", "A", "B", "C", "D", "AB", "AC", "AD", "BC", "BD", "CD", "ABC", "ABD", "ACD", "BCD", "ABCD"], "clado_csv": "E:/RASP/runs/phase0_smoke/20260827_201145/biogeobears/phase0_bgb_bs`
- warnings: `[]`

