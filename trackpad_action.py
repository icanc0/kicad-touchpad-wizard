#!/usr/bin/env python3
"""Entrypoint KiCad launches for the "Generate trackpad" action (scope: pcb).

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


def _project_dir_from_kicad() -> Path | None:
    try:
        from kipy import KiCad

        board = KiCad().get_board()
        project_path = board.get_project().path
    except Exception as exc:  # noqa: BLE001 — any IPC failure means "ask the user"
        print(f"[touchpad-wizard] no project via IPC ({exc})", file=sys.stderr)
        return None
    if not project_path:
        return None
    # KiCad reports the project path; normalize file-vs-directory to the
    # directory containing the .kicad_pro.
    return find_project_dir(Path(project_path))


def main() -> int:
    return run_dialog(_project_dir_from_kicad())


if __name__ == "__main__":
    raise SystemExit(main())
