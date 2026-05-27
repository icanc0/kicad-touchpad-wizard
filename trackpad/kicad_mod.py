"""Emit a .kicad_mod (footprint) s-expression text file from geometry specs.

This is a parallel output path to trackpad.footprint (which emits a kipy proto for the
IPC pipeline). The text-file path keeps users unblocked when the in-KiCad wizard is
inconvenient — and it's what we feed kicad-cli for headless golden-image testing.

Coordinates in .kicad_mod are millimeters with two decimals; we convert from internal nm.
"""

from __future__ import annotations

from trackpad.geometry import Layer, PadSpec, SegmentSpec, Trackpad, ViaSpec
from trackpad.params import TrackpadParams
from trackpad.units import Nanometers

FILE_VERSION = "20240108"
GENERATOR = "kicad-touchpad-wizard"


def _mm(value: Nanometers) -> str:
    return f"{value / 1_000_000:.4f}"


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render_footprint(trackpad: Trackpad, params: TrackpadParams) -> str:
    """Return the full content of a .kicad_mod file."""
    width_mm = params.width / 1_000_000
    height_mm = params.height / 1_000_000
    name = f"Trackpad-{width_mm:g}x{height_mm:g}mm"

    parts: list[str] = [
        f'(footprint "{_esc(name)}"',
        f"  (version {FILE_VERSION})",
        f'  (generator "{GENERATOR}")',
        '  (layer "F.Cu")',
        f'  (descr "Capacitive trackpad {width_mm:g}x{height_mm:g} mm, '
        f'{trackpad.tx_count} TX cols, {trackpad.rx_count} RX rows")',
        '  (attr smd)',
        f'  (fp_text reference "REF**" (at 0 {-height_mm / 2 - 1.5:.4f})',
        '    (layer "F.SilkS")',
        '    (effects (font (size 1 1) (thickness 0.15))))',
        f'  (fp_text value "{_esc(name)}" (at 0 {height_mm / 2 + 1.5:.4f})',
        '    (layer "F.Fab")',
        '    (effects (font (size 1 1) (thickness 0.15))))',
    ]

    for pad in trackpad.pads:
        parts.append(_render_pad(pad))
    for via in trackpad.vias:
        parts.append(_render_via(via))
    for seg in trackpad.segments:
        parts.append(_render_segment(seg))

    parts.append(")")
    return "\n".join(parts) + "\n"


def _render_pad(spec: PadSpec) -> str:
    layers = '"F.Cu" "F.Mask"' if not spec.masked else '"F.Cu"'
    delta_mm = spec.trapezoid_delta / 1_000_000
    return (
        f'  (pad "{_esc(spec.number)}" smd trapezoid '
        f"(at {_mm(spec.position.x)} {_mm(spec.position.y)} {float(spec.angle):g})\n"
        f"    (size {_mm(spec.size_x)} {_mm(spec.size_y)})\n"
        f"    (rect_delta {delta_mm:.4f} 0)\n"
        f"    (layers {layers}))"
    )


def _render_via(spec: ViaSpec) -> str:
    return (
        f'  (pad "{_esc(spec.associated_pad_number)}" thru_hole circle '
        f"(at {_mm(spec.position.x)} {_mm(spec.position.y)})\n"
        f"    (size {_mm(spec.diameter)} {_mm(spec.diameter)})\n"
        f"    (drill {_mm(spec.drill)})\n"
        f'    (layers "*.Cu" "*.Mask"))'
    )


def _render_segment(spec: SegmentSpec) -> str:
    layer = "F.Cu" if spec.layer == Layer.F_CU else "B.Cu"
    return (
        f"  (fp_line (start {_mm(spec.start.x)} {_mm(spec.start.y)}) "
        f"(end {_mm(spec.end.x)} {_mm(spec.end.y)})\n"
        f'    (stroke (width {_mm(spec.width)}) (type solid))\n'
        f'    (layer "{layer}"))'
    )
