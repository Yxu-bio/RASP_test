# WP2 Parameter Contract Checks

- Generated: `2026-08-29T17:27:15`
- Git commit: `a50296cae17e3f018d580b49557688fa75595eb7`
- Tracked worktree dirty at run start: `True`
- Untracked/status entries at run start: `107`
- Python: `3.7.4 (default, Aug  9 2019, 18:34:13) [MSC v.1915 64 bit (AMD64)]`
- Overall status: **PASSED**
- Run root: `E:\RASP\runs\wp2_parameter_contract\20260829_172715_297877`

## Cases

| Case | Status | Seconds |
| --- | --- | ---: |
| lagrange-ng fixed d/e + maxareas | passed | 0.280 |
| lagrange-ng period d/e + matrix/exclude rules | passed | 0.593 |
| BayArea prior wiring + initial-rate mode | passed | 0.653 |
| BayArea fixed-seed multi-chain reproducibility | passed | 0.564 |

## Scope

This is a native-engine parameter contract, not a convergence or biological-result benchmark.
It proves that fixed d/e, period d/e inheritance/override, maxareas and period masks/matrices
change lagrange-ng raw output in controlled A/B runs, and that BayArea prior scales, seed,
initial-rate mode, independent-chain execution and pooled raw state counts are reproducible.

The one-cycle BayArea probes are intentionally diagnostic and must not be interpreted as MCMC results.

Machine-readable report: `E:\RASP\runs\wp2_parameter_contract\20260829_172715_297877\report.json`
