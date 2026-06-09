# Psychotria Benchmark Report

- Started: `2026-05-31T02:02:30`
- Finished: `2026-05-31T04:07:02`
- Data dir: `E:\RASP\Psychotria测试数据`
- Tree entries: raw=1001, bifurcating=1001, analysis=1001
- Areas: `A, B, C, D`
- Root age estimate: `5.2`

## Methods

### S-DEC full tree set serial OpenBLAS-limited

- Status: `ok`
- Elapsed seconds: `158.708`
- model_name: `S-DEC`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- run_dir: `E:\RASP\runs\sdec\sdec_20260531_020230_056833`
- analysis_log_path: `E:\RASP\runs\sdec\sdec_20260531_020230_056833\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC CD B A AB BD D | 958/1001 |
| 21 | B BC AB BD C A AC CD D | 997/1001 |
| 22 | BC C B AC AB CD BD A D | 816/1001 |
| 23 | C BC AC CD B A AB BD | 882/1001 |
| 24 | BC C B AC AB CD BD A | 674/1001 |
| 25 | B BC C AC AB CD BD A D AD | 870/1001 |
| 26 | A AB AC AD | 1000/1001 |
| 27 | AB AC BC B A C AD BD CD D | 1000/1001 |

### S-BioGeoBEARS DEC full tree set

- Status: `ok`
- Elapsed seconds: `620.835`
- model_name: `S-BioGeoBEARS-DEC`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- run_dir: `E:\RASP\runs\sbgb\legacy_sbgb_dec_20260531_020508_770482`
- analysis_log_path: `E:\RASP\runs\sbgb\legacy_sbgb_dec_20260531_020508_770482\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC CD B ABC BCD ACD A AB BD ABCD D AD ABD | 958/1001 |
| 21 | B BC AB BD ABC C BCD ABD A AC CD ABCD D AD ACD | 997/1001 |
| 22 | BC C B ABC BCD AC AB CD BD ABCD A ACD ABD D AD | 816/1001 |
| 23 | C BC AC CD ABC BCD B ACD A AB BD ABCD D AD ABD | 882/1001 |
| 24 | BC C ABC B BCD AC CD ABCD AB BD ACD A D ABD AD | 674/1001 |
| 25 | BC B C ABC AC BCD AB CD BD ABCD ACD ABD A D AD | 870/1001 |
| 26 | A AB AC AD ABC ABD ACD B C ABCD BC BD D CD BCD | 1000/1001 |
| 27 | ABC AB AC BC B A ABCD C ABD ACD BCD AD BD CD D | 1000/1001 |

### S-BioGeoBEARS DECJ full tree set

- Status: `ok`
- Elapsed seconds: `1382.837`
- model_name: `S-BioGeoBEARS-DEC+J`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- run_dir: `E:\RASP\runs\sbgb\legacy_sbgb_decj_20260531_021529_607718`
- analysis_log_path: `E:\RASP\runs\sbgb\legacy_sbgb_decj_20260531_021529_607718\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC CD B A D ABC BCD ACD AB BD AD ABCD | 958/1001 |
| 21 | B BC AB BD C A D ABC BCD ABD AC CD AD ABCD | 997/1001 |
| 22 | C B BC AC ABC AB BCD CD BD A D ABCD ACD ABD AD | 816/1001 |
| 23 | C AC BC CD B A D ABC BCD ACD AB BD AD ABCD | 882/1001 |
| 24 | C B BC AC ABC CD AB BCD BD A D ACD ABCD ABD AD | 674/1001 |
| 25 | B C BC AB AC ABC BCD BD CD A D ABCD ABD ACD AD | 870/1001 |
| 26 | A AB AC AD B C D ABC ABD ACD BC BD CD ABCD | 1000/1001 |
| 27 | A B C AB AC ABC BC AD ABD ACD ABCD BCD BD CD D | 1000/1001 |

### S-BioGeoBEARS DIVALIKE full tree set

- Status: `ok`
- Elapsed seconds: `617.402`
- model_name: `S-BioGeoBEARS-DIVALIKE`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- run_dir: `E:\RASP\runs\sbgb\legacy_sbgb_divalike_20260531_023832_447381`
- analysis_log_path: `E:\RASP\runs\sbgb\legacy_sbgb_divalike_20260531_023832_447381\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC B AC CD BD AB D A BCD ABC ACD AD ABD ABCD | 958/1001 |
| 21 | B BC AB BD C BCD ABC CD AC D A ABD AD ABCD ACD | 997/1001 |
| 22 | BC C B AC CD BCD ABC AB BD D A ACD ABCD ABD AD | 816/1001 |
| 23 | C BC AC CD B ABC BCD AB BD A ACD D ABCD AD ABD | 882/1001 |
| 24 | C BC B BCD ABC CD AB AC BD A ABCD D ACD ABD AD | 674/1001 |
| 25 | BC C B BCD ABC AC AB CD BD A ABCD ACD ABD D AD | 870/1001 |
| 26 | A AB AD AC B C ABD ABC ACD D BC BD CD ABCD BCD | 1000/1001 |
| 27 | ABC AC AB BC B C ABCD A ACD ABD BCD CD BD AD D | 1000/1001 |

