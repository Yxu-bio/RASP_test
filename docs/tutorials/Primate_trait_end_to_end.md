# Primate trait reconstruction

This case contains continuous and categorical traits in the same matrix. It
checks that RASP5 uses the selected trait column rather than treating the whole
file as a geographic range matrix.

## Inputs

- Reference tree: `data/benchmarks/primate/Trees_States/Primates.tree`
- Trait matrix: `data/benchmarks/primate/Trees_States/characters.csv`
- Tree set: `data/benchmarks/primate/Trees_States/100Trees.trees`

Continuous columns include brain size, body mass, latitude, precipitation, and
temperature. `Sociality` is categorical. Some other continuous cells are
missing by design and are useful for checking missing-data messages.

## Fast continuous reconstruction

1. Open `Primates.tree` with **File > Open Tree File**.
2. Open `characters.csv` with **File > Open Matrix File**.
3. Select a cell or column in `Brain size species mean`.
4. Select **Trait Reconstruction > On Consensus Tree > phytools**.
5. Choose **Continuous: fastAnc** and keep data transformation at `none` for
   this first check.
6. Run the analysis and open the continuous-trait result tree.
7. Inspect the color legend, node table, estimation source, analysis scale, and
   uncertainty metadata. Toggle rectangular/circular display only after the
   initial result has rendered.

For positive size measurements, a `log` or `log10` input transformation may be
scientifically appropriate. RASP5 transforms tip values before estimation.
Display and color scales can then show the modeled scale or back-transformed
original units; record both choices in a publication.

## BayesTraits model statistics versus node reconstruction

1. Select **Trait Reconstruction > On Consensus Tree > BayesTraits**.
2. Choose Continuous Model A or Model B.
3. An ML run returns model-level statistics. It is not presented as a full set
   of internal-node ancestral values.
4. To estimate internal continuous node values, choose MCMC and enable the
   continuous ancestral-state reconstruction output. BayesTraits then uses its
   saved-model/unknown-value workflow.
5. Start with the supplied small primate tree. Check convergence and effective
   sample sizes before interpreting posterior summaries.

BayesTraits MCMC output and phytools estimates answer related but not identical
questions. Differences are not automatically errors.

## Tree-set reconstruction

1. Import `100Trees.trees` with **File > Import Tree Set**.
2. Select **Trait Reconstruction > On Trees > S-phytools**.
3. Choose a continuous method and an explicit tree sample count and seed.
4. Confirm that the result reports across-tree support/uncertainty and the
   effective number of trees.

S-BayesTraits is intentionally not part of the RASP5 5.0 scope. Large Bayesian
tree-set jobs should not be inferred from the single-tree BayesTraits menu.

## Artifacts to retain

Keep the normalized result, native engine log, selected trait and transform,
seed/MCMC settings when applicable, and `rasp5_provenance.json`. A model-
statistics result and an ancestral-node result are separate result types and
should not be reported interchangeably.
