"""Tier 3 — headless rendering with kicad-cli. No GUI, no display, no screen-lock interference.

Runs kicad-cli to:
  1. Validate the generated .kicad_mod parses by exporting it to SVG.
  2. Validate the generated .kicad_sym parses by exporting it to SVG.
  3. Diff against checked-in golden text outputs.

When KiCad's SVG renderer changes between versions, the binary SVG bytes will drift,
which is why we don't golden-check the SVG itself — we golden-check the deterministic
.kicad_mod / .kicad_sym text and use kicad-cli purely as a "does it parse" gate.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WIZARD = REPO_ROOT / "touchpad_wizard.py"
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"


pytestmark = pytest.mark.integration


def _have_kicad_cli() -> bool:
    return shutil.which("kicad-cli") is not None


def _emit(tmp_path: Path, **kwargs: object) -> tuple[Path, Path]:
    """Run the CLI emit subcommand. Returns (footprint_path, symbol_path)."""
    fp_path = tmp_path / "Trackpad.pretty" / "Trackpad-50x20mm.kicad_mod"
    sym_path = tmp_path / "Trackpad.kicad_sym"

    cmd = [
        sys.executable,
        str(WIZARD),
        "emit",
        "--footprint",
        str(fp_path),
        "--symbol",
        str(sym_path),
    ]
    for k, v in kwargs.items():
        cmd.extend([f"--{k.replace('_', '-')}", str(v)])

    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    subprocess.run(cmd, check=True, env=env)
    return fp_path, sym_path


def _strip_nondeterministic(text: str) -> str:
    """Remove fields that legitimately change run-to-run."""
    # KiCad writes timestamps and uuids on save, but we don't (we render to text directly).
    # Keep this hook in case future emitters add anything dynamic.
    return text


class TestKicadModRenders:
    def test_emit_then_kicad_cli_fp_export_svg(self, tmp_path: Path) -> None:
        if not _have_kicad_cli():
            pytest.skip("kicad-cli not installed")

        fp_path, _ = _emit(tmp_path)
        out_dir = tmp_path / "svg"
        out_dir.mkdir()

        result = subprocess.run(
            [
                "kicad-cli",
                "fp",
                "export",
                "svg",
                "--output",
                str(out_dir),
                str(fp_path.parent),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        svg = out_dir / "Trackpad-50x20mm.svg"
        assert svg.exists(), f"expected {svg} from kicad-cli output"
        assert svg.stat().st_size > 1000  # non-trivial SVG

    def test_emit_then_kicad_cli_sym_export_svg(self, tmp_path: Path) -> None:
        if not _have_kicad_cli():
            pytest.skip("kicad-cli not installed")

        _, sym_path = _emit(tmp_path)
        out_dir = tmp_path / "sym-svg"
        out_dir.mkdir()

        result = subprocess.run(
            [
                "kicad-cli",
                "sym",
                "export",
                "svg",
                "--output",
                str(out_dir),
                str(sym_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        # The output filename pattern is "<symbol_name>_unit1.svg"
        svgs = list(out_dir.glob("*.svg"))
        assert svgs, f"expected at least one SVG in {out_dir}"


class TestGoldenFootprint:
    """The .kicad_mod text is deterministic. Diff against the checked-in golden."""

    def test_default_footprint_matches_golden(self, tmp_path: Path) -> None:
        fp_path, _ = _emit(tmp_path)
        actual = _strip_nondeterministic(fp_path.read_text())
        golden = GOLDEN_DIR / "Trackpad-50x20mm.kicad_mod"
        if not golden.exists():
            golden.parent.mkdir(parents=True, exist_ok=True)
            golden.write_text(actual)
            pytest.skip(f"created golden at {golden}; re-run to compare")
        expected = _strip_nondeterministic(golden.read_text())
        if actual != expected:
            # Helpful diff on failure
            import difflib

            diff = "\n".join(
                difflib.unified_diff(
                    expected.splitlines(),
                    actual.splitlines(),
                    fromfile=str(golden),
                    tofile=str(fp_path),
                    lineterm="",
                )
            )
            pytest.fail("footprint diverged from golden:\n" + diff)


class TestGoldenSymbol:
    def test_default_symbol_matches_golden(self, tmp_path: Path) -> None:
        _, sym_path = _emit(tmp_path)
        actual = _strip_nondeterministic(sym_path.read_text())
        golden = GOLDEN_DIR / "Trackpad-50x20mm.kicad_sym"
        if not golden.exists():
            golden.parent.mkdir(parents=True, exist_ok=True)
            golden.write_text(actual)
            pytest.skip(f"created golden at {golden}; re-run to compare")
        expected = _strip_nondeterministic(golden.read_text())
        if actual != expected:
            import difflib

            diff = "\n".join(
                difflib.unified_diff(
                    expected.splitlines(),
                    actual.splitlines(),
                    fromfile=str(golden),
                    tofile=str(sym_path),
                    lineterm="",
                )
            )
            pytest.fail("symbol diverged from golden:\n" + diff)


class TestPinNumbersMatchPadNumbers:
    """The whole reason this rewrite exists: pad numbers and symbol pin numbers line up."""

    def test_pads_and_pins_share_numbers(self, tmp_path: Path) -> None:
        fp_path, sym_path = _emit(tmp_path)
        fp_text = fp_path.read_text()
        sym_text = sym_path.read_text()

        pad_numbers = set(re.findall(r'\(pad "([^"]+)"', fp_text))
        pin_numbers = set(re.findall(r'\(number "([^"]+)"', sym_text))

        # Every pin must have a matching pad. Pads include via pads which share numbers
        # with their associated electrode pad, so set equality is the right check.
        assert pin_numbers <= pad_numbers, f"orphan pins: {pin_numbers - pad_numbers}"
        # And every electrode (T*/R*) must have at least one pin
        electrode_pads = {n for n in pad_numbers if re.match(r"^[TR]\d+$", n)}
        assert pin_numbers == electrode_pads
