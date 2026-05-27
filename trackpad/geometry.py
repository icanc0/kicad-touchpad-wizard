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
    """A trapezoidal SMD touch pad. Pad numbers are unique by construction.

    KiCad's `rect_delta (dx dy)` collapses one edge of the rect to a point when
    one component equals the perpendicular size. To make a proper triangle we
    must collapse the *longer* edge — using a dx >= size_x produces a self-
    intersecting bowtie instead of a triangle.
    """

    number: str
    pin_name: str
    electrode: Electrode
    electrode_index: int  # 0-based column/row this pad belongs to
    position: Point
    size_x: Nanometers
    size_y: Nanometers
    trapezoid_delta_x: Nanometers
    trapezoid_delta_y: Nanometers
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
    tx_count: int  # number of TX columns (number of `c0..c{tx_count-1}` pad numbers)
    rx_count: int  # number of RX rows (number of `r0..r{rx_count-1}` pad numbers)


def _legacy_angle(triangle_angle_param: float) -> float:
    """Map the wizard's triangle_angle parameter to the actual rendered angle.

    The original SWIG code called `EDA_ANGLE(rotation * 10)`, which treated the
    argument as degrees directly. The intended 135° therefore wrapped to
    1350 mod 360 = 270°, and that is what the user's known-good reference
    pattern depends on. We preserve that mapping so default param 135 → 270°
    keeps producing the visually-correct trackpad.
    """
    return (triangle_angle_param * 10.0) % 360.0


