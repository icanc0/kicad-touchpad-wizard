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
    """One triangular touch pad, expressed as 3 explicit board-frame vertices.

    KiCad's `rect_delta` trapezoid shape has too many edge cases — collapsing the
    wrong edge gives a bowtie, switching which axis carries the delta moves the
    apex 90°, the delta convention itself was unclear from docs. We sidestep
    everything by emitting custom polygon pads (`gr_poly` primitives), giving
    us direct control over each triangle's vertex positions.

    `vertices` are absolute board-frame coords (nm). `anchor` is the pad's
    placement point — the KiCad pad's (at x y) coords. The renderer translates
    each vertex into the pad-local frame at emit time.
    """

    number: str
    pin_name: str
    electrode: Electrode
    electrode_index: int  # 0-based column/row
    anchor: Point
    vertices: tuple[Point, Point, Point]
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


class _ApexDirection(Enum):
    """Where the triangle's apex points, in board-frame cardinal directions."""

    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


def _triangle_vertices(
    center_x: int, center_y: int, base_half_width: int, height: int, apex: _ApexDirection
) -> tuple[Point, Point, Point]:
    """Isoceles triangle in board coords.

    `base_half_width` is half the base length, `height` is the triangle's height
    measured from base midpoint to apex.

    The triangle is inscribed in a rectangle that has the apex at one edge and
    the full base along the opposite edge. The base is perpendicular to the
    apex direction.
    """
    dx, dy = apex.value
    # Apex is at `center + (dx, dy) * height/2`. Wait — center should be the
    # centroid? Use bounding-box center: apex at `+height/2` along apex dir,
    # base at `-height/2`.
    apex_x = center_x + dx * height // 2
    apex_y = center_y + dy * height // 2
    base_mid_x = center_x - dx * height // 2
    base_mid_y = center_y - dy * height // 2
    # Base runs perpendicular to apex direction
    perp_x, perp_y = -dy, dx
    base_left_x = base_mid_x - perp_x * base_half_width
    base_left_y = base_mid_y - perp_y * base_half_width
    base_right_x = base_mid_x + perp_x * base_half_width
    base_right_y = base_mid_y + perp_y * base_half_width
    return (
        Point(Nanometers(apex_x), Nanometers(apex_y)),
        Point(Nanometers(base_left_x), Nanometers(base_left_y)),
        Point(Nanometers(base_right_x), Nanometers(base_right_y)),
    )


