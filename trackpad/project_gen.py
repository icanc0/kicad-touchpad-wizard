"""Generate a trackpad footprint + symbol *into a KiCad project* and wire it up.

This is the complete-experience path: given a project directory and parameters,
it leaves the project in a state where the schematic-to-PCB binding just works:

- ``<project>/Trackpad.pretty/Trackpad-<W>x<H>mm.kicad_mod`` — the footprint
- ``<project>/Trackpad.kicad_sym`` — symbol library (one file, symbols accumulate)
- ``fp-lib-table`` / ``sym-lib-table`` — both libraries registered under the
  nickname ``Trackpad`` with ``${KIPRJMOD}`` relative paths (the project stays
  relocatable / git-cloneable)

The generated symbol's Footprint property is ``Trackpad:Trackpad-<W>x<H>mm``,
which resolves through the fp-lib-table entry written here. Place the symbol in
eeschema, press F8, and the footprint lands on the board already bound.

Everything here is plain file I/O — no kipy, no running KiCad required — so it
is fully unit-testable and doubles as the backend for both the CLI
(``emit-project``) and the in-KiCad action plugin GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trackpad.geometry import Trackpad, build_trackpad
from trackpad.kicad_mod import render_footprint
from trackpad.libtable import TableKind, register_library
from trackpad.params import TrackpadParams
from trackpad.symbol import render_symbol, upsert_symbol_into_library_file

LIB_NICKNAME = "Trackpad"
PRETTY_DIR = f"{LIB_NICKNAME}.pretty"
SYMBOL_LIB_FILE = f"{LIB_NICKNAME}.kicad_sym"


def footprint_name(params: TrackpadParams) -> str:
    return f"Trackpad-{params.width / 1_000_000:g}x{params.height / 1_000_000:g}mm"


@dataclass(frozen=True, slots=True)
class GeneratedProject:
    """Everything the generator touched, for reporting back to the user."""

    project_dir: Path
    footprint_path: Path
    symbol_lib_path: Path
    footprint_lib_id: str  # e.g. "Trackpad:Trackpad-50x20mm"
    symbol_name: str
    fp_table_created_or_updated: bool
    sym_table_created_or_updated: bool
    trackpad: Trackpad

    def summary_lines(self) -> list[str]:
        """Human-readable report of what happened, used by both CLI and GUI."""
        lines = [
            f"Footprint:  {self.footprint_path}",
            f"Symbol:     {self.symbol_name!r} in {self.symbol_lib_path}",
        ]
        if self.fp_table_created_or_updated:
            lines.append("Registered footprint library 'Trackpad' in fp-lib-table")
        if self.sym_table_created_or_updated:
            lines.append("Registered symbol library 'Trackpad' in sym-lib-table")
        if self.fp_table_created_or_updated or self.sym_table_created_or_updated:
            lines.append("")
            lines.append("KiCad reads library tables when a project opens:")
            lines.append("close and reopen the project to see the new libraries.")
        lines.append("")
        lines.append(f"Then: place symbol {self.footprint_lib_id!r} in the schematic")
        lines.append("and use Update PCB from Schematic (F8) — the footprint is")
        lines.append("already bound through the symbol's Footprint property.")
        return lines


def generate_into_project(project_dir: Path, params: TrackpadParams) -> GeneratedProject:
    """Write footprint + symbol libraries into `project_dir` and register them.

    `project_dir` must be the directory containing the ``.kicad_pro`` file.
    Raises ValueError on invalid params, OSError on filesystem problems.
    """
    err = params.validate()
    if err is not None:
        raise ValueError(err)
    if not project_dir.is_dir():
        raise ValueError(f"not a directory: {project_dir}")

    name = footprint_name(params)
    trackpad = build_trackpad(params)

    pretty = project_dir / PRETTY_DIR
    pretty.mkdir(exist_ok=True)
    footprint_path = pretty / f"{name}.kicad_mod"
    footprint_path.write_text(render_footprint(trackpad, params), encoding="utf-8")

    symbol_lib_path = project_dir / SYMBOL_LIB_FILE
    existing = (
        symbol_lib_path.read_text(encoding="utf-8") if symbol_lib_path.exists() else None
    )
    merged = upsert_symbol_into_library_file(existing, render_symbol(trackpad, params), name)
    symbol_lib_path.write_text(merged, encoding="utf-8")

    fp_changed = register_library(
        project_dir,
        TableKind.FOOTPRINT,
        LIB_NICKNAME,
        f"${{KIPRJMOD}}/{PRETTY_DIR}",
        "Generated trackpad footprints (kicad-touchpad-wizard)",
    )
    sym_changed = register_library(
        project_dir,
        TableKind.SYMBOL,
        LIB_NICKNAME,
        f"${{KIPRJMOD}}/{SYMBOL_LIB_FILE}",
        "Generated trackpad symbols (kicad-touchpad-wizard)",
    )

    return GeneratedProject(
        project_dir=project_dir,
        footprint_path=footprint_path,
        symbol_lib_path=symbol_lib_path,
        footprint_lib_id=f"{LIB_NICKNAME}:{name}",
        symbol_name=name,
        fp_table_created_or_updated=fp_changed,
        sym_table_created_or_updated=sym_changed,
        trackpad=trackpad,
    )


def find_project_dir(start: Path) -> Path | None:
    """Locate the KiCad project directory at or above `start` (has a .kicad_pro)."""
    candidate = start if start.is_dir() else start.parent
    for directory in (candidate, *candidate.parents):
        if any(directory.glob("*.kicad_pro")):
            return directory
    return None
