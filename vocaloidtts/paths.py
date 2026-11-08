"""App data locations, with one-time migration from the old ToneTalk name."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_NAME = "VocaloidTTS"
OLD_NAME = "ToneTalk"


def _migrate(new: Path, old: Path) -> Path:
    try:
        if not new.exists() and old.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(old, new)
    except Exception:
        pass
    try:
        new.mkdir(parents=True, exist_ok=True)
    except Exception:
        # 退回旧目录会让数据写到 %APPDATA%\ToneTalk，而 V4 任务插件把
        # %LOCALAPPDATA%\VocaloidTTS\vocaloidtts_job.txt 写死了，插件会永远
        # 读不到数据。宁可返回新路径让后续写入报错，也不要静默分叉。
        pass
    return new


def appdata_dir() -> Path:
    root = Path(os.getenv("APPDATA") or Path.home())
    return _migrate(root / APP_NAME, root / OLD_NAME)


def localappdata_dir() -> Path:
    root = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return _migrate(root / APP_NAME, root / OLD_NAME)
