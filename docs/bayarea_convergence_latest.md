# BayArea Psychotria multi-chain convergence benchmark

Last run: `2026-08-29T17:24:35`

This is a real RASP service-path run of the patched BayArea executable, not a synthetic diagnostic. The diagnostics are the same lightweight split-Rhat and autocorrelation ESS used by the RASP Tracer view; they are not rank-normalized Stan diagnostics.

## Case

- Dataset: bundled Psychotria tree and four-area range matrix (19 taxa).
- Model: `DISTANCE_NORM`.
- Chains: `4` independent chains, up to `4` in parallel.
- Chain length: `5000000`; sample frequency: `1000`; final burn-in: `500000`.
- Base seed: `20260829`; actual chain seeds: `20260829, 21260832, 22260835, 23260838`.
- Wall time: `73.17 s`.
- Raw run directory: `runs\benchmarks\bayarea_convergence\psychotria_distance_norm_4chain_long_20260829_172322`.

## Convergence trajectory

| End cycle | Burn-in | Trace | Split-Rhat | Min per-chain ESS | Max half-shift | Minimum | Target |
| ---: | ---: | --- | ---: | ---: | ---: | :---: | :---: |
| 1000000 | 100000 | `lnL` | 1.015 | 152.4 | 0.285 | not yet | not yet |
| 1000000 | 100000 | `gain` | 1.031 | 42.3 | 0.432 | not yet | not yet |
| 1000000 | 100000 | `loss` | 1.039 | 35.5 | 0.532 | not yet | not yet |
| 1000000 | 100000 | `distP` | 1.008 | 77.8 | 0.281 | not yet | not yet |
| 2500000 | 250000 | `lnL` | 1.006 | 543.7 | 0.111 | pass | not yet |
| 2500000 | 250000 | `gain` | 1.009 | 187.2 | 0.163 | pass | not yet |
| 2500000 | 250000 | `loss` | 1.008 | 128.3 | 0.171 | pass | not yet |
| 2500000 | 250000 | `distP` | 1.004 | 303.4 | 0.178 | pass | not yet |
| 5000000 | 500000 | `lnL` | 1.003 | 882.9 | 0.183 | pass | not yet |
| 5000000 | 500000 | `gain` | 1.004 | 530.4 | 0.198 | pass | not yet |
| 5000000 | 500000 | `loss` | 1.004 | 276.6 | 0.249 | pass | not yet |
| 5000000 | 500000 | `distP` | 1.002 | 424.4 | 0.158 | pass | not yet |

Operational minimum: split-Rhat <= `1.050`, minimum per-chain ESS >= `100`, and maximum half-mean shift <= `0.250` posterior SD for every monitored trace. The stricter target is split-Rhat <= `1.010`, ESS >= `400`, and half-mean shift <= `0.100` SD.

Final diagnostic result: **minimum passed**; strict target: **not passed**.

## Node posterior agreement

After the final burn-in, `18/18` internal nodes (`100.0%`) had the same highest-probability range in all `4` chains. The median of each node's maximum pairwise total-variation distance was `0.059`; the maximum was `0.109`. Differences at uncertain nodes are reported rather than treated as an automatic convergence failure.

## Interpretation

A completed BayArea process is not by itself a convergence result. Use all monitored traces, independent seeds, and the node posterior comparison together. If the minimum is missed, increase chain length, retain the same sampling interval, choose a defensible burn-in from the trace, and rerun independent chains. Do not repair a failed diagnostic by pooling non-converged chains.

Fixed input and engine SHA256 values are stored in `data/benchmarks/psychotria/bayarea_convergence_spec.json`; each run also copies them into its raw JSON report.
