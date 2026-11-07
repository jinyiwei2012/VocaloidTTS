r"""Voicebank discovery for VOCALOID4 FE.

VOCALOID4 itself can use V3 libraries that were never added to its own
``DATABASE`` registry key (it scans the VoiceDB folders directly).  VocaloidTTS
therefore does a lightweight two-source scan at startup:

1. the VOCALOID4/VOCALOID3 database registry keys;
2. ``Program Files*\VoiceDB\<library>\<component-id>\*.vvd``.

The filesystem scan only reads directory names and the first ``.vvd`` name, so
it stays fast even with multi-GB voicebanks.
"""
from __future__ import annotations

import json
import os
import re
import winreg
from string import ascii_uppercase
from dataclasses import dataclass
from pathlib import Path


from .paths import appdata_dir

DEFAULT_V4_EXE = r"C:\Program Files (x86)\Vocaloid4FE\VOCALOID4.exe"
DEFAULT_V5_EXE = r"D:\VOCALOID6SE\Editor\VOCALOID5.exe"


def _v4_path_file() -> Path:
    return appdata_dir() / "v4_path.txt"


def _v5_path_file() -> Path:
    return appdata_dir() / "v5_path.txt"


def _valid_exe(path: str | Path, name: str = "vocaloid4.exe") -> bool:
    try:
        p = Path(path).expanduser()
        return p.is_file() and p.name.lower() == name
    except Exception:
        return False


def _find_v5_from_registry() -> str:
    try:
        with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\VOCALOID5\Application\Components") as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                sub = winreg.EnumKey(key, i)
                try:
                    with winreg.OpenKey(key, sub) as sk:
                        path = str(winreg.QueryValueEx(sk, "Path")[0])
                except OSError:
                    continue
                exe = Path(path) / "VOCALOID5.exe"
                if exe.is_file():
                    return str(exe)
    except OSError:
        pass
    for candidate in (
        DEFAULT_V5_EXE,
        r"C:\Program Files\VOCALOID5\VOCALOID5.exe",
        r"C:\Program Files (x86)\VOCALOID5\VOCALOID5.exe",
    ):
        if _valid_exe(candidate, "vocaloid5.exe"):
            return candidate
    return DEFAULT_V5_EXE


def _initial_v4_exe() -> str:
    try:
        saved = _v4_path_file().read_text(encoding="utf-8").strip()
    except Exception:
        saved = ""
    if saved and _valid_exe(saved):
        return str(Path(saved))
    return DEFAULT_V4_EXE


def _initial_v5_exe() -> str:
    try:
        saved = _v5_path_file().read_text(encoding="utf-8").strip()
    except Exception:
        saved = ""
    if saved and _valid_exe(saved, "vocaloid5.exe"):
        return str(Path(saved))
    return _find_v5_from_registry()


V4_EXE = _initial_v4_exe()
V4_DIR = os.path.dirname(V4_EXE)
JOBPLUGIN_DIR = os.path.join(V4_DIR, "JobPlugins")
V5_EXE = _initial_v5_exe()


def get_v4_exe() -> str:
    return V4_EXE


def get_v4_dir() -> str:
    return V4_DIR


def get_jobplugin_dir() -> str:
    return JOBPLUGIN_DIR


def set_v4_exe(path: str | Path) -> str:
    """Persist a user-selected VOCALOID4.exe and refresh derived paths."""
    global V4_EXE, V4_DIR, JOBPLUGIN_DIR
    p = Path(path).expanduser()
    if not _valid_exe(p):
        raise ValueError("请选择 VOCALOID4.exe 本体（不是快捷方式）。")
    p = p.resolve()
    V4_EXE = str(p)
    V4_DIR = str(p.parent)
    JOBPLUGIN_DIR = str(p.parent / "JobPlugins")
    try:
        f = _v4_path_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(V4_EXE, encoding="utf-8")
    except Exception:
        pass
    return V4_EXE

def get_v5_exe() -> str:
    return V5_EXE


def v5_available() -> bool:
    return _valid_exe(V5_EXE, "vocaloid5.exe")


