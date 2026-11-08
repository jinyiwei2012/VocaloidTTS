"""Decode imported text files without guessing the encoding wrong.

Chinese Windows still produces ANSI/GBK text files, and ``bytes.decode("utf-16")``
"succeeds" on almost any even-length byte string.  Trying UTF-16 before GB18030
therefore turns a valid GBK file into private-use/Hangul garbage, which then
parses into zero syllables.  BOM wins; without a BOM, Chinese encodings are
tried first.
"""
from __future__ import annotations

_BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)

# utf-16 stays last on purpose: see the module docstring.
_FALLBACK_ORDER = ("utf-8-sig", "gb18030", "utf-16")


def _looks_broken(text: str) -> bool:
    """Reject decodings dominated by private-use or Hangul code points."""
    if not text:
        return False
    suspicious = 0
    for ch in text:
        code = ord(ch)
        if 0xE000 <= code <= 0xF8FF or 0xDC80 <= code <= 0xDCFF:
            suspicious += 1
        elif 0xAC00 <= code <= 0xD7AF:
            suspicious += 1
    return suspicious > max(2, len(text) // 10)


def decode_text(raw: bytes) -> tuple[str, str]:
    """Return ``(text, encoding)`` for an arbitrary text file."""
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            try:
                text = raw.decode(encoding)
            except UnicodeDecodeError:
                break
            if text.startswith("\ufeff"):
                text = text[1:]
            return text, encoding
    for encoding in _FALLBACK_ORDER:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if _looks_broken(text):
            continue
        return text, encoding
    return raw.decode("utf-8", errors="replace"), "utf-8 (replace)"
