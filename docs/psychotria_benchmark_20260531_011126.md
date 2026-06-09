# Psychotria Benchmark Report

- Started: `2026-05-31T01:11:27`
- Finished: `2026-05-31T01:32:41`
- Data dir: `E:\RASP\Psychotria测试数据`
- Tree entries: raw=1001, bifurcating=1001, analysis=1001
- Areas: `A, B, C, D`
- Root age estimate: `5.2`

## Methods

### DIVA

- Status: `ok`
- Elapsed seconds: `5.313`
- model_name: `DIVA`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`

| Node | Summary | Trees |
|---|---|---|
| 20 | C | 1/1 |
| 21 | B | 1/1 |
| 22 | BC | 1/1 |
| 23 | C | 1/1 |
| 24 | C BC | 1/1 |
| 25 | B BC | 1/1 |
| 26 | A | 1/1 |
| 27 | AB AC ABC | 1/1 |

### S-DIVA full tree set

- Status: `ok`
- Elapsed seconds: `1.172`
- model_name: `S-DIVA`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- run_dir: `E:\RASP\runs\sdiva\legacy_sdiva_20260531_011132_942867`
- analysis_log_path: `E:\RASP\runs\sdiva\legacy_sdiva_20260531_011132_942867\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C(100.0%) A(0.0%) B(0.0%) D(0.0%) AB(0.0%) AC(0.0%) AD(0.0%) BC(0.0%) BD(0.0%) CD(0.0%) ABC(0.0%) ABD(0.0%) ACD(0.0%) BCD(0.0%) ABCD(0.0%) | 958/1001 |
| 21 | B(100.0%) A(0.0%) C(0.0%) D(0.0%) AB(0.0%) AC(0.0%) AD(0.0%) BC(0.0%) BD(0.0%) CD(0.0%) ABC(0.0%) ABD(0.0%) ACD(0.0%) BCD(0.0%) ABCD(0.0%) | 997/1001 |
| 22 | BC(97.3%) C(2.7%) A(0.0%) B(0.0%) D(0.0%) AB(0.0%) AC(0.0%) AD(0.0%) BD(0.0%) CD(0.0%) ABC(0.0%) ABD(0.0%) ACD(0.0%) BCD(0.0%) ABCD(0.0%) | 816/1001 |
| 23 | C(100.0%) A(0.0%) B(0.0%) D(0.0%) AB(0.0%) AC(0.0%) AD(0.0%) BC(0.0%) BD(0.0%) CD(0.0%) ABC(0.0%) ABD(0.0%) ACD(0.0%) BCD(0.0%) ABCD(0.0%) | 882/1001 |
| 24 | C(61.3%) BC(38.7%) A(0.0%) B(0.0%) D(0.0%) AB(0.0%) AC(0.0%) AD(0.0%) BD(0.0%) CD(0.0%) ABC(0.0%) ABD(0.0%) ACD(0.0%) BCD(0.0%) ABCD(0.0%) | 674/1001 |
| 25 | BC(38.2%) B(36.6%) C(25.2%) A(0.0%) D(0.0%) AB(0.0%) AC(0.0%) AD(0.0%) BD(0.0%) CD(0.0%) ABC(0.0%) ABD(0.0%) ACD(0.0%) BCD(0.0%) ABCD(0.0%) | 870/1001 |
| 26 | A(100.0%) B(0.0%) C(0.0%) D(0.0%) AB(0.0%) AC(0.0%) AD(0.0%) BC(0.0%) BD(0.0%) CD(0.0%) ABC(0.0%) ABD(0.0%) ACD(0.0%) BCD(0.0%) ABCD(0.0%) | 1000/1001 |
| 27 | AC(46.3%) AB(27.0%) ABC(26.6%) B(0.1%) C(0.0%) A(0.0%) D(0.0%) AD(0.0%) BC(0.0%) BD(0.0%) CD(0.0%) ABD(0.0%) ACD(0.0%) BCD(0.0%) ABCD(0.0%) | 1000/1001 |