def set_v5_exe(path: str | Path) -> str:
    global V5_EXE
    p = Path(path).expanduser()
    if not _valid_exe(p, "vocaloid5.exe"):
        raise ValueError("请选择 VOCALOID5.exe 本体（不是快捷方式）。")
    p = p.resolve()
    V5_EXE = str(p)
    try:
        f = _v5_path_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(V5_EXE, encoding="utf-8")
    except Exception:
        pass
    return V5_EXE


# bank select / program change for known libraries.
# Specific entries must come before generic ones (dict insertion order).
_KNOWN = [
    ("yuezhenglingv3", (4, 1, "乐正绫 · V3")),
    ("yuezhengling v3", (4, 1, "乐正绫 · V3")),
    ("yuezhengling", (4, 0, "乐正绫 · 中文")),
    ("yuezheng ling", (4, 0, "乐正绫 · 中文")),
    ("luotianyi", (4, 0, "洛天依 · 中文 Meng")),
    ("luo tianyi", (4, 0, "洛天依 · 中文 Meng")),
    ("yanhe", (4, 0, "言和 · 中文")),
    ("xingchen", (4, 0, "星尘 · 中文")),
    ("xinhua", (4, 0, "心华 · 中文")),
    ("kaito", (1, 0, "KAITO")),
    ("miku", (1, 0, "初音未来")),
    ("luka", (1, 0, "巡音流歌")),
    ("gumi", (1, 0, "GUMI")),
    ("ia_", (1, 0, "IA")),
    ("miku v4 chinese", (4, 0, "初音未来 · 中文")),
    ("miku_v4_chinese", (4, 0, "初音未来 · 中文")),
    ("yan he", (4, 0, "言和 · 中文")),
    ("moqingxian", (4, 0, "墨清弦")),
]

_CHINESE_MARKERS = ("chn", "china", "chinese", "ling", "luo", "yuezheng",
                    "yanhe", "xinhua", "xingchen", "tianyi", "中文",
                    "yan_he", "moqingxian")
_JAPANESE_MARKERS = ("jpn", "japan", "kaito", "miku", "luka", "gumi", "ia_",
                     "rin", "len", "meiko", "gakupo", "yukari", "kokone")


@dataclass
class Voicebank:
    id: str
    name: str
    display: str
    bs: int = 1
    pc: int = 0
    path: str = ""
    source: str = "registry"
    version: str = "unknown"

    @property
    def label(self) -> str:
        if "·" in self.display:
            return self.display
        return f"{self.display}  ({self.name})"


def _parse_name(raw: str) -> str:
    if "(" in raw and raw.endswith(")"):
        return raw[raw.rfind("(") + 1:-1].strip()
    return raw.strip()


def _override_path() -> Path:
    base = appdata_dir()
    return base / "voicebanks.json"


