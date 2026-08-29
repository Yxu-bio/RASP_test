# WP4 Trait Regression - Latest

Status: **passed**

Command:

```powershell
E:\Anaconda3\envs\RASP\python.exe tools\run_wp4_trait_regression_checks.py --tree-count 3
```

Fixed data:

- `data/benchmarks/primate/Trees_States/Primates.tree`
- `data/benchmarks/primate/Trees_States/100Trees.trees`
- `data/benchmarks/primate/Trees_States/characters.csv`

Verified:

- BayesTraits Model A ML statistics use a non-tree `TraitModelResult`.
- BayesTraits Model A/B MCMC internal-node reconstruction parses 41/41 nodes.
- BayesTraits MultiState ML parses selected-node probabilities; IC correlation remains statistics-only.
- Main-window statistics routing opens and closes without creating an ancestral tree view.
- Zero-node reconstruction is reported as a failure and cannot open a statistics/tree result view.
- fastAnc, fastAnc CI, anc.Bayes, experimental anc.ML BM and ape::ace return explicit result semantics.
- Experimental anc.ML BM/OU execute without estimator fallback; EB either estimates or reports its known singular-covariance limitation explicitly.
- Experimental DTT metadata is persisted in the result object and summary JSON.
- Mixed continuous/discrete trait columns preserve the user-selected column.
- S-phytools aggregates 3 sampled trees with across-tree uncertainty metadata.
- The BayesTraits dialog changes output and active parameters by model and ML/MCMC mode.

Machine-readable result: `runs/wp4_trait_regression/latest/wp4_trait_regression_summary.json`
