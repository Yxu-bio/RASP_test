# BayArea DISTANCE NORM: multi-chain analysis and convergence

BayArea is an MCMC analysis. A run that reaches 100% has produced samples, but
it has not automatically demonstrated convergence. This tutorial uses the
bundled Psychotria case to show the complete RASP5 workflow: meaningful
coordinates, independent chains, burn-in, trace inspection, diagnostics, and
retained native outputs.

`DISTANCE NORM` is the supported BayArea model in RASP5. `INDEPENDENCE` remains
available for compatibility but is not recommended for new analyses because
its stochastic-history sampler can mix very slowly even in long runs.

## Fixed tutorial inputs

- Tree: `data/benchmarks/psychotria/Psychotria.tree`
- Range matrix: `data/benchmarks/psychotria/distribution.csv`
- Coordinates: `data/benchmarks/psychotria/coordinates.csv`

The case contains 19 taxa and four areas, A-D. The coordinate file contains
one row per area in `area,latitude,longitude` order. DISTANCE NORM requires at
least two distinct coordinate pairs; all-zero or identical coordinates are
invalid for this model.

## Short installation check

This checks the executable and data flow only. Do not interpret it as a
scientific result.

1. Open `Psychotria.tree` with **File > Open Tree File**.
2. Open `distribution.csv` with **File > Open Matrix File**.
3. Select **Ancestral Distribution Reconstruction > On Consensus Tree > BayArea**.
4. Select `DISTANCE NORM` and click **Recommended settings**.
5. Click **Load** below the geographic table and select `coordinates.csv`.
6. Set **Chain Length** to `100000`, **Sample freq.** to `1000`,
   **Independent chains** to `2`, and **Parallel chains** to `2`.
7. Enter a positive integer seed, run the analysis, and confirm that both
   chains finish and the Tracer View opens.

Low ESS, visible drift, or split-Rhat above 1.05 is expected in this short
check. Its only success criterion is that the run and Tracer data are complete.

## Reproducible long-chain case

Repeat the workflow with these settings:

| Setting | Value |
| --- | ---: |
| Model | `DISTANCE NORM` |
| Chain Length | `5000000` |
| Sample freq. | `1000` |
| Independent chains | `4` |
| Parallel chains | `4` or the number the computer can run comfortably |
| Seed | `20260829` |
| Guess rates | `T` |
| Gain prior | `0.1` |
| Loss prior | `0.1` |
| Dist. power prior | `0.1` |
| Area proposal tuner | `0.1` |
| Rate proposal tuner | `0.5` |
| Dist. proposal tuner | `0.5` |
| Distance power + | `T` |
| Distance truncate | `F` |
| Aux sampling | `F` |

The base seed produces four deterministic but distinct chain seeds. Enabling
**Save original to** is recommended for a final analysis; each chain is copied
to a separate directory so native outputs are not overwritten.

## Burn-in and Tracer View

When the run completes, RASP5 opens Tracer View before constructing the final
pooled result.

1. Set **Burn-in** to `500000`.
2. Select each of `lnL`, `gain`, `loss`, and `distP` in the **Trace** menu.
3. Check that all chains overlap without a sustained directional trend.
4. Read the summary below the plot for every trace.
5. Click **Calculate**. RASP5 reparses every chain after the selected burn-in
   and only then rebuilds the pooled node probabilities.

Use the following values as screening rules, not as a mathematical proof of
convergence:

| Diagnostic | Operational minimum | Preferred target |
| --- | ---: | ---: |
| split-Rhat for every trace | `<= 1.05` | `<= 1.01` |
| minimum ESS in every chain | `>= 100` | `>= 400` |
| maximum first/second-half mean shift | `<= 0.25` posterior SD | `<= 0.10` posterior SD |

The half-mean shift is divided by the retained trace's standard deviation. It
is not divided by the parameter mean, because a broad posterior near zero can
otherwise produce a large and misleading percentage. RASP5 also keeps the old
relative field in internal metadata for compatibility.

## Expected result of the fixed case

The verified 4 x 5,000,000-cycle run completed in about 68 seconds on the
development machine. Hardware time is not a pass criterion. At burn-in
500,000 it produced:

- split-Rhat `1.002-1.004` across `lnL`, `gain`, `loss`, and `distP`;
- minimum per-chain ESS `276.6` across the four monitored traces;
- maximum half-mean shift `0.249` posterior SD;
- the same highest-probability range in all four chains at all 18 internal
  nodes;
- median node-level maximum pairwise total-variation distance `0.059`, with a
  maximum of `0.109`.

This passes the operational minimum but not every preferred target. The full
checkpoint trajectory is in `docs/bayarea_convergence_latest.md`. It shows why
the 100,000 and 1,000,000-cycle outputs must not be treated as equivalent to
the final run.

## When a run does not converge

Do not hide a failed diagnostic by pooling more non-converged samples.

1. Confirm that the coordinates are meaningful and the intended areas are in
   the same order as the matrix.
2. Confirm that at least two independent chains were run; four are recommended
   for a final analysis.
3. Increase chain length, normally by doubling it, while keeping a sampling
   interval that leaves enough retained samples.
4. Choose burn-in from all chain traces, then inspect every monitored
   parameter again.
5. If one chain remains different, retain its raw files and investigate the
   model/data combination rather than deleting that chain.
6. Report the chain count, cycles, sample frequency, burn-in, seed policy,
   diagnostics, and any warning in the final methods or supplement.

Reusing the same base seed for a longer run makes the benchmark reproducible.
Use a new documented base seed when performing an additional independent
replication.

## Outputs to retain

Keep these together for a scientific analysis:

- every chain's `*.parameters.txt`, `*.area_states.txt`, `*.area_probs.txt`,
  and `*.nhx` files;
- `bayarea_manifest.json`, stdout/stderr logs, and `rasp5_provenance.json`;
- the selected burn-in and exported Tracer CSV;
- the RASP5 result export and any figure derived from it.

Source-checkout runs are written under `runs/bayarea`; installed builds use
`%LOCALAPPDATA%\RASP5\runs\bayarea` unless `RASP5_DATA_HOME` is set.

## Reproduce the automated benchmark

From a source checkout with the packaged BayArea executable:

```powershell
python tools/run_bayarea_convergence_benchmark.py
```

The command validates input and engine SHA256 values, runs all four chains,
checks 1M, 2.5M, and 5M checkpoints, compares node posteriors across chains,
and writes raw reports under `runs/benchmarks/bayarea_convergence`. A plumbing
check without a convergence claim is available as:

```powershell
python tools/run_bayarea_convergence_benchmark.py --smoke --report ""
```
