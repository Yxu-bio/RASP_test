# Third-party engine inventory

This file records the engine payload represented by
`release/engine-bundle.json`. It is an engineering inventory, not legal advice.
Official license texts and notices are included in the generated archive.

RASP5's first-party Python and R wrapper source is MIT-licensed at the project
root. That license does not relicense any component listed below.

| Component | Bundled version | License | Upstream / source | RASP changes |
| --- | --- | --- | --- | --- |
| BayArea | 1.0.3, commit `e6918143cb9a79c3fedf55eed72e6a73961d131a` | MIT | https://github.com/mlandis/bayarea | Modern compiler, iterator safety, prior wiring, and rate-initialization fixes in `docs/patches/bayarea-v1.0.3-rasp.patch`. |
| lagrange-ng | commit `6a07587f8b4fb04e4a112668624cb01d8542a945` | GPL-2.0 | https://github.com/computations/lagrange-ng | Windows portability, range-map lifetime, fixed evaluate d/e, and per-period d/e fixes in `docs/patches/lagrange-ng-6a07587-rasp.patch`. |
| BayesTraits | 5.0.2, official Windows x64 build, source commit `20e40f395c000fb354672159c0bab1e276df72e9` | GPL-3.0 | https://github.com/AndrewPMeade/BayesTraits-Release and https://www.evolution.reading.ac.uk/BayesTraitsV5.0.2/BayesTraitsV5.0.2.html | None to the executable. RASP writes commands and parses output externally. |
| MrBayes | 3.2.7 Windows build, source commit `d50016695db24c58bcb36c83c487bd365fe2a566` | GPL-3.0 | https://github.com/NBISweden/MrBayes/releases/tag/v3.2.7 | None to the executable. Used by the BBM runner. |
| DIVA | Legacy DIVA 1.1-derived RASP executable | DIVA 1.1 free-distribution notice | https://sourceforge.net/projects/diva/ | Legacy RASP-modified executable used by DIVA/S-DIVA. Keep attribution to Fredrik Ronquist and RASP. |
| R runtime | 4.5.3 Windows x64 | GPL-2.0 or GPL-3.0 | https://cran.r-project.org/ | Bundled runtime with the installed package library used by RASP. |
| BioGeoBEARS | 1.1.3, GitHub SHA `71274118551b4299f13c0783df51c1829e8e93aa` | GPL >= 2 | https://github.com/nmatzke/BioGeoBEARS | Called through the tracked `engines/biogeobears/bgb_runner.R` wrapper. |
| phytools | 2.5-2 | GPL >= 2 | https://cran.r-project.org/package=phytools | No package source changes. |
| ape | 5.8-1 | GPL >= 2 | https://cran.r-project.org/package=ape | No package source changes. |

## Redistribution evidence

- lagrange-ng identifies its repository license as GPL-2.0.
- MrBayes identifies its repository license as GPL-3.0.
- The BayesTraits V5 manual states that its source is released under GPL-3.0.
- DIVA 1.1 documentation permits copying and distribution with attribution and
  permits source modification and recompilation.
- R is distributed under GPL-2.0 or GPL-3.0. Installed R package license fields
  are exported into `R_PACKAGE_INVENTORY.csv` during every bundle build.
- BayArea carries an MIT license in its upstream source tree.

For GPL components, the public RASP5 release must keep the exact upstream
revision/source URL and any RASP patch available beside the binary release.
Modified lagrange-ng and BayArea patches are therefore tracked in the main RASP
repository and copied into each engine bundle.

## Critical binary fingerprints

The authoritative fingerprints are machine-validated from
`release/engine-bundle.json`. Key executable hashes for this bundle are:

| File | SHA256 |
| --- | --- |
| `engines/bayarea/bin/bayarea.exe` | `F2BAD391D9DC828C6C87D060863F8BA69BC7D9827FBE239AE1D91547BF14EC12` |
| `engines/lagrange-ng/lagrange-ng.exe` | `DD13911EED072C09D24E07FA9B8FA737B98A50C013E0EB8F1169005665BFF048` |
| `engines/bayestraits/BayesTraitsV5.exe` | `CAF64A7979E20B81DB3DBFB603CE3333C0CF8B5620A518EB7629D59350A4F997` |
| `engines/mrbayes/mb.3.2.7-win32.exe` | `A7358C7E5B906C1872C8948A89BACF5E3A1966F69ADFF57F3C5D8F6346D19E62` |
| `engines/diva/DIVA.exe` | `945620C1A56E3D386BEB3D3126A331628953B4E704B0254DE05C5E9818FF8858` |
| `engines/R/bin/Rscript.exe` | `D9134A5BEEC18CD74A55AF84D9099993594D4063208F14BE050E78EBBF85C759` |