### S-BioGeoBEARS DIVALIKEJ full tree set

- Status: `ok`
- Elapsed seconds: `1377.104`
- model_name: `S-BioGeoBEARS-DIVALIKE+J`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- run_dir: `E:\RASP\runs\sbgb\legacy_sbgb_divalikej_20260531_024849_851688`
- analysis_log_path: `E:\RASP\runs\sbgb\legacy_sbgb_divalikej_20260531_024849_851688\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C B A D CD AC BC BD AB AD ACD BCD ABC | 958/1001 |
| 21 | B C A D BD BC AB CD AC AD ABD BCD ABC | 997/1001 |
| 22 | C B BC CD BD BCD A D AB AC ABC ABD ACD ABCD AD | 816/1001 |
| 23 | C B A D CD BC AC BD AB AD ACD BCD ABC | 882/1001 |
| 24 | C B BC CD BD BCD A D AC AB ABC ACD ABCD ABD AD | 674/1001 |
| 25 | B C BC CD BD BCD A AB D AC ABC ABD ACD ABCD AD | 870/1001 |
| 26 | A B C D AB AC AD CD BD BC ACD ABD ABC | 1000/1001 |
| 27 | A C B BC AC AB ABC CD BD BCD AD D ACD ABD ABCD | 1000/1001 |

### S-BioGeoBEARS BAYAREALIKE full tree set

- Status: `ok`
- Elapsed seconds: `926.615`
- model_name: `S-BioGeoBEARS-BAYAREALIKE`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- run_dir: `E:\RASP\runs\sbgb\legacy_sbgb_bayarealike_20260531_031146_960644`
- analysis_log_path: `E:\RASP\runs\sbgb\legacy_sbgb_bayarealike_20260531_031146_960644\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC ABC CD BCD B AB ACD ABCD A BD D ABD AD | 958/1001 |
| 21 | B BC AB ABC C BD BCD AC A ABD ABCD CD D ACD AD | 997/1001 |
| 22 | BC C ABC B AC BCD AB CD A ABCD BD ACD ABD D AD | 816/1001 |
| 23 | C BC AC ABC CD BCD B ACD ABCD AB A BD D ABD AD | 882/1001 |
| 24 | BC C ABC B AC AB BCD CD ABCD A BD ACD ABD D AD | 674/1001 |
| 25 | BC C ABC B AC AB BCD A ABCD CD BD ACD ABD AD D | 870/1001 |
| 26 | A AB AC AD ABC ABD ACD C B ABCD BC D BD CD BCD | 1000/1001 |
| 27 | ABC BC AC AB C B A ABCD BCD ACD ABD CD BD AD D | 1000/1001 |

### S-BioGeoBEARS BAYAREALIKEJ full tree set

