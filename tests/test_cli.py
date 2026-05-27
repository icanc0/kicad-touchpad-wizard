"""Tier 2 — CLI emit subcommand.

Exercises the standalone `python touchpad_wizard.py emit ...` flow that users hit
when they don't want to set up KiCad's plugin system.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import trackpad  # noqa: F401 — applies kipy 0.7.1 workaround

REPO_ROOT = Path(__file__).resolve().parents[1]
WIZARD = REPO_ROOT / "touchpad_wizard.py"


def _run_emit(tmp_path: Path, *extra_args: str) -> tuple[Path, Path]:
    fp_path = tmp_path / "out.pretty" / "Trackpad.kicad_mod"
    sym_path = tmp_path / "out.kicad_sym"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    cmd = [
        sys.executable,
        str(WIZARD),
        "emit",
        "--footprint",
        str(fp_path),
        "--symbol",
        str(sym_path),
        *extra_args,
    ]
    subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
    return fp_path, sym_path


class TestEmitDefaults:
    def test_defaults_produce_files(self, tmp_path: Path) -> None:
        fp, sym = _run_emit(tmp_path)
        assert fp.exists()
        assert sym.exists()
        assert fp.read_text().startswith('(footprint ')
        assert sym.read_text().startswith("(kicad_symbol_lib")

    def test_default_pad_count(self, tmp_path: Path) -> None:
        fp, _ = _run_emit(tmp_path)
        pads = re.findall(r'\(pad "[^"]+"', fp.read_text())
        # 100 SMD electrode pads + 50 PTH via pads at default 5×5
        assert len(pads) == 150


class TestEmitCustomSizes:
    def test_8x4_grid(self, tmp_path: Path) -> None:
        fp, _ = _run_emit(
            tmp_path,
            "--width",
            "80",
            "--height",
            "40",
            "--tx-columns",
            "8",
            "--rx-rows",
            "4",
        )
        text = fp.read_text()
        # 8 TX cols × 2 edges × 4 rows = 64 TX pads
        # 4 RX rows × 2 edges × 8 cols = 64 RX pads
        # Plus 8 × 4 × 2 = 64 vias
        # Total 192 pads
        pads = re.findall(r'\(pad "[^"]+"', text)
        assert len(pads) == 192

        tx_numbers = {m.group(1) for m in re.finditer(r'\(pad "(c\d+)"', text)}
        rx_numbers = {m.group(1) for m in re.finditer(r'\(pad "(r\d+)"', text)}
        assert tx_numbers == {f"c{i}" for i in range(8)}
        assert rx_numbers == {f"r{i}" for i in range(4)}

    def test_no_drill_holes(self, tmp_path: Path) -> None:
        fp, _ = _run_emit(tmp_path, "--no-drill-holes")
        text = fp.read_text()
        # Should have no thru_hole pads
        assert "thru_hole" not in text


class TestEmitErrors:
    def test_invalid_segments_returns_nonzero(self, tmp_path: Path) -> None:
        fp_path = tmp_path / "out.pretty" / "Trackpad.kicad_mod"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(
            [
                sys.executable,
                str(WIZARD),
                "emit",
                "--footprint",
                str(fp_path),
                "--tx-columns",
                "1",  # below minimum of 4
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "edge segments" in result.stderr.lower()


class TestPinPadAlignment:
    """The whole reason this rewrite exists — verify across sizes."""

    @pytest.mark.parametrize(
        ("w", "h", "tx", "rx"),
        [
            (50, 20, 5, 5),
            (80, 40, 8, 4),
            (30, 30, 4, 4),
            (100, 50, 10, 6),
        ],
    )
    def test_pin_numbers_equal_electrode_pad_numbers(
        self, tmp_path: Path, w: int, h: int, tx: int, rx: int
    ) -> None:
        fp, sym = _run_emit(
            tmp_path,
            "--width",
            str(w),
            "--height",
            str(h),
            "--tx-columns",
            str(tx),
            "--rx-rows",
            str(rx),
        )
        fp_text = fp.read_text()
        sym_text = sym.read_text()

        pad_numbers = set(re.findall(r'\(pad "([^"]+)"', fp_text))
        electrode_pads = {n for n in pad_numbers if re.match(r"^[cr]\d+$", n)}
        pin_numbers = set(re.findall(r'\(number "([^"]+)"', sym_text))
        assert pin_numbers == electrode_pads
