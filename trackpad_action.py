#!/usr/bin/env python3
"""Entrypoint KiCad launches for the "Generate trackpad" action.

The action is scoped to both the schematic editor and the PCB editor — the
intended flow is symbol-first (generate from eeschema, place the symbol, F8),
but the same dialog works from either side.

KiCad runs this script in the plugin's provisioned venv with KICAD_API_SOCKET
and KICAD_API_TOKEN set, so ``kipy.KiCad()`` connects without configuration.
We use the connection for exactly one thing: finding the open project's
directory so the dialog starts pointed at the right place. Every failure mode
degrades to the dialog's manual directory picker — the generator itself never
needs a running KiCad.
"""

from __future__ import annotations

import sys
from pathlib import Path

from trackpad.action_gui import run_dialog
from trackpad.project_gen import find_project_dir


def _project_path_probes() -> list[str]:
    """Project-path candidates from the running KiCad, best-effort.

    Launched from eeschema there may be no board open (get_board fails), and
    vice versa; in KiCad 10.0 each editor only answers for its own documents.
    Probe both and take whatever answers first.
    """
    from kipy import KiCad
    from kipy.proto.common.types import DocumentType

    kicad = KiCad()
    paths: list[str] = []

    try:
        for doc in kicad.get_open_documents(DocumentType.DOCTYPE_SCHEMATIC):
            paths.append(doc.project.path)
    except Exception as exc:  # noqa: BLE001 — probe failure is expected without eeschema
        print(f"[touchpad-wizard] no schematic documents ({exc})", file=sys.stderr)

    try:
        paths.append(kicad.get_board().get_project().path)
    except Exception as exc:  # noqa: BLE001 — probe failure is expected without pcbnew
        print(f"[touchpad-wizard] no board open ({exc})", file=sys.stderr)

    return [p for p in paths if p]


def _project_dir_from_kicad() -> Path | None:
    try:
        paths = _project_path_probes()
    except Exception as exc:  # noqa: BLE001 — any IPC failure means "ask the user"
        print(f"[touchpad-wizard] no project via IPC ({exc})", file=sys.stderr)
        return None
    for path in paths:
        # KiCad reports the project path; normalize file-vs-directory to the
        # directory containing the .kicad_pro.
        if found := find_project_dir(Path(path)):
            return found
    return None


def _place_callback():
    """Build a place-on-board callback if a board is reachable, else None.

    The kipy Board handle is resolved once here; the callback then only does
    the create_items round trip when the user generates with placement on.
    """
    try:
        from kipy import KiCad

        board = KiCad().get_board()
    except Exception:  # noqa: BLE001 — no board (e.g. launched from eeschema)
        return None

    from trackpad.board_place import place_on_board
    from trackpad.params import TrackpadParams

    def place(params: TrackpadParams) -> str:
        return place_on_board(board, params)

    return place


def main() -> int:
    return run_dialog(_project_dir_from_kicad(), _place_callback())


if __name__ == "__main__":
    raise SystemExit(main())
