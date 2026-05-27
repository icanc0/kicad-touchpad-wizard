"""Turn typed geometry specs into a kipy Footprint proto."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kipy.board_types import BoardSegment, Footprint, Pad
from kipy.common_types import LibraryIdentifier
from kipy.geometry import Angle, Vector2
from kipy.proto.board.board_types_pb2 import (
    BoardLayer,
    PadStackShape,
    PadStackType,
    PadType,
    SolderMaskMode,
)

from trackpad.geometry import Layer, PadSpec, SegmentSpec, Trackpad, ViaSpec

if TYPE_CHECKING:
    from trackpad.params import TrackpadParams

_LAYER_MAP: dict[Layer, BoardLayer.ValueType] = {
    Layer.F_CU: BoardLayer.BL_F_Cu,
    Layer.B_CU: BoardLayer.BL_B_Cu,
}


def _make_smd_pad(spec: PadSpec) -> Pad:
    pad = Pad()
    pad.number = spec.number
    pad.pad_type = PadType.PT_SMD
    pad.position = Vector2.from_xy(int(spec.position.x), int(spec.position.y))

    ps = pad.padstack
    ps.type = PadStackType.PST_NORMAL
    ps.layers = [BoardLayer.BL_F_Cu]
    ps.angle = Angle.from_degrees(float(spec.angle))

    front = ps.copper_layer(BoardLayer.BL_F_Cu)
    assert front is not None
    front.shape = PadStackShape.PSS_TRAPEZOID
    front.size = Vector2.from_xy(int(spec.size_x), int(spec.size_y))
    front.trapezoid_delta = Vector2.from_xy(int(spec.trapezoid_delta), 0)

    ps.front_outer_layers.solder_mask_mode = (
        SolderMaskMode.SMM_FROM_DESIGN_RULES if spec.masked else SolderMaskMode.SMM_UNMASKED
    )
    return pad


def _make_via_pad(spec: ViaSpec) -> Pad:
    """Footprints can't contain board-vias, so route-through-vias are PTH pads."""
    pad = Pad()
    pad.number = spec.associated_pad_number
    pad.pad_type = PadType.PT_PTH
    pad.position = Vector2.from_xy(int(spec.position.x), int(spec.position.y))

    ps = pad.padstack
    ps.type = PadStackType.PST_NORMAL
    ps.layers = [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu]

    front = ps.copper_layer(BoardLayer.BL_F_Cu)
    assert front is not None
    front.shape = PadStackShape.PSS_CIRCLE
    front.size = Vector2.from_xy(int(spec.diameter), int(spec.diameter))

    ps.drill.diameter = Vector2.from_xy(int(spec.drill), int(spec.drill))
    return pad


def _make_segment(spec: SegmentSpec) -> BoardSegment:
    seg = BoardSegment()
    seg.start = Vector2.from_xy(int(spec.start.x), int(spec.start.y))
    seg.end = Vector2.from_xy(int(spec.end.x), int(spec.end.y))
    seg.layer = _LAYER_MAP[spec.layer]
    seg.attributes.stroke.width = int(spec.width)
    return seg


def to_footprint(trackpad: Trackpad, params: TrackpadParams) -> Footprint:
    """Build the Footprint proto from typed geometry specs."""
    fp = Footprint()

    # Stable library identifier: "Trackpad:Trackpad-<w>x<h>mm"
    lib_id = LibraryIdentifier()
    lib_id.library = "Trackpad"
    lib_id.name = f"Trackpad-{params.width / 1_000_000:g}x{params.height / 1_000_000:g}mm"
    fp.id = lib_id

    for pad_spec in trackpad.pads:
        fp.add_item(_make_smd_pad(pad_spec))
    for via_spec in trackpad.vias:
        fp.add_item(_make_via_pad(via_spec))
    for seg_spec in trackpad.segments:
        fp.add_item(_make_segment(seg_spec))

    return fp
