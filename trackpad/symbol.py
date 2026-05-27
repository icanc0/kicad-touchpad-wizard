"""Emit a .kicad_sym file with pin numbers matching the footprint pad numbers.

The schematic editor doesn't yet accept WCT_SYMBOL content via the wizard IPC pipeline
(KiCad 9/10 only implements the IPC API for the PCB editor). So we emit the symbol as a
side-channel .kicad_sym text file that the user adds to their project once. After that, the
same library identifier (`Trackpad:Trackpad-<w>x<h>mm`) connects symbol -> footprint
automatically — no per-trackpad fiddling, the binding is by name.

KiCad .kicad_sym is a documented s-expression format. Generating it as text keeps us
decoupled from kipy's schematic API (which is still in flux).

Coordinates in this file are millimeters (the .kicad_sym native unit). The pin pitch is
2.54 mm (0.1") to match standard KiCad symbol convention.
"""

from __future__ import annotations

from trackpad.geometry import Trackpad
from trackpad.params import TrackpadParams

PIN_LENGTH_MM = 2.54
PIN_PITCH_MM = 2.54
BODY_VERTICAL_PADDING_MM = 2.54
BODY_WIDTH_MM = 12.7  # 500 mil — comfortable for "TX99" / "RX99" pin labels


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render_symbol(trackpad: Trackpad, params: TrackpadParams) -> str:
    """Return the full content of a .kicad_sym file containing one symbol."""
    width_mm = params.width / 1_000_000
    height_mm = params.height / 1_000_000
    name = f"Trackpad-{width_mm:g}x{height_mm:g}mm"

    tx_pins = [f"TX{i + 1}" for i in range(trackpad.tx_count)]
    rx_pins = [f"RX{i + 1}" for i in range(trackpad.rx_count)]

    rows = max(len(tx_pins), len(rx_pins))
    body_height_mm = rows * PIN_PITCH_MM + BODY_VERTICAL_PADDING_MM * 2
    body_top = body_height_mm / 2
    body_bottom = -body_top
    body_left = -BODY_WIDTH_MM / 2
    body_right = BODY_WIDTH_MM / 2

    def pin_y(index: int) -> float:
        return body_top - BODY_VERTICAL_PADDING_MM - index * PIN_PITCH_MM

    pins: list[str] = []
    # TX pins on left, facing right (orientation 0 means pin extends to the right from anchor)
    for i, label in enumerate(tx_pins):
        pins.append(
            _pin(
                x=body_left - PIN_LENGTH_MM,
                y=pin_y(i),
                angle_deg=0,
                name=label,
                number=f"T{i + 1}",
            )
        )
    # RX pins on right, facing left
    for i, label in enumerate(rx_pins):
        pins.append(
            _pin(
                x=body_right + PIN_LENGTH_MM,
                y=pin_y(i),
                angle_deg=180,
                name=label,
                number=f"R{i + 1}",
            )
        )

    body_rect = (
        f"      (rectangle (start {body_left:.4f} {body_bottom:.4f}) "
        f"(end {body_right:.4f} {body_top:.4f}) "
        f"(stroke (width 0.254) (type default)) (fill (type background)))"
    )
    pins_block = "\n".join(pins)

    return f"""(kicad_symbol_lib (version 20231120) (generator "kicad-touchpad-wizard")
  (symbol "{_esc(name)}"
    (pin_names (offset 0.508))
    (in_bom yes) (on_board yes)
    (property "Reference" "TP" (at 0 {body_top + 1.27:.4f} 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "{_esc(name)}" (at 0 {body_bottom - 1.27:.4f} 0)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "Trackpad:{_esc(name)}" (at 0 0 0)
      (effects (font (size 1.27 1.27)) hide))
    (property "Datasheet" "" (at 0 0 0)
      (effects (font (size 1.27 1.27)) hide))
    (property "Description" "Capacitive trackpad {width_mm:g}x{height_mm:g} mm \
({trackpad.tx_count} TX cols, {trackpad.rx_count} RX rows)" (at 0 0 0)
      (effects (font (size 1.27 1.27)) hide))
    (symbol "{_esc(name)}_1_1"
{body_rect}
{pins_block}
    )
  )
)
"""


def _pin(x: float, y: float, angle_deg: int, name: str, number: str) -> str:
    return (
        f"      (pin passive line (at {x:.4f} {y:.4f} {angle_deg}) (length {PIN_LENGTH_MM:.4f})\n"
        f'        (name "{_esc(name)}" (effects (font (size 1.27 1.27))))\n'
        f'        (number "{_esc(number)}" (effects (font (size 1.27 1.27)))))'
    )
