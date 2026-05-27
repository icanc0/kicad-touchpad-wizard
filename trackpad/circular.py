"""Circular (wheel) trackpad geometry.

Same TX/RX interlocking principle as the rectangular variant, but in polar
coordinates. Each cell is an annular sector — bounded by two radii and two
angles — rendered as a custom polygon pad in the .kicad_mod output.

Layout:
  - `sectors` wedges around the center, each one a TX electrode (`c{i}`).
  - `rings` concentric bands, each one an RX electrode (`r{j}`).
  - Each (sector, ring) cell is split: half goes to the TX of that sector,
    half to the RX of that ring. The split alternates by (sector + ring) % 2
    so the pattern interlocks like a checkerboard wrapped onto a disc.

That's the cleanest 1:1 analog of the rectangular zigzag-column /
zigzag-row pattern. Captures the same capacitive sensitivity property:
finger position perturbs both an angular and a radial measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from trackpad.geometry import Electrode
from trackpad.units import Nanometers, mm


@dataclass(frozen=True, slots=True)
class PolarPoint:
    x: Nanometers
    y: Nanometers


@dataclass(frozen=True, slots=True)
class PolygonPadSpec:
    """A custom-polygon SMD pad. KiCad supports these via the `custom` pad type."""

    number: str
    pin_name: str
    electrode: Electrode
    electrode_index: int
    anchor: PolarPoint
    polygon: list[PolarPoint]  # absolute coords (not relative to anchor)
    masked: bool


@dataclass(frozen=True, slots=True)
class CircularTrackpad:
    pads: list[PolygonPadSpec]
    sectors: int
    rings: int
    outer_radius: Nanometers


@dataclass(frozen=True, slots=True)
class CircularParams:
    outer_radius: Nanometers
    inner_radius: Nanometers
    sectors: int
    rings: int
    clearance: Nanometers
    add_soldermask: bool
    arc_steps_per_sector: int  # arc approximation quality

    @classmethod
    def defaults(cls) -> CircularParams:
        return cls(
            outer_radius=mm(25),
            inner_radius=mm(3),
            sectors=8,
            rings=3,
            clearance=mm(0.2),
            add_soldermask=True,
            arc_steps_per_sector=6,
        )

    def validate(self) -> str | None:
        if self.outer_radius <= self.inner_radius:
            return "outer radius must exceed inner radius"
        if self.sectors < 3:
            return "need at least 3 angular sectors"
        if self.rings < 1:
            return "need at least 1 ring"
        if self.clearance <= 0:
            return "clearance must be positive"
        ring_width = (self.outer_radius - self.inner_radius) // self.rings
        if ring_width <= self.clearance * 2:
            return "rings are too narrow for the chosen clearance"
        return None


def _polar(r: float, theta: float) -> PolarPoint:
    return PolarPoint(Nanometers(round(r * math.cos(theta))), Nanometers(round(r * math.sin(theta))))


def _arc(r: float, theta_start: float, theta_end: float, steps: int) -> list[PolarPoint]:
    """Discretize an arc into `steps + 1` points from theta_start to theta_end."""
    if steps <= 0:
        return [_polar(r, theta_start), _polar(r, theta_end)]
    return [_polar(r, theta_start + (theta_end - theta_start) * i / steps) for i in range(steps + 1)]


def _annular_sector_polygon(
    r_inner: float,
    r_outer: float,
    theta_start: float,
    theta_end: float,
    arc_steps: int,
) -> list[PolarPoint]:
    """Vertices walking around an annular-sector cell, counter-clockwise."""
    outer_arc = _arc(r_outer, theta_start, theta_end, arc_steps)
    inner_arc = _arc(r_inner, theta_end, theta_start, arc_steps)
    return outer_arc + inner_arc


def build_circular_trackpad(params: CircularParams) -> CircularTrackpad:
    """Place annular-sector polygon pads in a checkerboard TX/RX split."""
    pads: list[PolygonPadSpec] = []
    sectors = params.sectors
    rings = params.rings
    r_inner_total = float(params.inner_radius)
    r_outer_total = float(params.outer_radius)
    ring_width = (r_outer_total - r_inner_total) / rings
    sector_width_rad = 2 * math.pi / sectors

    # Margin per cell so adjacent cells don't kiss; clearance / 2 on every edge.
    radial_pad = float(params.clearance) / 2

    def angular_pad_at(r: float) -> float:
        """Convert linear clearance to angular clearance at radius r."""
        return float(params.clearance) / 2 / max(r, 1.0)

    for ring_idx in range(rings):
        r_in = r_inner_total + ring_idx * ring_width + radial_pad
        r_out = r_inner_total + (ring_idx + 1) * ring_width - radial_pad
        for sec_idx in range(sectors):
            theta_start = sec_idx * sector_width_rad
            theta_end = (sec_idx + 1) * sector_width_rad
            r_mid = (r_in + r_out) / 2
            ang_pad = angular_pad_at(r_mid)

            # Checkerboard split: cells where (sector + ring) is even -> TX,
            # else RX. This is the polar analog of the rectangular zigzag.
            if (sec_idx + ring_idx) % 2 == 0:
                number = f"c{sec_idx}"
                pin_name = f"TX{sec_idx}"
                electrode = Electrode.TX
                electrode_index = sec_idx
            else:
                number = f"r{ring_idx}"
                pin_name = f"RX{ring_idx}"
                electrode = Electrode.RX
                electrode_index = ring_idx

            polygon = _annular_sector_polygon(
                r_inner=r_in,
                r_outer=r_out,
                theta_start=theta_start + ang_pad,
                theta_end=theta_end - ang_pad,
                arc_steps=params.arc_steps_per_sector,
            )
            anchor = _polar(r_mid, (theta_start + theta_end) / 2)
            pads.append(
                PolygonPadSpec(
                    number=number,
                    pin_name=pin_name,
                    electrode=electrode,
                    electrode_index=electrode_index,
                    anchor=anchor,
                    polygon=polygon,
                    masked=params.add_soldermask,
                )
            )

    return CircularTrackpad(
        pads=pads,
        sectors=sectors,
        rings=rings,
        outer_radius=params.outer_radius,
    )


def render_circular_footprint(trackpad: CircularTrackpad) -> str:
    """Emit a .kicad_mod file containing the circular trackpad as custom polygon pads."""
    r_mm = float(trackpad.outer_radius) / 1_000_000
    name = f"Trackpad-Circular-d{r_mm * 2:g}mm-{trackpad.sectors}x{trackpad.rings}"

    parts: list[str] = [
        f'(footprint "{name}"',
        '  (version 20240108)',
        '  (generator "kicad-touchpad-wizard")',
        '  (layer "F.Cu")',
        f'  (descr "Circular capacitive trackpad, '
        f'{trackpad.sectors} TX sectors x {trackpad.rings} RX rings, diameter {r_mm * 2:g} mm")',
        '  (attr smd)',
        f'  (fp_text reference "REF**" (at 0 {-r_mm - 1.5:.4f})',
        '    (layer "F.SilkS")',
        '    (effects (font (size 1 1) (thickness 0.15))))',
        f'  (fp_text value "{name}" (at 0 {r_mm + 1.5:.4f})',
        '    (layer "F.Fab")',
        '    (effects (font (size 1 1) (thickness 0.15))))',
    ]

    for pad in trackpad.pads:
        parts.append(_render_polygon_pad(pad))

    # Outline as fp_arc on Edge.Cuts (kicad-cli renders this cleanly)
    parts.append(
        f'  (fp_circle (center 0 0) (end {r_mm:.4f} 0)\n'
        f'    (stroke (width 0.1) (type solid)) (fill none) (layer "Edge.Cuts"))'
    )

    parts.append(")")
    return "\n".join(parts) + "\n"


def _render_polygon_pad(spec: PolygonPadSpec) -> str:
    layers = '"F.Cu" "F.Mask"' if not spec.masked else '"F.Cu"'
    # Each polygon vertex needs to be expressed *relative* to the pad's anchor.
    pts_lines: list[str] = []
    for p in spec.polygon:
        dx = (p.x - spec.anchor.x) / 1_000_000
        dy = (p.y - spec.anchor.y) / 1_000_000
        pts_lines.append(f"        (xy {dx:.4f} {dy:.4f})")
    pts_block = "\n".join(pts_lines)

    ax = spec.anchor.x / 1_000_000
    ay = spec.anchor.y / 1_000_000

    return (
        f'  (pad "{spec.number}" smd custom (at {ax:.4f} {ay:.4f})\n'
        f'    (size 0.5 0.5)\n'
        f'    (layers {layers})\n'
        f'    (options (clearance outline) (anchor circle))\n'
        f'    (primitives\n'
        f'      (gr_poly\n'
        f'        (pts\n'
        f'{pts_block})\n'
        f'        (width 0) (fill yes))))'
    )
