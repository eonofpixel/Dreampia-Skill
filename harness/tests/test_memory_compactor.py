"""스마트 메모리 압축기, 양방향 SDD 테스트 합성기 및 단일 HTML 대시보드(Phase 4) 단위 테스트."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness import autopilot_engine, memory_compactor


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


if __name__ == "__main__":
    unittest.main()
