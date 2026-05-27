"""Tier 2 — protocol contract: invoke touchpad_wizard.py as KiCad does."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import trackpad as _trackpad  # applies kipy 0.7.1 workaround
_ = _trackpad

REPO_ROOT = Path(__file__).resolve().parents[1]
WIZARD = REPO_ROOT / "touchpad_wizard.py"


def _run(args: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + ":" + env.get("PYTHONPATH", "")
    # Always isolate the symbol library so tests don't pollute the user's home
    env.setdefault(
        "KICAD_TOUCHPAD_WIZARD_SYM_LIB", str(REPO_ROOT / "tests" / "build" / "test-sym.kicad_sym")
    )
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(WIZARD), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class TestGetInfo:
    def test_get_info_returns_zero_exit(self) -> None:
        result = _run(["--get-info"])
        assert result.returncode == 0, result.stderr

    def test_get_info_returns_valid_json(self) -> None:
        result = _run(["--get-info"])
        info = json.loads(result.stdout)
        assert info["meta"]["identifier"] == "io.github.icanc0.touchpad-wizard"
        assert info["meta"]["name"] == "Trackpad"
        assert "WCT_FOOTPRINT" in info["meta"]["types_generated"]

    def test_get_info_declares_expected_parameters(self) -> None:
        result = _run(["--get-info"])
        info = json.loads(result.stdout)
        identifiers = {p["identifier"] for p in info["parameters"]}
        expected = {
            "width",
            "height",
            "edge_segments_x",
            "edge_segments_y",
            "via_diameter",
            "via_drill",
            "clearance",
            "line_width",
            "drill_holes",
            "add_lines",
            "add_front_wiring",
            "add_back_wiring",
            "add_soldermask",
            "triangle_angle",
        }
        assert identifiers == expected

    def test_parameters_have_categories(self) -> None:
        result = _run(["--get-info"])
        info = json.loads(result.stdout)
        valid_categories = {"WPC_PACKAGE", "WPC_PADS", "WPC_RULES", "WPC_METADATA", "WPC_3DMODEL"}
        for param in info["parameters"]:
            assert param["category"] in valid_categories


class TestGenerate:
    def test_generate_with_defaults_returns_ok(self) -> None:
        result = _run(["--generate"])
        assert result.returncode == 0, result.stderr
        out = json.loads(result.stdout)
        assert out["status"] == "WGS_OK"

    def test_generate_returns_footprint(self) -> None:
        result = _run(["--generate"])
        out = json.loads(result.stdout)
        assert "Footprint" in out["content"]["@type"]
        assert out["content"]["id"]["library_nickname"] == "Trackpad"
        assert out["content"]["id"]["entry_name"] == "Trackpad-50x20mm"

    def test_generate_contains_pads_and_vias(self) -> None:
        result = _run(["--generate"])
        out = json.loads(result.stdout)
        items = out["content"]["items"]
        pads = [i for i in items if "Pad" in i["@type"]]
        # 100 SMD pads + 50 PTH via pads = 150
        assert len(pads) == 150
        smd_count = sum(1 for p in pads if p.get("type") == "PT_SMD")
        pth_count = sum(1 for p in pads if p.get("type") == "PT_PTH")
        assert smd_count == 100
        assert pth_count == 50

    def test_generate_with_invalid_params_returns_error(self) -> None:
        from google.protobuf.json_format import MessageToJson
        from kipy.proto.common.types.wizards_pb2 import (
            WizardParameterCategory,
            WizardParameterDataType,
            WizardParameterList,
        )
        from kipy.wizards import WizardParameter

        bad_width = WizardParameter.create(
            identifier="width",
            name="Width",
            category=WizardParameterCategory.WPC_PACKAGE,
            data_type=WizardParameterDataType.WPDT_DISTANCE,
            value=0,
        )
        params_list = WizardParameterList()
        params_list.parameters.append(bad_width.proto)
        params_json = MessageToJson(params_list, preserving_proto_field_name=True)

        result = _run(["--generate", "--params", params_json])
        out = json.loads(result.stdout)
        assert out["status"] == "WGS_ERROR"
        assert "width" in out["error_message"].lower()


class TestSchema:
    def test_plugin_json_validates_against_kicad_schema(self) -> None:
        import json as json_

        try:
            import jsonschema  # noqa: F401
        except ImportError:
            pytest.skip("jsonschema not installed")

        from importlib.resources import files

        from jsonschema import validate

        schema_text = (files("kipy.packaging.schemas") / "api.v1.schema.json").read_text()
        schema = json_.loads(schema_text)

        manifest = json_.loads((REPO_ROOT / "plugin.json").read_text())
        # Should not raise
        validate(instance=manifest, schema=schema)
