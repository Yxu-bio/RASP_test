# Bundled Python runtime inventory

RASP5 5.0 freezes a Python 3.6.13 Windows runtime instead of requiring a user
Python installation. `PYTHON_RUNTIME_PACKAGES.csv` is generated mechanically
from that runtime's `conda-meta/*.json` records and installed Python
distribution metadata.

The CSV intentionally keeps two record types:

- `conda-package` covers the interpreter, native libraries, and packages
  installed by Conda;
- `python-distribution` covers importable distributions represented by
  `.dist-info` or `.egg-info` metadata, including packages installed with pip.

Some software appears in both layers, and package names can differ between a
Conda package and its Python distribution. These rows are evidence records, not
a deduplicated dependency graph. `NOT_REPORTED` means the upstream package
metadata did not provide that field; it does not imply that the package has no
license.

The frozen runtime retains package license and metadata files. This inventory
does not replace their license terms and is not a legal compatibility opinion.
In particular, the recorded PyQt5 distribution is GPLv3/commercial software;
the public installer's aggregate licensing must be reviewed before an official
release is described as license-cleared.
Regenerate it whenever the runtime prefix changes:

```powershell
python tools\build_python_runtime_inventory.py `
  --prefix <runtime-prefix> `
  --output release\PYTHON_RUNTIME_PACKAGES.csv
```

RASP5 also vendors ETE 3.1.3 in the application source. Its GPL-3.0-or-later
notice and full GPLv3 text are kept beside the vendored package under
`infrastructure/tree/backend/ete3_vendor`.
