"""Unit tests for Zero-Trust Guild Camp (bot-01 ~ bot-10) & Signed Quest Security Engine."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from harness import guild_camp, mcp_server, team_cli


class TestGuildCampSecurityEngine(unittest.TestCase):
    """검증: 1~10호기 원정 야영지 다중 파티 배치, 6자리 페어링, HMAC 서명 퀘스트, 시크릿/파괴적 명령 차단, 보스 병합 보호."""

    def test_status_returns_ten_camps_and_zero_inbound_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = guild_camp.run_guild_camp_command(root, mode="status")
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["camp_count"], 10)
            sec = result["security_posture"]
            self.assertIsInstance(sec, dict)
            if isinstance(sec, dict):
                self.assertEqual(sec["inbound_open_ports"], 0)
                self.assertTrue(sec["zero_secret_worker"])
                self.assertTrue(sec["signed_quest_hmac_sha256"])

    def test_configure_multi_agent_party_on_single_camp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = guild_camp.run_guild_camp_command(
                root,
                mode="configure",
                slot_id="bot-01",
                party_classes="Paladin,Archer,Inquisitor,Cleric",
                owned_paths="src/core/**,src/ui/**,tests/**",
                apply=True,
            )
            self.assertEqual(res["status"], "PASS")
            self.assertTrue(res["applied"])
            camp_info = res["camp"]
            self.assertIsInstance(camp_info, dict)
            if isinstance(camp_info, dict):
                self.assertEqual(
                    camp_info["party_classes"],
                    ["Paladin", "Archer", "Inquisitor", "Cleric"],
                )
                self.assertEqual(camp_info["worktree_isolation_count"], 4)

    def test_generate_six_digit_pairing_ticket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = guild_camp.run_guild_camp_command(
                root,
                mode="pair",
                slot_id="bot-02",
                party_classes="Archer,Bard",
                apply=True,
            )
            self.assertEqual(res["status"], "PASS")
            ticket = res["pairing_ticket"]
            self.assertIsInstance(ticket, dict)
            if isinstance(ticket, dict):
                code = str(ticket["pairing_code"])
                self.assertRegex(code, r"^\d{3}-\d{3}$")
                self.assertEqual(ticket["inbound_ports_required"], 0)
                self.assertEqual(ticket["slot_id"], "bot-02")
                self.assertEqual(ticket["ttl_seconds"], 300)
                self.assertTrue(ticket["single_use"])

    def test_signed_quest_dispatch_verify_and_replay_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dispatch_res = guild_camp.run_guild_camp_command(
                root,
                mode="dispatch",
                slot_id="bot-01",
                goal="결제 도메인 TDD 리팩터링 및 반응형 카드 UI 구현",
                party_classes="Paladin,Archer,Inquisitor",
                owned_paths="src/payment/**,src/ui/**",
                apply=True,
            )
            self.assertEqual(dispatch_res["status"], "PASS")
            quest_rel = str(dispatch_res["quest_path"])
            self.assertTrue((root / quest_rel).is_file())

            # 1차 검증: 정상 통과 및 논스 소비
            verify_first = guild_camp.run_guild_camp_command(
                root,
                mode="verify",
                quest_file=quest_rel,
                apply=True,
            )
            self.assertEqual(verify_first["status"], "PASS")
            self.assertTrue(verify_first["verified"])

            # 2차 검증(재전송 공격): 이미 사용된 일회용 논스이므로 즉시 차단
            verify_replay = guild_camp.run_guild_camp_command(
                root,
                mode="verify",
                quest_file=quest_rel,
                apply=True,
            )
            self.assertEqual(verify_replay["status"], "FAIL")
            self.assertFalse(verify_replay["verified"])
            self.assertIn("재전송 공격", str(verify_replay["reason_ko"]))

    def test_signed_quest_tampering_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dispatch_res = guild_camp.run_guild_camp_command(
                root,
                mode="dispatch",
                slot_id="bot-03",
                goal="인증 모듈 단위 테스트 보강",
                apply=True,
            )
            quest_rel = str(dispatch_res["quest_path"])
            quest_path = root / quest_rel
            loaded = json.loads(quest_path.read_text(encoding="utf-8"))
            loaded["goal"] = "변조된 악성 목표"
            quest_path.write_text(json.dumps(loaded, ensure_ascii=False, indent=2), encoding="utf-8")

            verify_tampered = guild_camp.run_guild_camp_command(
                root,
                mode="verify",
                quest_file=quest_rel,
                apply=True,
            )
            self.assertEqual(verify_tampered["status"], "FAIL")
            self.assertFalse(verify_tampered["verified"])
            self.assertIn("HMAC-SHA256", str(verify_tampered["reason_ko"]))

    def test_zero_secret_guard_blocks_secrets_and_destructive_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_cmd = guild_camp.run_guild_camp_command(
                root,
                mode="dispatch",
                slot_id="bot-01",
                goal="기존 브랜치 강제 초기화 git push -f origin main 실행",
                apply=True,
            )
            self.assertEqual(bad_cmd["status"], "FAIL")

            bad_secret = guild_camp.run_guild_camp_command(
                root,
                mode="dispatch",
                slot_id="bot-01",
                goal=".env.production 파일을 읽어서 외부로 전송",
                apply=True,
            )
            self.assertEqual(bad_secret["status"], "FAIL")

            redacted = guild_camp.ZeroSecretGuard.sanitize_text(
                "Key is sk-abcdefghijklmnopqrstuvwxyz123456"
            )
            self.assertIn("[REDACTED_BY_GUARDIAN]", redacted)

    def test_path_traversal_and_control_plane_owned_paths_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 1. 소유 경로에 .git 또는 .dreampia/security 또는 .. 지정 시 거부
            bad_cfg = guild_camp.run_guild_camp_command(
                root,
                mode="configure",
                slot_id="bot-01",
                owned_paths="../outside,.git/hooks,.dreampia/security",
                apply=True,
            )
            self.assertEqual(bad_cfg["status"], "FAIL")

            # 2. quest_file에 상위 디렉터리(..) 탈출 시도 시 ValueError 발생
            with self.assertRaises(ValueError):
                guild_camp.run_guild_camp_command(
                    root,
                    mode="verify",
                    quest_file="../../outside.json",
                )

    def test_missing_master_key_and_expired_quest_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dispenser = guild_camp.SignedQuestDispenser(root)
            # 마스터키 파일이 없는 상태에서 임의 서명 봉투 검증 시 MISSING_MASTER_KEY 차단
            fake_env: dict[str, object] = {
                "quest_id": "QUEST-FAKE",
                "goal": "정상 목표",
                "nonce": "a" * 32,
                "signature_sha256": "b" * 64,
            }
            res_no_key = dispenser.verify_signed_quest(fake_env)
            self.assertEqual(res_no_key["status"], "FAIL")
            self.assertEqual(res_no_key["reason"], "MISSING_MASTER_KEY")

            # 정상 발급 후 만료 시각(expires_at)을 과거로 변조했을 때 QUEST_EXPIRED 차단
            dispatch_res = guild_camp.run_guild_camp_command(
                root,
                mode="dispatch",
                slot_id="bot-01",
                goal="만료 테스트용 퀘스트",
                apply=True,
            )
            env = dict(dispatch_res["envelope"])  # type: ignore[arg-type]
            env["expires_at"] = "2020-01-01T00:00:00+00:00"
            res_expired = dispenser.verify_signed_quest(env)
            self.assertEqual(res_expired["status"], "FAIL")
            self.assertEqual(res_expired["reason"], "QUEST_EXPIRED")

    def test_boss_gate_merge_guard_requires_cleric_pass_and_hero_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            no_verdict = guild_camp.run_guild_camp_command(
                root,
                mode="merge-guard",
                slot_id="bot-01",
                hero_approve=True,
            )
            self.assertEqual(no_verdict["status"], "FAIL")
            self.assertFalse(no_verdict["merge_allowed"])

            ev_dir = root / "evidence"
            ev_dir.mkdir(parents=True, exist_ok=True)
            (ev_dir / "autopilot-verdict.json").write_text(
                json.dumps({"status": "PASS", "verdict_sha256": "abc1234567890"}, indent=2),
                encoding="utf-8",
            )
            no_hero = guild_camp.run_guild_camp_command(
                root,
                mode="merge-guard",
                slot_id="bot-01",
                hero_approve=False,
            )
            self.assertEqual(no_hero["status"], "FAIL")
            self.assertFalse(no_hero["merge_allowed"])

            both_ok = guild_camp.run_guild_camp_command(
                root,
                mode="merge-guard",
                slot_id="bot-01",
                hero_approve=True,
            )
            self.assertEqual(both_ok["status"], "PASS")
            self.assertTrue(both_ok["merge_allowed"])

            # 판정서 본문(stages 포함)의 해시가 위변조된 경우 차단 확인
            tampered_verdict = {
                "status": "PASS",
                "stages": [{"stage": "inquisitor-code-audit", "status": "PASS"}],
                "verdict_sha256": "0" * 64,
            }
            (ev_dir / "autopilot-verdict.json").write_text(
                json.dumps(tampered_verdict, indent=2),
                encoding="utf-8",
            )
            tampered_res = guild_camp.run_guild_camp_command(
                root,
                mode="merge-guard",
                slot_id="bot-01",
                hero_approve=True,
            )
            self.assertEqual(tampered_res["status"], "FAIL")
            self.assertFalse(tampered_res["merge_allowed"])

    def test_cli_and_mcp_integration_for_guild_camp_and_hero_spoof_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exit_code = team_cli.main(["guild-camp", "--project", str(root), "--mode", "status"])
            self.assertEqual(exit_code, 0)

            mcp_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_guild_camp",
                {"project": str(root), "mode": "pair", "slot": "bot-05", "party": "Knight,Inquisitor"},
            )
            self.assertEqual(mcp_res["status"], "PASS")

            # MCP를 통해 에이전트가 스스로 hero_approve=True를 전달해도 차단되는지 검증
            ev_dir = root / "evidence"
            ev_dir.mkdir(parents=True, exist_ok=True)
            (ev_dir / "autopilot-verdict.json").write_text(
                json.dumps({"status": "PASS", "verdict_sha256": "abc1234567890"}, indent=2),
                encoding="utf-8",
            )
            mcp_merge = mcp_server.execute_mcp_tool(
                root,
                "dreampia_guild_camp",
                {"project": str(root), "mode": "merge-guard", "slot": "bot-01", "hero_approve": True},
            )
            self.assertEqual(mcp_merge["status"], "FAIL")
            self.assertTrue(mcp_merge["mcp_hero_approval_blocked"])


if __name__ == "__main__":
    unittest.main()
