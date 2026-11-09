"""项目文件：把原文、全局参数和逐字修改一起存下来。

后缀 ``.vttsproj``，内容是 JSON。读取时每个字段都兜底：缺字段用默认值，
类型不对就跳过；整份文件坏掉才抛 :class:`ValueError`，由界面提示。
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path

from .atomicio import atomic_write_text
from .edits import EditSet
from .prosody import VoiceOptions

SCHEMA = 1
SUFFIX = ".vttsproj"


@dataclass
class Project:
    text: str = ""
    mode: str = "chinese"
    bpm: float = 120.0
    numerator: int = 4
    denominator: int = 4
    options: VoiceOptions = field(default_factory=VoiceOptions)
    edits: EditSet = field(default_factory=EditSet)

    def to_dict(self) -> dict:
        return {
            "app": "VocaloidTTS",
            "schema": SCHEMA,
            "saved": datetime.now().isoformat(timespec="seconds"),
            "text": self.text,
            "mode": self.mode,
            "bpm": self.bpm,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "options": asdict(self.options),
            "edits": self.edits.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Project:
        if not isinstance(raw, dict):
            raise ValueError("项目文件不是 JSON 对象")

        opts_raw = raw.get("options")
        defaults = VoiceOptions()
        known = {f.name for f in fields(VoiceOptions)}
        kwargs: dict = {}
        if isinstance(opts_raw, dict):
            for key, value in opts_raw.items():
                if key not in known:
                    continue
                # 按默认值的类型转换一遍：坏文件里的 "pitch": "high" 如果直接
                # 塞进 VoiceOptions，compose 里的 int() 会在生成时才炸。
                default = getattr(defaults, key)
                try:
                    if isinstance(default, bool):
                        kwargs[key] = bool(value)
                    elif isinstance(default, int):
                        kwargs[key] = int(value)
                    elif isinstance(default, float):
                        # json 允许 NaN / Infinity 字面量，直接塞进来会让
                        # 后面的 int() 或格式化在生成时炸掉。
                        number = float(value)
                        kwargs[key] = (number if math.isfinite(number)
                                       else default)
                    elif isinstance(default, str):
                        kwargs[key] = str(value)
                    else:
                        kwargs[key] = value
                except (TypeError, ValueError, OverflowError):
                    continue
        options = VoiceOptions(**kwargs)

        edits_raw = raw.get("edits")
        edits = (EditSet.from_dict(edits_raw)
                 if isinstance(edits_raw, dict) else EditSet())

        def _num(key: str, default, cast):
            try:
                value = cast(raw.get(key, default))
            except (TypeError, ValueError, OverflowError):
                return default
            if isinstance(value, float) and not math.isfinite(value):
                return default
            return value

        text_raw = raw.get("text")
        return cls(
            text=text_raw if isinstance(text_raw, str) else "",
            mode="pinyin" if raw.get("mode") == "pinyin" else "chinese",
            bpm=_num("bpm", 120.0, float),
            numerator=_num("numerator", 4, int),
            denominator=_num("denominator", 4, int),
            options=options,
            edits=edits,
        )


def save_project(path: Path, project: Project) -> None:
    atomic_write_text(Path(path),
                      json.dumps(project.to_dict(), ensure_ascii=False,
                                 indent=2) + "\n")


def load_project(path: Path) -> Project:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"读不到项目文件：{exc}") from exc
    except RecursionError as exc:
        # json.loads 在 C 层递归，两万层嵌套就会抛 RecursionError；
        # 它不是 ValueError，不接住会绕过界面的错误提示直接冒到 Tk 回调。
        raise ValueError("项目文件嵌套太深，无法解析") from exc
    except ValueError as exc:
        raise ValueError(f"项目文件不是合法 JSON：{exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("项目文件不是 JSON 对象")
    # 任何 JSON 都能塞进来；没有我们的标记、也没有项目字段的，直接拒掉，
    # 否则「打开项目」选中 userdict.json 会得到一个空项目，把当前文本清空。
    if raw.get("app") != "VocaloidTTS" and not ({"text", "edits"} & set(raw)):
        raise ValueError("这不是 VocaloidTTS 项目文件")
    return Project.from_dict(raw)
