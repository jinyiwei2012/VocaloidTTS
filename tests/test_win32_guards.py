"""Win32 平台层的可测部分：托盘重建与带超时的 SendMessage。

真正的窗口、托盘图标和编辑器交互没法在单元测试里跑，这里只覆盖
「必须重设版本号」「消息必须带超时」这两条容易回归的规则。
"""
from __future__ import annotations

import ctypes
import sys
import unittest
from unittest.mock import MagicMock, patch

from vocaloidtts import tray, v4bridge

windows_only = unittest.skipUnless(sys.platform == "win32", "仅 Windows 可用")


@windows_only
class TrayRebuildTests(unittest.TestCase):
    def _icon(self) -> "tray.TrayIcon":
        icon = tray.TrayIcon.__new__(tray.TrayIcon)
        icon._nid = tray.NOTIFYICONDATAW()
        return icon

    def test_adding_the_icon_also_resets_the_version(self) -> None:
        icon = self._icon()
        calls: list[int] = []
        fake_shell = MagicMock()
        fake_shell.Shell_NotifyIconW.side_effect = (
            lambda op, _ptr: calls.append(op) or 1)
        with patch.object(tray, "shell32", fake_shell):
            self.assertTrue(icon._add_icon())
        # explorer 重启后只发 NIM_ADD 会让气泡通知退回 0 版行为
        self.assertEqual(calls, [tray.NIM_ADD, tray.NIM_SETVERSION])
        self.assertEqual(icon._nid.uVersion, 4)

    def test_failed_add_reports_false(self) -> None:
        icon = self._icon()
        fake_shell = MagicMock()
        fake_shell.Shell_NotifyIconW.return_value = 0
        with patch.object(tray, "shell32", fake_shell):
            self.assertFalse(icon._add_icon())


class SendTimeoutTests(unittest.TestCase):
    def test_message_uses_abort_if_hung(self) -> None:
        fake = MagicMock()
        fake.SendMessageTimeoutW.return_value = 1
        with patch.object(v4bridge, "user32", fake):
            self.assertTrue(v4bridge._send(1, 0x0C, 0, 0))
        args = fake.SendMessageTimeoutW.call_args[0]
        self.assertEqual(args[4], v4bridge.SMTO_ABORTIFHUNG)
        self.assertIsNotNone(args[6])

    def test_no_response_says_why(self) -> None:
        message = v4bridge._no_response("VOCALOID4", r"C:\x.vsqx")
        self.assertIn("管理员权限", message)
        self.assertIn(r"C:\x.vsqx", message)


if __name__ == "__main__":
    unittest.main()
