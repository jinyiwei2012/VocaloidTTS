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

try:
    from ctypes import wintypes
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
except (ImportError, AttributeError):  # non-Windows: importing must not fail
    wintypes = None  # type: ignore[assignment]
    _user32 = None
    _kernel32 = None

from .voicebank import get_v4_exe, get_v5_exe, v4_available, v5_available

user32 = _user32
kernel32 = _kernel32
WM_COMMAND = 0x0111
WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5
ID_FILE_OPEN = 57601
VK_CONTROL = 0x11
VK_O = 0x4F
KEYEVENTF_KEYUP = 0x0002
SMTO_ABORTIFHUNG = 0x0002


def _send(hwnd: int, msg: int, wparam: int, lparam: int,
          timeout_ms: int = 3000) -> bool:
    """带超时的 SendMessageW。

    目标进程卡住时 SendMessageW 会无限期阻塞，把载入线程吊死。
    SMTO_ABORTIFHUNG 让它在目标不处理消息时立即返回 0。
    """
    result = ctypes.c_size_t()
    try:
        ok = user32.SendMessageTimeoutW(
            hwnd, msg, wparam, lparam, SMTO_ABORTIFHUNG,
            timeout_ms, ctypes.byref(result))
    except Exception:
        return False
    return bool(ok)


def _no_response(label: str, path: str) -> str:
    return (f"{label} 没有响应载入指令。\n\n"
            "可能是编辑器正忙，或它是以管理员权限启动的——"
            "UIPI 会丢弃来自低权限进程的消息。\n"
            f"请用相同权限重新运行 VocaloidTTS，或手动打开：\n{path}")

if user32 is not None:
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    # 窗口句柄在 64 位下可能超过 32 位；不声明 restype 会被默认的 c_int 截断。
    user32.GetForegroundWindow.restype = wintypes.HWND
    # SendMessageW 在目标无响应时会一直阻塞，改用带超时的版本。
    user32.SendMessageTimeoutW.restype = ctypes.c_size_t
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
else:
    WNDENUMPROC = None


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _process_name(pid: int) -> str:
    """取进程可执行文件名（小写）；权限不足或调用失败时返回空串。"""
    if kernel32 is None or pid <= 0:
        return ""
    handle = None
    try:
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
        if not handle:
            return ""
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value).lower()
    except Exception:
        return ""
    finally:
        if handle:
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass


def _belongs_to(hwnd: int, exe: str) -> bool:
    """窗口必须属于目标进程。

    读不到进程名时放行：某些权限配置下 OpenProcess 会失败，宁可退回按窗口
    类名/标题匹配，也不要让「载入」彻底不可用。
    """
    name = _process_name(_window_pid(hwnd))
    return not name or name == exe.lower()


def find_v4_window() -> int | None:
    if user32 is None:
        return None
    found: list[int] = []

    @WNDENUMPROC
    def cb(hwnd, _):
        try:
            cls = _class_name(hwnd)
            title = _title(hwnd)
            if (cls.startswith("308ED0A5") or "VOCALOID4 Editor" in title) \
                    and _belongs_to(hwnd, "VOCALOID4.exe"):
                found.append(hwnd)
        except Exception:
            pass
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def find_v5_window() -> int | None:
    if user32 is None:
        return None
    found: list[int] = []

    @WNDENUMPROC
    def cb(hwnd, _):
        try:
            cls = _class_name(hwnd)
            title = _title(hwnd)
            if ("HwndWrapper[VOCALOID5" in cls or "VOCALOID5 Editor" in title) \
                    and _belongs_to(hwnd, "VOCALOID5.exe"):
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
    # cwd="" 在 Windows 上不是「当前目录」而是无效路径，Popen 会直接抛错
    subprocess.Popen([exe], cwd=os.path.dirname(exe) or None)
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


def _find_open_dialog(timeout: float = 15.0,
                      owner_pid: int | None = None) -> int | None:
    """等到一个文件对话框；给了 owner_pid 就只认这个进程的。

    桌面上随时可能有别的程序的「另存为」——只按「#32770 + 控件 1148」认，
    会把路径写进别人的对话框、还会去点它的确认键。调用方一律传 owner_pid。
    """
    end = time.time() + timeout
    while time.time() < end:
        found: list[int] = []

        @WNDENUMPROC
        def cb(hwnd, _, found=found):
            if _class_name(hwnd) == "#32770":
                if owner_pid is not None and _window_pid(hwnd) != owner_pid:
                    return True
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
    try:
        # Only inject keys when our window really owns the foreground,
        # otherwise Ctrl+O would hit whatever the user is typing in.
        if int(user32.GetForegroundWindow()) != int(hwnd):
            return
    except Exception:
        return
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_O, 0, 0, 0)
    user32.keybd_event(VK_O, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def open_vsqx(path: str, target: str | None = None) -> tuple[bool, str]:
    """Open *path* in V4/V5. target='v4' or 'v5' forces an editor."""
    if not os.path.isfile(path):
        return False, f"文件不存在：{path}"
    if user32 is None:
        return False, "当前不是 Windows，无法自动载入；请手动用编辑器打开工程文件。"
    want = target if target in ("v4", "v5") else None
    got = None
    if want:
        finder = find_v5_window if want == "v5" else find_v4_window
        hwnd = finder()
        if hwnd:
            got = (hwnd, want)
        else:
            got = launch_editor(want)
    if not got:
        got = find_editor_window()
    if not got:
        if not (v4_available() or v5_available()):
            return False, ("没找到 VOCALOID4/5 的安装路径。\n\n"
                           "请点「编辑器」设置 VOCALOID4.exe 或 VOCALOID5.exe，"
                           "或手动打开工程文件。")
        got = launch_editor()
        if not got:
            return False, ("已尝试启动 VOCALOID4/5，但没有等到主窗口。\n\n"
                           "可能是启动较慢或权限不足；请稍等后重试，"
                           "或手动打开工程文件。")
        time.sleep(1.0)
    hwnd, kind = got
    label = kind.upper()
    owner = _window_pid(hwnd)
    dlg = _find_open_dialog(0.4, owner_pid=owner)
    if not dlg:
        if kind == "v5":
            _send_ctrl_o(hwnd)
        else:
            user32.PostMessageW(hwnd, WM_COMMAND, ID_FILE_OPEN, 0)
        dlg = _find_open_dialog(20.0, owner_pid=owner)
    if not dlg:
        return False, (f"没有等到 {label} 的打开对话框。\n\n"
                       f"请手动按 Ctrl+O 选择：\n{path}")
    edit = _child_with_id(dlg, 1148)
    if not edit:
        return False, (f"{label} 的对话框里没找到文件名输入框。\n\n"
                       f"请手动打开：\n{path}")
    path_buf = ctypes.c_wchar_p(path)
    if not _send(edit, WM_SETTEXT, 0,
                 ctypes.cast(path_buf, ctypes.c_void_p).value):
        return False, _no_response(label, path)
    time.sleep(0.25)
    btn = _child_with_id(dlg, 1)
    if not btn:
        return False, (f"{label} 的对话框里没找到「打开」按钮。\n\n"
                       f"请手动打开：\n{path}")
    if not _send(btn, BM_CLICK, 0, 0):
        return False, _no_response(label, path)
    time.sleep(1.2)
    leftover = _find_open_dialog(0.5, owner_pid=owner)
    if leftover:
        _send(leftover, WM_COMMAND, 2, 0, timeout_ms=1000)
    return True, f"已发送载入指令（{label}）"
