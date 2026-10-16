"""Unit and integration tests for Dreampia SDD (Spec-Driven Development) & TDD traceability engine."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcp_server
import sdd_engine
import team_cli as team


class SddEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "tests").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_complete_sdd_to_tdd_chain_passes(self) -> None:
        (self.root / "docs/compact-project.md").write_text(
            "# Compact SDD Spec\n"
            "- PRD-R001: 학생은 회원가입 없이 접근 코드로 응답을 제출할 수 있어야 한다. (API-001, TASK-001) approved PASS\n"
            "- API-001: POST /api/submit 요청 스키마 및 201 응답 계약 (PRD-R001, TASK-001)\n"
            "- TASK-001: 제출 수직 슬라이스 구현 (PRD-R001, TEST-001) verified PASS\n"
            "- TEST-001: 제출 성공 및 중복 코드 거부 단위 테스트 (TASK-001) PASS\n",
            encoding="utf-8",
        )
        (self.root / "tests/test_submit.py").write_text(
            "def test_submit_flow():\n"
            "    # Verifies PRD-R001 and TEST-001\n"
            "    assert True\n",
            encoding="utf-8",
        )

        ledger_out = team.sdd_ledger_check(self.root, apply=True)
        self.assertEqual(ledger_out["status"], "PASS")
        self.assertTrue((self.root / "evidence/sdd-ledger.json").is_file())

        verdict = team.sdd_verify_check(self.root)
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["traceability_ratio"], 1.0)
        self.assertEqual(verdict["orphan_requirements"], [])
        self.assertEqual(verdict["stale_specs"], [])

    def test_orphan_requirement_and_missing_tdd_files_blocked(self) -> None:
        (self.root / "docs/compact-project.md").write_text(
            "# Spec with Orphan\n"
            "- PRD-R001: 학생 제출 기능 (TASK-001, TEST-001) approved\n"
            "- PRD-R002: 관리자 CSV 다운로드 감사 로그 기능 approved\n"
            "- TASK-001: 학생 제출 구현 (TEST-001)\n"
            "- TEST-001: 제출 검증 테스트\n",
            encoding="utf-8",
        )

        # No test files yet + PRD-R002 has no task or test
        verdict = sdd_engine.verify_sdd_compliance(self.root, require_tdd_files=True)
        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn("PRD-R002", verdict["orphan_requirements"])
        self.assertIn("PRD-R002", verdict["untested_requirements"])
        self.assertIn("missing-executable-tdd-test-files", verdict["blockers"])

    def test_spec_drift_detected_when_requirement_changes_after_ledger(self) -> None:
        spec_file = self.root / "docs/compact-project.md"
        spec_file.write_text(
            "# Spec\n"
            "- PRD-R001: 접근 코드는 6자리 숫자여야 한다. (TASK-001, TEST-001) approved PASS\n"
            "- TASK-001: 접근 코드 검증기 구현 (TEST-001) verified PASS\n"
            "- TEST-001: 6자리 숫자 검증 테스트 PASS\n",
            encoding="utf-8",
        )
        (self.root / "tests/test_access.py").write_text(
            "# TEST-001 implementation\ndef test_code(): assert True\n",
            encoding="utf-8",
        )

        # Save baseline SDD ledger
        team.sdd_ledger_check(self.root, apply=True)
        self.assertEqual(team.sdd_verify_check(self.root)["status"], "PASS")

        # Mutate PRD-R001 specification wording without re-running sdd-ledger
        spec_file.write_text(
            "# Spec\n"
            "- PRD-R001: 접근 코드는 8자리 영문+숫자 조합이어야 한다. (TASK-001, TEST-001) approved PASS\n"
            "- TASK-001: 접근 코드 검증기 구현 (TEST-001) verified PASS\n"
            "- TEST-001: 6자리 숫자 검증 테스트 PASS\n",
            encoding="utf-8",
        )
        drifted = team.sdd_verify_check(self.root)
        self.assertEqual(drifted["status"], "STALE")
        self.assertIn("PRD-R001", drifted["stale_specs"])

    def test_mcp_sdd_tools_execution(self) -> None:
        (self.root / "docs/compact-project.md").write_text(
            "# MCP SDD Test\n"
            "- REQ-001: API 헬스체크 엔드포인트 제공 (API-001, TASK-001, TEST-001) approved PASS\n"
            "- API-001: GET /api/health 200 OK\n"
            "- TASK-001: 헬스체크 라우트 구현 (TEST-001) verified PASS\n"
            "- TEST-001: 헬스체크 응답 코드 검증 PASS\n",
            encoding="utf-8",
        )
        (self.root / "tests/test_health.py").write_text(
            "def test_health():\n    # TEST-001\n    assert True\n",
            encoding="utf-8",
        )

        mcp_ledger = mcp_server.execute_mcp_tool(
            self.root,
            "dreampia_sdd_ledger",
            {"project": str(self.root), "apply": True},
        )
        self.assertEqual(mcp_ledger["status"], "PASS")

        mcp_check = mcp_server.execute_mcp_tool(
            self.root,
            "dreampia_sdd_check",
            {"project": str(self.root)},
        )
        self.assertEqual(mcp_check["status"], "PASS")
        self.assertEqual(mcp_check["traceability_ratio"], 1.0)

    def test_multiline_heading_and_four_hop_bfs_chain(self) -> None:
        (self.root / "docs/01-prd.md").write_text(
            "# PRD\n"
            "### PRD-R001 {{관찰 가능한 사용자 요구 제목}}\n"
            "- 연결: UX {{UX-S ID}}\n\n"
            "### PRD-R010 다중 단계 제출 요구\n"
            "- 상태: approved\n"
            "- 연결: UX-S010\n",
            encoding="utf-8",
        )
        (self.root / "docs/05-contracts.md").write_text(
            "# Contracts\n"
            "- UX-S010: 제출 화면 상태 전환 -> API-010\n"
            "- API-010: POST /api/v1/submit -> TASK-010\n"
            "- TASK-010: 제출 핸들러 구현 -> TEST-010\n"
            "- TEST-010: 4단계 체인 통합 검증 PASS\n",
            encoding="utf-8",
        )
        (self.root / "tests/test_chain.py").write_text(
            "def test_four_hop():\n    # TEST-010\n    assert True\n",
            encoding="utf-8",
        )

        verdict = sdd_engine.verify_sdd_compliance(self.root, require_tdd_files=True)
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["requirement_count"], 1)
        self.assertEqual(verdict["orphan_requirements"], [])

    def test_all_four_scaffold_presets_pass_gate_and_sdd_check(self) -> None:
        for preset in team.PROJECT_TYPES:
            with self.subTest(preset=preset), tempfile.TemporaryDirectory() as td:
                proot = Path(td)
                team.install(proot, "init", True)
                team.project_scaffold(proot, preset, True)
                gate_res = team.verify_gate(proot, "before-dev-start")
                self.assertEqual(gate_res["status"], "PASS")
                sdd_res = team.sdd_verify_check(proot, require_tdd_files=False)
                self.assertEqual(sdd_res["status"], "PASS")
                self.assertEqual(sdd_res["orphan_requirements"], [])


if __name__ == "__main__":
    unittest.main()
