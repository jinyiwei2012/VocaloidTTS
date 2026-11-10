"""CI 工作流触发条件的回归。

这里没有跑 GitHub Actions 的能力，所以守的是最容易改错的那一条约定：
**push 到 release 分支才发布，手动 workflow_dispatch 只构建**。
断言是文本级的——它防的是「有人把条件改回去」，不是验证 Actions 语义。
"""
from __future__ import annotations

import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"


def _publish_condition(text: str) -> str:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "publish:")
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped.startswith("if:"):
            return stripped
        if stripped and not stripped.startswith("#") and not line.startswith(" " * 4):
            break
    return ""


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_publish_requires_a_push_event(self) -> None:
        condition = _publish_condition(self.text)
        self.assertIn("github.event_name == 'push'", condition,
                      "publish 必须排除 workflow_dispatch，否则手动验证也会发版")
        self.assertIn("refs/heads/release", condition)

    def test_build_still_runs_on_manual_dispatch(self) -> None:
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("branches: [release]", self.text)

    def test_documented_contract_matches_the_condition(self) -> None:
        # 文件开头承诺「workflow_dispatch 只跑构建、不发布」，条件必须一致
        self.assertIn("workflow_dispatch 只跑构建、不发布", self.text)


if __name__ == "__main__":
    unittest.main()
