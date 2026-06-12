"""Place a generated trackpad footprint directly onto the open board via IPC.

Verified against the KiCad 10.0.1 source: ``CreateItems`` accepts a
``FootprintInstance`` whose container is a board, and ``FOOTPRINT::Deserialize``
rebuilds every item in ``definition().items()`` — including custom-polygon
pads — so the full trackpad arrives in one round trip. The creation goes
through KiCad's commit framework, so it is a single undo step (Ctrl+Z).

This is the "interactive" half of the plugin: something visible appears on the
board the moment you hit Generate. The library half (project_gen) is what
makes it maintainable; the placed instance carries the library id
``Trackpad:Trackpad-<W>x<H>mm``, so an instance placed here and the library
written alongside stay in sync.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kipy.board_types import FootprintInstance
from kipy.geometry import Vector2
from kipy.proto.board.board_types_pb2 import BoardLayer

from trackpad.footprint import populate_footprint
from trackpad.geometry import build_trackpad

if TYPE_CHECKING:
    from kipy.board import Board

    from trackpad.params import TrackpadParams

# Default landing spot: roughly the middle of an A4 page, which is also inside
# the demo board outline. The user drags it where they want it.
DEFAULT_POSITION_NM = (150_000_000, 105_000_000)


def build_footprint_instance(
    params: TrackpadParams, position_nm: tuple[int, int] = DEFAULT_POSITION_NM
) -> FootprintInstance:
    """Build the complete FootprintInstance, ready for Board.create_items()."""
    trackpad = build_trackpad(params)

    fpi = FootprintInstance()
    fpi.layer = BoardLayer.BL_F_Cu
    fpi.reference_field.text.value = "TP1"
    populate_footprint(fpi.definition, trackpad, params)
    # KiCad stores footprint children in board-absolute coordinates. The items
    # above are in footprint-local coordinates (around the origin), so set the
    # position LAST: kipy's position setter translates every child by the
    # delta, which converts local to absolute exactly once.
    fpi.position = Vector2.from_xy(*position_nm)
    return fpi


def place_on_board(board: Board, params: TrackpadParams) -> str:
    """Create the trackpad on the board. Returns a human-readable result line.

    Raises on IPC failure — callers surface the error to the user.
    """
    fpi = build_footprint_instance(params)
    created = board.create_items(fpi)
    if not created:
        raise RuntimeError("KiCad did not create the footprint (no item returned)")
    x_mm = DEFAULT_POSITION_NM[0] / 1_000_000
    y_mm = DEFAULT_POSITION_NM[1] / 1_000_000
    return (
        f"Placed footprint on the board at ({x_mm:g}, {y_mm:g}) mm "
        "(one undo step — Ctrl+Z removes it)."
    )
