# Phase 0 Smoke Test Latest

- Started: `2026-06-18T01:57:42`
- Finished: `2026-06-18T01:58:19`
- Run root: `E:\RASP\runs\phase0_smoke\20260618_015741`
- Data dir: `E:\RASP\Psychotria测试数据`
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
- Elapsed seconds: `0.098`
- class: `DivaResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: ``
- has_information: `True`
- has_time_data: `True`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260618_015741\diva_node_summary.csv`
- node_summary_rows: `31`

### P0-004/P0-005 S-DIVA sampled node result and export

- Status: `ok`
- Elapsed seconds: `0.567`
- class: `SDivaResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: `E:\RASP\runs\sdiva\legacy_sdiva_20260618_015742_655982`
- has_information: `True`
- has_time_data: `True`
- input_tree_count: `25`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260618_015741\s-diva_node_summary.csv`
- node_summary_rows: `270`

### P0-004/P0-005 DEC node result and export

- Status: `ok`
- Elapsed seconds: `0.181`
- class: `DECResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: ``
- has_information: `True`
- has_time_data: `True`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260618_015741\dec_node_summary.csv`
- node_summary_rows: `140`

### P0-004/P0-005 S-DEC sampled node result and export

- Status: `ok`
- Elapsed seconds: `2.541`
- class: `SDECResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: `E:\RASP\runs\sdec\sdec_20260618_015743_410502`
- has_information: `True`
- has_time_data: `True`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260618_015741\s-dec_node_summary.csv`
- node_summary_rows: `163`

### P0-002/P0-004/P0-005 BioGeoBEARS DEC result and export

- Status: `ok`
- Elapsed seconds: `6.816`
- class: `BioGeoBEARSResult`
- node_count: `18`
- warning_count: `0`
- warnings: `[]`
- run_dir: ``
- has_information: `True`
- has_time_data: `True`
- node_summary_csv: `E:\RASP\runs\phase0_smoke\20260618_015741\biogeobears-dec_node_summary.csv`
- node_summary_rows: `270`

### P0-003 BioGeoBEARS model test six models

- Status: `ok`
- Elapsed seconds: `19.509`
- class: `BioGeoBEARSModelTestResult`
- effective_model_count: `6`
- failed_model_count: `0`
- best_model_name: `DECJ`
- criterion_used: `AICc`
- teststable_path: `E:\RASP\runs\phase0_smoke\20260618_015741\biogeobears\phase0_bgb_model_test_batch\teststable.txt`
- rows: `[{"model": "DEC", "success": true, "aicc": 73.831361528575, "weight": 2.149093978372951e-06, "error": ""}, {"model": "DECJ", "success": true, "aicc": 49.4951767183824, "weight": 0.41380029326767426, "error": ""}, {"model": "DIVALIKE", "success": true, "aicc": 71.0466610374798, "weight": 8.648592521812276e-06, "error": ""}, {"model": "DIVALIKEJ", "success": true, "aicc": 49.7724184238102, "weight": 0.3602371704420458, "error": ""}, {"model": "BAYAREALIKE", "success": true, "aicc": 85.4012617942632, "weight": 6.605162194894386e-09, "error": ""}, {"model": "BAYAREALIKEJ", "success": true, "aicc":`

### P0-006/P0-007/P0-008/P0-009 BioGeoBEARS BSM events

- Status: `ok`
- Elapsed seconds: `7.668`
- class: `BioGeoBEARSEventResult`
- event_count: `128`
- raw_tables: `{"anagenetic": 38, "cladogenetic": 185}`
- summary: `{"enabled": true, "directory": "E:\\RASP\\runs\\phase0_smoke\\20260618_015741\\biogeobears\\phase0_bgb_bsm\\bsm", "nummaps": 5, "seed": 12345, "maxtries_per_branch": 40000, "clado_rows": 185, "ana_rows": 38, "clado_csv": "E:/RASP/runs/phase0_smoke/20260618_015741/biogeobears/phase0_bgb_bsm/bsm/bsm_clado_events.csv", "ana_csv": "E:/RASP/runs/phase0_smoke/20260618_015741/biogeobears/phase0_bgb_bsm/bsm/bsm_ana_events.csv"}`
- warnings: `[]`

