# BBM 功能说明与新旧差异说明

## 当前实现范围

Python 版 RASP 已接入单棵共识树 BBM（Bayesian Binary MCMC）分析。入口在主菜单的 `运行 BBM`，运行前会弹出 `Bayesian Analysis` 配置窗口。

当前 BBM 只处理共识树，不处理树集合。这一点与旧版 RASP 教程中的 BBM 定位一致。

## 执行流程

1. GUI 检查是否已经导入共识树和分布矩阵。
2. 配置窗口生成 `BBMConfig`，并校验区域、节点选择、MCMC 参数和模型参数。
3. `BBMDatasetBuilder` 将当前树和分布矩阵写成 MrBayes 可读取的 `clade1.nex`：
   - 分布矩阵写为 `datatype=restriction`。
   - 每个物种写为 `TID<ID>    0101` 形式。
   - 默认写入 `OG1` 和 `OG2` 两个 outgroup。
   - 如果开启 Large dataset mode，会额外写入 `OG0`，用于复刻旧版大数据模式的输入结构。
   - 被选中的节点会写成 MrBayes constraint，并启用 `report ancstates=yes`。
4. `MrBayesRunner` 调用 `engines/mrbayes/mb.3.2.7-win32.exe`。
5. `BBMOutputParser` 读取 `.run1.p` 和 `.run2.p`：
   - 按旧版 RASP 的列偏移规则读取每个区域的 `p(0)` / `p(1)`。
   - 丢弃 burn-in 后，对 run1/run2 分别求平均。
   - combined 结果为 run1 与 run2 的平均。
6. Python 版把区域级 posterior marginal probabilities 组合为 ancestral range probabilities，并绘制到树节点上。

## 输出文件

每次运行会写入 `runs/bbm/<run_name>/`，GUI 当前使用 `bbm_debug` 作为运行目录名，重复运行会覆盖同名中间文件。

主要文件：

- `clade1.nex`：传给 MrBayes 的输入文件。
- `clade1.nex.run1.p` / `clade1.nex.run2.p`：MrBayes 两次 run 的 ancestral-state 概率输出。
- `clade1.nex.mcmc`：MrBayes MCMC 摘要。
- `mrbayes_stdout.log` / `mrbayes_stderr.log`：MrBayes 标准输出和错误输出。
- `clade_b.log`：按旧版 RASP 风格记录每个 clade 的区域 0/1 概率。
- `analysis_result.log`：按旧版 RASP 结果文件结构输出 `[TAXON]`、`[TREE]`、`[RESULT]`、`[PROBABILITY]`、`[END]`。
- `bbm_manifest.json`：Python 版新增的结构化运行清单，便于排查节点映射、输入参数和 taxon ID。

## 配置项说明

`Maximum number of areas`：祖先分布中允许的最大区域数。比如有 A/B/C/D 四个区域且 max areas=2，则候选范围包括 A、B、C、D、AB、AC、AD、BC、BD、CD，不包括 ABC、ABCD。

`Allow null distribution in analysis`：是否把空分布 `/` 纳入候选祖先范围。旧版 BBM 默认不显示 null range；Python 版默认也关闭。

`Node list`：选择要让 MrBayes 统计 ancestral states 的内部节点。默认全选；也可以按支持率阈值选择。

`Number of cycles`：MrBayes 的 `ngen`，即 MCMC 总代数。

`Number of chains`：MrBayes 的 `nchains`，是同一次 MCMC 内部的链数，不是 CPU 线程数。

`Frequent of samples`：MrBayes 的 `Samplefreq`，即每隔多少代记录一次样本。

`Discard samples`：burn-in 丢弃的样本数。这里沿用旧版 RASP 的样本数口径，不是总代数口径。

`Temperature`：MrBayes heated chain 的温度参数。

`State frequencies`：

- `Fixed (JC)`：固定二态频率。
- `Estimated (F81)`：估计二态频率，并使用 Dirichlet prior。

`Among-site rate variation`：

- `Equal`：区域字符之间等速率。
- `Gamma (+G)`：使用 gamma rate variation，并启用 gamma shape prior 范围。

`Root distribution`：

- `Null`：outgroup 根分布为全 0。
- `Wide`：outgroup 根分布为全 1。
- `Custom`：手动指定根分布。

`Add OG0 outgroup`：额外写入一行 `OG0` outgroup。旧版中这个行为藏在 `Large dataset` 选项里；Python 版本来就统一使用 MrBayes exe，因此这里直接按真实作用命名。

`Save Setting` / `Load Setting`：Python 版新增 JSON 配置保存/加载。旧版 BBM 配置窗口没有这个保存/加载能力。

## 与旧版 RASP 的一致处

