# RASP5 内置 lagrange-ng 修复版说明与使用教程

本文档说明 RASP5 当前内置的 `lagrange-ng.exe` 修复版，包括它解决的问题、配置语法、DEC/S-DEC 中的使用方式、与上游版本的差异以及验证结果。

## 1. 文件位置

RASP5 当前调用的引擎为：

```text
E:\RASP\engines\lagrange-ng\lagrange-ng.exe
```

当前修复版文件信息：

```text
Size: 38870588
LastWriteTime: 2026/7/8 22:35:13
```

替换前的旧版备份为：

```text
E:\RASP\engines\lagrange-ng\lagrange-ng.exe.before_fixed_de_20260708_224045
```

修复版编译源码位于：

```text
C:\msys64\home\xuyan666\lagrange-ng
```

该源码基于上游 `computations/lagrange-ng` 的 `master`，commit 为：

```text
6a07587f8b4fb04e4a112668624cb01d8542a945
```

## 2. 这个引擎在 RASP5 中负责什么

`lagrange-ng.exe` 是 RASP5 中 DEC / S-DEC 的计算引擎。

在 RASP5 里：

```text
DEC   = 在一棵共识树上调用 lagrange-ng
S-DEC = RASP5 外层逐棵树调用 lagrange-ng，再合并树集合结果
```

`lagrange-ng` 本身不负责树集合统计。它一次只处理一棵树、一份地理分布矩阵和一份配置文件。

## 3. lagrange-ng 的核心运行模式

`lagrange-ng` 的主要计算模式只有两种：

| 模式 | 配置写法 | 含义 |
| --- | --- | --- |
| optimize | `mode = optimize` | 让引擎自动估计最优 dispersal rate 和 extinction rate |
| evaluate | `mode = evaluate` | 使用用户指定的固定 dispersal/extinction rate 计算 likelihood |

通俗理解：

```text
optimize = 引擎自己找最合适的 d/e
evaluate = 用户给定 d/e，引擎只计算这组参数下的结果
```

RASP5 常规 DEC/S-DEC 分析主要使用 `optimize`。

`evaluate` 更适合开发验证、固定参数比较、参数敏感性测试，或以后需要复现指定 d/e 的分析。

## 4. period / time-stratified 是什么

`period` 和 `time-stratified` 在这里指同一件事：时间分层。

它不是第三种计算模式，而是附加设置。它可以和 `optimize` 或 `evaluate` 组合。

例如：

```ini
period early
period early end = 2.0

period late
period late start = 2.0
```

含义是：

```text
0.0 到 2.0 使用 early period
2.0 到更古老时间使用 late period
```

注意：`lagrange-ng` 的 period 时间按“从现在向过去”计量，`0.0` 表示现在。

## 5. 本修复版解决的问题

上游版本存在一个关键问题：

```ini
mode = evaluate
dispersion = 2.0
extinction = 3.0
```

理论上应该使用 `d=2.0, e=3.0`。但上游版本实际会回到默认：

```text
Dispersion: 0.01
Extinction: 0.01
```

原因是源码中 `evaluate` 模式也会调用 `setInitialParams()`，导致配置里读入的 d/e 被默认初始值覆盖。

此外，上游版本的 period 参数组装也存在问题：

```ini
mode = evaluate
dispersion = 2.0
extinction = 3.0

period early
period early end = 2.0

period late
period late start = 2.0
```

合理预期是 early 和 late 都继承全局 `2.0 / 3.0`。但上游版本会让每个 period 回落到 `0.01 / 0.01`。

本修复版解决了三件事：

1. `evaluate` 模式不再覆盖用户指定的固定 d/e。
2. period 没有单独设置 d/e 时，会继承全局 `dispersion/extinction`。
3. 支持在 period 内单独写 `dispersion/extinction`。

## 6. 修复版新增或修正的配置写法

### 6.1 普通 evaluate 固定 d/e

```ini
treefile = example.nwk
datafile = example.phy
areanames = RA RB RC RD RE
states
workers = 1
threads-per-worker = 1
mode = evaluate
dispersion = 2.0
extinction = 3.0
prefix = eval_fixed_de
```

修复版输出应包含：

```text
Period: default, Dispersion: 2, Extinction: 3
```

### 6.2 period 继承全局 d/e

```ini
treefile = example.nwk
datafile = example.phy
areanames = RA RB RC RD RE
states
workers = 1
threads-per-worker = 1
mode = evaluate
dispersion = 2.0
extinction = 3.0

period early
period early end = 1.0

period middle
period middle start = 1.0
period middle end = 2.0

period late
period late start = 2.0

prefix = eval_period_global
```

修复版输出应包含：

```text
Period: early, Dispersion: 2, Extinction: 3
Period: middle, Dispersion: 2, Extinction: 3
Period: late, Dispersion: 2, Extinction: 3
```

### 6.3 period 单独覆盖 d/e

```ini
treefile = example.nwk
datafile = example.phy
areanames = RA RB RC RD RE
states
workers = 1
threads-per-worker = 1
mode = evaluate
dispersion = 2.0
extinction = 3.0

period early
period early end = 1.0
period early dispersion = 0.5
period early extinction = 0.8

period middle
period middle start = 1.0
period middle end = 2.0
period middle dispersion = 1e-3
period middle extinction = 2e-3

period late
period late start = 2.0

prefix = eval_period_override
```

