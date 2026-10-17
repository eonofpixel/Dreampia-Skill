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
            (root / "package.json").write_text(
                '{"dependencies": {"tailwindcss": "^3.4.0", "lucide-react": "^0.400.0"}}\n',
                encoding="utf-8",
            )

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
            (root / "package.json").write_text(
                '{"dependencies": {"tailwindcss": "^3.4.0", "lucide-react": "^0.400.0"}}\n',
                encoding="utf-8",
            )

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

            # 7. All prefix-free slash command markdown files exist and have no ** bold markers
            for cmd_name in ("version", "status", "doctor", "config", "update", "uninstall", "release", "clean", "discover"):
                cmd_file = team_cli.PACKAGE / "commands" / f"{cmd_name}.md"
                self.assertTrue(cmd_file.is_file(), f"Missing slash command file: {cmd_file}")
                cmd_text = cmd_file.read_text(encoding="utf-8")
                self.assertNotIn("**", cmd_text)

    def test_brownfield_discover_incremental_diff_audit_and_adaptive_rigor(self) -> None:
        import subprocess
        from harness import autopilot_engine, mcp_server, route_planner, sdd_engine

        # 1. Verify Adaptive Rigor Tiers (nano / standard / full)
        nano_route = route_planner.plan_route("오타 문구 1줄 수정", repo_dirty=False)
        self.assertEqual(nano_route.rigor_tier, "nano")
        std_route = route_planner.plan_route("주문 내역 조회 API 추가", repo_dirty=False)
        self.assertEqual(std_route.rigor_tier, "standard")
        full_route = route_planner.plan_route("ulw 인증 토큰 보안 개편", repo_dirty=False)
        self.assertEqual(full_route.rigor_tier, "full")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "legacy-repo"
            root.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=False)
            subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=str(root), capture_output=True, check=False)
            subprocess.run(["git", "config", "user.name", "Dev"], cwd=str(root), capture_output=True, check=False)

            # Create legacy backend code with technical debt (missing return type + Any) and commit it
            (root / "pyproject.toml").write_text('[project]\nname = "legacy-api"\ndependencies = ["fastapi", "pytest"]\n', encoding="utf-8")
            (root / "Cargo.toml").write_text('[package]\nname = "legacy-core"\nversion = "0.1.0"\n', encoding="utf-8")
            src_dir = root / "src"
            tests_dir = root / "tests"
            src_dir.mkdir(parents=True, exist_ok=True)
            tests_dir.mkdir(parents=True, exist_ok=True)

            (src_dir / "legacy_debt.py").write_text(
                "from typing import Any\n"
                "def old_untyped_func(x) -> Any:\n"
                "    return x\n",
                encoding="utf-8",
            )
            (tests_dir / "test_legacy.py").write_text(
                "def test_basic() -> None:\n"
                "    assert 2 + 2 == 4\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=False)
            subprocess.run(["git", "commit", "-m", "initial legacy commit"], cwd=str(root), capture_output=True, check=False)

            # 2. Full repo audit catches legacy debt, but incremental (--changed-only) audit on clean new file passes!
            (src_dir / "new_clean_feature.py").write_text(
                "def calculate_discount(price: int) -> int:\n"
                "    return max(0, price - 100)\n",
                encoding="utf-8",
            )
            full_audit = autopilot_engine.audit_project_code(root, changed_only=False)
            self.assertEqual(full_audit["status"], "FAIL")

            inc_audit = autopilot_engine.audit_project_code(root, changed_only=True)
            self.assertEqual(inc_audit["status"], "PASS")
            self.assertEqual(inc_audit["audit_scope"], "changed_only")
            self.assertEqual(inc_audit["scanned_file_count"], 1)

            # 3. Adaptive Nano Tier gate passes on brownfield repo without SDD docs when changed_only=True
            nano_gate = autopilot_engine.run_autopilot_gate(
                root,
                goal="오타 문구 1줄 수정",
                changed_only=True,
                apply=False,
            )
            self.assertEqual(nano_gate["status"], "PASS")
            self.assertEqual(nano_gate["rigor_tier"], "nano")
            self.assertEqual(nano_gate["audit_scope"], "changed_only")

            # 4. Discover brownfield repo and bootstrap SDD baseline via MCP
            disc_preview = mcp_server.execute_mcp_tool(
                root,
                "dreampia_discover",
                {"bootstrap_sdd": False, "apply": False},
            )
            self.assertEqual(disc_preview["status"], "PASS")
            self.assertEqual(disc_preview["project_mode"], "brownfield")
            self.assertIn("python", disc_preview["languages"])  # type: ignore[operator]
            self.assertIn("rust", disc_preview["languages"])  # type: ignore[operator]
            self.assertFalse(disc_preview["ui_stack_detected"])

            disc_apply = mcp_server.execute_mcp_tool(
                root,
                "dreampia_discover",
                {"bootstrap_sdd": True, "apply": True},
            )
            self.assertEqual(disc_apply["status"], "PASS")
            self.assertTrue(disc_apply["sdd_bootstrapped"])
            self.assertEqual(disc_apply["project_mode"], "sdd-ready")
            self.assertTrue((root / ".dreampia/memory/project-profile.json").is_file())
            self.assertTrue((root / ".dreampia/memory/brownfield-baseline.md").is_file())
            self.assertFalse(route_planner.is_ui_rule_enforced(root))

            sdd_after = sdd_engine.verify_sdd_compliance(root)
            self.assertEqual(sdd_after["status"], "PASS")
            self.assertEqual(sdd_after["traceability_ratio"], 1.0)

    def test_universal_oss_hardening_six_pillars(self) -> None:
        import json
        import subprocess
        from harness import autopilot_engine, route_planner, team_cli

        for required_dir in ("build", "dist", "out", "target", "vendor", "third_party", ".venv", "venv", "coverage", ".turbo", ".cache", ".omo"):
            self.assertIn(required_dir, autopilot_engine._IGNORED_DIRS)
        for required_ext in (".mjs", ".cjs", ".cpp", ".hpp", ".c", ".cs", ".swift"):
            self.assertIn(required_ext, autopilot_engine._AUDIT_EXTENSIONS)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "trc-daw-hybrid"
            root.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=False)
            subprocess.run(["git", "config", "user.email", "daw@example.com"], cwd=str(root), capture_output=True, check=False)
            subprocess.run(["git", "config", "user.name", "DAW Dev"], cwd=str(root), capture_output=True, check=False)

            # Pillar 1: Git-aware file scan respects .gitignore and _IGNORED_DIRS (build/, custom_ignored/)
            (root / ".gitignore").write_text("custom_ignored/\nbuild/\n", encoding="utf-8")
            (root / "build").mkdir(parents=True, exist_ok=True)
            (root / "build" / "bundle_bad.ts").write_text("export const x: any = 1;\n", encoding="utf-8")
            (root / "custom_ignored").mkdir(parents=True, exist_ok=True)
            (root / "custom_ignored" / "generated_bad.py").write_text("def bad(x):\n    return x\n", encoding="utf-8")

            # Pillar 3: Repo-local rules (CLAUDE.md, AGENTS.md) precedence and split language policy
            (root / "CLAUDE.md").write_text(
                "# Repo Rules\n- Conversation in Korean, code identifiers and comments in English.\n",
                encoding="utf-8",
            )
            (root / "AGENTS.md").write_text("# Agents Guide (see CLAUDE.md)\n", encoding="utf-8")

            # Pillar 5: Hybrid native / polyglot layout (native/windows/package.json, CMakeLists.txt, Makefile, .csproj, Package.swift, tools/*.mjs)
            (root / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\nproject(TrcAudioEngine)\n", encoding="utf-8")
            native_dir = root / "native"
            native_win_dir = native_dir / "windows"
            native_win_dir.mkdir(parents=True, exist_ok=True)
            (native_dir / "Makefile").write_text("all:\n\t@echo build\n", encoding="utf-8")
            (native_dir / "AudioHost.csproj").write_text("<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n", encoding="utf-8")
            (root / "Package.swift").write_text("// swift-tools-version:5.9\n", encoding="utf-8")
            (native_win_dir / "package.json").write_text(
                json.dumps(
                    {
                        "name": "trc-daw-win-shell",
                        "scripts": {"test": "node ../../tools/run-tests.mjs"},
                        "dependencies": {"electron": "^30.0.0"},
                    }
                ),
                encoding="utf-8",
            )
            tools_dir = root / "tools"
            tools_dir.mkdir(parents=True, exist_ok=True)
            (tools_dir / "run-tests.mjs").write_text("export function runSuite() { return true; }\n", encoding="utf-8")

            # Legacy file with `: any` committed in brownfield Git repo
            src_dir = root / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "legacy_mixer.ts").write_text(
                "export function legacyMix(channel: any): number {\n  return 0;\n}\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=False)
            subprocess.run(["git", "commit", "-m", "initial brownfield commit"], cwd=str(root), capture_output=True, check=False)

            # Verify Pillar 1: _iter_auditable_files excludes build/ and .gitignore'd custom_ignored/
            auditable_rels = [p.relative_to(root).as_posix() for p in autopilot_engine._iter_auditable_files(root)]
            self.assertNotIn("build/bundle_bad.ts", auditable_rels)
            self.assertNotIn("custom_ignored/generated_bad.py", auditable_rels)
            self.assertIn("tools/run-tests.mjs", auditable_rels)

            # Verify Pillar 2: Without Tailwind/Lucide, is_ui_rule_enforced is False by default (no false positives on standard <button>)
            self.assertFalse(route_planner.is_ui_rule_enforced(root))
            ui_caps = route_planner.detect_ui_rule_capabilities(root)
            self.assertFalse(ui_caps["has_tailwind"])
            self.assertFalse(ui_caps["has_lucide_react"])

            # Verify Pillar 3: expand_prompt & build_execution_manifest include Repo-Local Rules Take Precedence clause
            brief = route_planner.expand_prompt("오디오 트랙 솔로 버튼 추가해줘", root=root)
            self.assertIn("CLAUDE.md", brief.repo_rule_files)
            self.assertEqual(brief.chat_language, "ko")
            self.assertEqual(brief.code_identifier_policy, "repo-convention")
            self.assertIn("Repo-Local Rules Take Precedence", brief.expanded_prompt_ko)
            self.assertNotIn("bg-transparent", brief.expanded_prompt_ko)
            manifest = route_planner.build_execution_manifest("오디오 트랙 솔로 버튼 추가해줘", root=root)
            self.assertIn("CLAUDE.md", manifest["repo_rule_files"])  # type: ignore[operator]

            # Verify Pillar 4: Modify/add a clean file in brownfield Git repo -> audit_project_code & evaluate_autopilot_gate pass by default (changed_only=True)
            (src_dir / "solo_button.tsx").write_text(
                "import { FaPlay } from 'react-icons/fa';\n"
                "export interface SoloProps { label: string; }\n"
                "export function SoloButton(props: SoloProps): JSX.Element {\n"
                "  return <button className=\"daw-btn\">{props.label}</button>;\n"
                "}\n",
                encoding="utf-8",
            )
            inc_audit = autopilot_engine.audit_project_code(root)
            self.assertEqual(inc_audit["status"], "PASS")
            self.assertEqual(inc_audit["audit_scope"], "changed_only")
            self.assertEqual(inc_audit["scanned_file_count"], 1)

            gate_res = autopilot_engine.evaluate_autopilot_gate(root)
            self.assertEqual(gate_res["status"], "PASS")
            self.assertEqual(gate_res["audit_scope"], "changed_only")

            # When --all (force_all=True) is requested, legacy_mixer.ts with `any` is scanned and fails
            all_audit = autopilot_engine.audit_project_code(root, force_all=True)
            self.assertEqual(all_audit["status"], "FAIL")
            self.assertEqual(all_audit["audit_scope"], "full")

            # Commit solo_button.tsx so working tree is clean before testing Pillar 5 & Pillar 6
            subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=False)
            subprocess.run(["git", "commit", "-m", "add clean solo button"], cwd=str(root), capture_output=True, check=False)

            # Verify Pillar 5 & Pillar 6: discover_project detects hybrid stacks/subpackages and keeps git status --porcelain 100% clean via .git/info/exclude
            disc_res = autopilot_engine.discover_project(root, apply=True)
            self.assertEqual(disc_res["status"], "PASS")
            self.assertIn("cpp", disc_res["stacks"])  # type: ignore[operator]
            self.assertIn("csharp", disc_res["stacks"])  # type: ignore[operator]
            self.assertIn("swift", disc_res["stacks"])  # type: ignore[operator]
            self.assertIn("native/windows/package.json", disc_res["manifests_found"])  # type: ignore[operator]
            self.assertTrue((root / ".dreampia/memory/discovered-project.json").is_file())

            # Also create .dreampia-workflow/ and .harness/ state files and verify git status --porcelain is empty
            (root / ".dreampia-workflow").mkdir(parents=True, exist_ok=True)
            (root / ".dreampia-workflow" / "state.json").write_text("{}\n", encoding="utf-8")
            (root / ".harness").mkdir(parents=True, exist_ok=True)
            (root / ".harness" / "session.json").write_text("{}\n", encoding="utf-8")
            autopilot_engine.ensure_local_git_exclude(root)

            exclude_text = (root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
            self.assertIn(".dreampia-workflow/", exclude_text)
            self.assertIn(".harness/", exclude_text)

            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(status_proc.stdout.strip(), "")
            self.assertEqual(team_cli.main(["audit-code", "--project", str(root), "--all"]), 1)


if __name__ == "__main__":
    unittest.main()


