import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().with_name("run_phase1_spatial_checks.py")),
        run_name="__main__",
    )
