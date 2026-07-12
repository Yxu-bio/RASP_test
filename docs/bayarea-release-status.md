# BayArea Release Status

Last verified: 2026-07-11

## Release classification

- `DISTANCE NORM`: supported for release.
- `INDEPENDENCE`: retained for legacy compatibility, but not recommended for new analyses.

DISTANCE NORM requires meaningful coordinates with at least two distinct locations. RASP rejects an all-zero or identical-coordinate dataset before launching the engine. As with every MCMC analysis, a completed process is not proof of convergence; users must inspect the parameter traces, approximate ESS, and split-Rhat.

INDEPENDENCE can mix extremely slowly and can generate very large stochastic histories. RASP marks it as not recommended in the model list, shows a red explanation, requires an explicit confirmation with `No` as the default, and preserves the warning in the result. Its output should not be treated as a final inference unless independent chains demonstrate acceptable convergence.

## Engine provenance

- Upstream repository: `https://github.com/mlandis/bayarea`
- Upstream commit: `e6918143cb9a79c3fedf55eed72e6a73961d131a`
- RASP engine banner: `BayArea v1.0.3 (RASP patched)`
- Windows executable: `engines/bayarea/bin/bayarea.exe`
- SHA256: `F2BAD391D9DC828C6C87D060863F8BA69BC7D9827FBE239AE1D91547BF14EC12`
- Build command from `engines/bayarea/src/code`: `g++ -O3 *.cpp -o ../../bin/bayarea.exe`
- Reproducible patch: `docs/patches/bayarea-v1.0.3-rasp.patch`

The patch contains four changes:

1. Add the modern compiler `<ctime>` include.
2. Avoid repeatedly restarting the branch-history erase loop.
3. Connect `distancePowerPrior` to the distance-power prior scale instead of the upstream hard-coded value `1.0`.
4. When `Guess Initial Rates=F`, initialize gain/loss rates from the documented half-Cauchy priors rather than an exponential distribution.

## RASP integration

The supported execution path includes:

- Structured configuration for chain length, sample frequency, model, priors, proposal tuners, seed, coordinates, auxiliary sampling, and original-output export.
- One to eight independent chains, with a separate parallel-chain limit.
- Deterministic per-chain seeds when a base seed is supplied.
- Separate raw-output directories for every chain.
- Posterior pooling only after each chain has been parsed.
- Burn-in re-parsing for every chain followed by a fresh pooled result.
- Multi-chain trace display, per-chain approximate ESS, within-chain drift, and split-Rhat.
- Progress reporting and cooperative cancellation with partial logs retained.
- Legacy `analysis_result.log` generation and NHX taxon-name restoration.

The convergence diagnostics are lightweight application diagnostics. They are not rank-normalized Stan diagnostics and should not be described as such.

## Verification evidence

Final checks used the bundled Psychotria data and the rebuilt Windows executable.

- DISTANCE NORM 100,000-cycle smoke test: 18 internal nodes parsed; every tested node support sum was 100%.
- Prior-wiring probe with scales `0.1` and `1.0`: initial gain, loss, and distance-power values each changed by exactly 10x under the same seed.
- DISTANCE NORM 5,000,000-cycle two-seed test: previous verification produced split-Rhat values around `1.001-1.004` with reasonable ESS.
- Multi-chain fixed-seed repeat: sampled-history files were byte-for-byte reproducible.
- Burn-in reparse: two 100,000-cycle chains changed the pooled per-node sample count from 200 at burn-in 0 to 102 at burn-in 50,000.
- Cancellation test: two active 50,000,000-cycle chains stopped in about 0.8 seconds and left no BayArea process running.
- INDEPENDENCE 5,000,000-cycle two-chain diagnostic: after burn-in 500,000, split-Rhat was approximately `1.130` for lnL, `1.633` for gain, and `3.122` for loss; gain/loss ESS remained around 5-6. This is why the model is not recommended.

## Packaging requirement

The root `.gitignore` intentionally excludes `engines/*`. A normal source commit therefore does not contain the patched source tree or Windows executable. A distributable RASP package must separately include:

1. The executable whose hash is listed above.
2. The BayArea license and upstream attribution.
3. This status document or equivalent release notes.

Do not treat a GitHub source checkout without the separately packaged engine bundle as a complete Windows distribution.
