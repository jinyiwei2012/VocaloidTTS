"""Tiny Win32 notification-area icon (no external tray dependency).

The main window uses this only when the user closes it: right-clicking the
tray icon offers "显示主窗口" and "退出 VocaloidTTS".
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
from ctypes import wintypes
from typing import Callable

if sys.platform != "win32":  # pragma: no cover
    TrayIcon = None  # type: ignore
else:
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    WM_APP = 0x8000
    WM_TRAY = WM_APP + 1
    WM_COMMAND = 0x0111
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002
    WM_NULL = 0x0000
    WM_DROPFILES = 0x0233
    WM_CONTEXTMENU = 0x007B
    WM_RBUTTONUP = 0x0205
    WM_LBUTTONDBLCLK = 0x0203
    MF_STRING = 0x0000
    MF_SEPARATOR = 0x0800
    TPM_RETURNCMD = 0x0100
    TPM_RIGHTBUTTON = 0x0002
    NIM_ADD = 0
    NIM_DELETE = 2
    NIM_SETVERSION = 4
    NIF_MESSAGE = 0x01
    NIF_ICON = 0x02
    NIF_TIP = 0x04
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x0010
    LR_DEFAULTSIZE = 0x0040

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
        wintypes.WPARAM, wintypes.LPARAM)

    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = [
        wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
        wintypes.WPARAM, wintypes.LPARAM]
    user32.GetAncestor.restype = wintypes.HWND
    shell32.DragQueryFileW.argtypes = [
        wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    shell32.DragFinish.argtypes = [wintypes.HANDLE]
    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
        ]

    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadIconW.restype = wintypes.HICON
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    class TrayIcon:
        def __init__(self, icon_path: str, on_show: Callable[[], None],
                     on_quit: Callable[[], None], tooltip: str = "VocaloidTTS"):
            self.icon_path = icon_path
            self.on_show = on_show
            self.on_quit = on_quit
            self.tooltip = tooltip
            self._thread: threading.Thread | None = None
            self._ready = threading.Event()
            self._hwnd = 0
            self._hicon = 0
            self._nid = None
            self._taskbar_msg = 0
            self._class_name = f"VocaloidTTSTray_{os.getpid()}"
            self._wndproc = WNDPROC(self._proc)

        # -- tray thread -------------------------------------------------
        def start(self) -> bool:
            if self._thread and self._thread.is_alive():
                return True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            self._ready.wait(3.0)
            return bool(self._hwnd)

        def stop(self) -> None:
            hwnd = self._hwnd
            if hwnd:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            if self._thread and self._thread.is_alive():
                self._thread.join(2.0)

        def _run(self) -> None:
            hinst = kernel32.GetModuleHandleW(None)
            try:
                self._taskbar_msg = int(
                    user32.RegisterWindowMessageW("TaskbarCreated"))
            except Exception:
                self._taskbar_msg = 0
            wc = WNDCLASSW()
            wc.style = 0
            wc.lpfnWndProc = self._wndproc
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hinst
            wc.hIcon = 0
            wc.hCursor = 0
            wc.hbrBackground = 0
            wc.lpszMenuName = None
            wc.lpszClassName = self._class_name
            user32.RegisterClassW(ctypes.byref(wc))
            hwnd = user32.CreateWindowExW(
                0, self._class_name, "VocaloidTTS", 0,
                0, 0, 0, 0, 0, 0, hinst, 0)
            self._hwnd = hwnd
            if not hwnd:
                self._ready.set()
                return
            self._hicon = self._load_icon()
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = self._hicon
            nid.szTip = self.tooltip[:127]
            self._nid = nid
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                self._hwnd = 0
                self._ready.set()
                return
            try:
                nid.uVersion = 4
                shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))
            except Exception:
                pass
            self._ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        def _load_icon(self) -> int:
            try:
                h = user32.LoadImageW(
                    0, self.icon_path, IMAGE_ICON, 0, 0,
                    LR_LOADFROMFILE | LR_DEFAULTSIZE)
                if h:
                    return int(h)
            except Exception:
                pass
            return int(user32.LoadIconW(0, 32512))  # IDI_APPLICATION

        # -- window proc -------------------------------------------------
        def _proc(self, hwnd, msg, wparam, lparam):
            try:
                if msg == WM_TRAY:
                    code = int(lparam) & 0xFFFF
                    if code in (WM_RBUTTONUP, WM_CONTEXTMENU):
                        self._menu(hwnd)
                    elif code == WM_LBUTTONDBLCLK:
                        self._notify(self.on_show)
                    return 0
                if self._taskbar_msg and msg == self._taskbar_msg:
                    # Explorer restarted: the icon must be added again or the
                    # app becomes unreachable (the window is already hidden).
                    if self._nid is not None:
                        try:
                            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))
                        except Exception:
                            pass
                    return 0
                if msg == WM_CLOSE:
                    if self._nid is not None:
                        try:
                            shell32.Shell_NotifyIconW(
                                NIM_DELETE, ctypes.byref(self._nid))
                        except Exception:
                            pass
                    user32.DestroyWindow(hwnd)
                    return 0
                if msg == WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
            except Exception:
                pass
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        def _menu(self, hwnd) -> None:
            menu = user32.CreatePopupMenu()
            user32.AppendMenuW(menu, MF_STRING, 1, "显示主窗口")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, 2, "退出 VocaloidTTS")
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(
                menu, TPM_RETURNCMD | TPM_RIGHTBUTTON,
                pt.x, pt.y, 0, hwnd, None)
            user32.PostMessageW(hwnd, WM_NULL, 0, 0)
            user32.DestroyMenu(menu)
            if cmd == 1:
                self._notify(self.on_show)
            elif cmd == 2:
                self._notify(self.on_quit)

        @staticmethod
        def _notify(fn: Callable[[], None]) -> None:
            try:
                fn()
            except Exception:
                pass

    class CloseHook:
        """Intercept native WM_CLOSE and accept dropped .txt files."""

        def __init__(self, root, callback: Callable[[], None],
                     on_drop: Callable[[list[str]], None] | None = None):
            self.root = root
            self.callback = callback
            self.on_drop = on_drop
            self._drop_queue: list[list[str]] = []
            self._close_requested = False
            self._poll_job = None
            self._proc = WNDPROC(self._wndproc)
            self._olds: dict[int, object] = {}
            self.hwnds: list[int] = []
            self._hook_job = None
            self._hook_tries = 0
            self._add_hwnd(int(root.winfo_id()))
            try:
                self._hook_job = self.root.after(100, self._hook_top)
            except Exception:
                self._hook_job = None
            try:
                self._poll_job = self.root.after(100, self._poll_drops)
            except Exception:
                self._poll_job = None

        def _add_hwnd(self, hwnd: int) -> None:
            if not hwnd or hwnd in self.hwnds:
                return
            self.hwnds.append(hwnd)
            old = user32.SetWindowLongPtrW(
                hwnd, -4, ctypes.cast(self._proc, ctypes.c_void_p))
            self._olds[hwnd] = old
            try:
                shell32.DragAcceptFiles(hwnd, True)
            except Exception:
                pass
            self.hwnd = hwnd

        def _hook_top(self) -> None:
            self._hook_job = None
            top = 0
            try:
                child = int(self.root.winfo_id())
                top = int(user32.GetAncestor(child, 2) or 0)
                parent = int(user32.GetParent(child) or 0)
                self._add_hwnd(top)
                self._add_hwnd(parent)
                top = top or parent
            except Exception:
                pass
            if not top and self._hook_tries < 20:
                self._hook_tries += 1
                try:
                    self._hook_job = self.root.after(100, self._hook_top)
                except Exception:
                    self._hook_job = None

        def _poll_drops(self) -> None:
            """Run on Tk's event loop, never inside the native WndProc."""
            self._poll_job = None
            while self._drop_queue:
                paths = self._drop_queue.pop(0)
                try:
                    self.on_drop(paths)
                except Exception:
                    pass
            if self._close_requested:
                self._close_requested = False
                try:
                    self.callback()
                except Exception:
                    pass
            try:
                self._poll_job = self.root.after(100, self._poll_drops)
            except Exception:
                self._poll_job = None

        def _dropped_paths(self, hdrop) -> list[str]:
            paths: list[str] = []
            try:
                count = int(shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0))
                for i in range(min(count, 16)):
                    n = int(shell32.DragQueryFileW(hdrop, i, None, 0))
                    buf = ctypes.create_unicode_buffer(n + 1)
                    shell32.DragQueryFileW(hdrop, i, buf, n + 1)
                    if buf.value:
                        paths.append(buf.value)
            finally:
                try:
                    shell32.DragFinish(hdrop)
                except Exception:
                    pass
            return paths

        def _wndproc(self, hwnd, msg, wparam, lparam):
            if msg == WM_DROPFILES and self.on_drop is not None:
                paths = self._dropped_paths(wparam)
                if paths:
                    # Queue only: calling Tk/Tcl from inside a native WndProc
                    # during Tk's message pump can corrupt Python's thread state.
                    self._drop_queue.append(paths)
                return 0
            if msg == WM_CLOSE:
                self._close_requested = True
                return 0
            old = self._olds.get(int(hwnd))
            if not old:
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
            return user32.CallWindowProcW(
                old, hwnd, msg, wparam, lparam)

        def restore(self) -> None:
            if self._hook_job is not None:
                try:
                    self.root.after_cancel(self._hook_job)
                except Exception:
                    pass
                self._hook_job = None
            if self._poll_job is not None:
                try:
                    self.root.after_cancel(self._poll_job)
                except Exception:
                    pass
                self._poll_job = None
            for hwnd, old in list(self._olds.items()):
                try:
                    if old:
                        user32.SetWindowLongPtrW(
                            hwnd, -4, ctypes.c_void_p(old))
                except Exception:
                    pass
            self._olds.clear()
