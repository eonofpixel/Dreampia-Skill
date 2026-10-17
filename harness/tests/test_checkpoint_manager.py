"""Golden Checkpoint 스냅샷 매니저, 병렬 워크트리 병합 시뮬레이터 및 라이브 캠프 워커(Phase 3) 단위 테스트."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness import checkpoint_manager, guild_camp


class TestPhase3Resilience(unittest.TestCase):
    """Golden Checkpoint 생성·목록·무손실 복원, 워크트리 충돌 시뮬레이션, 캠프 라이브 워커 검증."""

    def test_checkpoint_create_list_and_byte_exact_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "src" / "engine.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            original_content = "def compute() -> int:\n    return 42\n"
            target.write_text(original_content, encoding="utf-8")

            c_res = checkpoint_manager.create_checkpoint(root, ["src/engine.py"], label="v1-golden", apply=True)
            self.assertEqual(c_res["status"], "PASS")

            l_res = checkpoint_manager.list_checkpoints(root)
            self.assertEqual(l_res["checkpoint_count"], 1)

            target.write_text("def compute() -> int:\n    return -999\n", encoding="utf-8")
            self.assertIn("-999", target.read_text(encoding="utf-8"))

            r_res = checkpoint_manager.restore_checkpoint(root, "latest", apply=True)
            self.assertEqual(r_res["status"], "PASS")
            self.assertEqual(target.read_text(encoding="utf-8"), original_content)

    def test_worktree_merge_simulator_detects_overlapping_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shared.py").write_text("X = 1\n", encoding="utf-8")

            slot1 = root / "worktrees" / "slot-1"
            slot2 = root / "worktrees" / "slot-2"
            slot1.mkdir(parents=True, exist_ok=True)
            slot2.mkdir(parents=True, exist_ok=True)

            (slot1 / "shared.py").write_text("X = 2\n", encoding="utf-8")
            (slot2 / "shared.py").write_text("X = 3\n", encoding="utf-8")

            sim_conflict = checkpoint_manager.simulate_worktree_merge(
                root,
                ["worktrees/slot-1", "worktrees/slot-2"],
            )
            self.assertEqual(sim_conflict["status"], "FAIL")
            self.assertEqual(sim_conflict["conflict_count"], 1)

            (slot2 / "shared.py").write_text("X = 1\n", encoding="utf-8")
            (slot2 / "other.py").write_text("Y = 10\n", encoding="utf-8")
            sim_clean = checkpoint_manager.simulate_worktree_merge(
                root,
                ["worktrees/slot-1", "worktrees/slot-2"],
            )
            self.assertEqual(sim_clean["status"], "PASS")
            self.assertEqual(sim_clean["conflict_count"], 0)

    def test_camp_worker_daemon_polls_and_completes_signed_quest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            disp = guild_camp.run_guild_camp_command(
                root,
                mode="dispatch",
                slot_id="bot-01",
                goal="단위 테스트 검증 수행",
                apply=True,
            )
            self.assertEqual(disp["status"], "PASS")

            worker_res = guild_camp.run_guild_camp_command(
                root,
                mode="worker-run",
                slot_id="bot-01",
                apply=True,
            )
            self.assertEqual(worker_res["status"], "PASS")
            self.assertEqual(worker_res["processed_count"], 1)


if __name__ == "__main__":
    unittest.main()
