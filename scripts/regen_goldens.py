#!/usr/bin/env python3
"""Regenerate every snapshot under tests/golden/.

Run after intentional geometry or output-format changes. Diff the result
into your PR so reviewers can see exactly what shifted.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"
WIZARD = REPO_ROOT / "touchpad_wizard.py"

SIZES = [
    (50, 20, 5, 5),
    (80, 40, 8, 4),
    (30, 30, 4, 4),
    (100, 50, 10, 6),
]


def main() -> int:
    if GOLDEN_DIR.exists():
        shutil.rmtree(GOLDEN_DIR)
    GOLDEN_DIR.mkdir(parents=True)

    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    for w, h, tx, rx in SIZES:
        fp = GOLDEN_DIR / f"Trackpad-{w}x{h}mm.kicad_mod"
        sym = GOLDEN_DIR / f"Trackpad-{w}x{h}mm.kicad_sym"
        subprocess.run(
            [
                sys.executable,
                str(WIZARD),
                "emit",
                "--width",
                str(w),
                "--height",
                str(h),
                "--tx-columns",
                str(tx),
                "--rx-rows",
                str(rx),
                "--footprint",
                str(fp),
                "--symbol",
                str(sym),
            ],
            env=env,
            check=True,
        )
        print(f"  refreshed {fp.name} + {sym.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
