# BayesTraits 功能说明与新旧差异说明

## 当前实现范围

Python 版当前接入的是旧版 RASP 实际暴露的 BayesTraits 功能：

- BayesTraits MultiState
- Maximum Likelihood
- MCMC
- 节点选择
- Fossil 节点状态约束
- HyperPriorAll / RevJumpHP / RestrictAll / stones
- Other commands 自定义命令
- 使用当前共识树，或使用已经准备好的树集合
- 运行后生成树图结果和 `analysis_result.log`

旧版源码里 BayesTraits 配置窗口列出了多个 BayesTraits 模型，但模型下拉框被禁用，实际默认只能运行 MultiState。因此 Python 版第一阶段也只实现 MultiState。

## 输入文件

运行时会在 `runs/bayestraits/<run_name>/` 下生成：

- `trait.trees`
- `trait.dat`
- `trait.ini`
- `trait.dat.Log.txt`
- `bayestraits_stdout.log`
- `bayestraits_stderr.log`
- `analysis_result.log`
- `bayestraits_manifest.json`

调用方式与旧版 RASP 一致：

```text
BayesTraitsV5.exe trait.trees trait.dat < trait.ini
```

## 配置项

### Model

固定为 `MultiState`。

这是旧版 RASP 的真实可见功能。旧版源码虽然列出了 Discrete、Continuous、Independent Contrast 等模型，但 UI 禁用了模型选择。

### Analysis

支持：

- `Maximum Likelihood`
- `MCMC`

对应旧版命令：

```text
1
1
```

或：

```text
1
2
```

第一行 `1` 是 MultiState，第二行是分析方式。

### Trait column

选择矩阵中哪一列作为 BayesTraits 性状列。

例如矩阵为：

```text
ID,Name,State
1,TaxonA,A
2,TaxonB,B
3,TaxonC,AB
```

则 `State` 会写入 `trait.dat`：

```text
1    A
2    B
3    AB
```

`AB` 在 BayesTraits MultiState 中表示 A/B 不确定状态，不是地理范围 AB。

### Node reconstruction / fossilisation

节点表支持：

- `Select`：是否输出该节点的祖先状态概率
- `Fossil`：给该节点施加状态约束

生成命令示例：

```text
AddTag TNode24 1 5 12 18
AddNode Node24 TNode24
Fossil FNode24 TNode24 A
```

### MCMC && ML

默认值按旧版 RASP：

- `Iterations = 5050000`
- `Sample = 10000`
- `BurnIn = 50000`
- `MLTries = 100`

ML 模式只写：

```text
MLTries 100
```

MCMC 模式写：

```text
Sample 10000
Iterations 5050000
BurnIn 50000
```

### Priors / Stones

保留旧版下拉项：

- `HyperPriorAll gamma 0 10 0 10`
- `HyperPriorAll exponential 0 10`
- `HyperPriorAll beta 0 100 0 50`
- `HyperPriorAll uniform 0 100 0 100`
- `RevJumpHP gamma 0 10 0 10`
- `RevJumpHP exponential 0 10`
- `RevJumpHP beta 0 100 0 50`
- `RevJumpHP uniform 0 100 0 100`
- `RestrictAll 1`
- `stones 100 10000`

`RevJumpHP` 和 `RestrictAll` 互斥，按旧版 UI 逻辑处理。

### Advanced

新增两个辅助项：

- `Use prepared tree set when available`
- `Auto-map categorical values to BayesTraits symbols`

`Use prepared tree set when available` 默认在已经导入树集合时开启，符合旧版 BayesTraits 位于 On Trees 菜单下的逻辑。没有树集合时自动退回单棵共识树。

`Auto-map categorical values` 是 Python 版增强项。旧版要求性状状态是连续字母，例如 A/B/C；Python 版可以把 `red/blue/green` 自动映射为 A/B/C 后传给 BayesTraits，并在 manifest 中保存映射。

## 结果解析

Python 版读取 `trait.dat.Log.txt` 中的概率表，例如：

```text
Tree No  Lh  qAB  qBA  Root P(A)  Root P(B)  Node24 P(A)  Node24 P(B)
```

对每个选中节点，按输出样本/树逐行平均，然后归一化为百分比。

## 与旧版 RASP 的主要差异

### 0. 菜单位置

旧版 BayesTraits 菜单位于 `On Trees` 下：

```text
MultiState Reconstruction in BayesTraits
```

Python 版把它放到单独的：

```text
Trait Reconstruction -> BayesTraits MultiState
```

原因是 BayesTraits 这里做的是性状祖先状态重建，不是祖先分布区重建。运行逻辑仍优先使用已准备好的树集合。

### 1. 引擎接入方式

旧版：

- 使用 `Plug-ins\BayesTraits.exe`
- 工作目录是旧版 `temp`
- 依赖 Plug-ins 目录中的 DLL

Python 版：

- 使用 `engines/bayestraits/BayesTraitsV5.exe`
- 工作目录是 `runs/bayestraits/...`
- 使用官方 BayesTraits V5.0.2 Win64 单文件 exe，不再保留旧 RASP Plug-ins 中的 V3.0.1 exe/DLL

### 2. 运行目录

旧版所有运行产物集中写入 `temp`。

Python 版每次运行独立目录，避免覆盖和污染：

```text
runs/bayestraits/bayestraits_debug/
```

### 3. 树集合处理

旧版 BayesTraits 菜单挂在 On Trees 下，运行时会从树集合导出 `trait.trees`。如果启用随机抽样，就导出随机树。

Python 版：

- 已导入并准备树集合时，可用树集合运行
- 没有树集合时允许用当前共识树运行

这是增强项，不会阻断单树测试。

### 4. 节点映射

旧版用 `Poly_Node` 和旧数组顺序生成 `AddTag TNodeX ...`。

Python 版用当前 reference tree 的后序 internal node 顺序生成节点号，并用 clade leaf IDs 写 `AddTag`。

一般情况下节点号与当前 Python 图上显示一致；如果后续要逐字符复刻旧版 `trait.ini`，需要再统一审计所有性状/生物地理方法的节点编号逻辑。

### 5. 概率缩放

旧版源码在读取 BayesTraits 概率时有一段 `* area_count` 的处理。按实际 BayesTraits 输出，`NodeX P(A) + NodeX P(B) + ...` 本身应约等于 1。

Python 版采用正常概率解释：

- 先对样本/树平均
- 再归一化到总和 100%

这避免出现 A 100%、B 100% 这类总和超过 100% 的显示。

### 6. State View

旧版运行后会显示 Tree View 和 State View。

Python 版当前：

- 打开通用 Result View
- 原始 `trait.dat.Log.txt` 保留在 run 目录
- 尚未单独复刻旧版 State View 窗口

后续如果需要，可以加一个只读 log viewer，并放到 `View` 菜单。

## 已做烟测

使用 `Psychotria测试数据`：

- `Psychotria.tree`
- `distribution.csv`
- `dataset.trees`

已完成：

- 单棵共识树 ML 短跑
- 树集合前 2 棵 ML 短跑
- BayesTraits 输出解析
- `analysis_result.log` 生成
- 结果对象生成

## 后续建议

1. 用旧版 RASP 同数据同参数跑一组 BayesTraits MultiState，对比节点概率。
2. 决定是否要完整复刻旧版 State View。
3. 决定是否开放 BayesTraits 其他模型。旧版 UI 没有真正开放这些模型，因此这属于新增功能，不是旧版复刻必需项。