### DEC

- Status: `ok`
- Elapsed seconds: `3.956`
- model_name: `DEC`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- run_dir: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\dec\psychotria_dec`

| Node | Summary | Trees |
|---|---|---|
| 0 | AB A AC AD B BC BD C D CD | 1/1 |
| 1 | A AB AC AD B C BC BD D | 1/1 |
| 2 | A AB AC AD B C BC BD D CD | 1/1 |
| 3 | AB AC A B BC AD C BD CD | 1/1 |
| 4 | B BC C AB AC BD CD A D | 1/1 |
| 5 | BC C AC B CD AB | 1/1 |
| 6 | BC C B AC CD AB BD | 1/1 |
| 7 | C BC AC CD B | 1/1 |

### S-DEC full tree set

- Status: `ok`
- Elapsed seconds: `68.833`
- model_name: `S-DEC`
- node_count: `18`
- warning_count: `76`
- input_tree_count: `1001`
- effective_tree_count: `925`
- run_dir: `E:\RASP\runs\sdec\sdec_20260531_011138_036778`
- analysis_log_path: `E:\RASP\runs\sdec\sdec_20260531_011138_036778\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC CD B A AB BD D | 887/925 |
| 21 | B BC AB BD C A AC CD D | 921/925 |
| 22 | BC C B AC AB CD BD A D | 758/925 |
| 23 | C BC AC CD B A AB BD | 819/925 |
| 24 | BC C B AC AB CD BD A | 624/925 |
| 25 | B BC C AC AB CD BD A D AD | 804/925 |
| 26 | A AB AC AD | 924/925 |
| 27 | AB AC BC B A C AD BD CD D | 924/925 |

### BioGeoBEARS DEC

- Status: `ok`
- Elapsed seconds: `52.529`
- model_name: `BioGeoBEARS-DEC`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- run_dir: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\biogeobears\psychotria_bgb_dec`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC CD ABC BCD ACD B ABCD A AB BD D AD ABD | 1/1 |
| 21 | B BC AB BD ABC BCD C ABD A AC ABCD CD D AD ACD | 1/1 |
| 22 | BC ABC C B BCD AC AB CD BD ABCD ABD ACD A D AD | 1/1 |
| 23 | C BC AC CD B ABC A BCD ACD D AB ABCD BD AD ABD | 1/1 |
| 24 | BC C ABC BCD AC CD ABCD B ACD AB BD ABD A D AD | 1/1 |
| 25 | BC B AB ABC C BCD AC BD A CD ABCD ABD ACD D AD | 1/1 |
| 26 | A AB AC AD ABC ABD ACD B C ABCD D BC BD CD BCD | 1/1 |
| 27 | AB ABC AC A B ABD BC ABCD C ACD AD BCD BD CD D | 1/1 |

### BioGeoBEARS DECJ

- Status: `ok`
- Elapsed seconds: `23.561`
- model_name: `BioGeoBEARS-DEC+J`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- run_dir: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\biogeobears\psychotria_bgb_decj`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC CD B A D ABC BCD ACD AB BD AD ABCD | 1/1 |
| 21 | B BC AB BD C A D ABC BCD ABD AC CD AD ABCD | 1/1 |
| 22 | C B BC ABC AC AB BCD CD BD A D ABCD ACD ABD AD | 1/1 |
| 23 | C BC AC CD B A D ABC BCD ACD AB BD AD ABCD | 1/1 |
| 24 | C B BC AC ABC AB CD BCD BD A D ABCD ACD ABD AD | 1/1 |
| 25 | B C BC AB ABC AC BCD BD CD A D ABCD ABD ACD AD | 1/1 |
| 26 | A AB AC AD B C D ABC ABD ACD BC BD CD ABCD | 1/1 |
| 27 | A B C AB AC ABC BC AD ABD ACD ABCD BD BCD CD D | 1/1 |

