"""Pure-function geometry layer.

Given typed TrackpadParams, returns lists of typed PadSpec/ViaSpec/SegmentSpec dataclasses.
No kipy imports here — this module is testable without KiCad.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from trackpad.params import TrackpadParams
from trackpad.units import Degrees, Nanometers


class Layer(Enum):
    F_CU = "F.Cu"
    B_CU = "B.Cu"


class Electrode(Enum):
    """Which axis of the capacitive sensor an electrode belongs to."""

    TX = "TX"  # columns, top/bottom edges
    RX = "RX"  # rows, left/right edges


@dataclass(frozen=True, slots=True)
class Point:
    x: Nanometers
    y: Nanometers


@dataclass(frozen=True, slots=True)
class PadSpec:
    """A trapezoidal SMD touch pad. Pad numbers are unique by construction."""

    number: str
    pin_name: str
    electrode: Electrode
    electrode_index: int  # 1-based column/row this pad belongs to
    position: Point
    size_x: Nanometers
    size_y: Nanometers
    trapezoid_delta: Nanometers
    angle: Degrees
    masked: bool


@dataclass(frozen=True, slots=True)
class ViaSpec:
    """A plated through-hole used to route a top electrode column to the back layer."""

    associated_pad_number: str
    position: Point
    diameter: Nanometers
    drill: Nanometers


@dataclass(frozen=True, slots=True)
class SegmentSpec:
    """A straight copper trace inside the footprint."""

    start: Point
    end: Point
    layer: Layer
    width: Nanometers


@dataclass(frozen=True, slots=True)
class Trackpad:
    """The full set of items the wizard generates for one trackpad."""

    pads: list[PadSpec]
    vias: list[ViaSpec]
    segments: list[SegmentSpec]
    tx_count: int  # number of TX columns
    rx_count: int  # number of RX rows


def build_trackpad(params: TrackpadParams) -> Trackpad:
    """Translate parameters into pure geometric specs."""
    width = params.width
    height = params.height
    seg_x = params.edge_segments_x
    seg_y = params.edge_segments_y
    clearance = params.clearance
    half_clearance = Nanometers(clearance // 2)

    pad_width = Nanometers(width // (seg_x * 2))
    pad_height = Nanometers(height // (seg_y * 2))

    pads: list[PadSpec] = []
    vias: list[ViaSpec] = []
    segments: list[SegmentSpec] = []

    angle = params.triangle_angle
    masked = params.add_soldermask
    trap_delta = Nanometers(min(pad_width, pad_height) - clearance)

    # TX columns occupy top and bottom edges (vertical strips).
    # Each column gets one TX pad number; both its top and bottom triangles share that number.
    for col in range(seg_x):
        tx_number = f"T{col + 1}"
        pin_name = f"TX{col + 1}"
        x = -width // 2 + col * (pad_width * 2) + pad_width

        # Top-edge triangles
        for row in range(seg_y):
            y = -height // 2 + pad_height // 2 + row * (pad_height * 2)
            pos = Point(Nanometers(x), Nanometers(y - half_clearance))
            pads.append(
                PadSpec(
                    number=tx_number,
                    pin_name=pin_name,
                    electrode=Electrode.TX,
                    electrode_index=col + 1,
                    position=pos,
                    size_x=Nanometers(pad_height - clearance),
                    size_y=Nanometers(pad_width - clearance),
                    trapezoid_delta=trap_delta,
                    angle=Degrees(angle),
                    masked=masked,
                )
            )
            if params.drill_holes:
                via_y = Nanometers(y + (pad_height // 2 - clearance * 4))
                via_pos = Point(Nanometers(x), via_y)
                vias.append(
                    ViaSpec(
                        associated_pad_number=tx_number,
                        position=via_pos,
                        diameter=params.via_diameter,
                        drill=params.via_drill,
                    )
                )
            if params.add_back_wiring:
                seg_start = Point(
                    Nanometers(x),
                    Nanometers(y + (pad_height // 2 - clearance * 4)),
                )
                seg_end = Point(
                    Nanometers(x),
                    Nanometers(y + pad_height + clearance - (pad_height // 2 - clearance * 4)),
                )
                segments.append(
                    SegmentSpec(
                        start=seg_start,
                        end=seg_end,
                        layer=Layer.B_CU,
                        width=params.line_width,
                    )
                )

        # Bottom-edge triangles (rotated 45 deg from the top)
        for row in range(seg_y):
            y = height // 2 - pad_height // 2 - row * (pad_height * 2)
            pos = Point(Nanometers(x), Nanometers(y + half_clearance))
            pads.append(
                PadSpec(
                    number=tx_number,
                    pin_name=pin_name,
                    electrode=Electrode.TX,
                    electrode_index=col + 1,
                    position=pos,
                    size_x=Nanometers(pad_height - clearance),
                    size_y=Nanometers(pad_width - clearance),
                    trapezoid_delta=trap_delta,
                    angle=Degrees(angle - 90.0),
                    masked=masked,
                )
            )
            if params.drill_holes:
                via_y = Nanometers(y - (pad_height // 2 - clearance * 4))
                via_pos = Point(Nanometers(x), via_y)
                vias.append(
                    ViaSpec(
                        associated_pad_number=tx_number,
                        position=via_pos,
                        diameter=params.via_diameter,
                        drill=params.via_drill,
                    )
                )

    # RX rows occupy left and right edges (horizontal strips)
    for row in range(seg_y):
        rx_number = f"R{row + 1}"
        pin_name = f"RX{row + 1}"
        y = -height // 2 + row * (pad_height * 2) + pad_height

        # Front routing line spans the row
        if params.add_front_wiring:
            segments.append(
                SegmentSpec(
                    start=Point(Nanometers(-width // 2), Nanometers(y)),
                    end=Point(Nanometers(width // 2), Nanometers(y)),
                    layer=Layer.F_CU,
                    width=params.line_width,
                )
            )

        # Right-edge triangles
        for col in range(seg_x):
            x = width // 2 - pad_width // 2 - col * (pad_width * 2)
            pos = Point(Nanometers(x + half_clearance), Nanometers(y))
            pads.append(
                PadSpec(
                    number=rx_number,
                    pin_name=pin_name,
                    electrode=Electrode.RX,
                    electrode_index=row + 1,
                    position=pos,
                    size_x=Nanometers(pad_width - clearance),
                    size_y=Nanometers(pad_height - clearance),
                    trapezoid_delta=trap_delta,
                    angle=Degrees(90.0),
                    masked=masked,
                )
            )

        # Left-edge triangles
        for col in range(seg_x):
            x = -width // 2 + pad_width // 2 + col * (pad_width * 2)
            pos = Point(Nanometers(x - half_clearance), Nanometers(y))
            pads.append(
                PadSpec(
                    number=rx_number,
                    pin_name=pin_name,
                    electrode=Electrode.RX,
                    electrode_index=row + 1,
                    position=pos,
                    size_x=Nanometers(pad_width - clearance),
                    size_y=Nanometers(pad_height - clearance),
                    trapezoid_delta=trap_delta,
                    angle=Degrees(0.0),
                    masked=masked,
                )
            )

    return Trackpad(
        pads=pads,
        vias=vias,
        segments=segments,
        tx_count=seg_x,
        rx_count=seg_y,
    )
