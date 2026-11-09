"""兼容层：导出器已迁到 :mod:`vocaloidtts.formats`。

保留这个模块是为了不破坏已有的 import；新代码请直接用 ``formats`` 包。
"""
from __future__ import annotations

from .formats import FORMATS
from .formats.base import (PitchIndex, curve_values, db_value, has_han,
                           lyric_for, pit_cents, pronunciation_for)
from .formats.svip import write_svip
from .formats.svip3 import write_svip3
from .formats.ustx import write_ustx

# 旧代码里用过带下划线的私有名，这里保留别名
_PitchIndex = PitchIndex
_curve_values = curve_values
_db_value = db_value
_has_han = has_han

__all__ = [
    "FORMATS", "PitchIndex", "curve_values", "db_value", "has_han",
    "lyric_for", "pit_cents", "pronunciation_for", "write_svip",
    "write_svip3", "write_ustx",
]
