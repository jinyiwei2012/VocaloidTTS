"""v4bridge 的守卫与降级路径。

真正的 Win32 注入（找窗口、按 Ctrl+O、点「打开」）只能在装有编辑器的机器上
人工验证；这里覆盖的是不需要编辑器的部分。
"""
import unittest

from vocaloidtts import v4bridge


class V4BridgeGuardTests(unittest.TestCase):
    def test_unknown_process_name_is_allowed(self):
        # pid 0 拿不到进程名，按设计放行，免得权限不足时彻底不可用
        self.assertTrue(v4bridge._belongs_to(0, "VOCALOID4.exe"))

    def test_missing_file_is_reported_with_its_path(self):
        ok, msg = v4bridge.open_vsqx("C:/definitely/not/here.vsqx")
        self.assertFalse(ok)
        self.assertIn("not/here.vsqx", msg)

    def test_finders_are_safe_without_user32(self):
        if v4bridge.user32 is not None:
            self.skipTest("Windows 上窗口枚举依赖真实桌面")
        self.assertIsNone(v4bridge.find_v4_window())
        self.assertIsNone(v4bridge.find_v5_window())
        self.assertIsNone(v4bridge.find_editor_window())


if __name__ == "__main__":
    unittest.main()
