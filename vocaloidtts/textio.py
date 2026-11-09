"""Decode imported text files without guessing the encoding wrong.

Chinese Windows still produces ANSI/GBK text files, and ``bytes.decode("utf-16")``
"succeeds" on almost any even-length byte string.  Trying UTF-16 before GB18030
therefore turns a valid GBK file into private-use/Hangul garbage, which then
parses into zero syllables.  BOM wins; without a BOM, Chinese encodings are
tried first.

两条容易踩的坑：

- UTF-32 的 BOM 前两字节和 UTF-16 一样（``FF FE 00 00`` / ``FF FE``），
  必须先按 4 字节匹配，否则 UTF-32 文件会被切成「NUL + 一个字符」。
- 无 BOM 的 UTF-16 只能靠 NUL 分布认，且只对 ASCII 为主的文本有效；
  纯中文的 UTF-16BE 解出来没有 NUL，和普通 UTF-8 无法可靠区分，不做猜测。
"""
from __future__ import annotations

# 长 BOM 必须排在短的之前：FF FE 00 00 同时以 FF FE 开头。
_BOMS = (
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)

# utf-16 stays last on purpose: see the module docstring.
_FALLBACK_ORDER = ("utf-8-sig", "gb18030", "utf-16")


def _has_control(text: str) -> bool:
    """文本里有没有 NUL 之类不该出现的控制字符。"""
    return any(ord(ch) < 0x20 and ch not in "\t\n\r" for ch in text)


def _looks_broken(text: str) -> bool:
    """Reject decodings dominated by private-use code points.

    韩文音节（U+AC00..U+D7AF）不算「坏」：真正的 UTF-8 韩文会先走 utf-8 分支，
    而被 utf-16 误判的 GBK 字节会被 utf-8 的严格解码挡掉；反过来把它们当可疑，
    会让合法的 UTF-8 韩文掉进 gb18030 变成乱码。
    """
    if not text:
        return False
    suspicious = 0
    for ch in text:
        code = ord(ch)
        if 0xE000 <= code <= 0xF8FF or 0xDC80 <= code <= 0xDCFF:
            suspicious += 1
    return suspicious > max(2, len(text) // 10)


def _utf16_by_nul(raw: bytes) -> tuple[str, str] | None:
    """无 BOM 时按 NUL 分布判 UTF-16 端序。

    ASCII 为主的 UTF-16 在每两个字节里有一个 0：BE 在偶数位、LE 在奇数位。
    纯中文的 UTF-16 没有这种规律，这里不猜——猜错的代价比不认更高。
    """
    if len(raw) < 4 or len(raw) % 2:
        return None
    half = len(raw) // 2
    even_nul = sum(1 for i in range(0, len(raw), 2) if raw[i] == 0)
    odd_nul = sum(1 for i in range(1, len(raw), 2) if raw[i] == 0)
    if even_nul > half * 0.4 and odd_nul == 0:
        encoding = "utf-16-be"
    elif odd_nul > half * 0.4 and even_nul == 0:
        encoding = "utf-16-le"
    else:
        return None
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        return None
    if _has_control(text):
        return None
    return text.lstrip("\ufeff"), encoding


def decode_text(raw: bytes) -> tuple[str, str]:
    """Return ``(text, encoding)`` for an arbitrary text file."""
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            try:
                text = raw.decode(encoding)
            except UnicodeDecodeError:
                # 文件声明了编码却解不开：按声明解码、坏字节换成替换符。
                # 掉进下面的 utf-16 分支会把它读成一串韩文，比乱码更难查。
                return (raw.decode(encoding, errors="replace").lstrip("\ufeff"),
                        encoding + " (replace)")
            return text.lstrip("\ufeff"), encoding
    guessed = _utf16_by_nul(raw)
    if guessed is not None:
        return guessed
    for encoding in _FALLBACK_ORDER:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if _looks_broken(text):
            continue
        if _has_control(text):
            # 正常歌词里不会有 NUL / \x16 这类控制字符。UTF-16 误判、
            # 编码声明与内容不符，都会在这里露出马脚。
            continue
        return text.lstrip("\ufeff"), encoding
    return raw.decode("utf-8", errors="replace").lstrip("\ufeff"), "utf-8 (replace)"
