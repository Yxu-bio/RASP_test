# Psychotria ancestral-range reconstruction

This compact case checks the main single-tree and tree-set ancestral-range
workflows. It is suitable for a first run after installation.

## Inputs

- Reference tree: `data/benchmarks/psychotria/Psychotria.tree`
- Range matrix: `data/benchmarks/psychotria/distribution.csv`
- Tree set: `data/benchmarks/psychotria/dataset.trees`
- Optional time periods: `data/benchmarks/psychotria/timeperiods.txt`

The matrix uses one encoded `State` column with areas A-D.

## Single-tree check

1. Start RASP5.
2. Select **File > Open Tree File** and open `Psychotria.tree`.
3. Select **File > Open Matrix File** and open `distribution.csv`.
4. Confirm that the tree and matrix taxa match in the right-hand QA panel.
5. Select **Ancestral Distribution Reconstruction > On Consensus Tree > DIVA**.
6. Keep the default range settings and run the analysis.
7. Open the result window and inspect the tree, List, Information, and Time
   pages.

As a compact identity check, the leading states for nodes 20-22 should be C,
B, and BC. In the fixed DIVA baseline all three have 100% support. DEC and
BioGeoBEARS-DEC have the same three leading states, with probabilities that are
close but not identical because they are different models and engines.

Repeat step 5 with **DEC** and **BioGeoBEARS** when checking those engine
installations. BioGeoBEARS exposes six model choices in its configuration; do
not interpret model-test output as evidence that all models are biologically
appropriate for a dataset.

BayArea is an MCMC workflow and needs a separate multi-chain convergence
check. Use [BayArea DISTANCE NORM: multi-chain analysis and convergence](BayArea_distance_norm_convergence.md)
instead of treating a short installation run as a final BayArea inference.

## Tree-set check

1. Keep the reference tree and matrix loaded.
2. Select **File > Import Tree Set** and open `dataset.trees`.
3. Select **Ancestral Distribution Reconstruction > On Trees > S-DIVA**.
4. For a short installation check, enable random tree sampling and select a
   small documented number of trees. For a final analysis, choose the intended
   sample size before starting and report it.
5. Confirm that the result reports input, effective, failed, and unmatched tree
   counts. These counts define the denominator used for each reference clade.
6. Repeat with **S-DEC** or **S-BioGeoBEARS** as required.

The fixed 25-tree regression baseline again gives C, B, and BC as the leading
states for nodes 20-22 across S-DIVA, S-DEC, and S-BioGeoBEARS-DEC.

## Artifacts to retain

Each run directory contains native engine inputs and outputs, normalized RASP5
results, logs, and `rasp5_provenance.json`. Source-checkout runs are under
`runs/`; installed builds use `%LOCALAPPDATA%\RASP5\runs` unless
`RASP5_DATA_HOME` is set.

If a leading state differs from the fixed check above, first verify the selected
tree, matrix, method, model, sampled-tree count, and loaded setting file. Do not
compare probabilities across different methods as if they were the same
statistical quantity.
