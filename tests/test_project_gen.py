"""Tests for the project-integration generator (libtable + project_gen)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trackpad.libtable import TableKind, has_lib, register_library, upsert_lib
from trackpad.params import TrackpadParams
from trackpad.project_gen import (
    GeneratedProject,
    find_project_dir,
    footprint_name,
    generate_into_project,
)
from trackpad.units import mm


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "demo.kicad_pro").write_text("{}", encoding="utf-8")
    return tmp_path


class TestLibTable:
    def test_creates_missing_table(self, project: Path) -> None:
        changed = register_library(
            project, TableKind.FOOTPRINT, "Trackpad", "${KIPRJMOD}/Trackpad.pretty", "d"
        )
        assert changed
        text = (project / "fp-lib-table").read_text(encoding="utf-8")
        assert text.startswith("(fp_lib_table")
        assert '(name "Trackpad")' in text
        assert '(uri "${KIPRJMOD}/Trackpad.pretty")' in text

    def test_appends_to_existing_table_preserving_entries(self, project: Path) -> None:
        existing = (
            "(fp_lib_table\n  (version 7)\n"
            '  (lib (name "MyLib")(type "KiCad")(uri "${KIPRJMOD}/my.pretty")'
            '(options "")(descr ""))\n)\n'
        )
        (project / "fp-lib-table").write_text(existing, encoding="utf-8")
        register_library(
            project, TableKind.FOOTPRINT, "Trackpad", "${KIPRJMOD}/Trackpad.pretty", "d"
        )
        text = (project / "fp-lib-table").read_text(encoding="utf-8")
        assert '(name "MyLib")' in text
        assert '(name "Trackpad")' in text
        # Still exactly one table, closed once
        assert text.count("(fp_lib_table") == 1

    def test_idempotent(self, project: Path) -> None:
        register_library(project, TableKind.SYMBOL, "Trackpad", "u", "d")
        before = (project / "sym-lib-table").read_text(encoding="utf-8")
        changed = register_library(project, TableKind.SYMBOL, "Trackpad", "u", "d")
        assert not changed
        assert (project / "sym-lib-table").read_text(encoding="utf-8") == before

    def test_does_not_clobber_existing_entry_with_different_uri(self) -> None:
        existing = (
            "(sym_lib_table\n  (version 7)\n"
            '  (lib (name "Trackpad")(type "KiCad")(uri "/custom/path.kicad_sym")'
            '(options "")(descr "user override"))\n)\n'
        )
        result = upsert_lib(existing, TableKind.SYMBOL, "Trackpad", "${KIPRJMOD}/x", "d")
        assert result == existing

    def test_has_lib_matches_unquoted_names(self) -> None:
        assert has_lib("(fp_lib_table (lib (name Trackpad)))", "Trackpad")


class TestGenerateIntoProject:
    def test_writes_footprint_symbol_and_tables(self, project: Path) -> None:
        params = TrackpadParams.defaults()
        result = generate_into_project(project, params)

        assert result.footprint_path.exists()
        assert result.footprint_path.name == "Trackpad-50x20mm.kicad_mod"
        assert result.footprint_path.parent.name == "Trackpad.pretty"
        assert result.symbol_lib_path.exists()
        assert (project / "fp-lib-table").exists()
        assert (project / "sym-lib-table").exists()
        assert result.footprint_lib_id == "Trackpad:Trackpad-50x20mm"

        fp_text = result.footprint_path.read_text(encoding="utf-8")
        assert fp_text.startswith('(footprint "Trackpad-50x20mm"')
        sym_text = result.symbol_lib_path.read_text(encoding="utf-8")
        assert '(symbol "Trackpad-50x20mm"' in sym_text
        # Symbol must point at the footprint through the registered nickname
        assert '"Footprint" "Trackpad:Trackpad-50x20mm"' in sym_text

    def test_second_size_accumulates_in_same_symbol_lib(self, project: Path) -> None:
        generate_into_project(project, TrackpadParams.defaults())
        from dataclasses import replace

        bigger = replace(TrackpadParams.defaults(), width=mm(80), height=mm(40))
        result = generate_into_project(project, bigger)

        sym_text = result.symbol_lib_path.read_text(encoding="utf-8")
        assert '(symbol "Trackpad-50x20mm"' in sym_text
        assert '(symbol "Trackpad-80x40mm"' in sym_text
        assert (project / "Trackpad.pretty" / "Trackpad-50x20mm.kicad_mod").exists()
        assert (project / "Trackpad.pretty" / "Trackpad-80x40mm.kicad_mod").exists()

    def test_regenerate_same_size_replaces_not_duplicates(self, project: Path) -> None:
        generate_into_project(project, TrackpadParams.defaults())
        result = generate_into_project(project, TrackpadParams.defaults())
        sym_text = result.symbol_lib_path.read_text(encoding="utf-8")
        assert sym_text.count('(symbol "Trackpad-50x20mm"') == 1
        assert not result.fp_table_created_or_updated
        assert not result.sym_table_created_or_updated

    def test_symbol_lib_stays_balanced(self, project: Path) -> None:
        generate_into_project(project, TrackpadParams.defaults())
        from dataclasses import replace

        generate_into_project(
            project, replace(TrackpadParams.defaults(), width=mm(30), height=mm(30))
        )
        text = (project / "Trackpad.kicad_sym").read_text(encoding="utf-8")
        assert text.count("(") == text.count(")")

    def test_invalid_params_raise(self, project: Path) -> None:
        from dataclasses import replace

        bad = replace(TrackpadParams.defaults(), width=mm(0))
        with pytest.raises(ValueError, match="positive"):
            generate_into_project(project, bad)

    def test_missing_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not a directory"):
            generate_into_project(tmp_path / "nope", TrackpadParams.defaults())

    def test_summary_mentions_reopen_only_when_tables_changed(self, project: Path) -> None:
        needle = "close and reopen the project"
        first = generate_into_project(project, TrackpadParams.defaults())
        assert any(needle in line for line in first.summary_lines())
        second = generate_into_project(project, TrackpadParams.defaults())
        assert not any(needle in line for line in second.summary_lines())

    def test_result_type_is_frozen(self, project: Path) -> None:
        result = generate_into_project(project, TrackpadParams.defaults())
        assert isinstance(result, GeneratedProject)
        with pytest.raises(AttributeError):
            result.symbol_name = "x"  # type: ignore[misc]


class TestFindProjectDir:
    def test_finds_from_subdirectory(self, project: Path) -> None:
        sub = project / "sub" / "deeper"
        sub.mkdir(parents=True)
        assert find_project_dir(sub) == project

    def test_finds_from_file_path(self, project: Path) -> None:
        f = project / "board.kicad_pcb"
        f.write_text("", encoding="utf-8")
        assert find_project_dir(f) == project

    def test_none_when_no_project(self, tmp_path: Path) -> None:
        lonely = tmp_path / "empty"
        lonely.mkdir()
        assert find_project_dir(lonely) is None


class TestFootprintName:
    def test_trailing_zeros_trimmed(self) -> None:
        from dataclasses import replace

        params = replace(TrackpadParams.defaults(), width=mm(50.5), height=mm(20))
        assert footprint_name(params) == "Trackpad-50.5x20mm"


class TestGenerateIntoLibrary:
    def test_writes_libs_and_registers_in_global_tables(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "kicad-config"
        fake_config.mkdir()
        monkeypatch.setenv("KICAD_CONFIG_HOME", str(fake_config))

        from trackpad.project_gen import generate_into_library

        lib_dir = tmp_path / "libs"
        result = generate_into_library(lib_dir, TrackpadParams.defaults())

        assert result.footprint_path.exists()
        assert result.symbol_lib_path.exists()
        assert result.registered_globally
        assert result.tables_changed
        fp_table = (fake_config / "fp-lib-table").read_text(encoding="utf-8")
        # global URIs must be absolute, not ${KIPRJMOD}
        assert str(lib_dir / "Trackpad.pretty") in fp_table
        assert "KIPRJMOD" not in fp_table
        assert (fake_config / "sym-lib-table").exists()

    def test_no_global_tables_found_degrades_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KICAD_CONFIG_HOME", str(tmp_path / "missing"))

        from trackpad.project_gen import generate_into_library

        result = generate_into_library(tmp_path / "libs", TrackpadParams.defaults())
        assert result.footprint_path.exists()
        assert not result.registered_globally
        assert any("manually" in line for line in result.summary_lines())

    def test_idempotent_registration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "kicad-config"
        fake_config.mkdir()
        monkeypatch.setenv("KICAD_CONFIG_HOME", str(fake_config))

        from trackpad.project_gen import generate_into_library

        generate_into_library(tmp_path / "libs", TrackpadParams.defaults())
        second = generate_into_library(tmp_path / "libs", TrackpadParams.defaults())
        assert not second.tables_changed


class TestFindGlobalTableDir:
    def test_env_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from trackpad.libtable import find_global_table_dir

        monkeypatch.setenv("KICAD_CONFIG_HOME", str(tmp_path))
        assert find_global_table_dir() == tmp_path

    def test_picks_highest_initialized_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from trackpad import libtable

        monkeypatch.delenv("KICAD_CONFIG_HOME", raising=False)
        base = tmp_path / ".config" / "kicad"
        for version, initialized in (("9.0", True), ("10.0", True), ("12.0", False)):
            d = base / version
            d.mkdir(parents=True)
            if initialized:
                (d / "kicad_common.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(libtable.Path, "home", classmethod(lambda cls: tmp_path))
        assert libtable.find_global_table_dir() == base / "10.0"
