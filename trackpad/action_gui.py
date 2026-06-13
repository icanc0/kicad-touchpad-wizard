"""tkinter dialog for the in-KiCad action plugin (scope: pcb).

KiCad launches ``trackpad_action.py`` in the plugin venv when the toolbar
button is clicked; that entrypoint resolves the open project via the IPC API
and hands the directory to :func:`run_dialog`. Everything KiCad-specific stays
out of this module so it can run (and be partially tested) standalone:

    python -m trackpad.action_gui --project ~/my-kicad-project

tkinter is the dialog toolkit because it ships with CPython — the KiCad plugin
venv inherits it from the base interpreter, so there is nothing to install.

The preview canvas draws the *real* pad polygons from the geometry layer (the
same vertices that end up in the .kicad_mod), scaled to fit — not a sketch.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from trackpad.geometry import Layer, Trackpad, build_trackpad
from trackpad.params import ConnectionStyle, TrackpadParams
from trackpad.project_gen import generate_into_library, generate_into_project
from trackpad.units import Degrees, mm

# pcbnew-ish dark theme
_BG = "#001017"
_FCU = "#C83434"
_BCU = "#4D7FC4"
_HOLE = "#11181F"
_OUTLINE = "#3A4148"

_PREVIEW_W = 460
_PREVIEW_H = 300
_MARGIN = 16

# Matches sv-ttk's dark palette for the widgets it can't theme (tk.Text, Canvas)
_CARD_BG = "#1C1C1C"
_CARD_FG = "#FAFAFA"


def apply_theme(root: tk.Tk) -> bool:
    """Make tkinter not look like 1996. Returns True if the modern theme loaded.

    Uses sv-ttk (pure-Python Sun Valley theme) when available — it is in
    requirements.txt so KiCad's plugin venv installs it automatically — and
    falls back to ttk's 'clam' so the stdlib-only path still avoids Motif.
    Also fixes font sizing on HiDPI displays.
    """
    try:
        dpi = root.winfo_fpixels("1i")
        if dpi > 100:
            root.tk.call("tk", "scaling", dpi / 72.0)
    except tk.TclError:
        pass

    from tkinter import font

    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            f = font.nametofont(name)
            if f.cget("size") < 10:
                f.configure(size=10)
        except tk.TclError:
            continue

    try:
        import sv_ttk  # type: ignore[import-not-found]
    except ImportError:
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        return False
    sv_ttk.set_theme("dark")
    return True


@dataclass(frozen=True, slots=True)
class PreviewShapes:
    """Canvas-space primitives for one trackpad, ready to draw."""

    polygons_front: list[tuple[float, ...]]  # flattened x0,y0,x1,y1,...
    rects_front: list[tuple[float, float, float, float]]
    circles: list[tuple[float, float, float, float, bool]]  # x0,y0,x1,y1, is_drill
    segments: list[tuple[float, float, float, float, bool]]  # x0,y0,x1,y1, is_front
    outline: tuple[float, float, float, float]


def compute_preview(
    trackpad: Trackpad,
    width_nm: int,
    height_nm: int,
    canvas_w: int = _PREVIEW_W,
    canvas_h: int = _PREVIEW_H,
    margin: int = _MARGIN,
) -> PreviewShapes:
    """Scale the trackpad geometry to canvas pixels. Pure — unit-testable."""
    scale = min(
        (canvas_w - 2 * margin) / width_nm,
        (canvas_h - 2 * margin) / height_nm,
    )
    # Geometry is centred on the footprint origin; centre it on the canvas.
    ox = canvas_w / 2
    oy = canvas_h / 2

    def px(x_nm: float, y_nm: float) -> tuple[float, float]:
        return (ox + x_nm * scale, oy + y_nm * scale)

    polygons: list[tuple[float, ...]] = []
    for pad in trackpad.pads:
        coords: list[float] = []
        for vertex in pad.vertices:
            coords.extend(px(vertex.x, vertex.y))
        polygons.append(tuple(coords))

    rects: list[tuple[float, float, float, float]] = []
    for landing in trackpad.landings:
        x0, y0 = px(landing.center.x - landing.size_x / 2, landing.center.y - landing.size_y / 2)
        x1, y1 = px(landing.center.x + landing.size_x / 2, landing.center.y + landing.size_y / 2)
        rects.append((x0, y0, x1, y1))

    circles: list[tuple[float, float, float, float, bool]] = []
    for via in trackpad.vias:
        for diameter, is_drill in ((via.diameter, False), (via.drill, True)):
            x0, y0 = px(via.position.x - diameter / 2, via.position.y - diameter / 2)
            x1, y1 = px(via.position.x + diameter / 2, via.position.y + diameter / 2)
            circles.append((x0, y0, x1, y1, is_drill))

    segments: list[tuple[float, float, float, float, bool]] = []
    for seg in trackpad.segments:
        sx, sy = px(seg.start.x, seg.start.y)
        ex, ey = px(seg.end.x, seg.end.y)
        segments.append((sx, sy, ex, ey, seg.layer is Layer.F_CU))

    ol_x0, ol_y0 = px(-width_nm / 2, -height_nm / 2)
    ol_x1, ol_y1 = px(width_nm / 2, height_nm / 2)
    return PreviewShapes(
        polygons_front=polygons,
        rects_front=rects,
        circles=circles,
        segments=segments,
        outline=(ol_x0, ol_y0, ol_x1, ol_y1),
    )


class _ParamForm:
    """The parameter widgets and their typed extraction into TrackpadParams."""

    def __init__(self, parent: tk.Misc, on_change: Callable[[], None]) -> None:
        self._on_change = on_change

        self.width_mm = tk.StringVar(value="50")
        self.height_mm = tk.StringVar(value="20")
        self.tx_columns = tk.StringVar(value="5")
        self.rx_rows = tk.StringVar(value="5")
        self.clearance_mm = tk.StringVar(value="0.2")
        self.connection_style = tk.StringVar(value=ConnectionStyle.APEX_ONLY.value)
        self.landing_mm = tk.StringVar(value="1.0")
        self.vias = tk.BooleanVar(value=True)
        self.lines = tk.BooleanVar(value=True)
        self.front_wiring = tk.BooleanVar(value=True)
        self.back_wiring = tk.BooleanVar(value=True)
        self.soldermask = tk.BooleanVar(value=True)

        size = ttk.LabelFrame(parent, text="Size", padding=(4, 4))
        size.pack(fill="x", padx=8, pady=(8, 4))
        self._spin(size, "Width (mm)", self.width_mm, 0, 5, 300, 5)
        self._spin(size, "Height (mm)", self.height_mm, 1, 5, 300, 5)

        grid = ttk.LabelFrame(parent, text="Electrodes", padding=(4, 4))
        grid.pack(fill="x", padx=8, pady=4)
        self._spin(grid, "TX columns", self.tx_columns, 0, 4, 64, 1)
        self._spin(grid, "RX rows", self.rx_rows, 1, 4, 64, 1)
        self._spin(grid, "Clearance (mm)", self.clearance_mm, 2, 0.05, 2, 0.05)

        conn = ttk.LabelFrame(parent, text="Edge connection", padding=(4, 4))
        conn.pack(fill="x", padx=8, pady=4)
        ttk.Label(conn, text="Style").grid(row=0, column=0, sticky="w", padx=6, pady=2)
        style_box = ttk.Combobox(
            conn,
            textvariable=self.connection_style,
            values=[s.value for s in ConnectionStyle],
            state="readonly",
            width=10,
        )
        style_box.grid(row=0, column=1, sticky="ew", padx=6, pady=2)
        self._landing_spin = self._spin(conn, "Landing (mm)", self.landing_mm, 1, 0.2, 5, 0.1)
        conn.columnconfigure(1, weight=1)

        opts = ttk.LabelFrame(parent, text="Options", padding=(4, 4))
        opts.pack(fill="x", padx=8, pady=4)
        for row, (label, var) in enumerate(
            (
                ("Routing vias", self.vias),
                ("Routing lines", self.lines),
                ("Front (RX) wiring", self.front_wiring),
                ("Back (TX) wiring", self.back_wiring),
                ("Solder mask over pads", self.soldermask),
            )
        ):
            check = ttk.Checkbutton(opts, text=label, variable=var, command=on_change)
            check.grid(row=row, column=0, sticky="w", padx=6, pady=1)

        for var in (
            self.width_mm,
            self.height_mm,
            self.tx_columns,
            self.rx_rows,
            self.clearance_mm,
            self.connection_style,
            self.landing_mm,
        ):
            var.trace_add("write", self._changed)

    def _spin(
        self,
        parent: tk.Misc,
        label: str,
        var: tk.StringVar,
        row: int,
        lo: float,
        hi: float,
        step: float,
    ) -> ttk.Spinbox:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=2)
        spin = ttk.Spinbox(parent, textvariable=var, from_=lo, to=hi, increment=step, width=8)
        spin.grid(row=row, column=1, sticky="ew", padx=6, pady=2)
        parent.columnconfigure(1, weight=1)
        return spin

    def _changed(self, _name: str, _index: str, _mode: str) -> None:
        landing_state = (
            "disabled"
            if self.connection_style.get() == ConnectionStyle.APEX_ONLY.value
            else "normal"
        )
        self._landing_spin.configure(state=landing_state)
        self._on_change()

    def current_params(self) -> TrackpadParams:
        """Parse the form. Raises ValueError with a user-readable message."""

        def fnum(var: tk.StringVar, label: str) -> float:
            try:
                return float(var.get())
            except ValueError:
                raise ValueError(f"{label}: not a number") from None

        def inum(var: tk.StringVar, label: str) -> int:
            try:
                return int(var.get())
            except ValueError:
                raise ValueError(f"{label}: not a whole number") from None

        defaults = TrackpadParams.defaults()
        return TrackpadParams(
            width=mm(fnum(self.width_mm, "width")),
            height=mm(fnum(self.height_mm, "height")),
            edge_segments_x=inum(self.tx_columns, "TX columns"),
            edge_segments_y=inum(self.rx_rows, "RX rows"),
            via_diameter=defaults.via_diameter,
            via_drill=defaults.via_drill,
            clearance=mm(fnum(self.clearance_mm, "clearance")),
            line_width=defaults.line_width,
            drill_holes=self.vias.get(),
            add_lines=self.lines.get(),
            add_front_wiring=self.front_wiring.get(),
            add_back_wiring=self.back_wiring.get(),
            add_soldermask=self.soldermask.get(),
            triangle_angle=Degrees(float(defaults.triangle_angle)),
            connection_style=ConnectionStyle.from_str(self.connection_style.get()),
            landing_size=mm(fnum(self.landing_mm, "landing size")),
        )


DEFAULT_GLOBAL_LIB_DIR = Path.home() / "Documents" / "KiCad" / "trackpad-lib"

PlaceCallback = Callable[[TrackpadParams], str]


class TrackpadDialog:
    """Main window: parameter form, live preview, destination choice, generate."""

    def __init__(
        self,
        root: tk.Tk,
        project_dir: Path | None,
        place: PlaceCallback | None = None,
        modern: bool = False,
    ) -> None:
        self._root = root
        self._project_dir = project_dir
        self._place = place
        root.title("Trackpad generator")
        root.resizable(False, False)

        main = ttk.Frame(root, padding=8)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="y")
        self._form = _ParamForm(left, self._schedule_redraw)

        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        self._canvas = tk.Canvas(
            right,
            width=_PREVIEW_W,
            height=_PREVIEW_H,
            bg=_BG,
            highlightthickness=1,
            highlightbackground=_OUTLINE,
        )
        self._canvas.pack()

        self._status = ttk.Label(right, text="", foreground="#FF6B63", wraplength=_PREVIEW_W)
        self._status.pack(anchor="w", pady=(4, 0))

        # -- destination ------------------------------------------------------
        dest = ttk.LabelFrame(right, text="Library destination", padding=(4, 4))
        dest.pack(fill="x", pady=(8, 0))
        self._dest = tk.StringVar(value="project" if project_dir else "global")
        self._dest.trace_add("write", lambda *_: self._dest_changed())

        ttk.Radiobutton(
            dest, text="Project library (registered in this project's lib tables)",
            variable=self._dest, value="project",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6)
        project_row = ttk.Frame(dest)
        project_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(24, 6))
        self._project_label = ttk.Label(
            project_row, text=str(project_dir) if project_dir else "(choose…)"
        )
        self._project_label.pack(side="left")
        ttk.Button(project_row, text="Browse…", command=self._pick_project).pack(side="right")

        ttk.Radiobutton(
            dest, text="Global library (all projects on this machine)",
            variable=self._dest, value="global",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=6)
        global_row = ttk.Frame(dest)
        global_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=(24, 6))
        self._global_dir = tk.StringVar(value=str(DEFAULT_GLOBAL_LIB_DIR))
        ttk.Entry(global_row, textvariable=self._global_dir, width=44).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(global_row, text="Browse…", command=self._pick_global_dir).pack(side="right")

        self._adhoc_radio = ttk.Radiobutton(
            dest, text="No library — just place on the board (quick & dirty)",
            variable=self._dest, value="none",
        )
        self._adhoc_radio.grid(row=4, column=0, columnspan=2, sticky="w", padx=6)
        dest.columnconfigure(0, weight=1)

        # -- board placement --------------------------------------------------
        self._place_now = tk.BooleanVar(value=place is not None)
        self._place_check = ttk.Checkbutton(
            right, text="Also place the footprint on the open board now",
            variable=self._place_now,
        )
        self._place_check.pack(anchor="w", pady=(6, 0))
        if place is None:
            self._adhoc_radio.configure(state="disabled")
            self._place_check.configure(state="disabled")
            self._place_now.set(False)

        self._generate_btn = ttk.Button(
            right,
            text="Generate",
            command=self._generate,
            style="Accent.TButton" if modern else "TButton",
        )
        self._generate_btn.pack(fill="x", pady=(10, 0), ipady=3)

        self._summary = tk.Text(
            right, height=10, width=56, state="disabled", relief="flat", padx=10, pady=8
        )
        if modern:
            self._summary.configure(bg=_CARD_BG, fg=_CARD_FG)
        self._summary.pack(fill="x", pady=(10, 0))

        self._redraw_pending = False
        self._schedule_redraw()

    def _dest_changed(self) -> None:
        if self._dest.get() == "none" and self._place is not None:
            # board-only mode IS placement; force the checkbox on
            self._place_now.set(True)
            self._place_check.configure(state="disabled")
        elif self._place is not None:
            self._place_check.configure(state="normal")

    # -- preview ------------------------------------------------------------

    def _schedule_redraw(self) -> None:
        if self._redraw_pending:
            return
        self._redraw_pending = True
        self._root.after(120, self._redraw)

    def _redraw(self) -> None:
        self._redraw_pending = False
        canvas = self._canvas
        canvas.delete("all")
        try:
            params = self._form.current_params()
            err = params.validate()
            if err is not None:
                raise ValueError(err)
            trackpad = build_trackpad(params)
        except ValueError as exc:
            self._status.configure(text=str(exc))
            self._generate_btn.configure(state="disabled")
            return
        self._status.configure(text="")
        self._generate_btn.configure(state="normal")

        shapes = compute_preview(trackpad, int(params.width), int(params.height))
        for x0, y0, x1, y1, is_front in shapes.segments:
            if not is_front:
                canvas.create_line(x0, y0, x1, y1, fill=_BCU, width=1)
        for x0, y0, x1, y1, is_front in shapes.segments:
            if is_front:
                canvas.create_line(x0, y0, x1, y1, fill=_FCU, width=1)
        for coords in shapes.polygons_front:
            canvas.create_polygon(*coords, fill=_FCU, outline="")
        for x0, y0, x1, y1 in shapes.rects_front:
            canvas.create_rectangle(x0, y0, x1, y1, fill=_FCU, outline="")
        for x0, y0, x1, y1, is_drill in shapes.circles:
            canvas.create_oval(x0, y0, x1, y1, fill=_HOLE if is_drill else _FCU, outline="")
        canvas.create_rectangle(*shapes.outline, outline=_OUTLINE, dash=(3, 3))

    # -- actions ------------------------------------------------------------

    def _pick_project(self) -> None:
        initial = str(self._project_dir) if self._project_dir else str(Path.home())
        chosen = filedialog.askdirectory(
            title="KiCad project directory (contains the .kicad_pro)", initialdir=initial
        )
        if chosen:
            self._project_dir = Path(chosen)
            self._project_label.configure(text=chosen)
            self._dest.set("project")

    def _pick_global_dir(self) -> None:
        chosen = filedialog.askdirectory(
            title="Directory for the global trackpad library", initialdir=self._global_dir.get()
        )
        if chosen:
            self._global_dir.set(chosen)
            self._dest.set("global")

    def _generate_libraries(self, params: TrackpadParams) -> list[str]:
        """Run the selected library destination. Returns summary lines."""
        dest = self._dest.get()
        if dest == "project":
            if self._project_dir is None:
                self._pick_project()
                if self._project_dir is None:
                    raise ValueError("no project directory chosen")
            if not any(self._project_dir.glob("*.kicad_pro")) and not messagebox.askyesno(
                "No .kicad_pro here",
                f"{self._project_dir} does not contain a .kicad_pro file.\n"
                "Generate the libraries there anyway?",
            ):
                raise ValueError("cancelled")
            return generate_into_project(self._project_dir, params).summary_lines()
        if dest == "global":
            return generate_into_library(Path(self._global_dir.get()), params).summary_lines()
        return ["No library written (board-only mode)."]

    def _generate(self) -> None:
        try:
            params = self._form.current_params()
            lines = self._generate_libraries(params)
        except ValueError as exc:
            if str(exc) != "cancelled":
                messagebox.showerror("Trackpad generator", str(exc))
            return
        except OSError as exc:
            messagebox.showerror("Trackpad generator", str(exc))
            return

        if self._place is not None and self._place_now.get():
            try:
                lines = [self._place(params), "", *lines]
            except Exception as exc:  # noqa: BLE001 — IPC errors must reach the user
                lines = [f"Board placement failed: {exc}", "", *lines]

        self._show_summary("\n".join(lines))

    def _show_summary(self, text: str) -> None:
        self._summary.configure(state="normal")
        self._summary.delete("1.0", "end")
        self._summary.insert("1.0", text)
        self._summary.configure(state="disabled")


def run_dialog(project_dir: Path | None, place: PlaceCallback | None = None) -> int:
    root = tk.Tk()
    modern = apply_theme(root)
    TrackpadDialog(root, project_dir, place, modern=modern)
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Trackpad generator dialog (standalone)")
    parser.add_argument("--project", type=Path, default=None, help="KiCad project directory")
    args = parser.parse_args(argv)
    project: Path | None = args.project
    return run_dialog(project.resolve() if project is not None else None)


if __name__ == "__main__":
    raise SystemExit(main())
