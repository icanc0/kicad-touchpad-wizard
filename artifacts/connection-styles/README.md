# Connection-style reference gallery

Visual references for the `--connection-style` feature (the perimeter
connection/alignment landings). **Regenerate with**
`python scripts/regen_connection_gallery.py` and diff the result so any visual
change is reviewable.

## What each style is

- **apex** — no extra landing (original behavior). Electrodes are tied together
  only by the apex vias (`v_c*`). This is the default.
- **edge** — a copper pad spanning the *whole outer edge* of each perimeter
  triangle, flush to the trackpad boundary.
- **center** — a *small* pad at the midpoint of each perimeter triangle's outer
  edge (an alignment aid).

Landings sit on the electrode net (`c*` / `r*`) and appear at **both ends** of
every electrode — the sensor is self-capacitance, so either end is electrically
identical. They follow the trackpad's solder-mask setting (covered by default,
same as the triangles — no exposed copper on the finger surface).

## Layout

- `compare-<grid>.png` — apex | edge | center side by side for one grid. Start here.
- `footprints/<grid>-<style>.png` — individual footprint renders.
- `symbols/<grid>.png` — the matching symbol (style-independent): TX on top &
  bottom, RX on left & right, each electrode exposed as two same-numbered pins.

## Comparison strips

- `compare-Trackpad-45x45-5x5.png` — card-size 5x5 (matches the business-card trackpad)
- `compare-Trackpad-50x20-5x5.png` — wide non-square — landings on a different aspect ratio
- `compare-Trackpad-45x45-6x6.png` — v2 6x6 — denser grid, more perimeter landings

## What to check

1. **edge**: a strip hugs all four boundaries, one per perimeter triangle, with
   small gaps at the corners (no TX↔RX bridge). Covered by mask (no exposed
   copper), so it reads as solid with the triangles, not as a separate opening.
2. **center**: a small pad sits at the midpoint of each outer edge, on all four
   sides — and at both ends of every electrode.
3. **apex**: identical to the pre-feature output (no perimeter landings).
4. **symbol**: every TX column number (`c*`) appears on both the top and bottom
   edges; every RX row number (`r*`) on both the left and right; the
   self-capacitance note is present.
