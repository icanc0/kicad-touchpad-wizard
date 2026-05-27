"""Typed parameter struct and the single boundary that converts kipy params into it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from trackpad.units import Degrees, Nanometers, mm

if TYPE_CHECKING:
    from kipy.wizards import WizardParameter


@dataclass(frozen=True, slots=True)
class TrackpadParams:
    """Fully resolved wizard parameters in internal units (nanometers, degrees, booleans).

    Constructed once at the wizard boundary via `from_wizard_params`. All downstream
    code consumes this struct and never touches the protobuf parameter list.
    """

    width: Nanometers
    height: Nanometers
    edge_segments_x: int
    edge_segments_y: int
    via_diameter: Nanometers
    via_drill: Nanometers
    clearance: Nanometers
    line_width: Nanometers
    drill_holes: bool
    add_lines: bool
    add_front_wiring: bool
    add_back_wiring: bool
    add_soldermask: bool
    triangle_angle: Degrees

    @classmethod
    def defaults(cls) -> TrackpadParams:
        return cls(
            width=mm(50),
            height=mm(20),
            edge_segments_x=5,
            edge_segments_y=5,
            via_diameter=mm(0.5),
            via_drill=mm(0.3),
            clearance=mm(0.2),
            line_width=mm(0.127),
            drill_holes=True,
            add_lines=True,
            add_front_wiring=True,
            add_back_wiring=True,
            add_soldermask=True,
            triangle_angle=Degrees(135.0),
        )

    @classmethod
    def from_wizard_params(cls, params: list[WizardParameter] | None) -> TrackpadParams:
        """Build from a kipy WizardParameter list. Missing entries fall back to defaults."""
        defaults = cls.defaults()
        if params is None:
            return defaults

        lookup: dict[str, WizardParameter] = {p.identifier: p for p in params}

        def get_int(identifier: str, default: int) -> int:
            p = lookup.get(identifier)
            if p is None:
                return default
            value = p.value
            return int(value) if isinstance(value, (int, float)) else default

        def get_nm(identifier: str, default: Nanometers) -> Nanometers:
            return Nanometers(get_int(identifier, int(default)))

        def get_bool(identifier: str, default: bool) -> bool:
            p = lookup.get(identifier)
            if p is None:
                return default
            value = p.value
            return bool(value) if isinstance(value, bool) else default

        def get_deg(identifier: str, default: Degrees) -> Degrees:
            p = lookup.get(identifier)
            if p is None:
                return default
            value = p.value
            if isinstance(value, (int, float)):
                return Degrees(float(value))
            return default

        return cls(
            width=get_nm("width", defaults.width),
            height=get_nm("height", defaults.height),
            edge_segments_x=get_int("edge_segments_x", defaults.edge_segments_x),
            edge_segments_y=get_int("edge_segments_y", defaults.edge_segments_y),
            via_diameter=get_nm("via_diameter", defaults.via_diameter),
            via_drill=get_nm("via_drill", defaults.via_drill),
            clearance=get_nm("clearance", defaults.clearance),
            line_width=get_nm("line_width", defaults.line_width),
            drill_holes=get_bool("drill_holes", defaults.drill_holes),
            add_lines=get_bool("add_lines", defaults.add_lines),
            add_front_wiring=get_bool("add_front_wiring", defaults.add_front_wiring),
            add_back_wiring=get_bool("add_back_wiring", defaults.add_back_wiring),
            add_soldermask=get_bool("add_soldermask", defaults.add_soldermask),
            triangle_angle=get_deg("triangle_angle", defaults.triangle_angle),
        )

    def validate(self) -> str | None:
        """Return an error message describing why the params are invalid, or None if ok."""
        if self.width <= 0 or self.height <= 0:
            return "width and height must be positive"
        if self.edge_segments_x < 4 or self.edge_segments_y < 4:
            return "edge segments must be >= 4"
        if self.clearance <= 0:
            return "clearance must be positive"
        if self.via_drill >= self.via_diameter:
            return "via drill must be smaller than via diameter"
        pad_width = self.width // (self.edge_segments_x * 2)
        pad_height = self.height // (self.edge_segments_y * 2)
        if pad_width <= self.clearance or pad_height <= self.clearance:
            return "clearance is too large for the chosen segment count"
        return None
