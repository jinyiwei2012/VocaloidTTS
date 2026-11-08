"""逐字纠音、局部修饰与用户词典。

edits 以原文中的字符偏移为键：0 起算，指向原始文本里的那一个字。汉字恒等于
一个音节，所以偏移和音节天然一一对应；数字和字母在 ``normalize_text`` 阶段
已经展开，不参与纠音。

文本随时会改，偏移会漂移，所以 :class:`EditSet` 同时记一份原文快照。应用前
比对快照，不一致就整体拒绝，而不是把拼音错配到别的字上。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .atomicio import atomic_write_text

#: 词条读音里的单个音节：字母 + 必需的声调数字。
_READING_RE = re.compile(r"([a-zA-ZüÜv:]+)([1-5])")


@dataclass
class CharEdit:
    """一个字的人工修正。所有字段留空表示「不覆盖」。"""

    pinyin: str = ""          # 不带声调的拼音，如 "zhong"
    tone: int = 0             # 0 = 不覆盖，1..5
    phonemes: str = ""        # 直接覆盖 X-SAMPA；留空则按 pinyin 重算
    stress: float | None = None      # 强调增量，-1..1
    dur_scale: float | None = None   # 拉长倍数，0.5..2.0
    pause_ms: int | None = None      # 这个字之后的精确停顿（毫秒）

    def is_empty(self) -> bool:
        return not (self.pinyin or self.tone or self.phonemes
                    or self.stress is not None
                    or self.dur_scale is not None
                    or self.pause_ms is not None)

    def to_dict(self) -> dict:
        out: dict = {}
        if self.pinyin:
            out["pinyin"] = self.pinyin
        if self.tone:
            out["tone"] = int(self.tone)
        if self.phonemes:
            out["phonemes"] = self.phonemes
        if self.stress is not None:
            out["stress"] = round(float(self.stress), 3)
        if self.dur_scale is not None:
            out["dur_scale"] = round(float(self.dur_scale), 3)
        if self.pause_ms is not None:
            out["pause_ms"] = int(self.pause_ms)
        return out

    @classmethod
    def from_dict(cls, raw: dict) -> CharEdit:
        def _num(key: str, cast):
            value = raw.get(key)
            if value is None:
                return None
            try:
                return cast(value)
            except (TypeError, ValueError):
                return None

        pinyin = str(raw.get("pinyin") or "").strip().lower()
        tone = _num("tone", int) or 0
        return cls(
            pinyin=pinyin,
            tone=max(0, min(5, tone)),
            phonemes=str(raw.get("phonemes") or "").strip(),
            stress=_num("stress", float),
            dur_scale=_num("dur_scale", float),
            pause_ms=_num("pause_ms", int),
        )


@dataclass
class EditSet:
    """一份纠音集合，带原文快照。"""

    snapshot: str = ""
    chars: dict[int, CharEdit] = field(default_factory=dict)

    def get(self, offset: int) -> CharEdit | None:
        return self.chars.get(offset)

    def set(self, offset: int, edit: CharEdit) -> None:
        """写入一条；全空的修正等于删除。"""
        if edit.is_empty():
            self.chars.pop(offset, None)
        else:
            self.chars[offset] = edit

    def matches(self, text: str) -> bool:
        """快照为空表示还没记过，直接接受；否则要求逐字相同。"""
        return not self.snapshot or self.snapshot == text

    def take_snapshot(self, text: str) -> None:
        self.snapshot = text

    def clear(self) -> None:
        self.chars.clear()
        self.snapshot = ""

    def to_dict(self) -> dict:
        return {
            "snapshot": self.snapshot,
            "chars": {str(k): v.to_dict()
                      for k, v in sorted(self.chars.items())},
        }

    @classmethod
    def from_dict(cls, raw: dict) -> EditSet:
        chars: dict[int, CharEdit] = {}
        for key, value in (raw.get("chars") or {}).items():
            try:
                offset = int(key)
            except (TypeError, ValueError):
                continue
            if offset < 0 or not isinstance(value, dict):
                continue
            edit = CharEdit.from_dict(value)
            if not edit.is_empty():
                chars[offset] = edit
        return cls(snapshot=str(raw.get("snapshot") or ""), chars=chars)


def parse_reading(text: str) -> list[tuple[str, int]] | None:
    """把 ``"zhong1 guo2"`` 解析成 ``[("zhong", 1), ("guo", 2)]``。

    每个音节都必须带声调数字；缺一个就整条作废，避免半对半错地把人读错。
    """
    parts = text.replace("u:", "v").replace("ü", "v").split()
    if not parts:
        return None
    out: list[tuple[str, int]] = []
    for part in parts:
        m = _READING_RE.fullmatch(part.strip())
        if not m:
            return None
        out.append((m.group(1).lower(), int(m.group(2))))
    return out


def dictionary_overrides(text: str,
                         dictionary: dict[str, str]) -> dict[int, tuple[str, int]]:
    """把用户词典换算成「字符偏移 → (拼音, 声调)」。

    长词优先：``中国`` 会盖过单独命中的 ``国``，不会被短词拆散。
    """
    out: dict[int, tuple[str, int]] = {}
    for word in sorted(dictionary, key=len, reverse=True):
        if not word:
            continue
        reading = parse_reading(dictionary[word])
        if reading is None or len(reading) != len(word):
            continue
        start = 0
        while True:
            pos = text.find(word, start)
            if pos < 0:
                break
            for k, (py, tone) in enumerate(reading):
                if pos + k not in out:
                    out[pos + k] = (py, tone)
            start = pos + 1
    return out


def load_userdict(path: Path) -> dict[str, str]:
    """读取用户词典；文件缺失或坏掉时返回空词典，不影响生成。"""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    words = raw.get("words") if isinstance(raw, dict) else None
    if not isinstance(words, dict):
        return {}
    return {str(k): str(v) for k, v in words.items() if str(k).strip()}


def save_userdict(path: Path, dictionary: dict[str, str]) -> None:
    payload = {"schema": 1,
               "words": {k: v for k, v in sorted(dictionary.items()) if k}}
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2)
                      + "\n")
