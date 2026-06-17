# Phase 0 Known Issues

Last updated: 2026-06-18

## Release Blockers

None known after the latest Phase 0 smoke test.

## Non-blocking Follow-ups

1. The automated smoke test uses 25 sampled trees for S-DIVA and S-DEC, not the full `dataset.trees` tree set. Full tree-set runs should still be used for final biological comparison, but the sampled smoke is sufficient as a development gate.
2. The BSM smoke uses `nummaps=5` to verify generation, parsing, filtering, and export plumbing. Production interpretation should use a larger BSM sample size.
3. GUI rendering itself is not fully automated. The smoke test covers service output, CSV export, and an offscreen BSM event table instantiation; final visual checks still require manual inspection.
4. Phase 0 intentionally does not include map/GIS outputs, branch highlighting from BSM events, posterior tree-set BSM aggregation, or source-sink maps. These remain Phase 1+ tasks.

## Latest Verification

Latest smoke report: `docs/phase0_smoke_latest.md`

Covered checks:

- P0-001 preflight range analysis
- P0-004/P0-005 DIVA, S-DIVA, DEC, S-DEC, and BioGeoBEARS DEC node result/export checks
- P0-003 BioGeoBEARS six-model test
- P0-006/P0-007/P0-008/P0-009 BioGeoBEARS BSM generation/parsing/event table checks
- Offscreen BSM event table filter/time-bin instantiation
