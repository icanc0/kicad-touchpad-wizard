"""Trackpad wizard package.

Importing this package applies a workaround for kipy <= 0.7.1 where
`kipy.proto.common.types.__init__` forgets to re-export wizard symbols, which breaks
the WizardInfo / WizardMetaInfo / WizardParameter default constructors. Safe to remove
once kipy fixes the upstream init.
"""

from __future__ import annotations

from kipy.proto.common import types as _kipy_types
from kipy.proto.common.types import wizards_pb2 as _wizards_pb2

for _attr in (
    "WizardInfo",
    "WizardMetaInfo",
    "WizardParameter",
    "WizardParameterList",
    "WizardIntParameter",
    "WizardRealParameter",
    "WizardBoolParameter",
    "WizardStringParameter",
    "WizardContentType",
    "WizardGeneratedContent",
    "WizardGenerationStatus",
    "WizardParameterCategory",
    "WizardParameterDataType",
):
    if not hasattr(_kipy_types, _attr):
        setattr(_kipy_types, _attr, getattr(_wizards_pb2, _attr))