def _load_overrides() -> dict:
    try:
        with open(_override_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _match_known(name: str, path: str) -> tuple[int, int, str] | None:
    """Map a bank name/path to ``(bs, pc, display)``.

    Chinese markers win over vendor names: ``MIKU_V4_Chinese`` must resolve to
    the Chinese bank (``bs=4``) even though ``miku`` alone means Japanese.
    """
    key = f"{name} {path}".lower().replace("_", " ").replace("-", " ")
    if any(marker in key for marker in _CHINESE_MARKERS):
        for needle, vals in _KNOWN:
            if needle in key and vals[0] == 4:
                return vals
        return 4, 0, name
    for needle, vals in _KNOWN:
        if needle in key:
            return vals
    return None


def _infer_unknown(name: str, path: str) -> tuple[int, int, str]:
    key = f"{name} {path}".lower()
    if any(x in key for x in _CHINESE_MARKERS):
        return 4, 0, name
    if any(x in key for x in _JAPANESE_MARKERS):
        return 1, 0, name
    return 1, 0, name


_VERSION_RE = re.compile(r"_V([345])(?:_|\s|$)", re.IGNORECASE)


def _detect_version(comp: Path, filenames: list[str]) -> str:
    """Best-effort V3/V4/V5 detection from EULA, path and component files."""
    eula = comp / "EULA"
    if eula.is_dir():
        try:
            for entry in eula.iterdir():
                match = _VERSION_RE.search(entry.name)
                if match:
                    return "V" + match.group(1)
        except OSError:
            pass
    low_path = str(comp).lower()
    if "v3" in low_path:
        return "V3"
    if "v4" in low_path:
        return "V4"
    vvds = [f.lower() for f in filenames if f.lower().endswith(".vvd")]
    if vvds and all(f.startswith("_v4compatible") for f in vvds):
        return "V5"
    for f in filenames:
        low = f.lower()
        if low.endswith((".ddb", ".ddi")) and "v4" in low:
            return "V4"
    return "unknown"


def _pick_name(filenames: list[str]) -> str | None:
    """Real-voice ``.vvd`` first, then ``.ddi``/``.ddb``; never the compat marker."""
    groups = (
        [f for f in filenames
         if f.lower().endswith(".vvd") and not f.lower().startswith("_v4compatible")],
        [f for f in filenames if f.lower().endswith(".ddi")],
        [f for f in filenames if f.lower().endswith(".ddb")],
    )
    for group in groups:
        if group:
            return Path(sorted(group, key=lambda x: x.lower())[0]).stem
    return None


def _make_bank(bid: str, name: str, vpath: str, source: str,
               overrides: dict, version: str = "unknown") -> Voicebank:
    ov = overrides.get(bid) or overrides.get(name) or {}
    known = _match_known(name, vpath)
    if known:
        bs, pc, pretty = known
    else:
        bs, pc, pretty = _infer_unknown(name, vpath)
    if version != "unknown" and version not in pretty:
        pretty = f"{pretty} · {version}"
    if isinstance(ov, dict):
        bs = int(ov.get("bs", bs))
        pc = int(ov.get("pc", pc))
        pretty = str(ov.get("display", pretty))
    return Voicebank(bid, name, pretty, bs, pc, vpath, source, version)


def _scan_registry(seen: set[str], overrides: dict) -> list[Voicebank]:
    found: list[Voicebank] = []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\VOCALOID4\DATABASE"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VOCALOID4\DATABASE"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\VOCALOID4\DATABASE"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\VOCALOID3\DATABASE"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VOCALOID3\DATABASE"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\VOCALOID3\DATABASE"),
    ]
    for hive, path in roots:
        try:
            with winreg.OpenKey(hive, path) as key:
                count = winreg.QueryInfoKey(key)[0]
                for i in range(count):
                    sub = winreg.EnumKey(key, i)
                    if sub in seen:
                        continue
                    try:
                        with winreg.OpenKey(key, sub) as sk:
                            name = _parse_name(str(winreg.QueryValueEx(sk, "NAME")[0]))
                            vpath = str(winreg.QueryValueEx(sk, "PATH")[0])
                            try:
                                installed = int(winreg.QueryValueEx(sk, "INSTALLED")[0])
                            except OSError:
                                installed = 1
                    except OSError:
                        continue
                    if not installed:
                        continue
                    seen.add(sub)
                    found.append(_make_bank(sub, name, vpath, "registry", overrides))
        except OSError:
            continue
    return found


def _roots_path() -> Path:
    return appdata_dir() / "voicebank_roots.txt"


def get_voicebank_roots() -> list[str]:
    """User-added folders, persisted across launches."""
    try:
        lines = _roots_path().read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        raw = line.strip().strip('"')
        if not raw or raw.startswith("#"):
            continue
        try:
            p = Path(raw).expanduser()
            if not p.is_dir():
                continue
            key = str(p).lower()
        except Exception:
            continue
        if key not in seen:
            seen.add(key)
            out.append(str(p))
    return out


def add_voicebank_root(path: str | Path) -> str:
    p = Path(path).expanduser()
    if not p.is_dir():
        raise ValueError("请选择声库文件夹（不是文件）。")
    try:
        p = p.resolve()
    except Exception:
        pass
    roots = get_voicebank_roots()
    if str(p).lower() not in {r.lower() for r in roots}:
        roots.append(str(p))
        try:
            f = _roots_path()
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("\n".join(roots) + "\n", encoding="utf-8")
        except Exception:
            pass
    return str(p)


def remove_voicebank_root(path: str | Path) -> None:
    try:
        target = str(Path(path).expanduser().resolve()).lower()
    except Exception:
        return
    roots = [r for r in get_voicebank_roots() if r.lower() != target]
    try:
        _roots_path().write_text("\n".join(roots) + "\n", encoding="utf-8")
    except Exception:
        pass


