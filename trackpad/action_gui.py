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
from trackpad.project_gen import generate_into_project
from trackpad.units import Degrees, mm

# pcbnew-ish dark theme
_BG = "#001017"
_FCU = "#C83434"
_BCU = "#4D7FC4"
_HOLE = "#11181F"
_OUTLINE = "#666E76"

_PREVIEW_W = 460
_PREVIEW_H = 300
_MARGIN = 16


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

        size = ttk.LabelFrame(parent, text="Size")
        size.pack(fill="x", padx=8, pady=(8, 4))
        self._spin(size, "Width (mm)", self.width_mm, 0, 5, 300, 5)
        self._spin(size, "Height (mm)", self.height_mm, 1, 5, 300, 5)

        grid = ttk.LabelFrame(parent, text="Electrodes")
        grid.pack(fill="x", padx=8, pady=4)
        self._spin(grid, "TX columns", self.tx_columns, 0, 4, 64, 1)
        self._spin(grid, "RX rows", self.rx_rows, 1, 4, 64, 1)
        self._spin(grid, "Clearance (mm)", self.clearance_mm, 2, 0.05, 2, 0.05)

        conn = ttk.LabelFrame(parent, text="Edge connection")
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

        opts = ttk.LabelFrame(parent, text="Options")
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


class TrackpadDialog:
    """Main window: parameter form, live preview, generate-into-project."""

    def __init__(self, root: tk.Tk, project_dir: Path | None) -> None:
        self._root = root
        self._project_dir = project_dir
        root.title("Trackpad generator")
        root.resizable(False, False)

        main = ttk.Frame(root)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="y")
        self._form = _ParamForm(left, self._schedule_redraw)

        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)
        self._canvas = tk.Canvas(
            right,
            width=_PREVIEW_W,
            height=_PREVIEW_H,
            bg=_BG,
            highlightthickness=1,
            highlightbackground=_OUTLINE,
        )
        self._canvas.pack()

        self._status = ttk.Label(right, text="", foreground="#B33", wraplength=_PREVIEW_W)
        self._status.pack(anchor="w", pady=(4, 0))

        project_row = ttk.Frame(right)
        project_row.pack(fill="x", pady=(8, 0))
        ttk.Label(project_row, text="Project:").pack(side="left")
        self._project_label = ttk.Label(
            project_row, text=str(project_dir) if project_dir else "(choose…)"
        )
        self._project_label.pack(side="left", padx=4)
        ttk.Button(project_row, text="Browse…", command=self._pick_project).pack(side="right")

        self._generate_btn = ttk.Button(right, text="Generate into project", command=self._generate)
        self._generate_btn.pack(fill="x", pady=(8, 0))

        self._summary = tk.Text(right, height=9, width=56, state="disabled", relief="flat")
        self._summary.pack(fill="x", pady=(8, 0))

        self._redraw_pending = False
        self._schedule_redraw()

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

    def _generate(self) -> None:
        if self._project_dir is None:
            self._pick_project()
            if self._project_dir is None:
                return
        if not any(self._project_dir.glob("*.kicad_pro")):
            ok = messagebox.askyesno(
                "No .kicad_pro here",
                f"{self._project_dir} does not contain a .kicad_pro file.\n"
                "Generate the libraries there anyway?",
            )
            if not ok:
                return
        try:
            params = self._form.current_params()
            result = generate_into_project(self._project_dir, params)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Trackpad generator", str(exc))
            return
        self._show_summary("\n".join(result.summary_lines()))

    def _show_summary(self, text: str) -> None:
        self._summary.configure(state="normal")
        self._summary.delete("1.0", "end")
        self._summary.insert("1.0", text)
        self._summary.configure(state="disabled")


def run_dialog(project_dir: Path | None) -> int:
    root = tk.Tk()
    TrackpadDialog(root, project_dir)
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
