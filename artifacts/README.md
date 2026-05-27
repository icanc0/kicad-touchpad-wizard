# Artifacts

Pre-rendered example outputs from the trackpad wizard. Every file here is
regenerable — run `python scripts/regen_artifacts.py` to refresh from current
source. Committed so you can browse the gallery on GitHub without checking out
the repo and running anything.

## Layout

- `rectangular/Trackpad-Rectangular.pretty/` — 16 footprints in one KiCad
  library, ready to drop into a project. Sizes range from 20×20 mm (4×4
  electrodes) up to 150×150 (12×12), with aspect-ratio variants for
  business-card and slider-strip use cases.
- `rectangular/Trackpad-Rectangular.kicad_sym` — symbol library containing
  the matching schematic symbols for every footprint above. Same `c0..c{n-1}`
  / `r0..r{m-1}` pin numbers as the pads.
- `rectangular/png/` — one PNG per variant. `gallery.png` is the tiled
  4×4 comparison.
- `circular/Trackpad-Circular.pretty/` — 9 circular trackpad footprints from
  30 mm to 80 mm diameter, varying sector × ring density. Annular-sector
  custom polygon pads.
- `circular/png/`, `circular/gallery.png` — same idea.
- `50x50-board-with-gerbers/` — the full manufacturing-ready bundle for the
  50×50 showcase variant: footprint, matching symbol, minimal `.kicad_pcb`
  embedding it, rendered preview, and a Gerber pack tarball you can upload
  directly to JLCPCB / PCBWay / OSHPark.

## Using as a library

Add the `.pretty` dirs to your project via KiCad → Preferences → Manage
Footprint Libraries → Add. The `.kicad_sym` file goes into Manage Symbol
Libraries the same way.
