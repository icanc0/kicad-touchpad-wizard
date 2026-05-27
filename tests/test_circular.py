"""Tier 1 + 2 — circular trackpad geometry and CLI."""

from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import sys
from pathlib import Path

import trackpad as _trackpad  # applies kipy 0.7.1 workaround
from trackpad.circular import (
    CircularParams,
    build_circular_trackpad,
    render_circular_footprint,
)
from trackpad.geometry import Electrode
from trackpad.units import mm

_ = _trackpad  # mark the side-effect import as intentional

REPO_ROOT = Path(__file__).resolve().parents[1]
WIZARD = REPO_ROOT / "touchpad_wizard.py"


def _defaults() -> CircularParams:
    return CircularParams.defaults()


class TestParams:
    def test_defaults_validate(self) -> None:
        assert _defaults().validate() is None

    def test_inner_must_be_smaller(self) -> None:
        bad = dataclasses.replace(_defaults(), inner_radius=mm(100))
        assert bad.validate() == "outer radius must exceed inner radius"

    def test_too_few_sectors_rejected(self) -> None:
        bad = dataclasses.replace(_defaults(), sectors=2)
        assert "sectors" in (bad.validate() or "")


class TestGeometry:
    def test_default_geometry_has_expected_cell_count(self) -> None:
        params = _defaults()  # 8 sectors × 3 rings = 24 cells
        result = build_circular_trackpad(params)
        assert len(result.pads) == 24
        assert result.sectors == 8
        assert result.rings == 3

    def test_checkerboard_split_assigns_both_electrodes(self) -> None:
        result = build_circular_trackpad(_defaults())
        tx_count = sum(1 for p in result.pads if p.electrode == Electrode.TX)
        rx_count = sum(1 for p in result.pads if p.electrode == Electrode.RX)
        # 8 × 3 = 24 cells, checkerboard ≈ split half each
        assert tx_count > 0
        assert rx_count > 0
        assert tx_count + rx_count == 24

    def test_pad_numbers_follow_c_r_convention(self) -> None:
        result = build_circular_trackpad(_defaults())
        for pad in result.pads:
            prefix = "c" if pad.electrode == Electrode.TX else "r"
            assert pad.number.startswith(prefix)
            idx = int(pad.number[1:])
            assert pad.electrode_index == idx


class TestRendering:
    def test_render_produces_valid_kicad_mod_text(self) -> None:
        result = build_circular_trackpad(_defaults())
        text = render_circular_footprint(result)
        assert text.startswith('(footprint "')
        # Has custom-pad primitives (gr_poly)
        assert "gr_poly" in text
        # Has the edge-cuts circle
        assert "Edge.Cuts" in text


class TestCli:
    def test_emit_circle_writes_a_parseable_kicad_mod(self, tmp_path: Path) -> None:
        fp_path = tmp_path / "out.pretty" / "Trackpad-Circle.kicad_mod"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(
            [
                sys.executable,
                str(WIZARD),
                "emit-circle",
                "--diameter",
                "40",
                "--inner-diameter",
                "5",
                "--sectors",
                "12",
                "--rings",
                "3",
                "--footprint",
                str(fp_path),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert fp_path.exists()
        text = fp_path.read_text()
        # 12 sectors × 3 rings = 36 cells
        pad_count = len(re.findall(r'\(pad "[^"]+" smd custom', text))
        assert pad_count == 36

    def test_emit_circle_validates(self, tmp_path: Path) -> None:
        fp_path = tmp_path / "out.pretty" / "bad.kicad_mod"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(
            [
                sys.executable,
                str(WIZARD),
                "emit-circle",
                "--diameter",
                "10",
                "--inner-diameter",
                "20",
                "--footprint",
                str(fp_path),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "outer radius" in result.stderr.lower()
