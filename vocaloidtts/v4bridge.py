"""Small Win32 bridge that opens a VSQX in an already running VOCALOID4 FE.

VOCALOID4 FE ignores command-line file arguments on this build, so the tool
drives the standard File > Open dialog through Win32 messages.  It is optional:
the generated .vsqx can always be opened manually with Ctrl+O.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes

from .voicebank import get_v4_exe, get_v5_exe, v4_available, v5_available

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
WM_COMMAND = 0x0111
WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5
ID_FILE_OPEN = 57601
VK_CONTROL = 0x11
VK_O = 0x4F
KEYEVENTF_KEYUP = 0x0002

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def find_v4_window() -> int | None:
    found: list[int] = []

    @WNDENUMPROC
    def cb(hwnd, _):
        try:
            cls = _class_name(hwnd)
            title = _title(hwnd)
            if cls.startswith("308ED0A5") or "VOCALOID4 Editor" in title:
                found.append(hwnd)
        except Exception:
            pass
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def find_v5_window() -> int | None:
    found: list[int] = []

    @WNDENUMPROC
    def cb(hwnd, _):
        try:
            cls = _class_name(hwnd)
            title = _title(hwnd)
            if "HwndWrapper[VOCALOID5" in cls or "VOCALOID5 Editor" in title:
                found.append(hwnd)
        except Exception:
            pass
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def find_editor_window() -> tuple[int, str] | None:
    v5 = find_v5_window()
    if v5:
        return v5, "v5"
    v4 = find_v4_window()
    if v4:
        return v4, "v4"
    return None


def is_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq VOCALOID5.exe"],
                             capture_output=True, text=True, timeout=5).stdout
        if "VOCALOID5.exe" in out:
            return True
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq VOCALOID4.exe"],
                             capture_output=True, text=True, timeout=5).stdout
        return "VOCALOID4.exe" in out
    except Exception:
        return find_editor_window() is not None


def launch_editor(kind: str | None = None) -> tuple[int, str] | None:
    if kind is None:
        if v5_available() and not v4_available():
            kind = "v5"
        elif v4_available():
            kind = "v4"
        elif v5_available():
            kind = "v5"
        else:
            return None
    exe = get_v5_exe() if kind == "v5" else get_v4_exe()
    if not os.path.isfile(exe):
        return None
    subprocess.Popen([exe], cwd=os.path.dirname(exe))
    finder = find_v5_window if kind == "v5" else find_v4_window
    for _ in range(120):
        time.sleep(0.5)
        hwnd = finder()
        if hwnd:
            return hwnd, kind
    return None


def launch_v4() -> int | None:
    got = launch_editor("v4")
    return got[0] if got else None


def _child_with_id(dlg: int, ctrl_id: int) -> int:
    found: list[int] = []

    @WNDENUMPROC
    def cb(hwnd, _):
        if user32.GetDlgCtrlID(hwnd) == ctrl_id:
            found.append(hwnd)
            return False
        return True

    user32.EnumChildWindows(dlg, cb, 0)
    return found[0] if found else 0


def _find_open_dialog(timeout: float = 15.0) -> int | None:
    end = time.time() + timeout
    while time.time() < end:
        found: list[int] = []

        @WNDENUMPROC
        def cb(hwnd, _):
            if _class_name(hwnd) == "#32770":
                # a file dialog exposes the filename edit with ID 1148
                if _child_with_id(hwnd, 1148):
                    found.append(hwnd)
                    return False
            return True

        user32.EnumWindows(cb, 0)
        if found:
            return found[0]
        time.sleep(0.2)
    return None


def _focus(hwnd: int) -> None:
    try:
        fg = user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        ft = user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        mt = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(mt, ft, True)
        user32.ShowWindow(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(mt, ft, False)
    except Exception:
        try:
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def _send_ctrl_o(hwnd: int) -> None:
    _focus(hwnd)
    time.sleep(0.2)
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_O, 0, 0, 0)
    user32.keybd_event(VK_O, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def open_vsqx(path: str, target: str | None = None) -> tuple[bool, str]:
    """Open *path* in V4/V5. target='v4' or 'v5' forces an editor."""
    if not os.path.isfile(path):
        return False, "文件不存在"
    got = None
    if target in ("v4", "v5"):
        finder = find_v5_window if target == "v5" else find_v4_window
        hwnd = finder()
        if hwnd:
            got = (hwnd, target)
        else:
            got = launch_editor(target)
    if not got:
        got = find_editor_window()
    if not got:
        got = launch_editor()
        if not got:
            return False, "未能启动 VOCALOID4/5"
        time.sleep(1.0)
    hwnd, kind = got
    dlg = _find_open_dialog(0.4)
    if not dlg:
        if kind == "v5":
            _send_ctrl_o(hwnd)
        else:
            user32.PostMessageW(hwnd, WM_COMMAND, ID_FILE_OPEN, 0)
        dlg = _find_open_dialog(20.0)
    if not dlg:
        return False, "未找到 V4/V5 的打开对话框，请手动按 Ctrl+O"
    edit = _child_with_id(dlg, 1148)
    if not edit:
        return False, "未找到文件名输入框，请手动打开"
    user32.SendMessageW(edit, WM_SETTEXT, 0, ctypes.c_wchar_p(path))
    time.sleep(0.25)
    btn = _child_with_id(dlg, 1)
    if not btn:
        return False, "未找到“打开”按钮，请手动打开"
    user32.SendMessageW(btn, BM_CLICK, 0, 0)
    time.sleep(1.2)
    leftover = _find_open_dialog(0.5)
    if leftover:
        user32.SendMessageW(leftover, WM_COMMAND, 2, 0)
    return True, f"已发送载入指令（{kind.upper()}）"
