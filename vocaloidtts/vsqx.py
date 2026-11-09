"""兼容层：VSQX 导出器已迁到 :mod:`vocaloidtts.formats.vsqx`。

保留这个模块是为了不破坏已有的 import；新代码请直接用 ``formats`` 包。
"""
from __future__ import annotations

from .formats.vsqx import FORMAT, write_vsqx

__all__ = ["FORMAT", "write_vsqx"]
