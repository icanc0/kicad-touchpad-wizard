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

EMPTY_LIBRARY = '(kicad_symbol_lib (version 20231120) (generator "kicad-touchpad-wizard")\n)\n'


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def extract_symbol_block(symbol_file_text: str) -> str:
    """Pull the top-level ``(symbol ...)`` block out of a one-symbol .kicad_sym file."""
    block_start = symbol_file_text.find('(symbol "')
    if block_start == -1:
        raise ValueError("symbol file has no (symbol ...) block")
    depth = 0
    for i in range(block_start, len(symbol_file_text)):
        c = symbol_file_text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return symbol_file_text[block_start : i + 1]
    raise ValueError("unbalanced parentheses in symbol file")


def upsert_symbol(library_text: str, symbol_block: str, name: str) -> str:
    """Replace the symbol named `name` in `library_text`, or append it before the close paren."""
    needle = f'(symbol "{name}"'
    start = library_text.find(needle)
    if start != -1:
        depth = 0
        for i in range(start, len(library_text)):
            c = library_text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return library_text[:start] + symbol_block.strip() + library_text[i + 1 :]

    # No existing entry — append before the closing paren of kicad_symbol_lib
    closing = library_text.rfind(")")
    if closing == -1:
        return library_text + "\n" + symbol_block
    return library_text[:closing] + "  " + symbol_block.strip() + "\n" + library_text[closing:]


def upsert_symbol_into_library_file(path_text: str | None, symbol_file_text: str, name: str) -> str:
    """Merge a freshly rendered one-symbol library into existing library text.

    `path_text` is the current content of the target .kicad_sym (None if the
    file doesn't exist yet). Returns the new file content.
    """
    existing = path_text if path_text is not None else EMPTY_LIBRARY
    block = extract_symbol_block(symbol_file_text)
    return upsert_symbol(existing, block, name)


def render_symbol(trackpad: Trackpad, params: TrackpadParams) -> str:
    """Return the full content of a .kicad_sym file containing one symbol."""
    width_mm = params.width / 1_000_000
    height_mm = params.height / 1_000_000
    name = f"Trackpad-{width_mm:g}x{height_mm:g}mm"

    tx_count = trackpad.tx_count
    rx_count = trackpad.rx_count

    # The sensor is self-capacitance: each electrode is a single node. We seat
    # TX columns on the top & bottom edges and RX rows on the left & right
    # edges, and give every electrode *two* same-numbered pins on opposite
    # edges. That makes the either-end connectivity explicit in the schematic —
    # KiCad treats duplicate pin numbers as one net, so wiring the column/row
    # from either end is functionally identical. Body is sized to seat the pins
    # with a floor so the self-capacitance note still fits.
    body_width = max(tx_count + 1, 6) * PIN_PITCH_MM
    body_height = max(rx_count + 1, 5) * PIN_PITCH_MM
    body_top = body_height / 2
    body_bottom = -body_top
    body_left = -body_width / 2
    body_right = body_width / 2
    tx_step = body_width / (tx_count + 1)
    rx_step = body_height / (rx_count + 1)

    pins: list[str] = []
    # TX columns -> top edge (270°, points down into body) + bottom edge (90°, up).
    # Pin numbers (c0..) match the footprint pad numbers exactly so the
    # symbol-to-footprint binding works without manual mapping.
    for i in range(tx_count):
        x = body_left + (i + 1) * tx_step
        pins.append(
            _pin(x=x, y=body_top + PIN_LENGTH_MM, angle_deg=270, name=f"TX{i}", number=f"c{i}")
        )
        pins.append(
            _pin(x=x, y=body_bottom - PIN_LENGTH_MM, angle_deg=90, name=f"TX{i}", number=f"c{i}")
        )
    # RX rows -> left edge (0°, points right) + right edge (180°, points left).
    for j in range(rx_count):
        y = body_top - (j + 1) * rx_step
        pins.append(
            _pin(x=body_left - PIN_LENGTH_MM, y=y, angle_deg=0, name=f"RX{j}", number=f"r{j}")
        )
        pins.append(
            _pin(x=body_right + PIN_LENGTH_MM, y=y, angle_deg=180, name=f"RX{j}", number=f"r{j}")
        )

    body_rect = (
        f"      (rectangle (start {body_left:.4f} {body_bottom:.4f}) "
        f"(end {body_right:.4f} {body_top:.4f}) "
        f"(stroke (width 0.254) (type default)) (fill (type background)))"
    )
    note = (
        '      (text "Self-capacitance\\nelectrode = one net\\nconnect either end" '
        "(at 0 0 0)\n"
        "        (effects (font (size 1.016 1.016))))"
    )
    pins_block = "\n".join(pins)
    ref_y = body_top + PIN_LENGTH_MM + 1.27
    val_y = body_bottom - PIN_LENGTH_MM - 1.27

    return f"""(kicad_symbol_lib (version 20231120) (generator "kicad-touchpad-wizard")
  (symbol "{_esc(name)}"
    (pin_names (offset 0.508))
    (in_bom yes) (on_board yes)
    (property "Reference" "TP" (at 0 {ref_y:.4f} 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "{_esc(name)}" (at 0 {val_y:.4f} 0)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "Trackpad:{_esc(name)}" (at 0 0 0)
      (effects (font (size 1.27 1.27)) hide))
    (property "Datasheet" "" (at 0 0 0)
      (effects (font (size 1.27 1.27)) hide))
    (property "Description" "Self-capacitance trackpad {width_mm:g}x{height_mm:g} mm \
({trackpad.tx_count} TX cols, {trackpad.rx_count} RX rows); each electrode is one node, \
connect either end" (at 0 0 0)
      (effects (font (size 1.27 1.27)) hide))
    (symbol "{_esc(name)}_1_1"
{body_rect}
{note}
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
