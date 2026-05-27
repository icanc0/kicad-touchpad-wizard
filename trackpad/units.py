"""Typed unit primitives so we cannot accidentally pass mm where nm is expected."""

from __future__ import annotations

from typing import NewType

Nanometers = NewType("Nanometers", int)
Millimeters = NewType("Millimeters", float)
Degrees = NewType("Degrees", float)


def mm(value: float) -> Nanometers:
    return Nanometers(round(value * 1_000_000))


def nm_to_mm(value: Nanometers) -> Millimeters:
    return Millimeters(value / 1_000_000)
