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
        return old
    return new


def appdata_dir() -> Path:
    root = Path(os.getenv("APPDATA") or Path.home())
    return _migrate(root / APP_NAME, root / OLD_NAME)


def localappdata_dir() -> Path:
    root = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return _migrate(root / APP_NAME, root / OLD_NAME)