_SKIP_DIRS = {
    "$recycle.bin", "system volume information", "__pycache__", "__macosx",
    "windows", "winsxs", "node_modules", ".git",
}


def _scan_folder(root, seen: set[str], overrides: dict,
                 source: str = "manual") -> list[Voicebank]:
    """Find every folder containing a .vvd under an arbitrary root."""
    try:
        root = Path(root)
        if not root.is_dir():
            return []
    except Exception:
        return []
    found: list[Voicebank] = []
    for dirpath, dirnames, filenames in os.walk(root):
        comp = Path(dirpath)
        try:
            depth = len(comp.relative_to(root).parts)
        except Exception:
            depth = 0
        if depth >= 8:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d.lower() not in _SKIP_DIRS]
        if not any(f.lower().endswith(".vvd") for f in filenames):
            continue
        name = _pick_name(filenames)
        if not name:
            continue
        bid = comp.name
        if bid in seen:
            continue
        seen.add(bid)
        version = _detect_version(comp, filenames)
        found.append(_make_bank(bid, name, str(comp.parent), source,
                                overrides, version))
    return found


def scan_voicebank_folder(path: str | Path) -> list[Voicebank]:
    """Preview what a folder would add without persisting it."""
    return _scan_folder(path, set(), _load_overrides(), "manual")


def _drive_available(base: Path) -> bool:
    try:
        if os.name == "nt":
            import ctypes
            # 2=removable, 3=fixed, 6=ramdisk; skip network/CD to avoid stalls
            return ctypes.windll.kernel32.GetDriveTypeW(str(base)) in (2, 3, 6)
        return base.is_dir()
    except Exception:
        return False


def _voice_db_roots() -> list[Path]:
    candidates: list[Path] = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "ProgramW6432"):
        base = os.getenv(env)
        if base:
            candidates.append(Path(base) / "VoiceDB")
    candidates += [
        Path(r"C:\VoiceDB"),
        Path(r"C:\Program Files (x86)\VOCALOID3\VoiceDB"),
        Path(r"C:\Program Files\VOCALOID3\VoiceDB"),
        Path(r"C:\VOCALOID4\VoiceDB"),
    ]
    for exe in (V4_EXE, V5_EXE):
        try:
            d = Path(exe).parent
        except Exception:
            continue
        for base in (d, d.parent):
            for name in ("VoiceDB", "VoiceBank", "Voicebank"):
                candidates.append(base / name)
            candidates.append(base / "Editor" / "VoiceDB")
    common = ("VoiceDB", "VoiceBank", "Voicebank")
    for letter in ascii_uppercase:
        base = Path(f"{letter}:\\")
        if not _drive_available(base):
            continue
        for name in common:
            candidates.append(base / name)
        for vendor in ("VOCALOID", "VOCALOID3", "VOCALOID4", "VOCALOID5",
                       "VOCALOID6", "VOCALOID6SE", "VOCALOID4FE", "Vocaloid"):
            for name in common:
                candidates.append(base / vendor / name)
            candidates.append(base / vendor / "Editor" / "VoiceDB")
    out: list[Path] = []
    seen: set[str] = set()
    for r in candidates:
        try:
            key = str(r).lower()
            if key not in seen and r.is_dir():
                seen.add(key)
                out.append(r)
        except OSError:
            continue
    return out


def _scan_filesystem(seen: set[str], overrides: dict) -> list[Voicebank]:
    found: list[Voicebank] = []
    for root in _voice_db_roots():
        found += _scan_folder(root, seen, overrides, "filesystem")
    return found


def detect_voicebanks() -> list[Voicebank]:
    overrides = _load_overrides()
    seen: set[str] = set()
    found = _scan_registry(seen, overrides)
    found += _scan_filesystem(seen, overrides)
    for root in get_voicebank_roots():
        found += _scan_folder(root, seen, overrides, "custom")
    # LuoTianyi first, then other Chinese banks, then the rest
    def sort_key(v: Voicebank):
        d = v.display.lower()
        n = v.name.lower()
        return (0 if "luo" in n else 1,
                0 if "乐正绫" in v.display else 1,
                d)
    found.sort(key=sort_key)
    return found


def v4_available() -> bool:
    return _valid_exe(V4_EXE)
