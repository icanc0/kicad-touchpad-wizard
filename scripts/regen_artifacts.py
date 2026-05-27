#!/usr/bin/env python3
"""Regenerate the artifacts/ gallery from scratch.

Produces ready-to-use KiCad libraries (.pretty dirs containing many .kicad_mod
files) plus per-variant PNG previews and a tiled montage for each shape family.

Requires `kicad-cli` (for SVG export) and `resvg` (for PNG rasterization) and
`montage` (ImageMagick) on PATH. Skips steps gracefully if any are missing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "artifacts"
WIZARD = REPO_ROOT / "touchpad_wizard.py"


@dataclass(frozen=True)
class RectVariant:
    width: int
    height: int
    tx: int
    rx: int

    @property
    def name(self) -> str:
        return f"Trackpad-{self.width}x{self.height}-{self.tx}x{self.rx}"


@dataclass(frozen=True)
class CircleVariant:
    diameter: int
    inner_diameter: int
    sectors: int
    rings: int

    @property
    def name(self) -> str:
        return f"Trackpad-Circular-d{self.diameter}-i{self.inner_diameter}-{self.sectors}x{self.rings}"


RECTANGLES = [
    RectVariant(20, 20, 4, 4),
    RectVariant(30, 30, 4, 4),
    RectVariant(30, 30, 6, 6),
    RectVariant(50, 50, 5, 5),
    RectVariant(50, 50, 8, 8),
    RectVariant(60, 60, 6, 6),
    RectVariant(100, 100, 10, 10),
    RectVariant(150, 150, 12, 12),
    RectVariant(100, 20, 10, 4),
    RectVariant(100, 40, 10, 5),
    RectVariant(150, 40, 15, 4),
    RectVariant(20, 80, 4, 8),
    RectVariant(40, 80, 5, 8),
    RectVariant(85, 55, 8, 5),
    RectVariant(85, 40, 8, 4),
    RectVariant(70, 30, 7, 5),
]

CIRCLES = [
    CircleVariant(30, 0, 6, 2),
    CircleVariant(30, 5, 8, 2),
    CircleVariant(40, 0, 8, 3),
    CircleVariant(50, 6, 8, 3),
    CircleVariant(50, 10, 12, 3),
    CircleVariant(60, 0, 16, 4),
    CircleVariant(60, 8, 12, 4),
    CircleVariant(80, 10, 16, 5),
    CircleVariant(80, 20, 8, 3),
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


def emit_rectangles(target: Path) -> Path:
    pretty = target / "Trackpad-Rectangular.pretty"
    pretty.mkdir(parents=True, exist_ok=True)
    symbol_lib = target / "Trackpad-Rectangular.kicad_sym"
    print(f"  rectangular: writing into {pretty}")
    for v in RECTANGLES:
        _run(
            [
                sys.executable,
                str(WIZARD),
                "emit",
                "--width",
                str(v.width),
                "--height",
                str(v.height),
                "--tx-columns",
                str(v.tx),
                "--rx-rows",
                str(v.rx),
                "--footprint",
                str(pretty / f"{v.name}.kicad_mod"),
                "--symbol",
                str(symbol_lib),
            ]
        )
    return pretty


def emit_circles(target: Path) -> Path:
    pretty = target / "Trackpad-Circular.pretty"
    pretty.mkdir(parents=True, exist_ok=True)
    print(f"  circular: writing into {pretty}")
    for v in CIRCLES:
        _run(
            [
                sys.executable,
                str(WIZARD),
                "emit-circle",
                "--diameter",
                str(v.diameter),
                "--inner-diameter",
                str(v.inner_diameter),
                "--sectors",
                str(v.sectors),
                "--rings",
                str(v.rings),
                "--footprint",
                str(pretty / f"{v.name}.kicad_mod"),
            ]
        )
    return pretty


def render_pngs(pretty: Path, png_dir: Path) -> list[Path]:
    if not _have("kicad-cli") or not _have("resvg"):
        print("  (skipping renders: kicad-cli or resvg missing)")
        return []
    svg_dir = png_dir.parent / f"{png_dir.name}-svg-tmp"
    svg_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)
    _run(["kicad-cli", "fp", "export", "svg", "--output", str(svg_dir), str(pretty)])
    pngs: list[Path] = []
    for svg in sorted(svg_dir.glob("*.svg")):
        png = png_dir / f"{svg.stem}.png"
        _run(["resvg", "--width", "800", str(svg), str(png)])
        pngs.append(png)
    shutil.rmtree(svg_dir, ignore_errors=True)
    return pngs


def make_montage(pngs: list[Path], out: Path, tile: str) -> None:
    if not pngs or not _have("montage"):
        return
    subprocess.run(
        [
            "montage",
            *[str(p) for p in pngs],
            "-tile",
            tile,
            "-geometry",
            "800x800+10+10",
            "-label",
            "%t",
            "-background",
            "white",
            str(out),
        ],
        check=True,
        capture_output=True,
    )


def emit_50x50_board(target: Path) -> None:
    """The 50x50 + Gerbers showcase."""
    print(f"  50x50-board-with-gerbers: writing into {target}")
    target.mkdir(parents=True, exist_ok=True)
    pretty = target / "Trackpad.pretty"
    pretty.mkdir(exist_ok=True)
    fp_path = pretty / "Trackpad-50x50mm.kicad_mod"
    sym_path = target / "touchpad-wizard.kicad_sym"
    _run(
        [
            sys.executable,
            str(WIZARD),
            "emit",
            "--width",
            "50",
            "--height",
            "50",
            "--tx-columns",
            "5",
            "--rx-rows",
            "5",
            "--footprint",
            str(fp_path),
            "--symbol",
            str(sym_path),
        ]
    )

    board_path = target / "board.kicad_pcb"
    _write_board_embedding(fp_path, board_path)

    if _have("kicad-cli"):
        gerbers = target / "gerbers"
        gerbers.mkdir(exist_ok=True)
        _run(
            [
                "kicad-cli",
                "pcb",
                "export",
                "gerbers",
                "--output",
                str(gerbers) + "/",
                "--layers",
                "F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts",
                "--no-protel-ext",
                str(board_path),
            ]
        )
        # Tarball
        tar_path = target / "trackpad-gerbers.tar.gz"
        subprocess.run(
            ["tar", "-czf", str(tar_path), "-C", str(gerbers), "."],
            check=True,
            capture_output=True,
        )

        # PCB color render
        svg_path = target / "board.svg"
        _run(
            [
                "kicad-cli",
                "pcb",
                "export",
                "svg",
                "--output",
                str(svg_path),
                "--layers",
                "F.Cu,B.Cu,F.Mask",
                "--page-size-mode",
                "2",
                str(board_path),
            ]
        )
        if _have("resvg"):
            _run(["resvg", "--width", "1600", str(svg_path), str(target / "board.png")])
            svg_path.unlink()


def _write_board_embedding(fp_path: Path, board_path: Path) -> None:
    """Minimal .kicad_pcb that embeds the footprint at center for Gerber export."""
    fp_text = fp_path.read_text()
    fp_lines = fp_text.splitlines()
    embedded = "\n".join(["  " + ln for ln in [fp_lines[0], "  (at 125 125)", *fp_lines[1:]]])

    board_text = """(kicad_pcb (version 20240108) (generator "manual")
  (general (thickness 1.6))
  (paper "A4")
  (layers
    (0 "F.Cu" signal) (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive") (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user) (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user) (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1") (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user) (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user) (49 "F.Fab" user))
  (setup (pad_to_mask_clearance 0))
  (net 0 "")
  (gr_rect (start 75 75) (end 175 175) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts"))
"""
    board_text += embedded + "\n)\n"
    board_path.write_text(board_text, encoding="utf-8")


def main() -> int:
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir()

    print("Regenerating artifacts/")

    rect_dir = ARTIFACTS / "rectangular"
    pretty = emit_rectangles(rect_dir)
    pngs = render_pngs(pretty, rect_dir / "png")
    make_montage(pngs, rect_dir / "gallery.png", tile="4x4")

    circle_dir = ARTIFACTS / "circular"
    pretty = emit_circles(circle_dir)
    pngs = render_pngs(pretty, circle_dir / "png")
    make_montage(pngs, circle_dir / "gallery.png", tile="3x3")

    emit_50x50_board(ARTIFACTS / "50x50-board-with-gerbers")

    (ARTIFACTS / "README.md").write_text(_readme(), encoding="utf-8")
    print("\nDone. artifacts/ regenerated.")
    return 0


def _readme() -> str:
    return """# Artifacts

Pre-rendered example outputs from the trackpad wizard. Every file here is
regenerable — run `python scripts/regen_artifacts.py` to refresh from current
source. Committed so you can browse the gallery on GitHub without checking out
the repo and running anything.

## Layout

- `rectangular/Trackpad-Rectangular.pretty/` — 16 footprints in one KiCad
  library, ready to drop into a project. Sizes range from 20×20 mm (4×4
  electrodes) up to 150×150 (12×12), with aspect-ratio variants for
  business-card and slider-strip use cases.
- `rectangular/Trackpad-Rectangular.kicad_sym` — symbol library containing
  the matching schematic symbols for every footprint above. Same `c0..c{n-1}`
  / `r0..r{m-1}` pin numbers as the pads.
- `rectangular/png/` — one PNG per variant. `gallery.png` is the tiled
  4×4 comparison.
- `circular/Trackpad-Circular.pretty/` — 9 circular trackpad footprints from
  30 mm to 80 mm diameter, varying sector × ring density. Annular-sector
  custom polygon pads.
- `circular/png/`, `circular/gallery.png` — same idea.
- `50x50-board-with-gerbers/` — the full manufacturing-ready bundle for the
  50×50 showcase variant: footprint, matching symbol, minimal `.kicad_pcb`
  embedding it, rendered preview, and a Gerber pack tarball you can upload
  directly to JLCPCB / PCBWay / OSHPark.

## Using as a library

Add the `.pretty` dirs to your project via KiCad → Preferences → Manage
Footprint Libraries → Add. The `.kicad_sym` file goes into Manage Symbol
Libraries the same way.
"""


if __name__ == "__main__":
    sys.exit(main())
