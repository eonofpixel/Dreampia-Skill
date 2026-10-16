"""Dreampia Autonomous Engineering OS Engine: Trinity Code Auditor, Context Pack Compiler, Golden I/O Verifier, and Unified Autopilot Gate.

Completes the 4 architectural pillars:
1. TrinityCodeAuditor (audit_project_code): AST & regex static auditor catching hollow TDD tests (assert True / empty tests) and enforcing SOLID/type-safety/UI rules.
2. ContextPackCompiler (compile_context_pack): Compiles active SDD requirements, ADR/RISK invariants, and current blockers into a <1,000-token anti-amnesia briefing packet.
3. GoldenIoVerifier (verify_golden_io): Black-box behavioral equivalence verifier testing cleanroom implementations against pure input/output vectors in approved-spec/golden-io.json.
4. UnifiedAutopilotGate (run_autopilot_gate): Morpheus + Tank atomic gate pipeline chaining instruction drift, SDD traceability, Trinity code audit, cleanroom coverage, and Golden I/O checks.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re

try:
    from . import reconstruct_engine, route_planner, sdd_engine, visual_acceptance, write_boundary
except ImportError:
    import reconstruct_engine  # type: ignore[no-redef]
    import route_planner  # type: ignore[no-redef]
    import sdd_engine  # type: ignore[no-redef]
    import visual_acceptance  # type: ignore[no-redef]
    import write_boundary  # type: ignore[no-redef]

AUTOPILOT_VERSION = "0.6.1"
DEFAULT_CONTEXT_PACK_REL = "evidence/context-pack.json"
DEFAULT_AUTOPILOT_VERDICT_REL = "evidence/autopilot-verdict.json"
DEFAULT_CODE_AUDIT_REL = "evidence/code-audit.json"
DEFAULT_GOLDEN_IO_REL = "approved-spec/golden-io.json"

_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".harness",
        ".dreampia-install",
        ".dreampia",
        ".dreampia-skill",
        ".agents",
        ".claude",
        ".gemini",
        ".qwen",
        ".workflow",
        ".dreampia-workflow",
        "__pycache__",
        "node_modules",
        ".next",
        "evidence",
        "contaminated-zone",
    }
)

_TS_ANY_RE = re.compile(r"(:\s*any\b|<any>|\bas\s+any\b)")
_TS_HOLLOW_TEST_RE = re.compile(r"expect\s*\(\s*true\s*\)\s*\.\s*toBe\s*\(\s*true\s*\)")
_FORBIDDEN_ICON_RE = re.compile(
    r"""from\s+['"](@heroicons/[^'"]+|react-icons[^'"]*|@mui/icons-material[^'"]*|@fortawesome/[^'"]+)['"]"""
)
_BUTTON_TAG_RE = re.compile(r"<button\b([^>]*)>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class AuditFinding:
    """Trinity(트리니티) 정적 코드·규칙·TDD 감사 결과 항목."""

    severity: str
    rule_id: str
    evidence: str
    issue_ko: str
    fix_ko: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "rule_id": self.rule_id,
            "evidence": self.evidence,
            "issue": self.issue_ko,
            "fix": self.fix_ko,
        }


def _iter_auditable_files(root: Path) -> list[Path]:
    resolved = root.resolve()
    files: list[Path] = []
    for current_root, dirs, filenames in os.walk(resolved, topdown=True, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in _IGNORED_DIRS and not (Path(current_root) / d).is_symlink())
        for fname in sorted(filenames):
            fpath = Path(current_root) / fname
            if not fpath.is_symlink() and fpath.is_file():
                files.append(fpath)
    return files


def _has_real_assertion_in_py_func(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, int | None]:
    """Python 테스트 함수 내부에 유효한 assertion이 있는지, 또는 `assert True` 같은 가짜 테스트인지 검사한다."""
    has_assertion = False
    tautology_line: int | None = None

    for node in ast.walk(func_node):
        if isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                tautology_line = node.lineno
            else:
                has_assertion = True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and (
                func.attr.startswith("assert") or func.attr in ("fail", "raises", "reject")
            ):
                has_assertion = True
            elif isinstance(func, ast.Name) and func.id.startswith("assert"):
                has_assertion = True

    return has_assertion, tautology_line


DEFAULT_PROJECT_RULES_REL = ".dreampia/memory/project-rules.json"


def _resolve_project_rules_rel(root: Path) -> str:
    state_dir = route_planner.resolve_skill_state_dir(root)
    return f"{state_dir}/memory/project-rules.json"


def load_project_rules(root: Path) -> list[dict[str, object]]:
    """프로젝트 메모리(.dreampia/memory/project-rules.json 또는 .dreampia-skill/memory/project-rules.json)에 저장된 자가 학습 규칙 목록을 로드한다."""
    if root.is_symlink() or not root.is_dir():
        return []
    resolved = root.resolve()
    rel = _resolve_project_rules_rel(resolved)
    rules_path = resolved / rel
    if not rules_path.is_file() and rel != DEFAULT_PROJECT_RULES_REL:
        rules_path = resolved / DEFAULT_PROJECT_RULES_REL
    if rules_path.is_symlink() or not rules_path.is_file():
        return []
    try:
        raw = json.loads(rules_path.read_text(encoding="utf-8"))
        items = raw.get("rules", []) if isinstance(raw, dict) else []
        return [dict(item) for item in items if isinstance(item, dict) and item.get("rule_ko")]
    except (OSError, ValueError, TypeError):
        return []


def learn_project_rule(
    root: Path,
    rule_ko: str,
    *,
    forbidden_regex: str = "",
    severity: str = "HIGH",
    apply: bool = True,
) -> dict[str, object]:
    """사용자 피드백이나 팀 컨벤션을 프로젝트 자가 학습 메모리(.dreampia/memory/project-rules.json)에 영구 등록한다."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    cleaned_rule = " ".join(rule_ko.strip().split())
    if not cleaned_rule:
        raise ValueError("학습할 프로젝트 규칙 내용(rule_ko)을 한글로 입력해 주십시오.")

    cleaned_regex = forbidden_regex.strip()
    if cleaned_regex:
        try:
            re.compile(cleaned_regex)
        except re.error as exc:
            raise ValueError(f"유효하지 않은 금지 정규식(forbidden_regex)입니다: {exc}") from exc

    norm_sev = severity.strip().upper()
    if norm_sev not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        norm_sev = "HIGH"

    resolved = root.resolve()
    rules_rel = _resolve_project_rules_rel(resolved)
    rules = load_project_rules(resolved)
    existing_idx: int | None = None
    for idx, item in enumerate(rules):
        if str(item.get("rule_ko") or "") == cleaned_rule:
            existing_idx = idx
            break

    rule_id = (
        str(rules[existing_idx].get("rule_id"))
        if existing_idx is not None
        else f"custom-rule-{len(rules) + 1:03d}"
    )
    entry: dict[str, object] = {
        "rule_id": rule_id,
        "rule_ko": cleaned_rule,
        "forbidden_regex": cleaned_regex,
        "severity": norm_sev,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if existing_idx is not None:
        rules[existing_idx] = entry
    else:
        rules.append(entry)

    if apply:
        rules_path = resolved / rules_rel
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "schema_version": 1,
            "engine_version": AUTOPILOT_VERSION,
            "rules_count": len(rules),
            "rules": rules,
        }
        rules_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "action": "learn-rule",
        "status": "PASS",
        "applied": apply,
        "rules_path": rules_rel if apply else None,
        "learned_rule": entry,
        "total_rules": len(rules),
        "rules": rules,
        "message_ko": (
            f"프로젝트 자가 학습 규칙('{rule_id}: {cleaned_rule}')이 메모리에 등록되었습니다. 이후 프롬프트 고도화 및 정적 코드 감사(audit-code)에 자동 반영됩니다."
            if apply
            else f"[미리보기] 프로젝트 자가 학습 규칙('{rule_id}: {cleaned_rule}') 등록 계획입니다. 실제 저장하려면 --apply를 추가하십시오."
        ),
    }


