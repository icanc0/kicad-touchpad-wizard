"""kipy WizardBase implementation: declares parameters, builds the Footprint.

Also writes a matching .kicad_sym to disk so the schematic side of the binding works.
The symbol-on-disk path is reported via the wizard description so users can find it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from kipy.board_types import Footprint
from kipy.proto.common.types.wizards_pb2 import (
    WizardContentType,
    WizardParameterCategory,
    WizardParameterDataType,
)
from kipy.wizards import WizardBase, WizardInfo, WizardMetaInfo, WizardParameter

# Importing any trackpad submodule triggers trackpad/__init__.py, which patches the
# kipy 0.7.1 missing-export bug *before* any WizardInfo()/WizardMetaInfo() call below.
from trackpad.footprint import to_footprint
from trackpad.geometry import build_trackpad
from trackpad.params import TrackpadParams
from trackpad.symbol import render_symbol
from trackpad.units import mm

IDENTIFIER = "io.github.icanc0.touchpad-wizard"
NAME = "Trackpad"
DESCRIPTION = (
    "Generates a capacitive trackpad footprint plus a matching schematic symbol "
    "(written to a .kicad_sym file alongside the project so pad numbers and pin "
    "numbers always line up)."
)


def symbol_library_path() -> Path:
    """Path of the .kicad_sym file we append generated symbols to.

    Uses KICAD_TOUCHPAD_WIZARD_SYM_LIB env var if set, otherwise
    `~/Documents/KiCad/touchpad-wizard.kicad_sym`. Users add this file once as
    a symbol library; subsequent wizard runs append more symbols to it.
    """
    override = os.environ.get("KICAD_TOUCHPAD_WIZARD_SYM_LIB")
    if override:
        return Path(override)
    return Path.home() / "Documents" / "KiCad" / "touchpad-wizard.kicad_sym"


def _ensure_symbol_library_exists(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '(kicad_symbol_lib (version 20231120) (generator "kicad-touchpad-wizard")\n)\n',
        encoding="utf-8",
    )


def _upsert_symbol(library_text: str, symbol_block: str, name: str) -> str:
    """Replace the symbol named `name` in `library_text`, or append it before the close paren."""
    needle = f'(symbol "{name}"'
    start = library_text.find(needle)
    if start != -1:
        depth = 0
        i = start
        while i < len(library_text):
            c = library_text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    return library_text[:start] + symbol_block.strip() + library_text[end:]
            i += 1

    # No existing entry — append before the closing paren of kicad_symbol_lib
    closing = library_text.rfind(")")
    if closing == -1:
        return library_text + "\n" + symbol_block
    return library_text[:closing] + "  " + symbol_block.strip() + "\n" + library_text[closing:]


def write_symbol_library(symbol_file_text: str, symbol_name: str) -> Path:
    """Append (or replace) one symbol in the user's symbol library on disk."""
    path = symbol_library_path()
    _ensure_symbol_library_exists(path)
    existing = path.read_text(encoding="utf-8")

    # The single-symbol file produced by render_symbol() wraps the symbol in its
    # own kicad_symbol_lib. Extract just the (symbol ...) block.
    block_start = symbol_file_text.find('(symbol "')
    if block_start == -1:
        raise ValueError("symbol file has no (symbol ...) block")
    depth = 0
    i = block_start
    while i < len(symbol_file_text):
        c = symbol_file_text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                block = symbol_file_text[block_start : i + 1]
                merged = _upsert_symbol(existing, block, symbol_name)
                path.write_text(merged, encoding="utf-8")
                return path
        i += 1
    raise ValueError("unbalanced parentheses in symbol file")


class TrackpadWizard(WizardBase):
    def __init__(self) -> None:
        super().__init__(DESCRIPTION)

    def build_wizard_info(self) -> WizardInfo:
        info = WizardInfo()
        meta = WizardMetaInfo()
        meta.identifier = IDENTIFIER
        meta.name = NAME
        meta.description = DESCRIPTION
        meta.types_generated = [WizardContentType.WCT_FOOTPRINT]
        info.meta = meta
        info.parameters = _parameter_definitions()
        return info

    def build_generated_content(
        self, parameters: list[WizardParameter] | None = None
    ) -> Footprint:
        params = TrackpadParams.from_wizard_params(parameters)
        err = params.validate()
        if err is not None:
            raise ValueError(err)

        trackpad = build_trackpad(params)
        footprint = to_footprint(trackpad, params)

        # Side-channel symbol emission. Failures here don't abort the footprint
        # generation -- the user can still place the pad, and we surface the
        # error via stderr so it shows up in KiCad's plugin console.
        try:
            symbol_text = render_symbol(trackpad, params)
            symbol_name = f"Trackpad-{params.width / 1_000_000:g}x{params.height / 1_000_000:g}mm"
            written = write_symbol_library(symbol_text, symbol_name)
            print(f"[touchpad-wizard] wrote symbol to {written}", file=sys.stderr)
        except OSError as exc:
            print(f"[touchpad-wizard] could not write symbol library: {exc}", file=sys.stderr)

        return footprint