def build_trackpad(params: TrackpadParams) -> Trackpad:
    """Translate parameters into pure geometric specs.

    Each TX column ``c{i}`` is a vertical strip of zigzagging triangles
    (top-loop and bottom-loop pads interleave at the same x). All pads in
    column i share the pad number ``c{i}`` so they form one electrical net —
    that's the entire point of an interdigitated capacitive sensor.
    Likewise each RX row ``r{j}`` is a horizontal strip with all pads sharing
    number ``r{j}``.
    """
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

    top_angle = _legacy_angle(float(params.triangle_angle))           # default 135 -> 270
    bottom_angle = _legacy_angle(float(params.triangle_angle) - 90.0)  # default 45  -> 90
    right_angle = _legacy_angle(90.0)                                  # 180
    left_angle = _legacy_angle(0.0)                                    # 0

    masked = params.add_soldermask
    # We always want a triangle pad. KiCad's rect_delta collapses one edge to a
    # point when one component equals the perpendicular size — BUT only when that
    # component is the SHORTER of size_x / size_y. If dx >= size_x you get a
    # bowtie, not a triangle.
    #
    # Rule: put the delta along the LONGER axis with magnitude = SHORTER axis.
    # For a pad with size (sx, sy):
    #   sx >= sy  →  rect_delta = (sy, 0)   triangle points along ±X
    #   sy >  sx  →  rect_delta = (0, sx)   triangle points along ±Y
    tx_size_x = Nanometers(pad_height - clearance)  # TX pads are vertical strips
    tx_size_y = Nanometers(pad_width - clearance)
    rx_size_x = Nanometers(pad_width - clearance)   # RX pads are horizontal strips
    rx_size_y = Nanometers(pad_height - clearance)

    def triangle_delta(sx: int, sy: int) -> tuple[Nanometers, Nanometers]:
        if sx >= sy:
            return Nanometers(sy), Nanometers(0)
        return Nanometers(0), Nanometers(sx)

    tx_dx, tx_dy = triangle_delta(tx_size_x, tx_size_y)
    rx_dx, rx_dy = triangle_delta(rx_size_x, rx_size_y)

    # TX columns occupy the full vertical strip at each x position. Top-loop and
    # bottom-loop pads interleave at the same x but staggered y, so the column
    # looks like a zigzag of alternating-orientation triangles.
    for col in range(seg_x):
        tx_number = f"c{col}"
        pin_name = f"TX{col}"
        x = -width // 2 + col * (pad_width * 2) + pad_width

        # Top-loop pads
        for row in range(seg_y):
            y = -height // 2 + pad_height // 2 + row * (pad_height * 2)
            pos = Point(Nanometers(x), Nanometers(y - half_clearance))
            pads.append(
                PadSpec(
                    number=tx_number,
                    pin_name=pin_name,
                    electrode=Electrode.TX,
                    electrode_index=col,
                    position=pos,
                    size_x=tx_size_x,
                    size_y=tx_size_y,
                    trapezoid_delta_x=tx_dx,
                    trapezoid_delta_y=tx_dy,
                    angle=Degrees(top_angle),
                    masked=masked,
                )
            )
            if params.drill_holes:
                via_y = Nanometers(y + (pad_height // 2 - clearance * 4))
                via_pos = Point(Nanometers(x), via_y)
                vias.append(
                    ViaSpec(
                        associated_pad_number=f"v_{tx_number}",
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

        # Bottom-loop pads (interleaved into the same column at offset y)
        for row in range(seg_y):
            y = height // 2 - pad_height // 2 - row * (pad_height * 2)
            pos = Point(Nanometers(x), Nanometers(y + half_clearance))
            pads.append(
                PadSpec(
                    number=tx_number,
                    pin_name=pin_name,
                    electrode=Electrode.TX,
                    electrode_index=col,
                    position=pos,
                    size_x=tx_size_x,
                    size_y=tx_size_y,
                    trapezoid_delta_x=tx_dx,
                    trapezoid_delta_y=tx_dy,
                    angle=Degrees(bottom_angle),
                    masked=masked,
                )
            )
            if params.drill_holes:
                via_y = Nanometers(y - (pad_height // 2 - clearance * 4))
                via_pos = Point(Nanometers(x), via_y)
                vias.append(
                    ViaSpec(
                        associated_pad_number=f"v_{tx_number}",
                        position=via_pos,
                        diameter=params.via_diameter,
                        drill=params.via_drill,
                    )
                )

    # RX rows occupy the full horizontal strip at each y position.
    for row in range(seg_y):
        rx_number = f"r{row}"
        pin_name = f"RX{row}"
        y = -height // 2 + row * (pad_height * 2) + pad_height

        # Front-side routing trace spans the row.
        if params.add_front_wiring:
            segments.append(
                SegmentSpec(
                    start=Point(Nanometers(-width // 2), Nanometers(y)),
                    end=Point(Nanometers(width // 2), Nanometers(y)),
                    layer=Layer.F_CU,
                    width=params.line_width,
                )
            )

        # Right-loop pads
        for col in range(seg_x):
            x = width // 2 - pad_width // 2 - col * (pad_width * 2)
            pos = Point(Nanometers(x + half_clearance), Nanometers(y))
            pads.append(
                PadSpec(
                    number=rx_number,
                    pin_name=pin_name,
                    electrode=Electrode.RX,
                    electrode_index=row,
                    position=pos,
                    size_x=rx_size_x,
                    size_y=rx_size_y,
                    trapezoid_delta_x=rx_dx,
                    trapezoid_delta_y=rx_dy,
                    angle=Degrees(right_angle),
                    masked=masked,
                )
            )

        # Left-loop pads
        for col in range(seg_x):
            x = -width // 2 + pad_width // 2 + col * (pad_width * 2)
            pos = Point(Nanometers(x - half_clearance), Nanometers(y))
            pads.append(
                PadSpec(
                    number=rx_number,
                    pin_name=pin_name,
                    electrode=Electrode.RX,
                    electrode_index=row,
                    position=pos,
                    size_x=rx_size_x,
                    size_y=rx_size_y,
                    trapezoid_delta_x=rx_dx,
                    trapezoid_delta_y=rx_dy,
                    angle=Degrees(left_angle),
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
