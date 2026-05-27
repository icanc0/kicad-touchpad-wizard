# KiCad Touchpad Wizard

Generates capacitive trackpad PCB footprints **with a matching schematic symbol**
so the pads actually bind to something on the schematic. Works on KiCad 9, 10,
and survives the KiCad 11 SWIG removal because it uses the IPC API
([`kicad-python`](https://pypi.org/project/kicad-python/)), not the old `pcbnew`
bindings.

| Footprint | Matching symbol |
|---|---|
| ![footprint](docs/footprint.png) | ![symbol](docs/symbol.png) |

Both images above were generated headlessly by the test suite: `python touchpad_wizard.py emit` writes the `.kicad_mod` and `.kicad_sym`, and `kicad-cli {fp,sym} export svg` renders the previews. No KiCad GUI is ever launched.

## What you get

- One footprint (`Trackpad-WxHmm.kicad_mod`) — trapezoidal SMD pads, optional
  routing vias and traces.
- One schematic symbol (`Trackpad-WxHmm` in `touchpad-wizard.kicad_sym`) whose
  pin numbers exactly match the footprint's pad numbers.
- TX columns numbered `T1, T2, …` and RX rows numbered `R1, R2, …` — no collisions.

## Use it

There are two ways. Pick whichever fits your workflow.

### Option A — Standalone CLI (easiest, works with any KiCad version)

```bash
pip install kicad-python   # the only dependency
python touchpad_wizard.py emit \
    --width 50 --height 20 \
    --tx-columns 5 --rx-rows 5 \
    --footprint MyProject.pretty/Trackpad-50x20mm.kicad_mod \
    --symbol MyProject.kicad_sym
```

That writes the footprint to your `.pretty` directory and the symbol to a
`.kicad_sym` library. Add both to your project's library tables and the
schematic-to-PCB binding works.

Run `python touchpad_wizard.py emit --help` for the full parameter list.

### Option B — In-KiCad wizard (KiCad 10.1+ / 11)

> [!IMPORTANT]
> **This does not work on KiCad 10.0.x.** Verified against the KiCad source: the
> `FOOTPRINT_WIZARD` plugin-action scope was added on master after the 10.0.1
> tag (commit on `master`, missing from `10.0.1` tag at
> `include/api/plugin_action_scope.h`). KiCad 10.0.1 detects our plugin and
> even provisions the Python venv, but maps the `footprint_wizard` scope to
> `INVALID` and never surfaces the wizard in the UI. Use Option A on K10.0.x.

1. Find your KiCad plugin directory:
   - Linux: `~/.local/share/kicad/<version>/plugins/`
   - macOS: `~/Library/Application Support/kicad/<version>/plugins/`
   - Windows: `%APPDATA%\kicad\<version>\plugins\`
2. Symlink (or clone) this repo into a `touchpad-wizard/` subdirectory there.
3. In KiCad → Preferences → KiCad → Plugins → check **"Enable KiCad API"**.
   Close and re-open KiCad (it overwrites `kicad_common.json` on shutdown,
   so flipping the flag from a terminal while KiCad is running will be reverted).
4. Open the footprint editor → File → New Footprint Using Footprint Wizard →
   look for "Trackpad" in the list.

KiCad reads `requirements.txt` (not `pyproject.toml`) to provision the plugin's
Python venv, so the file `requirements.txt` at the repo root is what's installed
into the venv at `~/.cache/kicad/<version>/python-environments/<plugin-id>/`.

Adjust parameters with live preview. On generate, the footprint lands in the
editor and the matching symbol is appended to
`~/Documents/KiCad/touchpad-wizard.kicad_sym` (override with
`KICAD_TOUCHPAD_WIZARD_SYM_LIB`). Add that file once as a global symbol library
and every future trackpad you generate slots into it automatically.

## How it stays correct

- **Strict types end-to-end.** `pyright --strict` passes; `TrackpadParams` is a
  frozen, slotted dataclass parsed once at the kipy boundary, and downstream
  code consumes typed `PadSpec`/`ViaSpec`/`SegmentSpec` dataclasses — no
  dict-juggling.
- **Headless tests with `kicad-cli`.** Tier 1 tests pure geometry with
  hypothesis property tests. Tier 2 invokes the wizard binary the way KiCad
  does. Tier 3 hands the generated `.kicad_mod`/`.kicad_sym` to `kicad-cli`
  for headless SVG rendering — no GUI, no display, no screen-lock interaction.
  Golden-text snapshots catch any geometric drift.
- **One source of truth for pad numbers.** The geometry layer assigns
  `T1…Tn`/`R1…Rm` once; both the footprint emitter and the symbol emitter
  consume the same list. Numbers cannot diverge.

## Development

```bash
git clone https://github.com/icanc0/kicad-touchpad-wizard
cd kicad-touchpad-wizard
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]

ruff check trackpad/ tests/ touchpad_wizard.py
pyright trackpad/ touchpad_wizard.py
pytest                       # all tiers
pytest -m "not integration"  # skip kicad-cli rendering
```

CI runs ruff + pyright + pytest on Python 3.10–3.12, plus an integration job
that installs KiCad and renders via `kicad-cli` under `xvfb-run`.

## Legacy SWIG version

The previous SWIG-based wizard (KiCad 8 and early 9) is preserved at the
[`v0-swig-legacy`](../../tree/v0-swig-legacy) git tag. It will not work on
KiCad 11+ because `pcbnew`'s Python bindings have been removed there.