### BioGeoBEARS DIVALIKE

- Status: `ok`
- Elapsed seconds: `12.795`
- model_name: `BioGeoBEARS-DIVALIKE`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- run_dir: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\biogeobears\psychotria_bgb_divalike`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC CD B ABC BCD AB BD A D ACD AD ABCD ABD | 1/1 |
| 21 | B BC AB BD C ABC BCD AC CD A D ABD AD ABCD ACD | 1/1 |
| 22 | BC C B ABC BCD AB BD AC CD A D ABD ABCD ACD AD | 1/1 |
| 23 | C BC AC CD B A D AB BD AD ACD ABC BCD ABD ABCD | 1/1 |
| 24 | C BC ABC BCD AC B CD AB BD ABCD ACD ABD A D AD | 1/1 |
| 25 | BC B C AC ABC BCD CD AB BD A ACD ABCD D AD ABD | 1/1 |
| 26 | A AD AC AB ACD ABD ABC B C D BC BD CD ABCD BCD | 1/1 |
| 27 | ABC AB AC A ABCD ACD ABD AD B C BCD BC BD CD D | 1/1 |

### BioGeoBEARS DIVALIKEJ

- Status: `ok`
- Elapsed seconds: `21.966`
- model_name: `BioGeoBEARS-DIVALIKE+J`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- run_dir: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\biogeobears\psychotria_bgb_divalikej`

| Node | Summary | Trees |
|---|---|---|
| 20 | C B A D BC AC CD AB BD AD ABC BCD ACD | 1/1 |
| 21 | B C A D BC AB BD AC CD AD ABC BCD ABD | 1/1 |
| 22 | C B BC A D AC AB CD BD ABC BCD AD ACD ABD ABCD | 1/1 |
| 23 | C B A D CD AC BC AD AB BD ACD BCD ABC | 1/1 |
| 24 | C B BC CD A D AB BD AC BCD ABC ACD AD ABD ABCD | 1/1 |
| 25 | B C BC BD CD BCD A AB D AC ABC ABD ABCD ACD AD | 1/1 |
| 26 | A B C D AC AD AB CD BD BC ACD ABD ABC | 1/1 |
| 27 | A B C BC AB AC ABC CD BD BCD AD D ACD ABD ABCD | 1/1 |

### BioGeoBEARS BAYAREALIKE

- Status: `ok`
- Elapsed seconds: `13.925`
- model_name: `BioGeoBEARS-BAYAREALIKE`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- run_dir: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\biogeobears\psychotria_bgb_bayarealike`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC AC ABC CD BCD ACD B ABCD AB A BD D AD ABD | 1/1 |
| 21 | B BC AB ABC BD BCD C ABD AC ABCD A CD D ACD AD | 1/1 |
| 22 | BC C ABC B AC BCD AB CD ABCD BD ACD A ABD D AD | 1/1 |
| 23 | BC ABC C AC BCD B CD ABCD AB ACD BD A ABD D AD | 1/1 |
| 24 | BC ABC C AC BCD B ABCD CD AB ACD BD ABD A D AD | 1/1 |
| 25 | BC ABC B AB AC C BCD ABCD BD ABD A CD ACD AD D | 1/1 |
| 26 | A AB AC ABC AD ABD ACD ABCD B C BC D BD CD BCD | 1/1 |
| 27 | ABC AB BC AC ABCD B ABD BCD A C ACD BD AD CD D | 1/1 |

### BioGeoBEARS BAYAREALIKEJ

- Status: `ok`
- Elapsed seconds: `23.67`
- model_name: `BioGeoBEARS-BAYAREALIKE+J`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- run_dir: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\biogeobears\psychotria_bgb_bayarealikej`

