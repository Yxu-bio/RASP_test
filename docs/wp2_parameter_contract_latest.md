# WP2 Parameter Contract Checks

- Generated: `2026-08-27T20:28:38`
- Git commit: `a07982bcb9d7cf2428d08fef1e8b0cec533142a5`
- Tracked worktree dirty at run start: `False`
- Untracked/status entries at run start: `1`
- Python: `3.6.13 |Anaconda, Inc.| (default, Mar 16 2021, 11:37:27) [MSC v.1916 64 bit (AMD64)]`
- Overall status: **PASSED**
- Run root: `E:\RASP\runs\wp2_parameter_contract\20260827_202838_100921`

## Cases

| Case | Status | Seconds |
| --- | --- | ---: |
| lagrange-ng fixed d/e + maxareas | passed | 0.124 |
| lagrange-ng period d/e + matrix/exclude rules | passed | 0.504 |
| BayArea prior wiring + initial-rate mode | passed | 0.611 |
| BayArea fixed-seed multi-chain reproducibility | passed | 0.508 |

## Scope

This is a native-engine parameter contract, not a convergence or biological-result benchmark.
It proves that fixed d/e, period d/e inheritance/override, maxareas and period masks/matrices
change lagrange-ng raw output in controlled A/B runs, and that BayArea prior scales, seed,
initial-rate mode, independent-chain execution and pooled raw state counts are reproducible.

The one-cycle BayArea probes are intentionally diagnostic and must not be interpreted as MCMC results.

Machine-readable report: `E:\RASP\runs\wp2_parameter_contract\20260827_202838_100921\report.json`
