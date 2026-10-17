"""네이티브 호스트 생애주기 훅 디스패처(hook_dispatcher.py) 단위 및 통합 테스트."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness import autopilot_engine, hook_dispatcher


class TestHookDispatcher(unittest.TestCase):
    """PreToolUse, PostToolUse, Stop(Sisyphus), UserPromptSubmit 및 settings.json 설치 검증."""

    def test_pre_tool_use_blocks_destructive_shell_and_outside_workspace_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res_shell = hook_dispatcher.dispatch_hook_event(
                root,
                "PreToolUse",
                {"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}},
            )
            self.assertEqual(res_shell["status"], "BLOCKED")
            self.assertEqual(res_shell["permissionDecision"], "deny")
            self.assertLess(float(res_shell["elapsed_ms"]), 30.0)  # type: ignore[arg-type]

            res_escape = hook_dispatcher.dispatch_hook_event(
                root,
                "PreToolUse",
                {"tool_name": "Write", "tool_input": {"file_path": str(root.parent / "outside.py")}},
            )
            self.assertEqual(res_escape["status"], "BLOCKED")

            res_protected = hook_dispatcher.dispatch_hook_event(
                root,
                "PreToolUse",
                {"tool_name": "Write", "tool_input": {"file_path": "ai-dev-execution/bundle-manifest.json"}},
            )
            self.assertEqual(res_protected["status"], "BLOCKED")

            res_ok = hook_dispatcher.dispatch_hook_event(
                root,
                "PreToolUse",
                {"tool_name": "Write", "tool_input": {"file_path": "src/app.py"}},
            )
            self.assertEqual(res_ok["status"], "PASS")
            self.assertEqual(res_ok["permissionDecision"], "allow")

    def test_post_tool_use_and_stop_continuation_enforcer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_file = root / "bad_service.py"
            bad_file.write_text(
                "def do_work() -> int:\n    try:\n        return 1\n    except:\n        pass\n    return 0\n",
                encoding="utf-8",
            )
            post_res = hook_dispatcher.dispatch_hook_event(
                root,
                "PostToolUse",
                {"tool_name": "Write", "tool_input": {"file_path": "bad_service.py"}},
            )
            self.assertEqual(post_res["status"], "WARN")
            self.assertGreaterEqual(int(post_res["finding_count"]), 1)  # type: ignore[arg-type]
            self.assertIn("slop-bare-except-pass", str(post_res.get("additionalContext")))

            stop_1 = hook_dispatcher.dispatch_hook_event(root, "Stop", {})
            self.assertEqual(stop_1["status"], "BLOCKED")
            self.assertEqual(stop_1["decision"], "block")
            self.assertEqual(stop_1["attempt"], 1)

            stop_2 = hook_dispatcher.dispatch_hook_event(root, "Stop", {})
            self.assertEqual(stop_2["attempt"], 2)
            stop_3 = hook_dispatcher.dispatch_hook_event(root, "Stop", {})
            self.assertEqual(stop_3["attempt"], 3)
            stop_4 = hook_dispatcher.dispatch_hook_event(root, "Stop", {})
            self.assertEqual(stop_4["status"], "PASS")
            self.assertTrue(stop_4.get("escape_hatch_triggered"))

    def test_user_prompt_submit_and_idempotent_host_settings_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            autopilot_engine.learn_project_rule(root, "모든 버튼에 bg-transparent를 적용한다", apply=True)
            prompt_res = hook_dispatcher.dispatch_hook_event(root, "UserPromptSubmit", {"prompt": "구현해줘"})
            self.assertEqual(prompt_res["status"], "PASS")
            self.assertEqual(prompt_res["injected_rule_count"], 1)

            settings_file = root / ".claude" / "settings.json"
            inst_res = hook_dispatcher.install_host_hooks(settings_file, "python -m harness.team_cli", apply=True)
            self.assertEqual(inst_res["status"], "PASS")
            self.assertTrue(settings_file.is_file())

            uninst_res = hook_dispatcher.uninstall_host_hooks(settings_file, apply=True)
            self.assertEqual(uninst_res["status"], "PASS")
            self.assertTrue(uninst_res["removed"])


if __name__ == "__main__":
    unittest.main()