修复版输出应包含：

```text
Period: early, Dispersion: 0.5, Extinction: 0.8
Period: middle, Dispersion: 0.001, Extinction: 0.002
Period: late, Dispersion: 2, Extinction: 3
```

这里 late 没有单独写 d/e，所以继承全局 `2.0 / 3.0`。

## 7. period 与 matrix/include/exclude 的组合

修复版保留上游已有的 period 功能，包括：

```ini
period early matrix = symmetric_matrix.csv
period middle include = 10000
period late exclude = 01000
```

同时支持 d/e：

```ini
dispersion = 0.4
extinction = 0.7

period early
period early end = 1.0
period early matrix = symmetric_matrix.csv
period early dispersion = 0.9
period early extinction = 1.1

period middle
period middle start = 1.0
period middle end = 2.0
period middle matrix = nonsymmetric_matrix.csv

period late
period late start = 2.0
period late exclude = 00010
```

含义：

```text
early 使用 matrix + d=0.9/e=1.1
middle 使用 matrix + 继承全局 d=0.4/e=0.7
late 使用 exclude mask + 继承全局 d=0.4/e=0.7
```

## 8. optimize 模式是否受影响

本修复不改变常规 `optimize` 的行为。

验证中，旧版和修复版在同一示例上得到一致结果：

```text
Initial LLH: -66.49851
Final LLH: -33.2499
Optimized d: 0.29980103102657335
Optimized e: 0.14585163919659286
```

因此 RASP5 的常规 DEC/S-DEC 优化分析不应因为这次修复发生变化。

## 9. RASP5 中的使用建议

### 9.1 普通用户

普通用户不需要直接编辑 `.conf` 文件。

在 RASP5 GUI 中运行：

```text
Ancestral Distribution Reconstruction -> On Consensus Tree -> DEC
Ancestral Distribution Reconstruction -> On Trees -> S-DEC
```

RASP5 会自动调用：

```text
E:\RASP\engines\lagrange-ng\lagrange-ng.exe
```

### 9.2 开发者

如果后续需要固定 d/e 做测试，应使用：

```ini
mode = evaluate
dispersion = <FLOAT>
extinction = <FLOAT>
```

如果使用 time-stratified 分析，并希望所有 period 使用同一组固定 d/e，只需要写全局 d/e：

```ini
dispersion = 2.0
extinction = 3.0
```

如果某些 period 需要独立 d/e，再额外写：

```ini
period early dispersion = 0.5
period early extinction = 0.8
```

## 10. 已完成的验证

验证目录：

```text
E:\RASP\runs\lagrange_ng_fixed_de_validation
E:\RASP\runs\lagrange_ng_de_extended_tests
E:\RASP\runs\lagrange_ng_current_engine_check
```

已验证内容：

| 测试 | 结果 |
| --- | --- |
| 默认 evaluate | 保持 `0.01 / 0.01` |
| evaluate 固定 `0.1 / 0.2` | 生效 |
| evaluate 固定 `2.0 / 3.0` | 生效 |
| period 继承全局 d/e | 生效 |
| period 单独覆盖 d/e | 生效 |
| period + matrix | 生效 |
| period + include/exclude | 能正常运行 |
| optimize 回归 | 与旧版一致 |
| 非法 period d/e | 按预期解析失败 |

关键验证输出：

```text
Period: default, Dispersion: 2, Extinction: 3

Period: early, Dispersion: 2, Extinction: 3
Period: middle, Dispersion: 2, Extinction: 3
Period: late, Dispersion: 2, Extinction: 3

Period: early, Dispersion: 0.5, Extinction: 0.8
Period: middle, Dispersion: 0.001, Extinction: 0.002
Period: late, Dispersion: 2, Extinction: 3
```

## 11. 与上游 lagrange-ng 的差异

本修复版不是未修改的官方上游二进制。

当前源码包含两类修改：

1. Windows 编译/运行兼容性修改  
   例如路径输出从 `.c_str()` 调整为 `.string()`，以及之前为 Windows 构建修复的 `dist_map` 生命周期问题。

2. fixed d/e 修复  
   包括：
   - `evaluate` 模式不再覆盖用户指定 d/e；
   - period d/e 默认继承全局 d/e；
   - parser 支持 `period xxx dispersion/extinction`。

## 12. 注意事项

1. `period` 时间从现在向过去计量，`0.0` 表示现在。
2. `period` 必须先声明再修改：

```ini
period early
period early end = 1.0
```

下面这种写法是错误的：

```ini
period early end = 1.0
period early
```

3. `evaluate` 是固定参数计算，不会优化 d/e。
4. `optimize` 会优化 d/e，配置里的 `dispersion/extinction` 不作为固定结果使用。
5. RASP5 的 S-DEC 是外层树集合逻辑，`lagrange-ng` 本身只处理单棵树。

## 13. 推荐后续使用原则

对 RASP5 用户：

```text
日常 DEC/S-DEC：使用 optimize
固定参数测试：使用 evaluate
时间分层约束：使用 period
需要每段不同 d/e：使用 period xxx dispersion/extinction
```

对 RASP5 开发：

```text
不要在 Python 层后处理 d/e；
不要把 fixed d/e 逻辑放到 GUI 外部兜底；
应让 lagrange-ng 引擎本身正确接收并使用配置参数。
```

