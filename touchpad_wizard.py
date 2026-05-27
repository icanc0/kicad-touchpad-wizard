#!/usr/bin/env python3
"""KiCad footprint wizard entry point.

This file is what KiCad's IPC plugin manifest (`plugin.json`) points at. It is
intentionally tiny — all logic lives in the `trackpad/` package so the wizard is
testable without KiCad.

Note: the SWIG-based version of this wizard for KiCad 8/early-9 is preserved at
the `v0-swig-legacy` git tag.
"""

from __future__ import annotations

from trackpad.wizard import main

if __name__ == "__main__":
    main()
