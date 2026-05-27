"""Tier 1 — parameter parsing and validation. No KiCad needed."""

from __future__ import annotations

import pytest

import trackpad  # noqa: F401 — applies kipy 0.7.1 workaround
from trackpad.params import TrackpadParams
from trackpad.units import Degrees, mm


class TestDefaults:
    def test_defaults_validate(self) -> None:
        assert TrackpadParams.defaults().validate() is None

    def test_defaults_have_sane_dimensions(self) -> None:
        d = TrackpadParams.defaults()
        assert d.width == mm(50)
        assert d.height == mm(20)
        assert d.edge_segments_x >= 4
        assert d.edge_segments_y >= 4

    def test_from_wizard_params_with_none_returns_defaults(self) -> None:
        params = TrackpadParams.from_wizard_params(None)
        assert params == TrackpadParams.defaults()


class TestValidation:
    def test_zero_width_rejected(self) -> None:
        import dataclasses

        bad = dataclasses.replace(TrackpadParams.defaults(), width=mm(0))
        assert bad.validate() == "width and height must be positive"

    def test_segments_below_four_rejected(self) -> None:
        import dataclasses

        bad = dataclasses.replace(TrackpadParams.defaults(), edge_segments_x=3)
        assert bad.validate() == "edge segments must be >= 4"

    def test_via_drill_too_big_rejected(self) -> None:
        import dataclasses

        bad = dataclasses.replace(
            TrackpadParams.defaults(),
            via_drill=mm(1),
            via_diameter=mm(0.5),
        )
        assert bad.validate() == "via drill must be smaller than via diameter"

    def test_clearance_too_large_rejected(self) -> None:
        import dataclasses

        bad = dataclasses.replace(
            TrackpadParams.defaults(),
            clearance=mm(100),  # bigger than the whole pad
        )
        assert "clearance" in (bad.validate() or "")


class TestFromWizardParams:
    """Verify the boundary parser ignores unknown identifiers and uses defaults for missing ones."""

    def test_partial_param_list_falls_back_to_defaults(self) -> None:
        # Build a fake WizardParameter for just `width`
        from kipy.proto.common.types.wizards_pb2 import (
            WizardParameterCategory,
            WizardParameterDataType,
        )
        from kipy.wizards import WizardParameter

        width_param = WizardParameter.create(
            identifier="width",
            name="Width",
            category=WizardParameterCategory.WPC_PACKAGE,
            data_type=WizardParameterDataType.WPDT_DISTANCE,
            value=int(mm(80)),
        )
        params = TrackpadParams.from_wizard_params([width_param])
        assert params.width == mm(80)
        # everything else should match defaults
        defaults = TrackpadParams.defaults()
        assert params.height == defaults.height
        assert params.edge_segments_x == defaults.edge_segments_x


@pytest.mark.parametrize("angle", [0, 45, 135, 270])
def test_angle_round_trip(angle: int) -> None:
    import dataclasses

    p = dataclasses.replace(TrackpadParams.defaults(), triangle_angle=Degrees(float(angle)))
    assert p.triangle_angle == float(angle)