- 方法定位一致：BBM 是共识树上的 Bayesian Binary MCMC 分析。
- 默认参数对齐旧版配置窗口：
  - cycles=50000
  - samplefreq=100
  - discard samples=100
  - chains=10
  - temperature=0.1
  - max areas=min(4, 区域数)
  - 默认 JC/equal
  - Dirichlet 默认 0.5/0.5
  - Gamma prior 默认 0.001/100
- 输入格式沿用旧版思路：`clade1.nex`、restriction data、`TID<ID>`、OG outgroup、constraint、`report ancstates=yes`。
- `.run1.p/.run2.p` 的读取使用旧版 VB 的列偏移逻辑，兼容 `LnPr` 和 `alpha` 列导致的偏移。
- run1/run2 的合并方式与旧版一致：区域 0/1 概率取两次 run 的平均。
- ancestral range probability 的组合逻辑与旧版一致：先得到每个区域存在/不存在的边际概率，再按独立乘积组合成范围概率，并按 max areas 截断。

## 与旧版 RASP 的差异

### 1. 引擎调用方式

旧版默认调用 `BAYESDLL.dll`，只有勾选 Large dataset 时才调用 `Plug-ins\mb.3.2.7-win32.exe`。

Python 版统一调用 `engines/mrbayes/mb.3.2.7-win32.exe`。这样更透明，所有输入、输出和错误日志都能保留下来，也避免继续依赖无法维护的旧 DLL。

### 2. Add OG0 outgroup 的含义

旧版 Large dataset 同时代表：

- 改用外部 MrBayes exe。
- 写入额外 outgroup `OG0`。

Python 版已经统一使用外部 MrBayes exe，所以界面只保留第二层含义：是否写 `OG0`。

### 3. 节点映射

旧版主要依赖 `Poly_Node`、`nodeView`、`Left_to_right` 这套位置数组和旧版节点编号。

Python 版构建节点记录时保存：

- display node id
- clade key
- terminal span
- leaf names
- constraint taxa

结果绘图时按 clade 映射到当前 reference tree。这个逻辑通常比单纯依赖显示顺序更稳，但在极端情况下，若树中存在多处同名 taxon 或非标准多分叉，显示编号可能与旧版细节不完全一致。

### 4. NEXUS constraint 文本

旧版写 constraint 时使用旧数组中的 terminal id 字符串。

Python 版直接写 MrBayes 矩阵中的 taxon label，例如 `TID1 TID5`。MrBayes 接受这种写法，而且更清楚；但逐字符比较 `clade1.nex` 时不会与旧版完全相同。

### 5. 结果显示和日志

旧版最终靠 `clade_b.log` 和主程序内部结构绘图。

Python 版除了写 `clade_b.log` 和 `analysis_result.log`，还生成结构化结果对象并复用当前概率饼图渲染通道。界面显示不需要解析旧日志，但旧日志仍保留用于核对。

### 6. 随机性

BBM 是 MCMC 方法。即使参数相同，如果随机种子、MrBayes 版本、起始状态或 DLL/exe 实现不同，节点百分比也不会逐字一致。判断一致性应关注：

- dominant state 是否一致。
- 概率量级是否接近。
- 多次独立链是否收敛。
- Tracer 中 ESS 是否足够。

### 7. 旧版 Tracer View

旧版 BBM 运行后主要进入旧 GUI 的结果绘图和日志流程；Python 版当前没有单独复刻旧版 BBM Tracer View 窗口。现在保留 `.p` 和 `.mcmc` 文件，可用 MrBayes 输出或外部工具检查链状态。后续如果需要，可以把 BayArea 的 Tracer View 增强思路迁移到 BBM。

## 当前验证

已使用项目实际 Python 环境 `E:\Anaconda3\envs\RASP\python.exe` 编译 BBM 相关模块。

已使用 `Psychotria测试数据` 进行极短链真实 smoke test：

- 输入：`Psychotria.tree` + `distribution.csv`
- 引擎：`engines/mrbayes/mb.3.2.7-win32.exe`
- 参数：2 个选中节点、300 cycles、samplefreq=10、discard=10、chains=2
- 结果：MrBayes 成功生成 `.run1.p/.run2.p`，Python 成功解析 2 个节点并写出 `analysis_result.log`

该 smoke test 只证明执行链路通了，不代表默认参数或短链结果具有生物学意义。

## 仍建议后续核对的点

1. 用旧版 RASP 和 Python 版在同一棵树、同一参数、同一节点选择下跑较长链，比较 dominant state 和概率量级。
2. 对 BBM 的节点编号显示做一次人工抽查，确认常用数据集下 display node id 与旧版界面认知一致。
3. 如果后续需要正式发表级输出，应补 BBM 专用 MCMC 诊断视图或导出到 Tracer 的说明入口。
4. 如果将来支持多字符区域名，`Custom root distribution` 需要从字符级输入升级为多选区域输入。