def _parameter_definitions() -> list[WizardParameter]:
    """Declare every wizard parameter once, in display order."""
    defaults = TrackpadParams.defaults()
    return [
        WizardParameter.create(
            identifier="width",
            name="Width",
            description="Overall trackpad width",
            category=WizardParameterCategory.WPC_PACKAGE,
            data_type=WizardParameterDataType.WPDT_DISTANCE,
            value=int(defaults.width),
            min_value=int(mm(1)),
        ),
        WizardParameter.create(
            identifier="height",
            name="Height",
            description="Overall trackpad height",
            category=WizardParameterCategory.WPC_PACKAGE,
            data_type=WizardParameterDataType.WPDT_DISTANCE,
            value=int(defaults.height),
            min_value=int(mm(1)),
        ),
        WizardParameter.create(
            identifier="edge_segments_x",
            name="TX columns",
            description="Number of capacitive TX columns (vertical strips)",
            category=WizardParameterCategory.WPC_PACKAGE,
            data_type=WizardParameterDataType.WPDT_INTEGER,
            value=defaults.edge_segments_x,
            min_value=4,
            max_value=64,
        ),
        WizardParameter.create(
            identifier="edge_segments_y",
            name="RX rows",
            description="Number of capacitive RX rows (horizontal strips)",
            category=WizardParameterCategory.WPC_PACKAGE,
            data_type=WizardParameterDataType.WPDT_INTEGER,
            value=defaults.edge_segments_y,
            min_value=4,
            max_value=64,
        ),
        WizardParameter.create(
            identifier="via_diameter",
            name="Via diameter",
            description="Diameter of the routing vias",
            category=WizardParameterCategory.WPC_PADS,
            data_type=WizardParameterDataType.WPDT_DISTANCE,
            value=int(defaults.via_diameter),
            min_value=int(mm(0.2)),
        ),
        WizardParameter.create(
            identifier="via_drill",
            name="Via drill",
            description="Drill diameter of the routing vias",
            category=WizardParameterCategory.WPC_PADS,
            data_type=WizardParameterDataType.WPDT_DISTANCE,
            value=int(defaults.via_drill),
            min_value=int(mm(0.1)),
        ),
        WizardParameter.create(
            identifier="clearance",
            name="Clearance",
            description="Space between adjacent electrodes",
            category=WizardParameterCategory.WPC_PADS,
            data_type=WizardParameterDataType.WPDT_DISTANCE,
            value=int(defaults.clearance),
            min_value=int(mm(0.05)),
        ),
        WizardParameter.create(
            identifier="line_width",
            name="Line width",
            description="Width of the routing copper lines",
            category=WizardParameterCategory.WPC_PADS,
            data_type=WizardParameterDataType.WPDT_DISTANCE,
            value=int(defaults.line_width),
            min_value=int(mm(0.05)),
        ),
        WizardParameter.create(
            identifier="drill_holes",
            name="Place routing vias",
            description="Drop a PTH pad at each TX electrode to route down to the back layer",
            category=WizardParameterCategory.WPC_RULES,
            data_type=WizardParameterDataType.WPDT_BOOL,
            value=defaults.drill_holes,
        ),
        WizardParameter.create(
            identifier="add_lines",
            name="Draw routing lines",
            description="Draw front/back copper traces between electrodes",
            category=WizardParameterCategory.WPC_RULES,
            data_type=WizardParameterDataType.WPDT_BOOL,
            value=defaults.add_lines,
        ),
        WizardParameter.create(
            identifier="add_front_wiring",
            name="Front wiring",
            description="Add front-side copper traces for RX rows",
            category=WizardParameterCategory.WPC_RULES,
            data_type=WizardParameterDataType.WPDT_BOOL,
            value=defaults.add_front_wiring,
        ),
        WizardParameter.create(
            identifier="add_back_wiring",
            name="Back wiring",
            description="Add back-side copper traces for TX columns",
            category=WizardParameterCategory.WPC_RULES,
            data_type=WizardParameterDataType.WPDT_BOOL,
            value=defaults.add_back_wiring,
        ),
        WizardParameter.create(
            identifier="add_soldermask",
            name="Solder mask over pads",
            description="Cover the touch pads with solder mask (recommended for production)",
            category=WizardParameterCategory.WPC_RULES,
            data_type=WizardParameterDataType.WPDT_BOOL,
            value=defaults.add_soldermask,
        ),
        WizardParameter.create(
            identifier="triangle_angle",
            name="Triangle angle",
            description="Rotation of the trapezoidal pad pattern (degrees)",
            category=WizardParameterCategory.WPC_PACKAGE,
            data_type=WizardParameterDataType.WPDT_ANGLE,
            value=float(defaults.triangle_angle),
            min_value=0.0,
            max_value=360.0,
        ),
    ]


