"""Register libraries in KiCad project library tables (fp-lib-table / sym-lib-table).

These are the small s-expression files in a project directory that map a library
*nickname* (the part before the colon in ``Trackpad:Trackpad-50x20mm``) to a path
on disk. Registering our generated libraries here is what makes the
symbol -> footprint binding resolve with zero manual setup.

KiCad reads project tables at project-open time, so a running KiCad instance
needs the project closed and reopened to pick up a new entry. We only ever
*append* a missing entry (never rewrite existing ones), so re-running the
generator is idempotent and user edits are preserved.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class TableKind(Enum):
    FOOTPRINT = "fp_lib_table"
    SYMBOL = "sym_lib_table"

    @property
    def filename(self) -> str:
        return "fp-lib-table" if self is TableKind.FOOTPRINT else "sym-lib-table"


def _empty_table(kind: TableKind) -> str:
    return f"({kind.value}\n  (version 7)\n)\n"


def _lib_entry(nickname: str, uri: str, description: str) -> str:
    return (
        f'  (lib (name "{nickname}")(type "KiCad")(uri "{uri}")'
        f'(options "")(descr "{description}"))\n'
    )


def has_lib(table_text: str, nickname: str) -> bool:
    """True if the table already contains a library with this nickname."""
    return f'(name "{nickname}")' in table_text or f"(name {nickname})" in table_text


def upsert_lib(table_text: str, kind: TableKind, nickname: str, uri: str, description: str) -> str:
    """Return table text guaranteed to contain `nickname`; appends if missing.

    Existing entries are left untouched even if their URI differs — clobbering a
    user's hand-edited table entry is worse than a stale path.
    """
    if has_lib(table_text, nickname):
        return table_text
    closing = table_text.rfind(")")
    if closing == -1:
        # Corrupt/empty file: rebuild a valid table around our entry.
        return _empty_table(kind).replace("\n)", "\n" + _lib_entry(nickname, uri, description) + ")")
    return table_text[:closing] + _lib_entry(nickname, uri, description) + table_text[closing:]


def register_library(
    project_dir: Path, kind: TableKind, nickname: str, uri: str, description: str
) -> bool:
    """Ensure the project's lib table registers `nickname` -> `uri`.

    Creates the table file if the project doesn't have one yet. Returns True if
    the file was modified (False means the entry was already present).
    """
    table_path = project_dir / kind.filename
    text = table_path.read_text(encoding="utf-8") if table_path.exists() else _empty_table(kind)
    updated = upsert_lib(text, kind, nickname, uri, description)
    if updated == text and table_path.exists():
        return False
    table_path.write_text(updated, encoding="utf-8")
    return True
