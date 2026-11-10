"""JUCE ValueTree 二进制序列化（VoiSona 的 ``.tssln`` / ``.tsmsln`` 用它装工程）。

JUCE 是 C++ 的音频框架，它的 ValueTree 存盘格式是这样的::

    节点 = 名字(CString) + 属性数组 + 子节点数组
    属性数组 = 压缩整数(个数) + 每个「名字(CString) + 变体」
    变体     = 压缩整数(字节长度) + 类型字节 + 值
    压缩整数 = 宽度字节(1..8) + 该宽度的小端无符号整数

「压缩整数」不是变长整数，而是「先写占几个字节，再写那几个字节」——所以 0
要占两个字节（``01 00``），255 占两个（``01 FF``），256 占三个（``02 00 01``）。

格式细节参考 LibreSVIP 的 ``libresvip/utils/binary/value_tree.py``（MIT，见
THIRD_PARTY_NOTICES.md），这里只实现**写**方向。
"""
from __future__ import annotations

import math
import struct

#: 变体的类型标签。
INT = 1
BOOL_TRUE = 2
BOOL_FALSE = 3
DOUBLE = 4
STRING = 5
INT64 = 6
ARRAY = 7
BINARY = 8
UNDEFINED = 9


def compressed_int(value: int) -> bytes:
    """宽度字节 + 该宽度的小端无符号整数。"""
    if value < 0:
        raise ValueError(f"压缩整数不支持负数：{value}")
    width = max(math.ceil(value.bit_length() / 8), 1)
    return bytes([width]) + value.to_bytes(width, "little")


def _cstring(text: str) -> bytes:
    return text.encode("utf-8") + b"\x00"


def _payload(value: object) -> bytes:
    # bool 必须在 int 之前判断：Python 里 True 是 int 的子类
    if isinstance(value, bool):
        return bytes([BOOL_TRUE if value else BOOL_FALSE])
    if isinstance(value, int):
        return bytes([INT]) + int(value).to_bytes(4, "little", signed=True)
    if isinstance(value, float):
        return bytes([DOUBLE]) + struct.pack("<d", value)
    if isinstance(value, str):
        return bytes([STRING]) + _cstring(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes([BINARY]) + bytes(value)
    if isinstance(value, (list, tuple)):
        return (bytes([ARRAY]) + compressed_int(len(value))
                + b"".join(variant(item) for item in value))
    raise TypeError(f"JUCE 变体不支持这个类型：{type(value).__name__}")


def variant(value: object) -> bytes:
    """一个变体：字节长度 + 类型标签 + 值。"""
    payload = _payload(value)
    return compressed_int(len(payload)) + payload


def node(name: str,
         attrs: tuple[tuple[str, object], ...] = (),
         children: tuple[bytes, ...] = ()) -> bytes:
    """序列化一个节点，``children`` 里放已经序列化好的子节点字节。"""
    out = bytearray(_cstring(name))
    out += compressed_int(len(attrs))
    for attr_name, value in attrs:
        out += _cstring(attr_name)
        out += variant(value)
    out += compressed_int(len(children))
    for child in children:
        out += child
    return bytes(out)
