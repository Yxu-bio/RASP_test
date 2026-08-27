# WP2 Parameter Contract Checks

- Generated: `2026-08-27T20:21:50`
- Git commit: `6a83bacb6c247504f5891e2ebb3fb9a34b374007`
- Tracked worktree dirty at run start: `True`
- Untracked/status entries at run start: `3`
- Python: `3.6.13 |Anaconda, Inc.| (default, Mar 16 2021, 11:37:27) [MSC v.1916 64 bit (AMD64)]`
- Overall status: **PASSED**
- Run root: `E:\RASP\runs\wp2_parameter_contract\20260827_202149_969981`

## Cases

| Case | Status | Seconds |
| --- | --- | ---: |
| lagrange-ng fixed d/e + maxareas | passed | 0.129 |
| lagrange-ng period d/e + matrix/exclude rules | passed | 0.517 |
| BayArea prior wiring + initial-rate mode | passed | 0.623 |
| BayArea fixed-seed multi-chain reproducibility | passed | 0.496 |

## Scope

This is a native-engine parameter contract, not a convergence or biological-result benchmark.
It proves that fixed d/e, period d/e inheritance/override, maxareas and period masks/matrices
change lagrange-ng raw output in controlled A/B runs, and that BayArea prior scales, seed,
initial-rate mode, independent-chain execution and pooled raw state counts are reproducible.

The one-cycle BayArea probes are intentionally diagnostic and must not be interpreted as MCMC results.

Machine-readable report: `E:\RASP\runs\wp2_parameter_contract\20260827_202149_969981\report.json`
