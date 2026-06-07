#!/usr/bin/env python3
"""Regenerate the connection-style reference gallery under artifacts/connection-styles/.

Renders the footprint produced by every `--connection-style` (apex / edge /
center) across a few representative grids, plus the matching symbol, and builds
a side-by-side comparison montage per grid. Use it to eyeball the feature and
confirm nothing's visually wrong after a geometry or symbol change. Every image
here is regenerable — re-run this script and diff the result into your PR.

Requires `kicad-cli` (SVG export), `resvg` (rasterize), and `montage`
(ImageMagick, for the comparison strips). Skips renders gracefully if missing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WIZARD = REPO_ROOT / "touchpad_wizard.py"
GALLERY = REPO_ROOT / "artifacts" / "connection-styles"

STYLES = ["apex", "edge", "center"]


@dataclass(frozen=True)
class Variant:
    width: int
    height: int
    tx: int
    rx: int
    note: str  # why this variant is in the gallery

    @property
    def grid(self) -> str:
        return f"Trackpad-{self.width}x{self.height}-{self.tx}x{self.rx}"


# Representative cases — keep this list small and meaningful so the gallery
# stays quick to scan rather than exhaustive.
VARIANTS = [
    Variant(45, 45, 5, 5, "card-size 5x5 (matches the business-card trackpad)"),
    Variant(50, 20, 5, 5, "wide non-square — landings on a different aspect ratio"),
    Variant(45, 45, 6, 6, "v2 6x6 — denser grid, more perimeter landings"),
]


def _env() -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, env=_env(), check=True, capture_output=True)


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _emit(variant: Variant, style: str, fp_path: Path, sym_path: Path) -> None:
    fp_path.parent.mkdir(parents=True, exist_ok=True)
    sym_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable,
            str(WIZARD),
            "emit",
            "--width",
            str(variant.width),
            "--height",
            str(variant.height),
            "--tx-columns",
            str(variant.tx),
            "--rx-rows",
            str(variant.rx),
            "--connection-style",
            style,
            "--footprint",
            str(fp_path),
            "--symbol",
            str(sym_path),
        ]
    )


def _render_footprint_png(pretty: Path, out_png: Path) -> bool:
    if not (_have("kicad-cli") and _have("resvg")):
        return False
    svg_dir = out_png.parent / "_svg_tmp"
    svg_dir.mkdir(parents=True, exist_ok=True)
    _run(["kicad-cli", "fp", "export", "svg", "--output", str(svg_dir), str(pretty)])
    svgs = sorted(svg_dir.glob("*.svg"))
    if not svgs:
        shutil.rmtree(svg_dir, ignore_errors=True)
        return False
    out_png.parent.mkdir(parents=True, exist_ok=True)
    _run(["resvg", "--width", "800", str(svgs[0]), str(out_png)])
    shutil.rmtree(svg_dir, ignore_errors=True)
    return True


def _render_symbol_png(sym_path: Path, out_png: Path) -> bool:
    if not (_have("kicad-cli") and _have("resvg")):
        return False
    svg_dir = out_png.parent / "_svg_tmp"
    svg_dir.mkdir(parents=True, exist_ok=True)
    _run(["kicad-cli", "sym", "export", "svg", "--output", str(svg_dir), str(sym_path)])
    svgs = sorted(svg_dir.glob("*.svg"))
    if not svgs:
        shutil.rmtree(svg_dir, ignore_errors=True)
        return False
    out_png.parent.mkdir(parents=True, exist_ok=True)
    _run(["resvg", "--width", "600", str(svgs[0]), str(out_png)])
    shutil.rmtree(svg_dir, ignore_errors=True)
    return True


def _montage(pngs: list[Path], out: Path, tile: str) -> None:
    if not pngs or not _have("montage"):
        return
    subprocess.run(
        [
            "montage",
            *[str(p) for p in pngs],
            "-tile",
            tile,
            "-geometry",
            "800x800+12+12",
            "-label",
            "%t",
            "-background",
            "white",
            str(out),
        ],
        check=True,
        capture_output=True,
    )


def main() -> int:
    if GALLERY.exists():
        shutil.rmtree(GALLERY)
    (GALLERY / "footprints").mkdir(parents=True)
    (GALLERY / "symbols").mkdir(parents=True)

    work = GALLERY / "_work"
    print(f"Regenerating {GALLERY.relative_to(REPO_ROOT)}/")

    for variant in VARIANTS:
        style_pngs: list[Path] = []
        for style in STYLES:
            pretty = work / f"{variant.grid}-{style}" / "Trackpad.pretty"
            fp_path = pretty / f"{variant.grid}.kicad_mod"
            sym_path = work / f"{variant.grid}-{style}" / "sym.kicad_sym"
            _emit(variant, style, fp_path, sym_path)

            fp_png = GALLERY / "footprints" / f"{variant.grid}-{style}.png"
            if _render_footprint_png(pretty, fp_png):
                style_pngs.append(fp_png)
            print(f"  {variant.grid}  style={style}")

            # The symbol is style-independent — render it once per grid.
            if style == STYLES[0]:
                _render_symbol_png(sym_path, GALLERY / "symbols" / f"{variant.grid}.png")

        # Side-by-side apex | edge | center for this grid.
        _montage(style_pngs, GALLERY / f"compare-{variant.grid}.png", tile=f"{len(style_pngs)}x1")

    shutil.rmtree(work, ignore_errors=True)
    (GALLERY / "README.md").write_text(_readme(), encoding="utf-8")
    print(f"Done. See {GALLERY.relative_to(REPO_ROOT)}/README.md")
    return 0


def _readme() -> str:
    rows = "\n".join(f"- `compare-{v.grid}.png` — {v.note}" for v in VARIANTS)
    return f"""# Connection-style reference gallery

Visual references for the `--connection-style` feature (the perimeter
connection/alignment landings). **Regenerate with**
`python scripts/regen_connection_gallery.py` and diff the result so any visual
change is reviewable.

## What each style is

- **apex** — no extra landing (original behavior). Electrodes are tied together
  only by the apex vias (`v_c*`). This is the default.
- **edge** — a copper pad spanning the *whole outer edge* of each perimeter
  triangle, flush to the trackpad boundary.
- **center** — a *small* pad at the midpoint of each perimeter triangle's outer
  edge (an alignment aid).

Landings sit on the electrode net (`c*` / `r*`) and appear at **both ends** of
every electrode — the sensor is self-capacitance, so either end is electrically
identical. They follow the trackpad's solder-mask setting (covered by default,
same as the triangles — no exposed copper on the finger surface).

## Layout

- `compare-<grid>.png` — apex | edge | center side by side for one grid. Start here.
- `footprints/<grid>-<style>.png` — individual footprint renders.
- `symbols/<grid>.png` — the matching symbol (style-independent): TX on top &
  bottom, RX on left & right, each electrode exposed as two same-numbered pins.

## Comparison strips

{rows}

## What to check

1. **edge**: a strip hugs all four boundaries, one per perimeter triangle, with
   small gaps at the corners (no TX↔RX bridge). Covered by mask (no exposed
   copper), so it reads as solid with the triangles, not as a separate opening.
2. **center**: a small pad sits at the midpoint of each outer edge, on all four
   sides — and at both ends of every electrode.
3. **apex**: identical to the pre-feature output (no perimeter landings).
4. **symbol**: every TX column number (`c*`) appears on both the top and bottom
   edges; every RX row number (`r*`) on both the left and right; the
   self-capacitance note is present.
"""


if __name__ == "__main__":
    sys.exit(main())