def _cli_emit(argv: list[str]) -> int:
    """Standalone CLI: write .kicad_mod and .kicad_sym to disk.

    Usable without KiCad's wizard system at all. For people who just want files.
    """
    import argparse

    from trackpad.kicad_mod import render_footprint

    parser = argparse.ArgumentParser(
        prog="touchpad-wizard emit",
        description="Generate a trackpad footprint and matching symbol on disk.",
    )
    parser.add_argument("--width", type=float, default=50.0, help="width in mm (default 50)")
    parser.add_argument("--height", type=float, default=20.0, help="height in mm (default 20)")
    parser.add_argument("--tx-columns", type=int, default=5, help="TX columns (default 5)")
    parser.add_argument("--rx-rows", type=int, default=5, help="RX rows (default 5)")
    parser.add_argument(
        "--via-diameter", type=float, default=0.5, help="via diameter mm (default 0.5)"
    )
    parser.add_argument(
        "--via-drill", type=float, default=0.3, help="via drill mm (default 0.3)"
    )
    parser.add_argument(
        "--clearance", type=float, default=0.2, help="electrode clearance mm (default 0.2)"
    )
    parser.add_argument(
        "--line-width", type=float, default=0.127, help="line width mm (default 0.127)"
    )
    parser.add_argument("--no-drill-holes", action="store_true")
    parser.add_argument("--no-lines", action="store_true")
    parser.add_argument("--no-front-wiring", action="store_true")
    parser.add_argument("--no-back-wiring", action="store_true")
    parser.add_argument("--no-soldermask", action="store_true")
    parser.add_argument(
        "--triangle-angle", type=float, default=135.0, help="degrees (default 135)"
    )
    parser.add_argument(
        "--footprint", type=Path, required=True, help="output .kicad_mod path"
    )
    parser.add_argument("--symbol", type=Path, help="output .kicad_sym path (optional)")
    args = parser.parse_args(argv)

    from trackpad.units import Degrees
    from trackpad.units import mm as nm_from_mm

    params = TrackpadParams(
        width=nm_from_mm(args.width),
        height=nm_from_mm(args.height),
        edge_segments_x=args.tx_columns,
        edge_segments_y=args.rx_rows,
        via_diameter=nm_from_mm(args.via_diameter),
        via_drill=nm_from_mm(args.via_drill),
        clearance=nm_from_mm(args.clearance),
        line_width=nm_from_mm(args.line_width),
        drill_holes=not args.no_drill_holes,
        add_lines=not args.no_lines,
        add_front_wiring=not args.no_front_wiring,
        add_back_wiring=not args.no_back_wiring,
        add_soldermask=not args.no_soldermask,
        triangle_angle=Degrees(args.triangle_angle),
    )
    err = params.validate()
    if err is not None:
        print(f"error: {err}", file=sys.stderr)
        return 1

    trackpad = build_trackpad(params)
    footprint_text = render_footprint(trackpad, params)
    args.footprint.parent.mkdir(parents=True, exist_ok=True)
    args.footprint.write_text(footprint_text, encoding="utf-8")
    print(f"wrote footprint: {args.footprint}")

    if args.symbol:
        symbol_text = render_symbol(trackpad, params)
        args.symbol.parent.mkdir(parents=True, exist_ok=True)
        args.symbol.write_text(symbol_text, encoding="utf-8")
        print(f"wrote symbol: {args.symbol}")
    return 0


def _cli_emit_circle(argv: list[str]) -> int:
    """Standalone CLI for the circular/wheel trackpad shape."""
    import argparse

    from trackpad.circular import (
        CircularParams,
        build_circular_trackpad,
        render_circular_footprint,
    )
    from trackpad.units import mm as nm_from_mm

    parser = argparse.ArgumentParser(
        prog="touchpad-wizard emit-circle",
        description="Generate a circular (wheel) trackpad footprint.",
    )
    parser.add_argument("--diameter", type=float, default=50.0, help="outer diameter in mm")
    parser.add_argument("--inner-diameter", type=float, default=6.0, help="inner hole diameter in mm")
    parser.add_argument("--sectors", type=int, default=8, help="angular TX sectors")
    parser.add_argument("--rings", type=int, default=3, help="concentric RX rings")
    parser.add_argument("--clearance", type=float, default=0.2, help="electrode clearance mm")
    parser.add_argument("--no-soldermask", action="store_true")
    parser.add_argument("--footprint", type=Path, required=True, help="output .kicad_mod path")
    args = parser.parse_args(argv)

    params = CircularParams(
        outer_radius=nm_from_mm(args.diameter / 2),
        inner_radius=nm_from_mm(args.inner_diameter / 2),
        sectors=args.sectors,
        rings=args.rings,
        clearance=nm_from_mm(args.clearance),
        add_soldermask=not args.no_soldermask,
        arc_steps_per_sector=8,
    )
    err = params.validate()
    if err is not None:
        print(f"error: {err}", file=sys.stderr)
        return 1

    trackpad = build_circular_trackpad(params)
    text = render_circular_footprint(trackpad)
    args.footprint.parent.mkdir(parents=True, exist_ok=True)
    args.footprint.write_text(text, encoding="utf-8")
    print(f"wrote footprint: {args.footprint}")
    return 0


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "emit":
        sys.exit(_cli_emit(argv[1:]))
    if argv and argv[0] == "emit-circle":
        sys.exit(_cli_emit_circle(argv[1:]))
    TrackpadWizard().run()


if __name__ == "__main__":
    main()