def build_trackpad(params: TrackpadParams) -> Trackpad:
    """Translate parameters into geometry specs with explicit triangle vertices.

    Each TX column ``c{i}`` is a vertical strip of triangles. Top-loop pads point
    UP toward the top of the trackpad, bottom-loop pads point DOWN. All pads in
    column i share pad number ``c{i}``. Each RX row ``r{j}`` is the horizontal
    equivalent — left-loop pads point RIGHT, right-loop pads point LEFT, all
    sharing pad number ``r{j}``.

    Triangles are sized to fit (pad_width × pad_height) cells, scaling correctly
    for any aspect ratio.
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
    masked = params.add_soldermask

    # Triangle shape matches KiCad's rect_delta(size_x, 0) at size_x = size_y:
    # the base is TWICE the nominal pad_width (extending across two cell columns),
    # and the height equals pad_height. Adjacent pads in a column share half-cells —
    # this is what makes the iconic full-coverage diamond pattern tile.
    tx_base_half = Nanometers(pad_width - clearance)        # full base = 2*(pad_width - clearance)
    tx_height = Nanometers(pad_height - clearance)
    rx_base_half = Nanometers(pad_height - clearance)
    rx_height = Nanometers(pad_width - clearance)

    # TX columns. Top-loop pads point UP (board -Y), bottom-loop pads point DOWN.
    for col in range(seg_x):
        tx_number = f"c{col}"
        pin_name = f"TX{col}"
        x = -width // 2 + col * (pad_width * 2) + pad_width

        # Top-loop pads — apex DOWN (toward trackpad center). The pad sits near the
        # top edge of the trackpad; its triangle's base is at the edge and its
        # apex points inward to meet the adjacent bottom-loop pad's apex.
        for row in range(seg_y):
            y_center = -height // 2 + pad_height // 2 + row * (pad_height * 2) - half_clearance
            anchor = Point(Nanometers(x), Nanometers(y_center))
            vertices = _triangle_vertices(
                x, y_center, tx_base_half, tx_height, _ApexDirection.DOWN
            )
            pads.append(
                PadSpec(
                    number=tx_number,
                    pin_name=pin_name,
                    electrode=Electrode.TX,
                    electrode_index=col,
                    anchor=anchor,
                    vertices=vertices,
                    masked=masked,
                )
            )
            if params.drill_holes:
                via_y = Nanometers(y_center + (pad_height // 2 - clearance * 4))
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
                    Nanometers(y_center + (pad_height // 2 - clearance * 4)),
                )
                seg_end = Point(
                    Nanometers(x),
                    Nanometers(
                        y_center
                        + pad_height
                        + clearance
                        - (pad_height // 2 - clearance * 4)
                    ),
                )
                segments.append(
                    SegmentSpec(
                        start=seg_start,
                        end=seg_end,
                        layer=Layer.B_CU,
                        width=params.line_width,
                    )
                )

        # Bottom-loop pads — apex UP (toward trackpad center)
        for row in range(seg_y):
            y_center = height // 2 - pad_height // 2 - row * (pad_height * 2) + half_clearance
            anchor = Point(Nanometers(x), Nanometers(y_center))
            vertices = _triangle_vertices(
                x, y_center, tx_base_half, tx_height, _ApexDirection.UP
            )
            pads.append(
                PadSpec(
                    number=tx_number,
                    pin_name=pin_name,
                    electrode=Electrode.TX,
                    electrode_index=col,
                    anchor=anchor,
                    vertices=vertices,
                    masked=masked,
                )
            )
            if params.drill_holes:
                via_y = Nanometers(y_center - (pad_height // 2 - clearance * 4))
                via_pos = Point(Nanometers(x), via_y)
                vias.append(
                    ViaSpec(
                        associated_pad_number=f"v_{tx_number}",
                        position=via_pos,
                        diameter=params.via_diameter,
                        drill=params.via_drill,
                    )
                )

    # RX rows. Right-loop pads point LEFT (board -X), left-loop pads point RIGHT.
    for row in range(seg_y):
        rx_number = f"r{row}"
        pin_name = f"RX{row}"
        y = -height // 2 + row * (pad_height * 2) + pad_height

        if params.add_front_wiring:
            segments.append(
                SegmentSpec(
                    start=Point(Nanometers(-width // 2), Nanometers(y)),
                    end=Point(Nanometers(width // 2), Nanometers(y)),
                    layer=Layer.F_CU,
                    width=params.line_width,
                )
            )

        # Right-loop pads — apex LEFT? actually apex points inward toward column gap.
        # The pad sits near the right edge of its cell with base at the trackpad
        # right and apex pointing leftward into the cell.
        # TODO verify empirically — for symmetry with TX, this should be the apex
        # pointing into the row direction (i.e., toward the row's center axis).
        for col in range(seg_x):
            x_center = width // 2 - pad_width // 2 - col * (pad_width * 2) + half_clearance
            anchor = Point(Nanometers(x_center), Nanometers(y))
            vertices = _triangle_vertices(
                x_center, y, rx_base_half, rx_height, _ApexDirection.LEFT
            )
            pads.append(
                PadSpec(
                    number=rx_number,
                    pin_name=pin_name,
                    electrode=Electrode.RX,
                    electrode_index=row,
                    anchor=anchor,
                    vertices=vertices,
                    masked=masked,
                )
            )

        # Left-loop pads — apex RIGHT
        for col in range(seg_x):
            x_center = -width // 2 + pad_width // 2 + col * (pad_width * 2) - half_clearance
            anchor = Point(Nanometers(x_center), Nanometers(y))
            vertices = _triangle_vertices(
                x_center, y, rx_base_half, rx_height, _ApexDirection.RIGHT
            )
            pads.append(
                PadSpec(
                    number=rx_number,
                    pin_name=pin_name,
                    electrode=Electrode.RX,
                    electrode_index=row,
                    anchor=anchor,
                    vertices=vertices,
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