| Node | Summary | Trees |
|---|---|---|
| 20 | C B A D BC AC CD AB BD AD ABC BCD ACD ABD ABCD | 1/1 |
| 21 | B C A D BC AB BD AC CD AD ABC BCD ABD ACD ABCD | 1/1 |
| 22 | C B A AB AC BD CD D BC AD ABD ACD ABC BCD ABCD | 1/1 |
| 23 | C B A D CD AC BC AD AB BD ACD BCD ABD ABC ABCD | 1/1 |
| 24 | C B CD A AB D BD AC BC AD ACD ABD BCD ABC | 1/1 |
| 25 | B C BD CD A AB D AC BC ABD ACD AD BCD ABC ABCD | 1/1 |
| 26 | A B C D AD AC AB CD BD BC ACD ABD BCD ABC ABCD | 1/1 |
| 27 | A B C BD CD BC AD AC AB D BCD ACD ABD ABC ABCD | 1/1 |

### BioGeoBEARS model test

- Status: `ok`
- Elapsed seconds: `59.844`

| Model | Success | lnL | AICc | Weight | Error |
|---|---:|---:|---:|---:|---|
| BioGeoBEARS-DEC | True | -34.5406807642875 | 73.831361528575 | 2.149093978372951e-06 |  |
| BioGeoBEARS-DEC+J | True | -20.9475883591912 | 49.4951767183824 | 0.41380029326767426 |  |
| BioGeoBEARS-DIVALIKE | True | -33.1483305187399 | 71.0466610374798 | 8.648592521812276e-06 |  |
| BioGeoBEARS-DIVALIKE+J | True | -21.0862092119051 | 49.7724184238102 | 0.3602371704420458 |  |
| BioGeoBEARS-BAYAREALIKE | True | -40.3256308971316 | 85.4012617942632 | 6.605162194894386e-09 |  |
| BioGeoBEARS-BAYAREALIKE+J | True | -21.5526504319863 | 50.7053008639726 | 0.2259517319986174 |  |

### S-BioGeoBEARS DEC full tree set

- Status: `ok`
- Elapsed seconds: `626.824`
- model_name: `S-BioGeoBEARS-DEC`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- run_dir: `E:\RASP\runs\sbgb\legacy_sbgb_dec_20260531_011615_603936`
- analysis_log_path: `E:\RASP\runs\sbgb\legacy_sbgb_dec_20260531_011615_603936\analysis_result.log`

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

### BayArea 5M

- Status: `ok`
- Elapsed seconds: `66.24`
- model_name: `BayArea`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- run_dir: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\bayarea\psychotria_bayarea_5m`
- analysis_log_path: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\bayarea\psychotria_bayarea_5m\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C BC | 1/1 |
| 21 | B BC C AB | 1/1 |
| 22 | C BC B AC | 1/1 |
| 23 | C BC AC B | 1/1 |
| 24 | C BC AC B | 1/1 |
| 25 | C B A AC AB BC ABC | 1/1 |
| 26 | A AC AB AD | 1/1 |
| 27 | A AC AB ABC B C BC | 1/1 |

### BBM

- Status: `ok`
- Elapsed seconds: `7.598`
- model_name: `BBM`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1`
- effective_tree_count: `1`
- analysis_log_path: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\bbm\psychotria_bbm\analysis_result.log`

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

### BayesTraits MultiState

- Status: `ok`
- Elapsed seconds: `80.13`
- model_name: `BayesTraits MultiState`
- node_count: `18`
- warning_count: `0`
- input_tree_count: `1001`
- effective_tree_count: `1001`
- analysis_log_path: `E:\RASP\runs\benchmarks\psychotria_20260531_011126\bayestraits\psychotria_bayestraits_multistate\analysis_result.log`

| Node | Summary | Trees |
|---|---|---|
| 20 | C D B A | 1001/1001 |
| 21 | B C D A | 1001/1001 |
| 22 | C B D A | 1001/1001 |
| 23 | C D B A | 1001/1001 |
| 24 | C B D A | 1001/1001 |
| 25 | C B D A | 1001/1001 |
| 26 | A D B C | 1001/1001 |
| 27 | C B D A | 1001/1001 |

