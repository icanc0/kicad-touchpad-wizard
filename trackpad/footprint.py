"""Turn typed geometry specs into a kipy Footprint proto.

WARNING: this path is only exercised when KiCad runs the wizard plugin via the
IPC API. KiCad 10.0.1 ships the API server disabled by default and has not been
verified to wire up `footprint_wizard`-scoped IPC plugins. The standalone CLI
(`touchpad-wizard emit ...`) uses `trackpad.kicad_mod` instead, which is the
production path right now.

Triangles are emitted as PSS_CUSTOM padstacks with a polygon primitive. kipy
0.7.1's BoardPolygon API has some read-only setters that make assembling the
custom-shape list awkward; we mutate the underlying proto directly to sidestep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kipy.board_types import BoardSegment, Footprint, Pad
from kipy.common_types import LibraryIdentifier
from kipy.geometry import Vector2
from kipy.proto.board.board_types_pb2 import (
    BoardLayer,
    PadStackShape,
    PadStackType,
    PadType,
    SolderMaskMode,
)
from kipy.proto.common.types import base_types_pb2 as common_types

from trackpad.geometry import (
    LandingPadSpec,
    Layer,
    PadSpec,
    SegmentSpec,
    Trackpad,
    ViaSpec,
)

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
    pad.position = Vector2.from_xy(int(spec.anchor.x), int(spec.anchor.y))

    ps = pad.padstack
    ps.type = PadStackType.PST_NORMAL
    ps.layers = [BoardLayer.BL_F_Cu]

    front = ps.copper_layer(BoardLayer.BL_F_Cu)
    assert front is not None
    front.shape = PadStackShape.PSS_CUSTOM
    front.custom_anchor_shape = PadStackShape.PSS_CIRCLE
    # Anchor primitive — tiny circle, hidden under the polygon
    front.size = Vector2.from_xy(250_000, 250_000)

    # Build the custom polygon shape by mutating the underlying proto directly.
    # The kipy 0.7.1 wrapper exposes `custom_shapes` as a read-only list; we
    # append directly to the proto's repeated field instead. protobuf RepeatedCompositeContainer
    # has `del[:]` for clearing.
    del front._proto.custom_shapes[:]  # type: ignore[attr-defined]
    custom_shape_proto = front._proto.custom_shapes.add()  # type: ignore[attr-defined]
    poly_with_holes = custom_shape_proto.shape.polygon.polygons.add()
    for vertex in spec.vertices:
        node = poly_with_holes.outline.nodes.add()
        node.point.x_nm = int(vertex.x - spec.anchor.x)
        node.point.y_nm = int(vertex.y - spec.anchor.y)
    poly_with_holes.outline.closed = True
    # Layer for the BoardGraphicShape wrapping this polygon
    custom_shape_proto.layer = BoardLayer.BL_F_Cu

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


def _make_landing_pad(spec: LandingPadSpec) -> Pad:
    """A rectangular connection/alignment landing — plain exposed SMD rect pad."""
    pad = Pad()
    pad.number = spec.number
    pad.pad_type = PadType.PT_SMD
    pad.position = Vector2.from_xy(int(spec.center.x), int(spec.center.y))

    ps = pad.padstack
    ps.type = PadStackType.PST_NORMAL
    ps.layers = [BoardLayer.BL_F_Cu]

    front = ps.copper_layer(BoardLayer.BL_F_Cu)
    assert front is not None
    front.shape = PadStackShape.PSS_RECTANGLE
    front.size = Vector2.from_xy(int(spec.size_x), int(spec.size_y))

    # Mask follows the trackpad setting — covered by default, like the triangles.
    ps.front_outer_layers.solder_mask_mode = (
        SolderMaskMode.SMM_FROM_DESIGN_RULES if spec.masked else SolderMaskMode.SMM_UNMASKED
    )
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
    _ = common_types  # imported for namespace effect; protos resolve lazily
    fp = Footprint()

    lib_id = LibraryIdentifier()
    lib_id.library = "Trackpad"
    lib_id.name = f"Trackpad-{params.width / 1_000_000:g}x{params.height / 1_000_000:g}mm"
    fp.id = lib_id

    for pad_spec in trackpad.pads:
        fp.add_item(_make_smd_pad(pad_spec))
    for landing_spec in trackpad.landings:
        fp.add_item(_make_landing_pad(landing_spec))
    for via_spec in trackpad.vias:
        fp.add_item(_make_via_pad(via_spec))
    for seg_spec in trackpad.segments:
        fp.add_item(_make_segment(seg_spec))

    return fp
