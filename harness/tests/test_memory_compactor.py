"""스마트 메모리 압축기, 양방향 SDD 테스트 합성기 및 단일 HTML 대시보드(Phase 4) 단위 테스트."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness import autopilot_engine, mcp_server, memory_compactor, team_cli


class TestPhase4MemoryAndSynthesis(unittest.TestCase):
    """memory-compact 중복 제거 및 32개 캡, sdd-synthesize 합성, HTML 대시보드 생성 검증."""

    def test_memory_compactor_deduplicates_and_caps_active_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            autopilot_engine.learn_project_rule(root, "중복 규칙 테스트", forbidden_regex=r"foo_bar", severity="MEDIUM", apply=True)
            autopilot_engine.learn_project_rule(root, "중복 규칙 테스트 업데이트", forbidden_regex=r"foo_bar", severity="CRITICAL", apply=True)
            for idx in range(5):
                autopilot_engine.learn_project_rule(root, f"개별 규칙 {idx}", severity="LOW", apply=True)

            comp_res = memory_compactor.compact_project_memory(root, max_active_rules=3, apply=True)
            self.assertEqual(comp_res["status"], "PASS")
            self.assertEqual(comp_res["merged_duplicate_count"], 1)
            self.assertEqual(comp_res["active_count"], 3)
            self.assertEqual(comp_res["archived_count"], 3)
            active = comp_res["active_rules"]
            assert isinstance(active, list)
            self.assertEqual(active[0]["severity"], "CRITICAL")

    def test_sdd_synthesize_and_dashboard_html_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            syn_res = memory_compactor.synthesize_sdd_tests_and_golden_io(root, language="python", apply=True)
            self.assertEqual(syn_res["status"], "PASS")
            self.assertTrue((root / "approved-spec" / "golden-io.json").is_file())
            self.assertTrue((root / "tests" / "test_sdd_synthesized.py").is_file())

            dash_res = memory_compactor.export_dashboard_html(root, {"version": "1.0.0", "learned_rules_count": 5}, apply=True)
            self.assertTrue(dash_res["dashboard_generated"])
            html_file = root / memory_compactor.DEFAULT_DASHBOARD_HTML_REL
            self.assertTrue(html_file.is_file())
            self.assertIn("Dreampia-Skill", html_file.read_text(encoding="utf-8"))

    def test_mcp_server_dispatches_all_phase1_to_4_tools_in_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src/service.py").write_text("def calc_fee(amount: int) -> int:\n    return amount + 100\n", encoding="utf-8")
            (root / "test_service.py").write_text(
                "import unittest\nfrom src.service import calc_fee\n"
                "class T(unittest.TestCase):\n"
                "    def test_f(self) -> None:\n"
                "        self.assertEqual(calc_fee(50), 150)\n",
                encoding="utf-8",
            )
            r1 = mcp_server.execute_mcp_tool(root, "dreampia_benchmark", {"language": "python"})
            self.assertEqual(r1["status"], "PASS")
            r2 = mcp_server.execute_mcp_tool(root, "dreampia_mutation_check", {"target": "src/service.py", "cmd": "python -m unittest test_service.py"})
            self.assertEqual(r2["mutation_score"], 1.0)
            r3 = mcp_server.execute_mcp_tool(
                root,
                "dreampia_hook_dispatch",
                {"event": "PreToolUse", "payload": {"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}}},
            )
            self.assertEqual(r3["decision"], "block")
            r4 = mcp_server.execute_mcp_tool(root, "dreampia_symbol_map", {"target": "src/service.py"})
            self.assertEqual(r4["total_symbols"], 1)
            r5 = mcp_server.execute_mcp_tool(root, "dreampia_symbol_slice", {"target": "src/service.py", "symbol": "calc_fee"})
            self.assertEqual(r5["status"], "PASS")
            r6_c = mcp_server.execute_mcp_tool(root, "dreampia_checkpoint", {"mode": "create", "target": "src/service.py", "apply": True})
            ck_obj = r6_c["checkpoint"]
            assert isinstance(ck_obj, dict)
            ck_id = str(ck_obj["checkpoint_id"])
            (root / "src/service.py").write_text("BROKEN\n", encoding="utf-8")
            r6_r = mcp_server.execute_mcp_tool(root, "dreampia_checkpoint", {"mode": "restore", "target": ck_id, "apply": True})
            self.assertEqual(r6_r["restored_count"], 1)
            self.assertIn("calc_fee", (root / "src/service.py").read_text(encoding="utf-8"))
            wt1 = root / "wt1"
            wt2 = root / "wt2"
            (wt1 / "src").mkdir(parents=True)
            (wt2 / "src").mkdir(parents=True)
            (wt1 / "src/a.py").write_text("x = 1\n", encoding="utf-8")
            (wt2 / "src/b.py").write_text("y = 2\n", encoding="utf-8")
            r7 = mcp_server.execute_mcp_tool(root, "dreampia_squad_merge_check", {"target": "wt1,wt2"})
            self.assertEqual(r7["status"], "PASS")
            r8 = mcp_server.execute_mcp_tool(root, "dreampia_memory_compact", {"max_rules": 32, "apply": True})
            self.assertEqual(r8["status"], "PASS")
            team_cli.interview_compile_check(root, "수수료 계산기", answers="정수;0;50ms", apply=True)
            r9 = mcp_server.execute_mcp_tool(root, "dreampia_sdd_synthesize", {"language": "python", "apply": True})
            self.assertGreaterEqual(int(r9["golden_case_count"]), 1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
