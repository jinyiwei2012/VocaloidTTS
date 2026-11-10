"""导出格式注册表。

加一个格式：在 ``formats/`` 下写一个模块，导出 ``FORMAT``（:class:`Format`），
然后在 :func:`formats` 的元组里加一行。``app.py`` 只认注册表，不再有
``if fmt == ...`` 这样的分支。

注册表是懒加载的：各格式模块会 ``from .base import Format``，如果这里在
模块级 import 它们就会循环，所以推迟到第一次取用时。
"""
from __future__ import annotations

from .base import Format

_cache: dict[str, Format] | None = None


def formats() -> dict[str, Format]:
    """返回 ``key -> Format``，首次调用时构建并缓存。"""
    global _cache
    if _cache is None:
        from . import (acep, aisp, ass, dspx, lrc, mid, nn, s5p, srt, svip,
                       svip3, svp, tlp, tlpx, ustx, vfp, vog, vpr, vspx,
                       vsqx, vxf, y77)

        _cache = {
            entry.key: entry
            for entry in (vsqx.FORMAT, vpr.FORMAT, svp.FORMAT, s5p.FORMAT,
                          mid.FORMAT, acep.FORMAT, svip3.FORMAT, ustx.FORMAT,
                          svip.FORMAT, y77.FORMAT, aisp.FORMAT, tlp.FORMAT,
                          tlpx.FORMAT, nn.FORMAT, vspx.FORMAT, dspx.FORMAT,
                          vog.FORMAT, vfp.FORMAT, vxf.FORMAT, lrc.FORMAT,
                          srt.FORMAT, ass.FORMAT)
        }
    return _cache


def __getattr__(name: str):
    # 让 ``from .formats import FORMATS`` 这种写法继续可用
    if name == "FORMATS":
        return formats()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["FORMATS", "Format", "formats"]