def audit_project_code(
    root: Path,
    *,
    check_return_types: bool = True,
    check_ui_rules: bool | None = None,
    apply: bool = False,
) -> dict[str, object]:
    """Trinity(트리니티) 정적 감사기: 가짜 TDD 테스트(assert True/빈 테스트), any 타입, 반환 타입 누락, UI 아이콘/버튼 규칙 및 자가 학습 규칙을 검사한다."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    eff_ui_rules = route_planner.is_ui_rule_enforced(resolved) if check_ui_rules is None else bool(check_ui_rules)
    findings: list[AuditFinding] = []
    scanned_files: list[str] = []
    learned_rules = load_project_rules(resolved)
    compiled_custom_rules: list[tuple[dict[str, object], re.Pattern[str]]] = []
    for r_item in learned_rules:
        pat_str = str(r_item.get("forbidden_regex") or "").strip()
        if pat_str:
            try:
                compiled_custom_rules.append((r_item, re.compile(pat_str)))
            except re.error:
                continue

    for fpath in _iter_auditable_files(resolved):
        rel = fpath.relative_to(resolved).as_posix()
        suffix = fpath.suffix.lower()
        if suffix not in (".py", ".ts", ".tsx", ".js", ".jsx"):
            continue
        scanned_files.append(rel)
        text = fpath.read_text(encoding="utf-8", errors="replace")
        is_test_file = (
            fpath.name.startswith("test_")
            or fpath.name.endswith("_test.py")
            or ".test." in fpath.name
            or ".spec." in fpath.name
            or "tests" in PurePosixPath(rel).parts
        )

        if suffix == ".py":
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError as exc:
                findings.append(
                    AuditFinding(
                        severity="CRITICAL",
                        rule_id="python-syntax-error",
                        evidence=f"{rel}:{exc.lineno or 1}",
                        issue_ko="파이썬 문법 오류가 존재합니다.",
                        fix_ko="구문 오류를 먼저 수정한 뒤 다시 검증하십시오.",
                    )
                )
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if is_test_file and node.name.startswith("test_"):
                        has_assert, taut_line = _has_real_assertion_in_py_func(node)
                        if taut_line is not None:
                            findings.append(
                                AuditFinding(
                                    severity="HIGH",
                                    rule_id="hollow-tdd-assert-true",
                                    evidence=f"{rel}:{taut_line}",
                                    issue_ko=f"테스트 함수 '{node.name}'에 항상 참인 가짜 단언문(assert True)이 포함되어 있습니다.",
                                    fix_ko="실제 함수 호출 결과와 기대값을 비교하는 단언문(assert actual == expected)으로 교체하십시오.",
                                )
                            )
                        elif not has_assert:
                            findings.append(
                                AuditFinding(
                                    severity="HIGH",
                                    rule_id="hollow-tdd-no-assertion",
                                    evidence=f"{rel}:{node.lineno}",
                                    issue_ko=f"테스트 함수 '{node.name}'에 실제 검증 단언문(assertion)이 없습니다.",
                                    fix_ko="정상·거부·경계 조건을 실제로 검증하는 assertion을 추가하십시오.",
                                )
                            )
                    elif (
                        check_return_types
                        and not is_test_file
                        and not node.name.startswith("_")
                        and node.returns is None
                    ):
                        findings.append(
                            AuditFinding(
                                severity="MEDIUM",
                                rule_id="missing-return-type",
                                evidence=f"{rel}:{node.lineno}",
                                issue_ko=f"공개 함수 '{node.name}'에 반환 타입(Return Type) 어노테이션이 명시되지 않았습니다.",
                                fix_ko="타입 안전성 규칙에 따라 모든 공개 함수에 명시적 반환 타입(-> Type)을 선언하십시오.",
                            )
                        )
                    if node.returns is not None and isinstance(node.returns, ast.Name) and node.returns.id == "Any":
                        findings.append(
                            AuditFinding(
                                severity="HIGH",
                                rule_id="forbidden-any-type",
                                evidence=f"{rel}:{node.lineno}",
                                issue_ko=f"함수 '{node.name}'의 반환 타입에 금지된 'Any' 타입이 사용되었습니다.",
                                fix_ko="구체적인 타입, TypedDict, dataclass 또는 프로토콜을 사용하십시오.",
                            )
                        )
                elif isinstance(node, ast.ExceptHandler):
                    if node.type is None and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        findings.append(
                            AuditFinding(
                                severity="HIGH",
                                rule_id="slop-bare-except-pass",
                                evidence=f"{rel}:{node.lineno}",
                                issue_ko="예외 타입 지정 없이 모든 오류를 묵살하는 AI 슬롭 패턴(bare except: pass)이 감지되었습니다.",
                                fix_ko="구체적인 예외 타입을 명시하고 사용자 친화적인 한글 오류 처리 또는 명시적 복구 로직을 작성하십시오.",
                            )
                        )

        elif suffix in (".ts", ".tsx", ".js", ".jsx"):
            lines = text.splitlines()
            for idx, line in enumerate(lines, start=1):
                if suffix in (".ts", ".tsx") and _TS_ANY_RE.search(line):
                    findings.append(
                        AuditFinding(
                            severity="HIGH",
                            rule_id="forbidden-any-type",
                            evidence=f"{rel}:{idx}",
                            issue_ko="TypeScript 코드에 금지된 'any' 타입이 사용되었습니다.",
                            fix_ko="명시적 인터페이스(Props/Contract) 또는 구체적인 유니온/제네릭 타입으로 교체하십시오.",
                        )
                    )
                if is_test_file and _TS_HOLLOW_TEST_RE.search(line):
                    findings.append(
                        AuditFinding(
                            severity="HIGH",
                            rule_id="hollow-tdd-assert-true",
                            evidence=f"{rel}:{idx}",
                            issue_ko="가짜 테스트 단언문(expect(true).toBe(true))이 감지되었습니다.",
                            fix_ko="실제 컴포넌트/함수 동작을 검증하는 단언문으로 교체하십시오.",
                        )
                    )
                if eff_ui_rules and _FORBIDDEN_ICON_RE.search(line):
                    findings.append(
                        AuditFinding(
                            severity="MEDIUM",
                            rule_id="forbidden-icon-library",
                            evidence=f"{rel}:{idx}",
                            issue_ko="허용되지 않은 외부 아이콘 라이브러리가 사용되었습니다.",
                            fix_ko="아이콘 라이브러리 통일 규칙에 따라 'lucide-react'만 사용하십시오.",
                        )
                    )

            if eff_ui_rules and suffix in (".tsx", ".jsx"):
                for match in _BUTTON_TAG_RE.finditer(text):
                    attrs = match.group(1)
                    if "className" in attrs and "bg-transparent" not in attrs:
                        line_no = text[: match.start()].count("\n") + 1
                        findings.append(
                            AuditFinding(
                                severity="LOW",
                                rule_id="button-bg-transparent-missing",
                                evidence=f"{rel}:{line_no}",
                                issue_ko="<button> 요소의 className에 기본 'bg-transparent' 스타일이 누락되었습니다.",
                                fix_ko="버튼 기본 스타일 규칙에 따라 'bg-transparent' 및 hover/focus 상태를 포함하십시오.",
                            )
                        )

        if not is_test_file:
            for custom_rule, custom_re in compiled_custom_rules:
                c_match = custom_re.search(text)
                if c_match:
                    line_no = text[: c_match.start()].count("\n") + 1
                    rule_desc = str(custom_rule.get("rule_ko") or "")
                    findings.append(
                        AuditFinding(
                            severity=str(custom_rule.get("severity") or "HIGH"),
                            rule_id=str(custom_rule.get("rule_id") or "custom-learned-rule"),
                            evidence=f"{rel}:{line_no}",
                            issue_ko=f"프로젝트 자가 학습 규칙 위반: {rule_desc}",
                            fix_ko=f"프로젝트 메모리에 등록된 규칙('{rule_desc}')을 준수하십시오.",
                        )
                    )

    blocking = [f for f in findings if f.severity in ("CRITICAL", "HIGH")]
    passed = len(blocking) == 0
    payload: dict[str, object] = {
        "status": "PASS" if passed else "FAIL",
        "auditor": "Trinity (reviewer)",
        "applied": apply,
        "report_path": DEFAULT_CODE_AUDIT_REL if apply else None,
        "ui_rules_enforced": eff_ui_rules,
        "scanned_file_count": len(scanned_files),
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "learned_rule_count": len(learned_rules),
        "findings": [f.to_dict() for f in findings],
        "message_ko": (
            f"Trinity 코드·TDD·규칙 정적 감사를 통과했습니다. (검사 파일 {len(scanned_files)}개, 차단 결함 0건)"
            if passed
            else f"Trinity 감사에서 차단 결함 {len(blocking)}건(전체 {len(findings)}건)이 발견되었습니다."
        ),
    }
    if apply:
        audit_out = resolved / DEFAULT_CODE_AUDIT_REL
        audit_out.parent.mkdir(parents=True, exist_ok=True)
        audit_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


_FORBIDDEN_GOLDEN_MODULES: frozenset[str] = frozenset(
    {"subprocess", "shutil", "socket", "ctypes", "pty", "multiprocessing", "urllib", "http"}
)
_FORBIDDEN_GOLDEN_CALLS: frozenset[str] = frozenset(
    {"eval", "exec", "compile", "__import__", "system", "popen", "spawnl", "spawnv"}
)


def _validate_golden_target_ast(mod_file: Path) -> str | None:
    """Golden I/O 검증 대상 파이썬 모듈을 로드하기 전, 최상위 부작용(Top-Level Execution)이나 시스템 명령 호출이 없는지 정적으로 검증한다."""
    try:
        src = mod_file.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(mod_file))
    except (OSError, SyntaxError) as exc:
        return f"syntax-or-read-error:{type(exc).__name__}"

    allowed_top = (
        ast.Import,
        ast.ImportFrom,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Assign,
        ast.AnnAssign,
    )
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        if type(stmt).__name__ == "TypeAlias":
            continue
        if not isinstance(stmt, allowed_top):
            return f"top-level-side-effect-blocked:{type(stmt).__name__}"
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and any(isinstance(n, ast.Call) for n in ast.walk(stmt)):
            return "top-level-call-in-assignment-blocked"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_mod = alias.name.split(".")[0]
                if top_mod in _FORBIDDEN_GOLDEN_MODULES:
                    return f"forbidden-import:{top_mod}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_mod = node.module.split(".")[0]
            if top_mod in _FORBIDDEN_GOLDEN_MODULES:
                return f"forbidden-import:{top_mod}"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_GOLDEN_CALLS:
                return f"forbidden-call:{node.func.id}"
            if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_GOLDEN_CALLS:
                return f"forbidden-call:{node.func.attr}"
    return None


def verify_golden_io(
    root: Path,
    golden_rel: str = DEFAULT_GOLDEN_IO_REL,
) -> dict[str, object]:
    """Keymaker & Tank 블랙박스 입출력 동등성(Golden I/O) 검증기."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    pure = PurePosixPath(golden_rel.strip())
    if pure.is_absolute() or any(p in ("", ".", "..") for p in pure.parts):
        raise ValueError("유효하지 않은 Golden I/O 명세 경로입니다.")
    golden_path = resolved.joinpath(*pure.parts)
    if not golden_path.is_file():
        return {
            "status": "NOT_RUN",
            "golden_path": pure.as_posix(),
            "case_count": 0,
            "passed_count": 0,
            "failures": [],
            "message_ko": "Golden I/O 명세 파일이 없어 입출력 동등성 검증을 건너뛰었습니다.",
        }

    spec_doc = json.loads(golden_path.read_text(encoding="utf-8"))
    mod_rel = str(spec_doc.get("module_path") or "implementation/reconstructed_service.py").strip()
    mod_pure = PurePosixPath(mod_rel)
    if (
        mod_pure.is_absolute()
        or any(p in ("", ".", "..") or p == "contaminated-zone" for p in mod_pure.parts)
        or mod_pure.parts[0] not in ("implementation", "src", "app")
    ):
        raise ValueError("Golden I/O 대상 모듈 경로는 클린룸 구현 영역(implementation/, src/, app/) 내부여야 합니다.")
    mod_file = resolved.joinpath(*mod_pure.parts)
    if spec_doc.get("template_only") is True and not mod_file.is_file():
        return {
            "status": "NOT_RUN",
            "golden_path": pure.as_posix(),
            "module_path": mod_pure.as_posix(),
            "case_count": 0,
            "passed_count": 0,
            "failures": [],
            "message_ko": "Golden I/O 명세가 초안 템플릿(template_only) 상태이며 기본 대상 모듈이 없어 건너뜁니다.",
        }
    if not mod_file.is_file():
        return {
            "status": "FAIL",
            "golden_path": pure.as_posix(),
            "module_path": mod_pure.as_posix(),
            "case_count": 0,
            "passed_count": 0,
            "failures": [{"id": "MODULE_LOAD", "reason": f"구현 모듈을 찾을 수 없습니다: {mod_pure.as_posix()}"}],
            "message_ko": "Golden I/O 검증 대상 구현 모듈이 존재하지 않습니다.",
        }

    ast_violation = _validate_golden_target_ast(mod_file)
    if ast_violation is not None:
        return {
            "status": "FAIL",
            "golden_path": pure.as_posix(),
            "module_path": mod_pure.as_posix(),
            "case_count": 0,
            "passed_count": 0,
            "failures": [{"id": "UNSAFE_MODULE", "reason": ast_violation}],
            "message_ko": f"Golden I/O 대상 모듈에서 허용되지 않는 최상위 실행 코드 또는 시스템 호출이 감지되어 차단되었습니다: {ast_violation}",
        }

    spec = importlib.util.spec_from_file_location("_dreampia_golden_target", mod_file)
    if spec is None or spec.loader is None:
        raise ValueError("Golden I/O 모듈 로더를 초기화할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    cases_raw = spec_doc.get("cases", [])
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ValueError("Golden I/O 명세에 최소 1개 이상의 cases 항목이 필요합니다.")

    passed_count = 0
    failures: list[dict[str, object]] = []
    for idx, case in enumerate(cases_raw, start=1):
        if not isinstance(case, dict):
            continue
        cid = str(case.get("id") or f"G-{idx:03d}")
        fn_name = str(case.get("function") or "")
        args = list(case.get("args") or []) if isinstance(case.get("args"), list) else []
        kwargs = dict(case.get("kwargs") or {}) if isinstance(case.get("kwargs"), dict) else {}
        expected = case.get("expected")

        target_fn = getattr(module, fn_name, None)
        if not callable(target_fn):
            failures.append({"id": cid, "function": fn_name, "reason": "function-not-found"})
            continue
        try:
            actual = target_fn(*args, **kwargs)
            if actual == expected:
                passed_count += 1
            else:
                failures.append(
                    {
                        "id": cid,
                        "function": fn_name,
                        "expected": expected,
                        "actual": actual,
                        "reason": "output-mismatch",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            failures.append({"id": cid, "function": fn_name, "reason": f"exception:{type(exc).__name__}"})

    passed = len(failures) == 0 and passed_count == len(cases_raw)
    return {
        "status": "PASS" if passed else "FAIL",
        "golden_path": pure.as_posix(),
        "module_path": mod_pure.as_posix(),
        "case_count": len(cases_raw),
        "passed_count": passed_count,
        "failures": failures,
        "message_ko": (
            f"Golden I/O 블랙박스 입출력 동등성 검증 100% 통과 ({passed_count}/{len(cases_raw)} 케이스)"
            if passed
            else f"Golden I/O 불일치 발생: {len(failures)}개 케이스 실패"
        ),
    }


def compile_context_pack(
    root: Path,
    goal: str = "",
    *,
    apply: bool = False,
) -> dict[str, object]:
    """세션 전환·장기 실행 시 기억 상실(Context Amnesia)을 방지하는 초고밀도 컨텍스트 브리핑 패킷을 컴파일한다."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    eff_goal = goal.strip() or "현재 프로젝트 다음 수직 기능 구현 및 검증"
    route_dec = route_planner.plan_route(eff_goal, root=resolved).to_dict()
    sdd_res = sdd_engine.verify_sdd_compliance(resolved, require_tdd_files=False)
    scan = sdd_engine.scan_project_specs(resolved)
    items: dict[str, sdd_engine.SpecItem] = scan["items"]  # type: ignore[assignment]

    invariants: list[dict[str, str]] = []
    next_tasks: list[dict[str, object]] = []
    active_requirements: list[dict[str, object]] = []

    for item_id in sorted(items):
        item = items[item_id]
        if item.kind in ("decision", "risk"):
            invariants.append({"id": item.item_id, "kind": item.kind, "statement": item.statement})
        elif item.kind == "task" and item.verdict != "PASS":
            next_tasks.append(
                {
                    "id": item.item_id,
                    "status": item.status,
                    "verdict": item.verdict,
                    "statement": item.statement,
                    "linked_ids": list(item.linked_ids),
                }
            )
        elif item.kind == "requirement" and item.verdict != "PASS":
            active_requirements.append(
                {
                    "id": item.item_id,
                    "status": item.status,
                    "verdict": item.verdict,
                    "statement": item.statement,
                    "linked_ids": list(item.linked_ids),
                }
            )

    drift = write_boundary.check_instruction_drift(resolved)
    pack: dict[str, object] = {
        "schema_version": AUTOPILOT_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "goal": eff_goal,
        "commander": route_dec["commander"],
        "profile": route_dec["profile"],
        "agent_squad": route_dec["agent_squad"],
        "sdd_traceability": {
            "status": sdd_res["status"],
            "traceability_ratio": sdd_res["traceability_ratio"],
            "blockers": sdd_res["blockers"],
        },
        "instruction_health": {
            "status": drift["status"],
            "drift_detected": drift["drift_detected"],
        },
        "invariants_and_risks": invariants[:10],
        "active_requirements": active_requirements[:10],
        "next_actionable_tasks": next_tasks[:5],
        "anti_amnesia_rules_ko": [
            "1. 과거 PASS 증거를 코드 수정 후 재실행 없이 현재 PASS로 재사용하지 마십시오.",
            "2. 모든 공개 함수에 반환 타입을 명시하고 any 타입을 절대 사용하지 마십시오.",
            "3. 테스트 함수에 assert True 같은 가짜 단언문을 작성하지 마십시오 (Trinity 감사기가 즉시 차단합니다).",
            "4. 클린룸 프로파일에서는 contaminated-zone 파일을 구현 코드에 직접 복사하지 마십시오.",
        ],
    }

    if apply:
        out_path = resolved / DEFAULT_CONTEXT_PACK_REL
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "action": "context-pack",
        "status": "PASS",
        "applied": apply,
        "context_pack_path": DEFAULT_CONTEXT_PACK_REL if apply else None,
        **pack,
    }


def run_autopilot_gate(
    root: Path,
    goal: str = "",
    *,
    allow_doc_only: bool = False,
    apply: bool = False,
) -> dict[str, object]:
    """Morpheus & Tank 단일 오토파일럿 통합 게이트: 프로파일에 맞춰 지침·SDD·코드감사·클린룸·Golden I/O를 원자적으로 연쇄 검증한다."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    eff_goal = goal.strip() or "프로젝트 기능 구현 및 품질 게이트 통합 검증"
    decision = route_planner.plan_route(eff_goal, root=resolved)

    stages: list[dict[str, object]] = []

    # Stage 1: Instruction Drift Check
    inst_res = write_boundary.check_instruction_drift(resolved)
    stages.append(
        {
            "stage": "instruction-drift",
            "owner": "Seraph (privacy-guard)",
            "status": inst_res["status"],
            "detail": inst_res["message_ko"],
        }
    )

    # Stage 2: SDD + TDD Traceability Check
    saved_sdd: dict[str, object] | None = None
    sdd_ledger_file = resolved / sdd_engine.DEFAULT_SDD_LEDGER_REL
    if sdd_ledger_file.is_file():
        try:
            saved_sdd = json.loads(sdd_ledger_file.read_text(encoding="utf-8"))
        except ValueError:
            saved_sdd = None
    sdd_res = sdd_engine.verify_sdd_compliance(
        resolved,
        saved_ledger=saved_sdd,
        require_tdd_files=not allow_doc_only,
    )
    stages.append(
        {
            "stage": "sdd-tdd-traceability",
            "owner": "Oracle (planner) & Tank (verifier)",
            "status": "PASS" if sdd_res["status"] == "PASS" else "FAIL",
            "traceability_ratio": sdd_res["traceability_ratio"],
            "blockers": sdd_res["blockers"],
            "detail": sdd_res["message_ko"],
        }
    )

    # Stage 3: Trinity Code & Hollow-TDD Static Audit
    if not allow_doc_only:
        audit_res = audit_project_code(resolved)
        stages.append(
            {
                "stage": "trinity-code-audit",
                "owner": "Trinity (reviewer)",
                "status": audit_res["status"],
                "blocking_count": audit_res["blocking_count"],
                "finding_count": audit_res["finding_count"],
                "findings": audit_res["findings"],
                "detail": audit_res["message_ko"],
            }
        )

    # Stage 4: Cleanroom Reconstruction & Golden I/O (when cleanroom profile or ledger exists)
    rec_ledger_file = resolved / "evidence/reconstruction-ledger.json"
    if decision.cleanroom_isolation or rec_ledger_file.is_file():
        if (resolved / "contaminated-zone").is_dir():
            live_rec = reconstruct_engine.build_obligation_ledger(resolved, "contaminated-zone")
            cov_res = reconstruct_engine.evaluate_reconstruction_coverage(
                live_rec,
                root=resolved,
                require_zero_contamination=True,
            )
            stages.append(
                {
                    "stage": "cleanroom-reconstruction",
                    "owner": "Keymaker (analyst) & Tank (verifier)",
                    "status": cov_res["status"],
                    "coverage_ratio": cov_res["coverage_ratio"],
                    "detail": cov_res["message_ko"],
                }
            )
        golden_res = verify_golden_io(resolved)
        if golden_res["status"] != "NOT_RUN":
            stages.append(
                {
                    "stage": "golden-io-equivalence",
                    "owner": "Keymaker (analyst) & Tank (verifier)",
                    "status": golden_res["status"],
                    "passed_count": golden_res["passed_count"],
                    "case_count": golden_res["case_count"],
                    "detail": golden_res["message_ko"],
                }
            )

    # Stage 5: Visual Acceptance (when visual-manifest.json exists)
    vis_manifest = resolved / "visual-manifest.json"
    if vis_manifest.is_file():
        vis_res = visual_acceptance.verify_visual_acceptance(vis_manifest, root=resolved)
        stages.append(
            {
                "stage": "visual-acceptance",
                "owner": "Niobe (ux-designer) & Tank (verifier)",
                "status": vis_res["status"],
                "detail": vis_res["message_ko"],
            }
        )

    all_passed = decision.goal_kind != "unsupported" and all(s["status"] == "PASS" for s in stages)
    verdict_doc: dict[str, object] = {
        "schema_version": AUTOPILOT_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "PASS" if all_passed else "FAIL",
        "commander": decision.to_dict()["commander"],
        "profile": decision.profile,
        "risk_level": decision.risk_level,
        "agent_squad": decision.to_dict()["agent_squad"],
        "stage_count": len(stages),
        "stages": stages,
        "message_ko": (
            f"Morpheus & Tank 오토파일럿 통합 게이트({decision.profile}) 전 단계({len(stages)}개) 검증을 통과했습니다."
            if all_passed
            else f"오토파일럿 통합 게이트 차단: 실패 단계 {[s['stage'] for s in stages if s['status'] != 'PASS']}"
        ),
    }

    if apply:
        verdict_bytes = (json.dumps(verdict_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        verdict_doc["verdict_sha256"] = hashlib.sha256(verdict_bytes).hexdigest()
        out_path = resolved / DEFAULT_AUTOPILOT_VERDICT_REL
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(verdict_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "action": "autopilot-gate",
        "applied": apply,
        "verdict_path": DEFAULT_AUTOPILOT_VERDICT_REL if apply else None,
        **verdict_doc,
    }


DEFAULT_BLAST_RADIUS_REL = "evidence/blast-radius-report.json"
DEFAULT_METRIC_CLIMB_LEDGER_REL = "evidence/metric-climb-ledger.json"
DEFAULT_METRIC_CLIMB_TSV_REL = "evidence/metric-climb-results.tsv"

_TS_EXPORT_SYMBOL_RE = re.compile(
    r"\bexport\s+(?:async\s+)?(?:function|class|interface|type|const)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_BOUNDARY_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api-http", re.compile(r"\b(fetch|axios|urllib|http\.client|FastAPI|APIRouter|Response)\b")),
    ("database-sql", re.compile(r"\b(SELECT\s+|INSERT\s+INTO|UPDATE\s+|sqlite3|prisma|sqlalchemy)\b", re.IGNORECASE)),
    ("serialization-wire", re.compile(r"\b(json\.dumps|json\.loads|JSON\.stringify|JSON\.parse|protobuf)\b")),
    ("subprocess-cli", re.compile(r"\b(subprocess\.run|subprocess\.Popen|child_process|argparse)\b")),
    ("security-auth", re.compile(r"\b(jwt|token|password|secret|hmac|hashlib|authorization)\b", re.IGNORECASE)),
)


def _extract_defined_symbols(fpath: Path, text: str) -> list[str]:
    """파일에서 정의된 공개 함수·클래스·인터페이스 심볼 목록을 추출한다."""
    suffix = fpath.suffix.lower()
    symbols: list[str] = []
    if suffix == ".py":
        try:
            tree = ast.parse(text)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if not node.name.startswith("_"):
                        symbols.append(node.name)
        except SyntaxError:
            pass
    elif suffix in (".ts", ".tsx", ".js", ".jsx"):
        for m in _TS_EXPORT_SYMBOL_RE.finditer(text):
            sym = m.group(1)
            if sym not in symbols:
                symbols.append(sym)
    return symbols


def analyze_blast_radius(
    root: Path,
    *,
    target_files: list[str] | tuple[str, ...] = (),
    test_command: list[str] | tuple[str, ...] = (),
    apply: bool = False,
) -> dict[str, object]:
    """Architect & Tank 폭발 반경(Blast Radius) 분석기: 대상 파일의 심볼 참조(1-Hop/2-Hop), 시스템 경계 교차, 5단계 안전 증명 등급을 산출한다."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    all_files = _iter_auditable_files(resolved)
    code_files = [f for f in all_files if f.suffix.lower() in (".py", ".ts", ".tsx", ".js", ".jsx")]

    normalized_targets: list[str] = [PurePosixPath(t).as_posix() for t in target_files if t.strip()]
    if not normalized_targets:
        normalized_targets = [
            f.relative_to(resolved).as_posix()
            for f in code_files
            if "test" not in f.name.lower()
        ][:5]

    file_texts: dict[str, str] = {}
    file_symbols: dict[str, list[str]] = {}
    for fpath in code_files:
        rel = fpath.relative_to(resolved).as_posix()
        txt = fpath.read_text(encoding="utf-8", errors="replace")
        file_texts[rel] = txt
        file_symbols[rel] = _extract_defined_symbols(fpath, txt)

    exported_by_targets: dict[str, list[str]] = {}
    target_symbol_set: set[str] = set()
    for t_rel in normalized_targets:
        syms = file_symbols.get(t_rel, [])
        exported_by_targets[t_rel] = syms
        target_symbol_set.update(syms)

    direct_dependents: list[dict[str, object]] = []
    direct_rel_set: set[str] = set()
    linked_test_files: list[str] = []

    for rel, txt in file_texts.items():
        if rel in normalized_targets:
            continue
        matched_syms = [
            sym
            for sym in sorted(target_symbol_set)
            if re.search(rf"\b{re.escape(sym)}\b", txt) is not None
        ]
        if matched_syms:
            direct_rel_set.add(rel)
            is_test = "test" in PurePosixPath(rel).name.lower() or "tests" in PurePosixPath(rel).parts
            if is_test:
                linked_test_files.append(rel)
            boundaries = [b_name for b_name, b_re in _BOUNDARY_SIGNALS if b_re.search(txt)]
            direct_dependents.append(
                {
                    "file": rel,
                    "is_test": is_test,
                    "matched_symbols": matched_syms,
                    "boundaries_crossed": boundaries,
                }
            )

    hop1_symbols: set[str] = set()
    for d_rel in direct_rel_set:
        if d_rel not in linked_test_files:
            hop1_symbols.update(file_symbols.get(d_rel, []))

    transitive_dependents: list[str] = []
    for rel, txt in file_texts.items():
        if rel in normalized_targets or rel in direct_rel_set:
            continue
        if any(re.search(rf"\b{re.escape(sym)}\b", txt) is not None for sym in hop1_symbols):
            transitive_dependents.append(rel)

    test_passed = False
    if test_command:
        import subprocess

        try:
            proc = subprocess.run(
                list(test_command),
                cwd=str(resolved),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            test_passed = proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            test_passed = False

    golden_res = verify_golden_io(resolved)
    golden_proven = golden_res["status"] == "PASS"

    if test_passed and golden_proven:
        proof_level = 5
        proof_label = "LEVEL_5_GOLDEN_IO_PROVEN"
    elif test_passed:
        proof_level = 4
        proof_label = "LEVEL_4_RUNTIME_TEST_EXECUTED"
    elif linked_test_files:
        proof_level = 3
        proof_label = "LEVEL_3_TEST_COVERAGE_LINKED"
    elif normalized_targets:
        proof_level = 2
        proof_label = "LEVEL_2_STATIC_SYMBOL_TRACE"
    else:
        proof_level = 1
        proof_label = "LEVEL_1_UNVERIFIED_CLAIM"

    report_doc: dict[str, object] = {
        "schema_version": AUTOPILOT_VERSION,
        "action": "blast-radius",
        "status": "PASS" if proof_level >= 3 else "WARN",
        "target_files": normalized_targets,
        "exported_symbols": exported_by_targets,
        "direct_dependents": direct_dependents,
        "transitive_dependents": sorted(transitive_dependents),
        "linked_test_files": sorted(linked_test_files),
        "safety_proof_level": proof_level,
        "safety_proof_label": proof_label,
        "message_ko": (
            f"폭발 반경 분석 완료: 1차 영향 파일 {len(direct_dependents)}개, "
            f"2차 전이 파일 {len(transitive_dependents)}개, 안전 증명 등급 {proof_level}단계({proof_label})."
        ),
    }

    if apply:
        out_path = resolved / DEFAULT_BLAST_RADIUS_REL
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "applied": apply,
        "report_path": DEFAULT_BLAST_RADIUS_REL if apply else None,
        **report_doc,
    }


def _compute_files_hash_and_loc(resolved: Path, rel_paths: list[str]) -> tuple[str, int, dict[str, str]]:
    """지정된 파일 목록의 통합 SHA-256 해시, 총 코드 라인 수(LOC), 개별 파일 해시 맵을 반환한다."""
    digest = hashlib.sha256()
    total_loc = 0
    per_file: dict[str, str] = {}
    for rel in sorted(set(rel_paths)):
        fpath = (resolved / rel).resolve()
        if not fpath.is_file():
            continue
        raw = fpath.read_bytes()
        f_hash = hashlib.sha256(raw).hexdigest()
        per_file[rel] = f_hash
        digest.update(f"{rel}:{f_hash}\n".encode("utf-8"))
        text = raw.decode("utf-8", errors="replace")
        total_loc += sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))
    return digest.hexdigest()[:12], total_loc, per_file


def _monte_carlo_win_probability(
    best_samples: list[float],
    candidate_samples: list[float],
    *,
    direction: str,
    iterations: int = 2000,
) -> float:
    """결정론적 몬테카를로 리샘플링으로 후보 지표가 기존 최고 지표를 이길 확률(0.0~1.0)을 계산한다."""
    import random

    if not best_samples or not candidate_samples:
        return 0.0
    rng = random.Random(42)
    n_b = len(best_samples)
    n_c = len(candidate_samples)
    wins = 0
    for _ in range(iterations):
        mean_b = sum(best_samples[rng.randrange(n_b)] for _ in range(n_b)) / n_b
        mean_c = sum(candidate_samples[rng.randrange(n_c)] for _ in range(n_c)) / n_c
        if direction == "minimize" and mean_c < mean_b:
            wins += 1
        elif direction == "maximize" and mean_c > mean_b:
            wins += 1
    return round(wins / iterations, 4)


def run_metric_climb(
    root: Path,
    *,
    benchmark_cmd: list[str] | tuple[str, ...],
    metric_regex: str = r"metric:\s*([0-9]+(?:\.[0-9]+)?)",
    direction: str = "minimize",
    target_files: list[str] | tuple[str, ...] = (),
    immutable_files: list[str] | tuple[str, ...] = (),
    trials: int = 3,
    confidence_threshold: float = 0.90,
    hypothesis: str = "candidate-experiment",
    apply: bool = False,
) -> dict[str, object]:
    """Dreampia 자율 지표 등반 엔진(Metric Climb): 불변 채점 파일 가드, 중복 실험 해시 차단, Fast-Fail, 몬테카를로 유의성 및 단순성 기준(Simplicity Criterion)을 집행한다."""
    import statistics
    import subprocess

    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    if direction not in ("minimize", "maximize"):
        raise ValueError("direction은 'minimize' 또는 'maximize'여야 합니다.")
    if not benchmark_cmd:
        raise ValueError("벤치마크 실행 명령어(benchmark_cmd)가 필요합니다.")

    resolved = root.resolve()
    ledger_path = resolved / DEFAULT_METRIC_CLIMB_LEDGER_REL
    tsv_path = resolved / DEFAULT_METRIC_CLIMB_TSV_REL

    ledger_data: dict[str, object] = {"immutable_baseline": {}, "entries": []}
    if ledger_path.is_file():
        try:
            loaded = json.loads(ledger_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                ledger_data = loaded
        except json.JSONDecodeError:
            pass

    entries: list[dict[str, object]] = list(ledger_data.get("entries", []))  # type: ignore[arg-type]
    immutable_baseline: dict[str, str] = dict(ledger_data.get("immutable_baseline", {}))  # type: ignore[arg-type]

    norm_immutables = [PurePosixPath(p).as_posix() for p in immutable_files if p.strip()]
    _, _, current_immutables = _compute_files_hash_and_loc(resolved, norm_immutables)

    if not immutable_baseline and current_immutables:
        immutable_baseline = dict(current_immutables)
    else:
        for im_rel, expected_sha in immutable_baseline.items():
            actual_sha = current_immutables.get(im_rel)
            if actual_sha != expected_sha:
                return {
                    "action": "metric-climb",
                    "status": "FAIL",
                    "verdict": "IMMUTABLE_TAMPERED",
                    "violated_file": im_rel,
                    "message_ko": f"불변 평가 파일('{im_rel}')이 수정되었습니다! 채점 기준 조작(Reward Hacking) 방지를 위해 실험이 즉시 기각되었습니다.",
                }

    norm_targets = [PurePosixPath(p).as_posix() for p in target_files if p.strip()]
    if not norm_targets:
        norm_targets = [
            f.relative_to(resolved).as_posix()
            for f in _iter_auditable_files(resolved)
            if f.suffix.lower() in (".py", ".ts", ".tsx")
        ][:10]

    config_hash, loc_count, _ = _compute_files_hash_and_loc(resolved, norm_targets)

    for past in entries:
        if past.get("config_hash") == config_hash:
            return {
                "action": "metric-climb",
                "status": "SKIPPED",
                "verdict": "DUPLICATE_CONFIG",
                "config_hash": config_hash,
                "prior_verdict": past.get("verdict"),
                "prior_mean": past.get("metric_mean"),
                "message_ko": f"동일한 코드 해시({config_hash})에 대한 실험 이력이 이미 존재하여 중복 실행을 건너뛰었습니다(never-repeat).",
            }

    if not apply:
        return {
            "action": "metric-climb",
            "status": "PASS",
            "verdict": "PREVIEW",
            "applied": False,
            "config_hash": config_hash,
            "loc_count": loc_count,
            "benchmark_cmd": list(benchmark_cmd),
            "trials": max(1, trials),
            "direction": direction,
            "target_files": norm_targets,
            "immutable_files": norm_immutables,
            "message_ko": (
                f"[미리보기] 자율 지표 등반 실험(코드 해시 {config_hash}, 대상 파일 {len(norm_targets)}개, {max(1, trials)}회 반복) 계획입니다. "
                "실제 벤치마크 명령어를 실행하고 원장에 기록하려면 --apply 옵션을 추가하십시오."
            ),
        }

    kept_entries = [e for e in entries if e.get("verdict") == "KEEP" and isinstance(e.get("samples"), list)]
    if direction == "minimize":
        best_entry = min(kept_entries, key=lambda e: float(e["metric_mean"]), default=None)  # type: ignore[arg-type]
    else:
        best_entry = max(kept_entries, key=lambda e: float(e["metric_mean"]), default=None)  # type: ignore[arg-type]

    pattern = re.compile(metric_regex, re.MULTILINE)
    samples: list[float] = []
    fast_failed = False
    log_path = resolved / "evidence/metric-climb-last.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    for trial_idx in range(max(1, trials)):
        try:
            proc = subprocess.run(
                list(benchmark_cmd),
                cwd=str(resolved),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "action": "metric-climb",
                "status": "FAIL",
                "verdict": "CRASH",
                "config_hash": config_hash,
                "message_ko": f"벤치마크 실행 중 오류 또는 타임아웃이 발생했습니다: {exc}",
            }

        combined_out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        log_path.write_text(combined_out[-8000:], encoding="utf-8")
        match = pattern.search(combined_out)
        if proc.returncode != 0 or match is None:
            return {
                "action": "metric-climb",
                "status": "FAIL",
                "verdict": "CRASH",
                "config_hash": config_hash,
                "returncode": proc.returncode,
                "log_tail": combined_out[-500:],
                "message_ko": "벤치마크 실행이 실패했거나 출력에서 지표 정규식(metric_regex)을 찾지 못했습니다.",
            }

        val = float(match.group(1))
        samples.append(val)

        if best_entry is not None and trial_idx == 0 and trials > 1:
            best_mean = float(best_entry["metric_mean"])  # type: ignore[arg-type]
            if (direction == "minimize" and val > best_mean * 1.02) or (
                direction == "maximize" and val < best_mean * 0.98
            ):
                fast_failed = True
                break

    _, _, post_immutables = _compute_files_hash_and_loc(resolved, norm_immutables)
    for im_rel, expected_sha in immutable_baseline.items():
        if post_immutables.get(im_rel) != expected_sha:
            return {
                "action": "metric-climb",
                "status": "FAIL",
                "verdict": "IMMUTABLE_TAMPERED",
                "violated_file": im_rel,
                "message_ko": f"벤치마크 실행 도중 불변 파일('{im_rel}')이 변조되었습니다. 결과를 즉시 기각합니다.",
            }

    mean_val = round(statistics.mean(samples), 6)
    std_val = round(statistics.pstdev(samples), 6) if len(samples) > 1 else 0.0

    if best_entry is None:
        verdict = "KEEP"
        win_prob = 1.0
        loc_delta = 0
        reason_ko = f"초기 베이스라인 지표({mean_val})가 설정되어 KEEP으로 기록되었습니다."
    else:
        best_samples = [float(x) for x in best_entry["samples"]]  # type: ignore[union-attr]
        best_mean = float(best_entry["metric_mean"])  # type: ignore[arg-type]
        best_loc = int(best_entry.get("loc_count", loc_count))  # type: ignore[call-overload]
        loc_delta = loc_count - best_loc
        win_prob = _monte_carlo_win_probability(best_samples, samples, direction=direction)

        is_simpler_and_equal = loc_delta < 0 and abs(mean_val - best_mean) <= max(std_val, 1e-6)
        is_bloated_micro_gain = loc_delta >= 25 and abs(mean_val - best_mean) / max(abs(best_mean), 1e-9) < 0.002

        if fast_failed:
            verdict = "DISCARD"
            reason_ko = f"첫 시드 측정값({mean_val})이 기존 최고 평균({best_mean})보다 열등하여 조기 중단(Fast-Fail) 및 기각(DISCARD)되었습니다."
        elif is_bloated_micro_gain:
            verdict = "DISCARD"
            reason_ko = f"단순성 기준(Simplicity Criterion) 위반: 코드가 {loc_delta}줄 증가했으나 지표 개선폭이 0.2% 미만이어서 기각(DISCARD)되었습니다."
        elif win_prob >= confidence_threshold or is_simpler_and_equal:
            verdict = "KEEP"
            reason_ko = (
                f"통계적 유의성(승률 {win_prob:.2f} >= {confidence_threshold:.2f}) 또는 코드 단순화({loc_delta} LOC)를 달성하여 채택(KEEP)되었습니다."
            )
        else:
            verdict = "DISCARD"
            reason_ko = f"기존 최고 평균({best_mean}) 대비 유의미한 개선(승률 {win_prob:.2f} < {confidence_threshold:.2f})에 미달하여 기각(DISCARD)되었습니다."

    entry_doc: dict[str, object] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "config_hash": config_hash,
        "hypothesis": hypothesis,
        "direction": direction,
        "samples": samples,
        "metric_mean": mean_val,
        "metric_std": std_val,
        "loc_count": loc_count,
        "loc_delta": loc_delta,
        "win_probability": win_prob,
        "fast_failed": fast_failed,
        "verdict": verdict,
        "message_ko": reason_ko,
    }

    if apply:
        entries.append(entry_doc)
        ledger_data["immutable_baseline"] = immutable_baseline
        ledger_data["entries"] = entries
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        write_header = not tsv_path.is_file()
        with tsv_path.open("a", encoding="utf-8") as tsv_file:
            if write_header:
                tsv_file.write("config_hash\tmetric_mean\tmetric_std\tloc_delta\twin_probability\tverdict\thypothesis\n")
            tsv_file.write(
                f"{config_hash}\t{mean_val:.6f}\t{std_val:.6f}\t{loc_delta:+d}\t{win_prob:.4f}\t{verdict}\t{hypothesis}\n"
            )

    return {
        "action": "metric-climb",
        "status": "PASS" if verdict == "KEEP" else "REJECTED",
        "ledger_path": DEFAULT_METRIC_CLIMB_LEDGER_REL if apply else None,
        "tsv_path": DEFAULT_METRIC_CLIMB_TSV_REL if apply else None,
        **entry_doc,
    }

