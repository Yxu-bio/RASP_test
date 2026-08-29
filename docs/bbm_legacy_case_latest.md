# BBM 旧案例系统对照（最新）

状态：**Passed**

- 运行时间：`2026-08-28T03:37:00`
- Git commit：`a50296cae17e3f018d580b49557688fa75595eb7`
- 机器可读报告：`E:\RASP\runs\bbm_legacy_case\20260828_033641_180066\report.json`
- 当前 MrBayes SHA256：`a7358c7e5b906c1872c8948a89bacf5e3a1966f69adff57f3c5d8f6346d19e62`
- 旧版 Large dataset MrBayes SHA256：`a7358c7e5b906c1872c8948a89bacf5e3a1966f69adff57f3c5d8f6346d19e62`
- 两个 MrBayes 二进制完全相同：`True`

## 覆盖

- Psychotria：19 tips、4 areas、18 internal nodes。
- 检查当前安全默认、旧版 10-chain 默认、旧版 Large dataset/OG0、F81+Gamma+custom root+null range+node subset 四套输入契约。
- 对照 `Config_BBM.vb` 的 NEXUS/命令写法、`Module_BBM.vb` 的 discard+1 与双 run 平均、`Form_Main.vb` 的范围概率乘积与归一化。
- 使用相同 MrBayes、固定 seed/swapseed，实跑当前 `TID` 约束和旧版数值 taxon 约束。

## 数值结果

- 10-chain 对照选中/输出节点：`18/18`
- 当前原生运行耗时：`6.428 s`
- 旧约束原生运行耗时：`6.511 s`
- 当前安全默认链数：`4`；warning 数：`0`
- `raw_current_TID_vs_legacy_numeric_constraints_combined` 最大绝对差：`0`
- `raw_current_TID_vs_legacy_numeric_constraints_run1` 最大绝对差：`0`
- `raw_current_TID_vs_legacy_numeric_constraints_run2` 最大绝对差：`0`
- `raw_current_parser_vs_raw_oracle_combined` 最大绝对差：`0`
- `raw_current_parser_vs_raw_oracle_run1` 最大绝对差：`0`
- `raw_current_parser_vs_raw_oracle_run2` 最大绝对差：`0`
- `raw_current_range_states_vs_raw_formula` 最大绝对差：`0`
- `raw_faithful_precision_TID_vs_numeric_constraints` 最大绝对差：`0`
- `precision_current_full_precision_states_vs_legacy_Single_F6_formula` 最大绝对差：`0.000148394356742`
- `precision_current_full_precision_vs_legacy_F6_marginals` 最大绝对差：`1.0483378905e-06`
- 高级参数原生运行耗时：`1.544 s`
- 高级参数选中节点：`9`；输出节点：`9`
- `advanced_raw_parser_vs_raw_oracle_combined` 最大绝对差：`0`
- `advanced_raw_parser_vs_raw_oracle_run1` 最大绝对差：`0`
- `advanced_raw_parser_vs_raw_oracle_run2` 最大绝对差：`0`
- `advanced_raw_range_states_vs_raw_formula` 最大绝对差：`0`
- `advanced_precision_full_precision_states_vs_legacy_Single_F6_formula` 最大绝对差：`0.000176587289261`
- `advanced_precision_full_precision_vs_legacy_F6_marginals` 最大绝对差：`8.3117428229e-07`
- 高级参数案例 warning 数：`0`

## 原生引擎警告

隔离实验确认警告由旧版默认 `nchains=10` 触发，不是由全节点约束触发。当前默认改为 4 chains，实跑无 warning；显式 10-chain 当前/旧约束运行均产生以下已知 warning：
- `WARNING: Allocation of zero size attempted. This is probably a bug; problems may follow.`

## 结论与边界

当前 BBM 的参数输入、MrBayes 原始输出读取和全精度双 run 汇总通过独立 raw oracle。固定 seed 下，当前 TID 与旧数字 taxon 约束的原始输出完全一致。旧版随后用 VB Single 并在两阶段写 F6，产生上面记录的微小精度差；当前保留更高精度，不人为降级。当前只输出用户选中的节点，不再继承旧版把未选节点伪装成缺失范围 100% 的展示错误。外部 MrBayes 仍是唯一执行主链，旧 BAYESDLL.dll 不重新接回。