- Status: `ok`
- Elapsed seconds: `1634.324`
- model_name: `S-BioGeoBEARS-BAYAREALIKE+J`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- run_dir: `E:\RASP\runs\sbgb\legacy_sbgb_bayarealikej_20260531_032713_578494`
- analysis_log_path: `E:\RASP\runs\sbgb\legacy_sbgb_bayarealikej_20260531_032713_578494\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C B A D CD BC AC BD AB AD ACD BCD ABD ABC ABCD | 958/1001 |
| 21 | B C A D BD BC AB CD AC AD ABD BCD ACD ABC ABCD | 997/1001 |
| 22 | C B BD CD A AB D AC BC ABD ACD AD BCD ABC ABCD | 816/1001 |
| 23 | C B A D CD BC AC BD AB AD ACD BCD ABD ABC ABCD | 882/1001 |
| 24 | C B CD BD A AC D AB BC ACD ABD AD BCD ABC ABCD | 674/1001 |
| 25 | B C BD CD A AB D AC BC ABD ACD AD BCD ABC ABCD | 870/1001 |
| 26 | A B C D AD AB AC CD BD BC ACD ABD BCD ABC ABCD | 1000/1001 |
| 27 | A B C BD CD BC AD AC AB D BCD ACD ABD ABC ABCD | 1000/1001 |

### BayArea 50M

- Status: `ok`
- Elapsed seconds: `635.302`
- model_name: `BayArea`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- run_dir: `E:\RASP\runs\benchmarks\psychotria_tier3_20260531_020229\bayarea\psychotria_tier3_bayarea_50m`
- analysis_log_path: `E:\RASP\runs\benchmarks\psychotria_tier3_20260531_020229\bayarea\psychotria_tier3_bayarea_50m\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC | 1/1 |
| 21 | B BC C ABC | 1/1 |
| 22 | C BC B AC | 1/1 |
| 23 | C BC AC B ABC | 1/1 |
| 24 | C BC AC B ABC | 1/1 |
| 25 | C B A AC AB BC ABC D | 1/1 |
| 26 | A AB AC | 1/1 |
| 27 | A AC AB ABC B C BC AD | 1/1 |

### BBM 500k

- Status: `ok`
- Elapsed seconds: `63.457`
- model_name: `BBM`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- analysis_log_path: `E:\RASP\runs\benchmarks\psychotria_tier3_20260531_020229\bbm\psychotria_tier3_bbm_500k\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC CD B ABC BCD A D ACD AB BD ABCD AD ABD | 1/1 |
| 21 | B BC AB BD C ABC BCD A D ABD AC CD ABCD AD ACD | 1/1 |
| 22 | C BC B AC CD ABC A BCD D AB BD ACD ABCD AD ABD | 1/1 |
| 23 | C BC AC CD B ABC A BCD D ACD AB BD ABCD AD ABD | 1/1 |
| 24 | C BC B AC A ABC CD AB D BCD BD ACD AD ABCD ABD | 1/1 |
| 25 | B A C AB BC AC ABC D BD AD CD ABD BCD ACD ABCD | 1/1 |
| 26 | A AB AC AD B C ABC D ABD ACD BC BD CD ABCD BCD | 1/1 |
| 27 | A AB AC AD B C ABC D ABD ACD BC BD CD ABCD BCD | 1/1 |

### BayesTraits MultiState MCMC

- Status: `ok`
- Elapsed seconds: `55.644`
- model_name: `BayesTraits MultiState`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `501`
- analysis_log_path: `E:\RASP\runs\benchmarks\psychotria_tier3_20260531_020229\bayestraits\psychotria_tier3_bayestraits_multistate_mcmc\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C B D A | 501/1001 |
| 21 | B C D A | 501/1001 |
| 22 | C B D A | 501/1001 |
| 23 | C D B A | 501/1001 |
| 24 | C B D A | 501/1001 |
| 25 | C B D A | 501/1001 |
| 26 | A D B C | 501/1001 |
| 27 | C B A D | 501/1001 |

