"""Tier 1 — pure geometry. Property-based via hypothesis."""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from trackpad.geometry import Electrode, Layer, build_trackpad
from trackpad.params import TrackpadParams
from trackpad.units import Degrees, mm


def _params(
    width_mm: float = 50.0,
    height_mm: float = 20.0,
    seg_x: int = 5,
    seg_y: int = 5,
    **overrides: object,
) -> TrackpadParams:
    base = dataclasses.replace(
        TrackpadParams.defaults(),
        width=mm(width_mm),
        height=mm(height_mm),
        edge_segments_x=seg_x,
        edge_segments_y=seg_y,
    )
    return dataclasses.replace(base, **overrides) if overrides else base


class TestDefaults:
    def test_default_geometry_has_expected_counts(self) -> None:
        trackpad = build_trackpad(_params())
        # 5 TX cols × 2 edges × 5 rows = 50 TX pads
        # 5 RX rows × 2 edges × 5 cols = 50 RX pads
        # Total 100 pads
        assert len(trackpad.pads) == 100
        # 5 cols × 5 rows × 2 edges = 50 vias when drill_holes=True
        assert len(trackpad.vias) == 50
        # 5 front lines (RX rows) + 25 back segments (TX columns × top rows)
        assert sum(1 for s in trackpad.segments if s.layer == Layer.F_CU) == 5
        assert sum(1 for s in trackpad.segments if s.layer == Layer.B_CU) == 25

    def test_pad_numbers_are_partitioned_by_electrode(self) -> None:
        trackpad = build_trackpad(_params())
        tx_numbers = {p.number for p in trackpad.pads if p.electrode == Electrode.TX}
        rx_numbers = {p.number for p in trackpad.pads if p.electrode == Electrode.RX}
        # All pads in column i share number `c{i}` — that's intentional, each column
        # is a single capacitive electrode (one net) made up of many trapezoid pads.
        assert tx_numbers == {f"c{i}" for i in range(5)}
        assert rx_numbers == {f"r{i}" for i in range(5)}
        # TX and RX namespaces must not collide.
        assert not (tx_numbers & rx_numbers)


class TestOptions:
    def test_no_drill_holes_drops_vias(self) -> None:
        trackpad = build_trackpad(_params(drill_holes=False))
        assert trackpad.vias == []

    def test_no_front_wiring_drops_front_segments(self) -> None:
        trackpad = build_trackpad(_params(add_front_wiring=False))
        assert all(s.layer != Layer.F_CU for s in trackpad.segments)

    def test_no_back_wiring_drops_back_segments(self) -> None:
        trackpad = build_trackpad(_params(add_back_wiring=False))
        assert all(s.layer != Layer.B_CU for s in trackpad.segments)


@st.composite
def trackpad_params(draw: st.DrawFn) -> TrackpadParams:
    """Generate valid TrackpadParams for property testing."""
    width = draw(st.integers(min_value=5, max_value=200))
    height = draw(st.integers(min_value=5, max_value=200))
    seg_x = draw(st.integers(min_value=4, max_value=10))
    seg_y = draw(st.integers(min_value=4, max_value=10))
    angle = draw(st.sampled_from([0.0, 45.0, 90.0, 135.0, 180.0]))
    params = _params(
        width_mm=float(width),
        height_mm=float(height),
        seg_x=seg_x,
        seg_y=seg_y,
        triangle_angle=Degrees(angle),
    )
    return params


class TestProperties:
    @given(trackpad_params())
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_all_params_produce_valid_trackpad(self, params: TrackpadParams) -> None:
        if params.validate() is not None:
            pytest.skip("validation rejected")
        trackpad = build_trackpad(params)
        assert trackpad.tx_count == params.edge_segments_x
        assert trackpad.rx_count == params.edge_segments_y

    @given(trackpad_params())
    def test_pad_numbers_correspond_to_electrode_index(self, params: TrackpadParams) -> None:
        if params.validate() is not None:
            pytest.skip("validation rejected")
        trackpad = build_trackpad(params)
        for pad in trackpad.pads:
            expected_prefix = "c" if pad.electrode == Electrode.TX else "r"
            assert pad.number == f"{expected_prefix}{pad.electrode_index}"

    @given(trackpad_params())
    def test_pads_stay_within_bounding_box(self, params: TrackpadParams) -> None:
        if params.validate() is not None:
            pytest.skip("validation rejected")
        trackpad = build_trackpad(params)
        # 10% margin allowed for the trapezoid extending past the nominal grid
        half_w = params.width // 2 + params.width // 10
        half_h = params.height // 2 + params.height // 10
        for pad in trackpad.pads:
            assert -half_w <= pad.position.x <= half_w
            assert -half_h <= pad.position.y <= half_h

    @given(trackpad_params())
    def test_vias_only_at_tx_columns(self, params: TrackpadParams) -> None:
        if params.validate() is not None:
            pytest.skip("validation rejected")
        trackpad = build_trackpad(params)
        # Vias are named `v_c{i}` (the original convention) — one per TX column.
        expected = {f"v_c{i}" for i in range(trackpad.tx_count)}
        for via in trackpad.vias:
            assert via.associated_pad_number in expected
