"""Tests for the action-plugin GUI: pure preview math + an Xvfb construction smoke test."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from trackpad.action_gui import compute_preview
from trackpad.geometry import build_trackpad
from trackpad.params import TrackpadParams

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestComputePreview:
    def test_everything_fits_inside_canvas(self) -> None:
        params = TrackpadParams.defaults()
        trackpad = build_trackpad(params)
        shapes = compute_preview(trackpad, int(params.width), int(params.height), 460, 300, 16)

        xs: list[float] = []
        ys: list[float] = []
        for coords in shapes.polygons_front:
            xs.extend(coords[0::2])
            ys.extend(coords[1::2])
        for x0, y0, x1, y1, _ in shapes.circles:
            xs.extend((x0, x1))
            ys.extend((y0, y1))
        assert min(xs) >= 0
        assert max(xs) <= 460
        assert min(ys) >= 0
        assert max(ys) <= 300

    def test_aspect_ratio_preserved(self) -> None:
        params = TrackpadParams.defaults()  # 50x20 -> 2.5:1
        trackpad = build_trackpad(params)
        shapes = compute_preview(trackpad, int(params.width), int(params.height), 460, 300, 16)
        x0, y0, x1, y1 = shapes.outline
        assert (x1 - x0) / (y1 - y0) == pytest.approx(2.5, rel=1e-6)

    def test_pad_count_matches_geometry(self) -> None:
        params = TrackpadParams.defaults()
        trackpad = build_trackpad(params)
        shapes = compute_preview(trackpad, int(params.width), int(params.height))
        assert len(shapes.polygons_front) == len(trackpad.pads)
        # one copper ring + one drill hole per via
        assert len(shapes.circles) == 2 * len(trackpad.vias)


@pytest.mark.integration
class TestDialogSmoke:
    def test_dialog_constructs_and_draws_under_xvfb(self, tmp_path: Path) -> None:
        if shutil.which("xvfb-run") is None:
            pytest.skip("xvfb-run not installed")
        (tmp_path / "demo.kicad_pro").write_text("{}", encoding="utf-8")
        script = (
            "import tkinter as tk\n"
            "from pathlib import Path\n"
            "from trackpad.action_gui import TrackpadDialog\n"
            f"root = tk.Tk()\n"
            f"dialog = TrackpadDialog(root, Path({str(tmp_path)!r}))\n"
            "root.update()\n"  # let the after()-scheduled redraw run
            "root.after(300, root.destroy)\n"
            "root.mainloop()\n"
            "print('SMOKE-OK')\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(
            ["xvfb-run", "-a", sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "SMOKE-OK" in result.stdout
