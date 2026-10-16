from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness import autopilot_engine, mcp_server, team_cli


class AutopilotEngineTests(unittest.TestCase):
    def test_audit_code_detects_hollow_tdd_and_rule_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests_dir = root / "tests"
            src_dir = root / "src"
            tests_dir.mkdir(parents=True, exist_ok=True)
            src_dir.mkdir(parents=True, exist_ok=True)

            # 1. Hollow Python test (assert True & zero-assert test)
            (tests_dir / "test_hollow.py").write_text(
                "def test_fake() -> None:\n"
                "    assert True\n\n"
                "def test_empty() -> None:\n"
                "    x = 1 + 1\n",
                encoding="utf-8",
            )
            # 2. Python missing return type
            (src_dir / "service.py").write_text(
                "def compute_score(value: int):\n"
                "    return value * 2\n",
                encoding="utf-8",
            )
            # 3. TSX with any, non-lucide icon, and button without bg-transparent
            (src_dir / "Button.tsx").write_text(
                "import { FaBeer } from 'react-icons/fa';\n"
                "export function ActionButton(props: any) {\n"
                "  return <button className=\"px-4 py-2\">Click</button>;\n"
                "}\n",
                encoding="utf-8",
            )

            report = autopilot_engine.audit_project_code(root)
            self.assertEqual(report["status"], "FAIL")
            rules_hit = {f["rule_id"] for f in report["findings"]}  # type: ignore[index]
            self.assertIn("hollow-tdd-assert-true", rules_hit)
            self.assertIn("hollow-tdd-no-assertion", rules_hit)
            self.assertIn("missing-return-type", rules_hit)
            self.assertIn("forbidden-any-type", rules_hit)
            self.assertIn("forbidden-icon-library", rules_hit)
            self.assertIn("button-bg-transparent-missing", rules_hit)

    def test_audit_code_passes_on_compliant_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests_dir = root / "tests"
            src_dir = root / "src"
            tests_dir.mkdir(parents=True, exist_ok=True)
            src_dir.mkdir(parents=True, exist_ok=True)

            (src_dir / "calc.py").write_text(
                "def add_numbers(a: int, b: int) -> int:\n"
                "    return a + b\n",
                encoding="utf-8",
            )
            (tests_dir / "test_calc.py").write_text(
                "from src.calc import add_numbers\n\n"
                "def test_add_numbers() -> None:\n"
                "    result = add_numbers(2, 3)\n"
                "    assert result == 5\n",
                encoding="utf-8",
            )
            (src_dir / "ActionButton.tsx").write_text(
                "import { Check } from 'lucide-react';\n"
                "export interface ActionButtonProps { label: string; }\n"
                "export function ActionButton(props: ActionButtonProps): JSX.Element {\n"
                "  return <button className=\"bg-transparent hover:bg-slate-100 focus:ring-2\">{props.label}</button>;\n"
                "}\n",
                encoding="utf-8",
            )

            report = autopilot_engine.audit_project_code(root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["finding_count"], 0)
            self.assertEqual(report["blocking_count"], 0)

    def test_golden_io_verifier_passes_and_catches_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            impl_dir = root / "implementation"
            spec_dir = root / "approved-spec"
            impl_dir.mkdir(parents=True, exist_ok=True)
            spec_dir.mkdir(parents=True, exist_ok=True)

            (impl_dir / "pricing.py").write_text(
                "def calculate_total(amount: int, tax_rate: float) -> dict[str, float]:\n"
                "    tax = round(amount * tax_rate, 2)\n"
                "    return {'total': amount + tax, 'tax': tax}\n",
                encoding="utf-8",
            )
            (spec_dir / "golden-io.json").write_text(
                "{\n"
                '  "module_path": "implementation/pricing.py",\n'
                '  "cases": [\n'
                "    {\n"
                '      "id": "GIO-001",\n'
                '      "function": "calculate_total",\n'
                '      "args": [100, 0.1],\n'
                '      "expected": {"total": 110.0, "tax": 10.0}\n'
                "    }\n"
                "  ]\n"
                "}\n",
                encoding="utf-8",
            )

            pass_report = autopilot_engine.verify_golden_io(root)
            self.assertEqual(pass_report["status"], "PASS")
            self.assertEqual(pass_report["passed_count"], 1)

            # Introduce behavioral drift
            (spec_dir / "golden-io.json").write_text(
                "{\n"
                '  "module_path": "implementation/pricing.py",\n'
                '  "cases": [\n'
                "    {\n"
                '      "id": "GIO-001",\n'
                '      "function": "calculate_total",\n'
                '      "args": [100, 0.1],\n'
                '      "expected": {"total": 999.0, "tax": 10.0}\n'
                "    }\n"
                "  ]\n"
                "}\n",
                encoding="utf-8",
            )
            fail_report = autopilot_engine.verify_golden_io(root)
            self.assertEqual(fail_report["status"], "FAIL")
            self.assertEqual(len(fail_report["failures"]), 1)  # type: ignore[arg-type]

    def test_context_pack_and_autopilot_gate_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            team_cli.project_scaffold(root, "api-service", apply=True)

            # Create compliant implementation + real TDD test linked to TASK-001 / TEST-001
            tests_dir = root / "tests"
            tests_dir.mkdir(parents=True, exist_ok=True)
            (tests_dir / "test_api_service.py").write_text(
                "# TASK-001 TEST-001 REQ-001\n"
                "def calculate_health(status_code: int) -> str:\n"
                "    return 'OK' if status_code == 200 else 'ERR'\n\n"
                "def test_health_endpoint() -> None:\n"
                "    assert calculate_health(200) == 'OK'\n",
                encoding="utf-8",
            )

            # Refresh SDD ledger so hashes and test files match
            team_cli.sdd_ledger_check(root, apply=True)

            # Compile context pack via MCP
            ctx_res = mcp_server.execute_mcp_tool(root, "dreampia_context_pack", {"project": str(root), "apply": True})
            self.assertEqual(ctx_res["status"], "PASS")
            self.assertTrue((root / "evidence" / "context-pack.json").is_file())

            # Run unified autopilot gate via MCP
            gate_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_autopilot_gate",
                {"project": str(root), "allow_doc_only": False, "apply": True},
            )
            self.assertEqual(gate_res["status"], "PASS")
            self.assertTrue((root / "evidence" / "autopilot-verdict.json").is_file())

    def test_setup_global_one_click_installer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp) / "home"
            fake_home.mkdir(parents=True, exist_ok=True)

            preview = team_cli.setup_global(apply=False, home_dir=fake_home)
            self.assertEqual(preview["status"], "PASS")
            self.assertFalse(preview["applied"])
            self.assertFalse((fake_home / ".gemini/antigravity/skills/ai-dev-execution/SKILL.md").exists())

            applied = team_cli.setup_global(apply=True, home_dir=fake_home)
            self.assertEqual(applied["status"], "PASS")
            self.assertTrue(applied["applied"])
            self.assertTrue((fake_home / ".gemini/config/skills/ai-dev-execution/SKILL.md").is_file())
            self.assertTrue((fake_home / ".gemini/antigravity/skills/ai-dev-execution/SKILL.md").is_file())
            self.assertTrue((fake_home / ".claude/skills/ai-dev-execution/SKILL.md").is_file())
            self.assertTrue((fake_home / ".cursor/skills/ai-dev-execution/SKILL.md").is_file())
            self.assertTrue((fake_home / ".agents/skills/ai-dev-execution/SKILL.md").is_file())
            self.assertTrue((fake_home / ".gemini/antigravity/mcp_config.json").is_file())

    def test_blast_radius_and_new_magic_shorthands(self) -> None:
        from harness import route_planner

        climb_route = route_planner.plan_route("climb optimize token parser latency", repo_dirty=False)
        self.assertIn("climb", climb_route.magic_shorthands)
        self.assertEqual(climb_route.execution_mode, "metric-climb")
        self.assertTrue(climb_route.continuous_loop)

        blast_route = route_planner.plan_route("blast check auth token change impact", repo_dirty=False)
        self.assertIn("blast", blast_route.magic_shorthands)
        self.assertEqual(blast_route.execution_mode, "blast-radius")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            tests = root / "tests"
            src.mkdir(parents=True, exist_ok=True)
            tests.mkdir(parents=True, exist_ok=True)

            (src / "core_token.py").write_text(
                "def verify_jwt_signature(token: str) -> bool:\n"
                "    return token.startswith('valid_')\n",
                encoding="utf-8",
            )
            (src / "api_handler.py").write_text(
                "import json\n"
                "from src.core_token import verify_jwt_signature\n\n"
                "def handle_request(payload: str) -> str:\n"
                "    data = json.loads(payload)\n"
                "    ok = verify_jwt_signature(data.get('token', ''))\n"
                "    return json.dumps({'ok': ok})\n",
                encoding="utf-8",
            )
            (src / "gateway.py").write_text(
                "from src.api_handler import handle_request\n\n"
                "def entrypoint(raw: str) -> str:\n"
                "    return handle_request(raw)\n",
                encoding="utf-8",
            )
            (tests / "test_core_token.py").write_text(
                "from src.core_token import verify_jwt_signature\n\n"
                "def test_sig() -> None:\n"
                "    assert verify_jwt_signature('valid_123') is True\n",
                encoding="utf-8",
            )

            res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_blast_radius",
                {"project": str(root), "target": "src/core_token.py", "apply": True},
            )
            self.assertEqual(res["status"], "PASS")
            self.assertGreaterEqual(int(res["safety_proof_level"]), 3)  # type: ignore[arg-type]
            self.assertIn("src/gateway.py", res["transitive_dependents"])  # type: ignore[operator]
            self.assertTrue((root / "evidence/blast-radius-report.json").is_file())

    def test_metric_climb_engine_deduplication_and_immutable_guard(self) -> None:
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_py = root / "algo.py"
            eval_py = root / "eval_harness.py"

            target_py.write_text(
                "def score() -> float:\n"
                "    return 10.0\n",
                encoding="utf-8",
            )
            eval_py.write_text(
                "import algo\n"
                "print(f'metric: {algo.score():.4f}')\n",
                encoding="utf-8",
            )

            cmd_str = f'"{sys.executable}" eval_harness.py'

            # 1. Baseline run -> KEEP
            base_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_metric_climb",
                {
                    "project": str(root),
                    "cmd": cmd_str,
                    "direction": "minimize",
                    "target": "algo.py",
                    "immutable": "eval_harness.py",
                    "trials": 2,
                    "hypothesis": "baseline",
                    "apply": True,
                },
            )
            self.assertEqual(base_res["verdict"], "KEEP")
            self.assertTrue((root / "evidence/metric-climb-results.tsv").is_file())

            # 2. Duplicate run without changing algo.py -> SKIPPED (never-repeat)
            dup_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_metric_climb",
                {
                    "project": str(root),
                    "cmd": cmd_str,
                    "direction": "minimize",
                    "target": "algo.py",
                    "immutable": "eval_harness.py",
                    "trials": 2,
                    "hypothesis": "repeat-same-code",
                    "apply": True,
                },
            )
            self.assertEqual(dup_res["status"], "SKIPPED")
            self.assertEqual(dup_res["verdict"], "DUPLICATE_CONFIG")

            # 3. Improved candidate -> KEEP
            target_py.write_text(
                "def score() -> float:\n"
                "    return 5.0\n",
                encoding="utf-8",
            )
            win_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_metric_climb",
                {
                    "project": str(root),
                    "cmd": cmd_str,
                    "direction": "minimize",
                    "target": "algo.py",
                    "immutable": "eval_harness.py",
                    "trials": 2,
                    "hypothesis": "halve-latency",
                    "apply": True,
                },
            )
            self.assertEqual(win_res["verdict"], "KEEP")

            # 4. Tamper with immutable eval_harness.py -> IMMUTABLE_TAMPERED
            eval_py.write_text("print('metric: 0.0001')\n", encoding="utf-8")
            tamper_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_metric_climb",
                {
                    "project": str(root),
                    "cmd": cmd_str,
                    "direction": "minimize",
                    "target": "algo.py",
                    "immutable": "eval_harness.py",
                    "trials": 2,
                    "hypothesis": "reward-hack-attempt",
                    "apply": True,
                },
            )
            self.assertEqual(tamper_res["status"], "FAIL")
            self.assertEqual(tamper_res["verdict"], "IMMUTABLE_TAMPERED")

    def test_korean_prompt_expansion_and_echo_markdown(self) -> None:
        from harness import route_planner

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # 1. Casual UI button prompt expands into Korean engineering spec with UI rules + SOLID + edge cases (without parroting)
            brief = route_planner.expand_prompt_brief("쿠폰 발급 버튼 만들어줘", root=root)
            self.assertEqual(brief.goal_kind, "change")
            self.assertEqual(brief.core_subject, "쿠폰 발급 버튼 만들어줘")
            self.assertEqual(route_planner._extract_clean_topic_ko(brief.core_subject), "쿠폰 발급 버튼")
            self.assertNotIn("만들어줘", brief.expanded_prompt_ko)
            self.assertNotIn("원본 입력", brief.echo_markdown_ko)
            self.assertIn("자동 챙김 항목", brief.echo_markdown_ko)
            self.assertIn("bg-transparent", brief.expanded_prompt_ko)
            self.assertIn("lucide-react", brief.expanded_prompt_ko)
            self.assertIn("SOLID 5원칙", brief.expanded_prompt_ko)
            self.assertIn("[Dreampia 국문 프롬프트 고도화 & 작전 브리핑]", brief.echo_markdown_ko)
            self.assertTrue(any("중복 클릭" in e for e in brief.edge_cases_to_check_ko))

            # 2. Shorthand prefix ("고도화" / "구체화" / "sharpen") strips prefix cleanly and activates prompt-sharpen
            sharpen_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_expand_prompt",
                {"project": str(root), "goal": "고도화 결제 환불 상태 검증 로직"},
            )
            self.assertEqual(sharpen_res["status"], "PASS")
            self.assertEqual(sharpen_res["core_subject"], "결제 환불 상태 검증 로직")
            self.assertEqual(sharpen_res["execution_mode"], "prompt-sharpen")
            self.assertIn("한 번 더 생각한 고도화 프롬프트", str(sharpen_res["echo_markdown_ko"]))

            # 3. route-plan also embeds prompt_expansion automatically
            route_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_route_plan",
                {"project": str(root), "goal": "ulw loop 로그인 토큰 만료 버그 고쳐줘"},
            )
            self.assertEqual(route_res["status"], "PASS")
            self.assertIn("prompt_expansion", route_res)
            exp = route_res["prompt_expansion"]  # type: ignore[index]
            self.assertEqual(exp["core_subject"], "로그인 토큰 만료 버그 고쳐줘")  # type: ignore[index]
            self.assertIn("Morpheus(라우터)", exp["squad_pipeline_ko"])  # type: ignore[index]

            # 4. Korean and English native shorthand routing verification
            compat_cases = (
                ("설계 결제 정산 아키텍처 설계", "sdd-spec"),
                ("풀가동 주문 상태 머신", "ultrawork"),
                ("인터뷰 신규 구독 요금제 기획", "prompt-sharpen"),
                ("명세 대형 모노레포 메모리", "sdd-spec"),
                ("plan 인증 모듈", "sdd-spec"),
                ("autopilot 장바구니 API", "ultrawork"),
                ("완주 정산 배치 테스트", "continuous-loop"),
            )
            for raw_prompt, expected_mode in compat_cases:
                dec = route_planner.plan_route(raw_prompt, repo_dirty=False)
                self.assertEqual(dec.execution_mode, expected_mode, f"Failed for {raw_prompt}")

    def test_self_hosting_cli_allows_analysis_and_blocks_mutation_on_package(self) -> None:
        import contextlib
        import io
        import json
        from harness import route_planner, team_cli

        pkg_str = str(team_cli.PACKAGE)
        # 1. Self-hosting analysis commands on PACKAGE succeed
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = team_cli.main(["expand-prompt", "--project", pkg_str, "--goal", "지금 우리가 우리스킬로 우리스킬을 고도화하는 작업하자"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["goal_kind"], "change")
        self.assertEqual(route_planner._extract_clean_topic_ko(payload["core_subject"]), "우리스킬로 우리스킬을 고도화")

        # 2. Self-hosting doctor and 3 verify gates on PACKAGE succeed
        doc_res = team_cli.doctor(team_cli.PACKAGE)
        self.assertTrue(doc_res["healthy"])
        self.assertTrue(doc_res.get("self_hosted"))
        for gate_name in ("before-dev-start", "before-claim-complete", "before-client-send"):
            g_res = team_cli.verify_gate(team_cli.PACKAGE, gate_name)
            self.assertEqual(g_res["status"], "PASS", f"Self-hosted gate failed: {gate_name} -> {g_res}")

        # 3. Self-hosting code audit on PACKAGE has 0 blocking issues and 0 button-bg-transparent-missing
        audit_buf = io.StringIO()
        with contextlib.redirect_stdout(audit_buf):
            rc_audit = team_cli.main(["audit-code", "--project", pkg_str])
        self.assertEqual(rc_audit, 0)
        audit_payload = json.loads(audit_buf.getvalue())
        self.assertEqual(audit_payload["status"], "PASS")
        self.assertEqual(audit_payload["blocking_count"], 0)
        self.assertEqual(audit_payload["finding_count"], 0)
        self.assertEqual(audit_payload["findings"], [])

        # 4. Mutating installer actions (e.g., init) still block PACKAGE to protect source repository
        err_buf = io.StringIO()
        with contextlib.redirect_stdout(err_buf):
            rc_init = team_cli.main(["init", "--project", pkg_str])
        self.assertEqual(rc_init, 2)

    def test_socratic_interview_questions_in_prompt_expansion(self) -> None:
        from harness import route_planner

        # 1. sharpen / 구체화 mode surfaces Oracle clarifying questions in echo_markdown_ko
        brief_sharpen = route_planner.expand_prompt_brief("구체화 결제 버튼 만들어줘")
        self.assertEqual(brief_sharpen.execution_mode, "prompt-sharpen")
        self.assertEqual(brief_sharpen.ambiguity_level, "high")
        self.assertEqual(len(brief_sharpen.clarifying_questions_ko), 3)
        self.assertIn("Oracle(오라클) 사전 인터뷰 핵심 질문", brief_sharpen.echo_markdown_ko)
        self.assertTrue(any("뷰포트" in q or "버튼" in q for q in brief_sharpen.clarifying_questions_ko))

        # 2. Cleanroom RE domain questions
        brief_re = route_planner.expand_prompt_brief("re 인증 모듈 분석해줘")
        self.assertEqual(len(brief_re.clarifying_questions_ko), 3)
        self.assertTrue(any("아티팩트" in q or "golden-io.json" in q for q in brief_re.clarifying_questions_ko))

    def test_learn_rule_and_interview_compile_and_squad_worktree(self) -> None:
        from harness import mcp_server, route_planner

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # 1. [과제 2] learn-rule: register custom rule with forbidden_regex and verify prompt injection + audit-code enforcement
            learn_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_learn_rule",
                {
                    "rule": "날짜 처리에 moment.js 사용을 금지하고 dayjs만 사용할 것",
                    "forbidden_regex": r"import\s+moment\b",
                    "severity": "HIGH",
                    "apply": True,
                },
            )
            self.assertEqual(learn_res["status"], "PASS")
            self.assertEqual(learn_res["total_rules"], 1)

            brief = route_planner.expand_prompt_brief("일정 관리 모듈 구현해줘", root=root)
            self.assertTrue(any("moment.js" in c for c in brief.injected_constraints_ko))

            bad_ts = root / "src" / "calendar.ts"
            bad_ts.parent.mkdir(parents=True, exist_ok=True)
            bad_ts.write_text("import moment from 'moment';\nexport function now(): string { return ''; }\n", encoding="utf-8")
            audit_res = autopilot_engine.audit_project_code(root)
            self.assertEqual(audit_res["status"], "FAIL")
            self.assertTrue(any(f["rule_id"] == "custom-rule-001" for f in audit_res["findings"]))  # type: ignore[index]
            bad_ts.unlink()

            # 2. [과제 1] interview-compile: compile Socratic answers into PRD/TASK/TEST markdown + SDD ledger
            comp_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_interview_compile",
                {
                    "goal": "구체화 결제 버튼 만들어줘",
                    "answers": "모바일 390x844 우선 및 연타 시 비활성화; 인라인 한글 에러 문구 표시; 픽셀 오차 0.01 이하",
                    "apply": True,
                },
            )
            self.assertEqual(comp_res["status"], "PASS")
            self.assertTrue((root / "docs" / "01_PRD_REQUIREMENTS.md").is_file())
            self.assertTrue((root / "docs" / "06_TEST_PLAN.md").is_file())
            self.assertTrue((root / "docs" / "07_BACKLOG.md").is_file())
            self.assertTrue((root / "evidence" / "sdd-ledger.json").is_file())

            sdd_check_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_sdd_check",
                {"allow_doc_only": True},
            )
            self.assertEqual(sdd_check_res["status"], "PASS")
            self.assertEqual(sdd_check_res["traceability_ratio"], 1.0)

            # 3. [과제 4] squad-worktree: plan, create, and cleanup isolated parallel squad tracks
            wt_create = mcp_server.execute_mcp_tool(
                root,
                "dreampia_squad_worktree",
                {"goal": "ulw 백엔드 및 프론트 대시보드 병렬 구현", "mode": "create", "apply": True},
            )
            self.assertEqual(wt_create["status"], "PASS")
            self.assertEqual(wt_create["tracks_count"], 3)
            self.assertTrue((root / ".dreampia" / "worktrees" / "manifest.json").is_file())

            wt_clean = mcp_server.execute_mcp_tool(
                root,
                "dreampia_squad_worktree",
                {"mode": "cleanup", "apply": True},
            )
            self.assertEqual(wt_clean["status"], "PASS")
            self.assertFalse((root / ".dreampia" / "worktrees").exists())

            # 4. [다음 작업 안내] next-actions: verify state-aware recommendations and echo_markdown_ko integration (no ** or emojis)
            next_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_next_actions",
                {"goal": "구체화 결제 버튼 만들어줘"},
            )
            self.assertEqual(next_res["status"], "PASS")
            self.assertEqual(len(next_res["next_actions"]), 3)  # type: ignore[arg-type]
            self.assertIn("다음 추천 작업 가이드", str(next_res["markdown_ko"]))
            self.assertNotIn("**", str(next_res["markdown_ko"]))
            self.assertNotIn("🧭", str(next_res["markdown_ko"]))
            self.assertGreaterEqual(len(brief.recommended_next_actions_ko), 2)
            self.assertIn("다음 추천 작업 (Next Actions)", brief.echo_markdown_ko)
            self.assertNotIn("**", brief.echo_markdown_ko)
            self.assertNotIn("🧠", brief.echo_markdown_ko)
            self.assertNotIn("🧭", brief.echo_markdown_ko)

    def test_builder_review_p0_p1_p2_hardening(self) -> None:
        import json
        from harness import mcp_server, route_planner, sdd_engine, team_cli

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # 1. Unmanaged .dreampia/ application data folder collision detection & .dreampia-skill isolation
            builder_data = root / ".dreampia" / "projects"
            builder_data.mkdir(parents=True, exist_ok=True)
            (builder_data / "site-01.json").write_text("{}", encoding="utf-8")

            self.assertTrue(route_planner.has_unmanaged_dreampia_data_dir(root))
            self.assertEqual(route_planner.resolve_skill_state_dir(root), ".dreampia-skill")
            with self.assertRaises(team_cli.Conflict):
                team_cli.install(root, "init", apply=True)

            # Learned rules are stored in .dreampia-skill/memory when .dreampia/ is unmanaged
            learn_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_learn_rule",
                {"rule": "콘솔 목업 토큰 준수", "apply": True},
            )
            self.assertEqual(learn_res["status"], "PASS")
            self.assertTrue((root / ".dreampia-skill" / "memory" / "project-rules.json").is_file())

            # 2. UI rule opt-out (enforce_ui_rules: false) & audit-code --apply writing evidence/code-audit.json
            rules_path = root / ".dreampia-skill" / "memory" / "project-rules.json"
            rules_payload = json.loads(rules_path.read_text(encoding="utf-8"))
            rules_payload["enforce_ui_rules"] = False
            rules_path.write_text(json.dumps(rules_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            self.assertFalse(route_planner.is_ui_rule_enforced(root))
            brief_no_ui = route_planner.expand_prompt_brief("콘솔 버튼 컴포넌트 수정", root=root)
            self.assertNotIn("bg-transparent", brief_no_ui.expanded_prompt_ko)

            ui_file = root / "src" / "ConsoleButton.tsx"
            ui_file.parent.mkdir(parents=True, exist_ok=True)
            ui_file.write_text(
                "import { FaCheck } from 'react-icons/fa';\n"
                "export function ConsoleButton(): JSX.Element {\n"
                "  return <button className=\"mockup-btn\">확인</button>;\n"
                "}\n",
                encoding="utf-8",
            )
            audit_applied = autopilot_engine.audit_project_code(root, apply=True)
            self.assertEqual(audit_applied["status"], "PASS")
            self.assertEqual(audit_applied["ui_rules_enforced"], False)
            self.assertTrue((root / "evidence" / "code-audit.json").is_file())
            ui_file.unlink()

            # 3. SDD SPEC-* and T* task IDs + direct test file citation
            spec_dir = root / "docs"
            spec_dir.mkdir(parents=True, exist_ok=True)
            (spec_dir / "01_SPEC.md").write_text(
                "# SPEC-1207: 콘솔 배포 상태 동기화\n- 관련 작업: T1207\n",
                encoding="utf-8",
            )
            (spec_dir / "07_TASKS.md").write_text(
                "# T1207: 배포 상태 폴링 훅 구현\n- 상위 명세: SPEC-1207\n",
                encoding="utf-8",
            )
            test_dir = root / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            (test_dir / "test_deploy_sync.py").write_text(
                "def test_t1207_sync() -> None:\n"
                "    # T1207 검증\n"
                "    assert 1 + 1 == 2\n",
                encoding="utf-8",
            )
            sdd_res = sdd_engine.verify_sdd_compliance(root)
            self.assertEqual(sdd_res["status"], "PASS")
            self.assertEqual(sdd_res["traceability_ratio"], 1.0)

            # 4. MCP reconstruct-doctor blocks apply=True and MCP project root boundary locks outside paths
            mcp_doc = mcp_server.execute_mcp_tool(
                root,
                "dreampia_reconstruct_doctor",
                {"install_tool": "rizin", "apply": True},
            )
            self.assertEqual(mcp_doc["install_plan"]["applied"], False)  # type: ignore[index]
            self.assertTrue(mcp_doc.get("mcp_install_blocked"))

            with self.assertRaises(ValueError):
                mcp_server.execute_mcp_tool(
                    root,
                    "dreampia_next_actions",
                    {"project": str(root.parent), "goal": "상태 확인"},
                )

            # 5. metric-climb defaults to safe PREVIEW without executing command when apply=False
            climb_preview = autopilot_engine.run_metric_climb(
                root,
                benchmark_cmd=["python", "-c", "print('metric: 1.0')"],
                apply=False,
            )
            self.assertEqual(climb_preview["verdict"], "PREVIEW")
            self.assertEqual(climb_preview["applied"], False)

            # 6. verify_golden_io blocks unsafe imports / top-level side effects via AST validation
            spec_zone = root / "approved-spec"
            impl_zone = root / "implementation"
            spec_zone.mkdir(parents=True, exist_ok=True)
            impl_zone.mkdir(parents=True, exist_ok=True)
            (impl_zone / "unsafe_mod.py").write_text(
                "import subprocess\n"
                "def compute(x: int) -> int:\n"
                "    return x + 1\n",
                encoding="utf-8",
            )
            (spec_zone / "golden-io.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "module_path": "implementation/unsafe_mod.py",
                        "cases": [
                            {
                                "id": "G-01",
                                "function": "compute",
                                "args": [1],
                                "expected": 2,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            gio_res = autopilot_engine.verify_golden_io(root)
            self.assertEqual(gio_res["status"], "FAIL")
            self.assertEqual(gio_res["failures"][0]["id"], "UNSAFE_MODULE")  # type: ignore[index]

    def test_standard_prefix_free_operational_commands_and_release_preview(self) -> None:
        from harness import mcp_server, route_planner, team_cli

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            fake_home = Path(tmp) / "home"
            root.mkdir(parents=True, exist_ok=True)
            fake_home.mkdir(parents=True, exist_ok=True)

            # 1. version command returns version + git commit
            ver_res = team_cli.get_version_info(check_remote=False)
            self.assertEqual(ver_res["status"], "PASS")
            self.assertEqual(ver_res["version"], (team_cli.PACKAGE / "VERSION").read_text(encoding="utf-8").strip())

            # 2. config command toggles ui_rules off -> on and updates custom SDD task_pattern
            cfg_off = mcp_server.execute_mcp_tool(
                root,
                "dreampia_config",
                {
                    "ui_rules": "off",
                    "task_pattern": r"\bT\d{4}\b",
                    "apply": True,
                },
            )
            self.assertEqual(cfg_off["status"], "PASS")
            self.assertTrue(cfg_off["applied"])
            self.assertFalse(route_planner.is_ui_rule_enforced(root))

            # 3. status command reports unified project & global health
            status_res = team_cli.project_status(root, home_dir=fake_home)
            self.assertEqual(status_res["status"], "PASS")
            self.assertFalse(status_res["ui_rules_enforced"])
            self.assertIn("global_health", status_res)

            # 4. doctor with include_global checks global targets
            team_cli.setup_global(apply=True, home_dir=fake_home)
            doc_global = team_cli.doctor(team_cli.PACKAGE, include_global=True, home_dir=fake_home)
            self.assertTrue(doc_global["healthy"])
            self.assertTrue(doc_global["global_health"]["healthy"])  # type: ignore[index]

            # 5. clean command cleans up squad worktrees and interrupted journal
            mcp_server.execute_mcp_tool(
                root,
                "dreampia_squad_worktree",
                {"goal": "병렬 테스트", "mode": "create", "apply": True},
            )
            clean_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_clean",
                {"apply": True},
            )
            self.assertEqual(clean_res["status"], "PASS")
            self.assertTrue(clean_res["applied"])

            # 6. release preview validates semver and lists files to update without mutating
            rel_preview = team_cli.release_version("9.9.9", apply=False, sync_global=False)
            self.assertEqual(rel_preview["status"], "PASS")
            self.assertFalse(rel_preview["applied"])
            self.assertGreaterEqual(int(rel_preview["updated_count"]), 10)  # type: ignore[arg-type]

            # 7. All 8 prefix-free slash command markdown files exist and have no ** bold markers
            for cmd_name in ("version", "status", "doctor", "config", "update", "uninstall", "release", "clean"):
                cmd_file = team_cli.PACKAGE / "commands" / f"{cmd_name}.md"
                self.assertTrue(cmd_file.is_file(), f"Missing slash command file: {cmd_file}")
                cmd_text = cmd_file.read_text(encoding="utf-8")
                self.assertNotIn("**", cmd_text)


if __name__ == "__main__":
    unittest.main()

