"""Dreampia Autonomous Engineering OS Engine: Inquisitor Code Auditor, Context Pack Compiler, Golden I/O Verifier, and Unified Autopilot Gate.

Completes the 4 architectural pillars:
1. InquisitorCodeAuditor (audit_project_code): AST & regex static auditor catching hollow TDD tests (assert True / empty tests) and enforcing SOLID/type-safety/UI rules.
2. ContextPackCompiler (compile_context_pack): Compiles active SDD requirements, ADR/RISK invariants, and current blockers into a <1,000-token anti-amnesia briefing packet.
3. GoldenIoVerifier (verify_golden_io): Black-box behavioral equivalence verifier testing cleanroom implementations against pure input/output vectors in approved-spec/golden-io.json.
4. UnifiedAutopilotGate (run_autopilot_gate): GuildMaster + Cleric atomic gate pipeline chaining instruction drift, SDD traceability, Inquisitor code audit, cleanroom coverage, and Golden I/O checks.
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

AUTOPILOT_VERSION = "1.0.0"
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
        "build",
        "dist",
        "out",
        "target",
        "vendor",
        "third_party",
        ".venv",
        "venv",
        "coverage",
        ".turbo",
        ".cache",
        ".omo",
    }
)

_AUDIT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".cpp",
        ".hpp",
        ".c",
        ".h",
        ".mm",
        ".m",
        ".cs",
        ".swift",
    }
)


def _is_test_or_check_file(rel: str, fpath: Path) -> bool:
    """파일 경로 및 파일명을 기반으로 테스트·검증 스크립트 여부를 판별한다."""
    name_low = fpath.name.lower()
    parts = PurePosixPath(rel).parts
    return (
        fpath.name.startswith("test_")
        or fpath.name.endswith(("_test.py", "_test.go", "_test.rs", "Test.java", "Test.kt", "Tests.cs", "Tests.swift"))
        or name_low.endswith(
            (
                "-test.py",
                "-check.py",
                "_check.py",
                "-test.mjs",
                "-test.js",
                "-test.cjs",
                "-test.ts",
                "-check.mjs",
                "-check.js",
                "-check.cjs",
                "-check.ts",
            )
        )
        or name_low in ("test.py", "test.js", "test.mjs", "test.cjs", "test.ts")
        or ".test." in name_low
        or ".spec." in name_low
        or "tests" in parts
    )


ensure_local_git_exclude = route_planner.ensure_local_git_exclude

_C_LEX_STANDARD_RE = re.compile(
    r'("(?:\\[\s\S]|[^"\\\n])*"|\'(?:\\[\s\S]|[^\'\\\n])*\'|`(?:\\[\s\S]|[^`\\])*`)'
    r"|(?://[^\n]*|/\*[\s\S]*?\*/)"
)
_C_LEX_RUST_RE = re.compile(
    r'(r#*".*?"#*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\.|[^\'\\\n])\')'
    r"|(?://[^\n]*|/\*[\s\S]*?\*/)",
    re.DOTALL,
)


def _mask_c_comments(text: str, *, is_rust: bool = False) -> str:
    """줄 번호와 컬럼 오프셋을 100% 보존하면서 C 계열(TS/JS/Rust/Go 등) 주석(//, /* */)만 공백으로 마스킹한다."""
    lex_re = _C_LEX_RUST_RE if is_rust else _C_LEX_STANDARD_RE

    def _repl(m: re.Match[str]) -> str:
        if m.group(1) is not None:
            return m.group(1)
        s = m.group(0)
        return "\n".join(" " * len(part) for part in s.split("\n")) if "\n" in s else " " * len(s)

    return lex_re.sub(_repl, text)


def _mask_c_comments_and_strings(text: str, *, is_rust: bool = False) -> str:
    """줄 번호와 오프셋을 보존하면서 주석과 문자열 리터럴 내부 텍스트를 모두 공백으로 마스킹한 코드 스켈레톤을 반환한다."""
    lex_re = _C_LEX_RUST_RE if is_rust else _C_LEX_STANDARD_RE

    def _repl(m: re.Match[str]) -> str:
        s = m.group(0)
        if m.group(1) is not None:
            if len(s) <= 2:
                return s
            inner = s[1:-1]
            masked_inner = "\n".join(" " * len(part) for part in inner.split("\n")) if "\n" in inner else " " * len(inner)
            return s[0] + masked_inner + s[-1]
        return "\n".join(" " * len(part) for part in s.split("\n")) if "\n" in s else " " * len(s)

    return lex_re.sub(_repl, text)


def _find_matching_delimiter(skeleton: str, open_idx: int, open_ch: str = "{", close_ch: str = "}") -> int | None:
    """코드 스켈레톤에서 C 레벨 str.find 점프로 여는 괄호(open_idx)와 짝이 맞는 닫는 괄호 위치를 반환한다 (불일치 시 Fail-Safe None)."""
    n = len(skeleton)
    if open_idx < 0 or open_idx >= n or skeleton[open_idx] != open_ch:
        return None
    depth = 1
    pos = open_idx + 1
    while depth > 0 and pos < n:
        next_close = skeleton.find(close_ch, pos)
        if next_close == -1:
            return None
        next_open = skeleton.find(open_ch, pos, next_close)
        if next_open != -1:
            depth += 1
            pos = next_open + 1
        else:
            depth -= 1
            if depth == 0:
                return next_close
            pos = next_close + 1
    return None


_JSX_BUTTON_START_RE = re.compile(r"<button\b", re.IGNORECASE)


def _iter_jsx_button_attrs(comment_masked: str) -> list[tuple[int, str]]:
    """JSX <button ...> 여는 태그에서 onClick={() => ...} 화살표의 '>'에 끊기지 않고 전체 속성 문자열과 시작 오프셋을 추출한다."""
    results: list[tuple[int, str]] = []
    n = len(comment_masked)
    for m in _JSX_BUTTON_START_RE.finditer(comment_masked):
        start_idx = m.start()
        pos = m.end()
        brace_depth = 0
        quote_ch: str | None = None
        while pos < n:
            ch = comment_masked[pos]
            if quote_ch is not None:
                if ch == "\\" and pos + 1 < n:
                    pos += 2
                    continue
                if ch == quote_ch:
                    quote_ch = None
            else:
                if ch in ('"', "'", "`"):
                    quote_ch = ch
                elif ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    if brace_depth > 0:
                        brace_depth -= 1
                elif ch == ">" and brace_depth == 0:
                    results.append((start_idx, comment_masked[m.end() : pos]))
                    break
            pos += 1
    return results


_TS_ANY_RE = re.compile(r"(:\s*any\b|<any>|\bas\s+any\b|\bArray<any>|\bRecord<[^,>]+,\s*any>|\bany\[\])")
_TS_HOLLOW_TEST_RE = re.compile(
    r"(?:expect\s*\(\s*(?:true|1)\s*\)\s*\.\s*(?:toBe|toEqual|toStrictEqual)\s*\(\s*(?:true|1)\s*\)"
    r"|expect\s*\(\s*false\s*\)\s*\.\s*(?:toBe|toEqual|toStrictEqual)\s*\(\s*false\s*\)"
    r"|assert(?:\.ok|\.equal|\.strictEqual)?\s*\(\s*true(?:\s*,\s*true)?\s*\))"
)
_TS_TEST_CALL_RE = re.compile(r"\b(?:it|test)\s*\(")
_TS_CALLBACK_MARKER_RE = re.compile(r"(?:=>|\bfunction\b)")
_TS_REAL_ASSERT_RE = re.compile(
    r"(?:\b(?:expect|expectTypeOf|assert|should)\b"
    r"|\b(?:assert\w*|expect\w*|verify\w*|check\w*)\s*\("
    r"|\.(?:toBe\w*|toEqual\w*|toStrictEqual|toHave\w*|toContain\w*|toMatch\w*|toThrow\w*|rejects|resolves)\s*\()"
)
_TS_WEAK_MATCHER_RE = re.compile(r"\.(?:toBeDefined|toBeNull|toBeUndefined)\s*\(")
_TS_STRONG_ASSERT_RE = re.compile(
    r"(?:\b(?:expectTypeOf|assert|should)\b"
    r"|\b(?:assert\w*|verify\w*|check\w*|expect[A-Z]\w*)\s*\("
    r"|\.(?:toBe|toBeTruthy|toBeFalsy|toBeGreaterThan\w*|toBeLessThan\w*|toBeCloseTo|toBeInstanceOf|toEqual\w*|toStrictEqual|toHave\w*|toContain\w*|toMatch\w*|toThrow\w*|rejects|resolves)\s*\()"
)
_C_EMPTY_CATCH_RE = re.compile(r"\bcatch\b\s*(?:\([^)]*\))?\s*\{")
_FORBIDDEN_ICON_RE = re.compile(
    r"""from\s+['"](@heroicons/[^'"]+|react-icons[^'"]*|@mui/icons-material[^'"]*|@fortawesome/[^'"]+)['"]"""
)
_BUTTON_TAG_RE = re.compile(r"<button\b([^>]*)>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class AuditFinding:
    """Inquisitor(인퀴지터/심판관) 정적 코드·규칙·TDD 감사 결과 항목."""

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


def _iter_auditable_files(
    root: Path,
    changed_only: bool = False,
    base_ref: str = "HEAD",
    *,
    precomputed_changed: set[str] | None = None,
) -> list[Path]:
    """Git 저장소일 경우 git ls-files -z --cached --others --exclude-standard로 .gitignore/.git/info/exclude를 반영해 스캔하고, 실패 시 os.walk + _IGNORED_DIRS 폴백을 수행한다."""
    import subprocess

    resolved = root.resolve()
    changed_filter: set[str] | None = (
        (precomputed_changed if precomputed_changed is not None else set(collect_git_changed_files(resolved, base_ref=base_ref)))
        if changed_only
        else None
    )
    if changed_filter is not None:
        direct_files: list[Path] = []
        for rel_str in sorted(changed_filter):
            parts = PurePosixPath(rel_str).parts
            if any(part in _IGNORED_DIRS for part in parts):
                continue
            fpath = resolved / rel_str
            if not fpath.is_symlink() and fpath.is_file():
                direct_files.append(fpath)
        return direct_files

    if (resolved / ".git").exists():
        try:
            proc = subprocess.run(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=str(resolved),
                capture_output=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0:
                git_files: list[Path] = []
                seen_rels: set[str] = set()
                for raw_bytes in proc.stdout.split(b"\x00"):
                    if not raw_bytes:
                        continue
                    rel_str = raw_bytes.decode("utf-8", errors="replace").strip()
                    if not rel_str or rel_str in seen_rels:
                        continue
                    seen_rels.add(rel_str)
                    parts = PurePosixPath(rel_str).parts
                    if any(part in _IGNORED_DIRS for part in parts):
                        continue
                    fpath = resolved / rel_str
                    if not fpath.is_symlink() and fpath.is_file():
                        git_files.append(fpath)
                return sorted(git_files)
        except (OSError, subprocess.TimeoutExpired):
            pass

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


def _find_weak_only_assertion_in_py_func(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int | None:
    """Python 테스트 함수 내부에 구체적 값 검증 없이 단순 `assert x is not None` 단독 단언만 존재하는지 검사한다."""
    weak_lines: list[int] = []
    strong_count = 0

    for node in ast.walk(func_node):
        if isinstance(node, ast.Assert):
            test_expr = node.test
            if (
                isinstance(test_expr, ast.Compare)
                and len(test_expr.ops) == 1
                and isinstance(test_expr.ops[0], ast.IsNot)
                and len(test_expr.comparators) == 1
                and isinstance(test_expr.comparators[0], ast.Constant)
                and test_expr.comparators[0].value is None
                and isinstance(test_expr.left, (ast.Name, ast.Call))
            ):
                weak_lines.append(node.lineno)
            elif not (isinstance(test_expr, ast.Constant) and test_expr.value is True):
                strong_count += 1
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr == "assertIsNotNone" and len(node.args) >= 1 and isinstance(node.args[0], (ast.Name, ast.Call)):
                    weak_lines.append(node.lineno)
                elif func.attr.startswith("assert") or func.attr in ("fail", "raises", "reject"):
                    strong_count += 1
            elif isinstance(func, ast.Name) and func.id.startswith("assert"):
                strong_count += 1

    if len(weak_lines) == 1 and strong_count == 0:
        return weak_lines[0]
    return None


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
        ensure_local_git_exclude(resolved)
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


def collect_git_changed_files(root: Path, base_ref: str = "HEAD") -> list[str]:
    """Git 작업 트리(status --porcelain) 및 기준 커밋(diff --name-only) 대비 변경·신규 추가된 프로젝트 상대 경로 목록을 반환한다."""
    import subprocess

    resolved = root.resolve()
    if not (resolved / ".git").exists():
        return []
    changed: set[str] = set()
    ref = (base_ref or "HEAD").strip()
    status_ok = False

    try:
        r_status = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            cwd=str(resolved),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r_status.returncode == 0:
            status_ok = True
            for raw_line in r_status.stdout.splitlines():
                if len(raw_line) < 4:
                    continue
                path_part = raw_line[3:].strip()
                if " -> " in path_part:
                    path_part = path_part.split(" -> ", 1)[1].strip()
                path_part = path_part.strip('"')
                cand = (resolved / path_part).resolve()
                if cand.is_file() and not cand.is_symlink() and (cand == resolved or resolved in cand.parents):
                    rel_posix = cand.relative_to(resolved).as_posix()
                    if not any(part in _IGNORED_DIRS for part in PurePosixPath(rel_posix).parts):
                        changed.add(rel_posix)
    except (OSError, subprocess.TimeoutExpired):
        pass

    if ref.upper() != "HEAD" or not status_ok:
        try:
            r_diff = subprocess.run(
                ["git", "diff", "--name-only", ref],
                cwd=str(resolved),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if r_diff.returncode == 0:
                for raw_line in r_diff.stdout.splitlines():
                    path_part = raw_line.strip().strip('"')
                    if not path_part:
                        continue
                    cand = (resolved / path_part).resolve()
                    if cand.is_file() and not cand.is_symlink() and (cand == resolved or resolved in cand.parents):
                        rel_posix = cand.relative_to(resolved).as_posix()
                        if not any(part in _IGNORED_DIRS for part in PurePosixPath(rel_posix).parts):
                            changed.add(rel_posix)
        except (OSError, subprocess.TimeoutExpired):
            pass

    return sorted(changed)


_git_changed_files = collect_git_changed_files


def discover_project(
    root: Path,
    *,
    bootstrap_sdd: bool = False,
    apply: bool = False,
) -> dict[str, object]:
    """브라운필드/그린필드/폴리글랏/하이브리드 네이티브 프로젝트를 자동 탐색하여 스택 프로필(.dreampia/memory/project-profile.json 및 discovered-project.json)과 선택적 SDD 베이스라인을 구성한다."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    state_dir = route_planner.resolve_skill_state_dir(resolved)

    languages: list[str] = []
    frameworks: list[str] = []
    manifests_found: list[str] = []
    workspace_packages: list[str] = []
    test_runners: list[str] = []
    is_monorepo = False
    ui_stack_detected = False
    recommended_commands: dict[str, str] = {}

    def add_unique(target_list: list[str], item: str) -> None:
        if item and item not in target_list:
            target_list.append(item)

    ui_caps = route_planner.detect_ui_rule_capabilities(resolved)
    has_tailwind = bool(ui_caps["has_tailwind"])
    has_lucide_react = bool(ui_caps["has_lucide_react"])
    if has_tailwind:
        add_unique(frameworks, "tailwindcss")
        ui_stack_detected = True
    if has_lucide_react:
        add_unique(frameworks, "lucide-react")
        ui_stack_detected = True

    lang_policy = route_planner.resolve_language_policy(resolved)
    repo_rule_files: list[str] = [str(x) for x in lang_policy["repo_rule_files"]]  # type: ignore[union-attr]

    # Collect candidate directories up to depth 2 (root, depth 1, depth 2), excluding _IGNORED_DIRS
    candidate_dirs: list[Path] = [resolved]
    priority_parents = (
        "packages",
        "apps",
        "services",
        "crates",
        "native",
        "client",
        "server",
        "frontend",
        "backend",
        "src",
        "tools",
    )
    seen_dirs: set[Path] = {resolved}

    def _register_dir(d: Path) -> None:
        if d not in seen_dirs and d.is_dir() and not d.is_symlink():
            seen_dirs.add(d)
            candidate_dirs.append(d)

    for p_name in priority_parents:
        p_dir = resolved / p_name
        if p_dir.is_dir() and not p_dir.is_symlink() and p_name not in _IGNORED_DIRS:
            _register_dir(p_dir)
            try:
                for child in sorted(p_dir.iterdir()):
                    if child.is_dir() and not child.is_symlink() and child.name not in _IGNORED_DIRS and not child.name.startswith("."):
                        _register_dir(child)
            except OSError:
                pass

    try:
        for d1 in sorted(resolved.iterdir()):
            if not d1.is_dir() or d1.is_symlink() or d1.name in _IGNORED_DIRS or d1.name.startswith("."):
                continue
            _register_dir(d1)
            for d2 in sorted(d1.iterdir()):
                if d2.is_dir() and not d2.is_symlink() and d2.name not in _IGNORED_DIRS and not d2.name.startswith("."):
                    _register_dir(d2)
    except OSError:
        pass

    for cand_dir in candidate_dirs:
        rel_dir = "" if cand_dir == resolved else cand_dir.relative_to(resolved).as_posix()

        def _rel_file(fname: str) -> str:
            return fname if not rel_dir else f"{rel_dir}/{fname}"

        pkg_json_path = cand_dir / "package.json"
        if pkg_json_path.is_file() and not pkg_json_path.is_symlink():
            add_unique(manifests_found, _rel_file("package.json"))
            if rel_dir:
                add_unique(workspace_packages, rel_dir)
            try:
                pkg_data = json.loads(pkg_json_path.read_text(encoding="utf-8", errors="replace"))
            except ValueError:
                pkg_data = {}
            if isinstance(pkg_data, dict):
                deps: dict[str, object] = {}
                for dep_key in ("dependencies", "devDependencies", "peerDependencies"):
                    sub = pkg_data.get(dep_key)
                    if isinstance(sub, dict):
                        deps.update(sub)
                if "typescript" in deps or (cand_dir / "tsconfig.json").is_file() or (resolved / "tsconfig.json").is_file():
                    add_unique(languages, "typescript")
                else:
                    add_unique(languages, "javascript")

                for fw_pkg, fw_name in (
                    ("next", "nextjs"),
                    ("react", "react"),
                    ("vue", "vue"),
                    ("svelte", "svelte"),
                    ("tailwindcss", "tailwindcss"),
                    ("lucide-react", "lucide-react"),
                    ("express", "express"),
                    ("@nestjs/core", "nestjs"),
                    ("electron", "electron"),
                    ("vite", "vite"),
                    ("vitest", "vitest"),
                    ("jest", "jest"),
                    ("@playwright/test", "playwright"),
                ):
                    if fw_pkg in deps:
                        add_unique(frameworks, fw_name)
                if any(x in frameworks for x in ("nextjs", "react", "vue", "svelte", "tailwindcss")):
                    ui_stack_detected = True

                scripts = pkg_data.get("scripts")
                if isinstance(scripts, dict):
                    prefix_arg = f"--prefix {rel_dir} " if rel_dir else ""
                    if "test" in scripts:
                        cmd = f"npm {prefix_arg}test"
                        recommended_commands.setdefault("test", cmd)
                        add_unique(test_runners, cmd)
                    if "lint" in scripts:
                        recommended_commands.setdefault("lint", f"npm {prefix_arg}run lint")
                    if "build" in scripts:
                        recommended_commands.setdefault("build", f"npm {prefix_arg}run build")
                    if "typecheck" in scripts:
                        recommended_commands.setdefault("typecheck", f"npm {prefix_arg}run typecheck")

                if "workspaces" in pkg_data:
                    is_monorepo = True

        cargo_path = cand_dir / "Cargo.toml"
        if cargo_path.is_file() and not cargo_path.is_symlink():
            add_unique(manifests_found, _rel_file("Cargo.toml"))
            if rel_dir:
                add_unique(workspace_packages, rel_dir)
            add_unique(languages, "rust")
            cargo_text = cargo_path.read_text(encoding="utf-8", errors="replace")
            if "[workspace]" in cargo_text:
                is_monorepo = True
            cargo_manifest_arg = f" --manifest-path {_rel_file('Cargo.toml')}" if rel_dir else ""
            recommended_commands.setdefault("test", f"cargo test{cargo_manifest_arg}")
            recommended_commands.setdefault("lint", f"cargo clippy{cargo_manifest_arg}")
            recommended_commands.setdefault("build", f"cargo build{cargo_manifest_arg}")
            add_unique(test_runners, f"cargo test{cargo_manifest_arg}")

        cmake_path = cand_dir / "CMakeLists.txt"
        if cmake_path.is_file() and not cmake_path.is_symlink():
            add_unique(manifests_found, _rel_file("CMakeLists.txt"))
            if rel_dir:
                add_unique(workspace_packages, rel_dir)
            add_unique(languages, "cpp")
            add_unique(frameworks, "cmake")
            cmake_text = cmake_path.read_text(encoding="utf-8", errors="replace").lower()
            if any(tok in cmake_text for tok in ("wasm", "emscripten", "emcc", "em++")):
                add_unique(frameworks, "wasm")
            recommended_commands.setdefault("build", "cmake --build build")
            recommended_commands.setdefault("test", "ctest --test-dir build --output-on-failure")
            add_unique(test_runners, "ctest --test-dir build --output-on-failure")

        makefile_path = cand_dir / "Makefile"
        if makefile_path.is_file() and not makefile_path.is_symlink():
            add_unique(manifests_found, _rel_file("Makefile"))
            if rel_dir:
                add_unique(workspace_packages, rel_dir)
            add_unique(languages, "cpp")
            makefile_text = makefile_path.read_text(encoding="utf-8", errors="replace").lower()
            if any(tok in makefile_text for tok in ("wasm", "emscripten", "emcc", "em++")):
                add_unique(frameworks, "wasm")
            make_cmd = f"make -C {rel_dir}" if rel_dir else "make"
            recommended_commands.setdefault("build", make_cmd)

        swift_path = cand_dir / "Package.swift"
        if swift_path.is_file() and not swift_path.is_symlink():
            add_unique(manifests_found, _rel_file("Package.swift"))
            if rel_dir:
                add_unique(workspace_packages, rel_dir)
            add_unique(languages, "swift")
            recommended_commands.setdefault("test", "swift test")
            recommended_commands.setdefault("build", "swift build")
            add_unique(test_runners, "swift test")

        try:
            html_entries_added = 0
            for cs_file in sorted(cand_dir.iterdir()):
                if not cs_file.is_file() or cs_file.is_symlink():
                    continue
                cs_suffix = cs_file.suffix.lower()
                cs_name_low = cs_file.name.lower()
                if cs_suffix in (".sln", ".csproj"):
                    add_unique(manifests_found, _rel_file(cs_file.name))
                    if rel_dir:
                        add_unique(workspace_packages, rel_dir)
                    add_unique(languages, "csharp")
                    recommended_commands.setdefault("test", "dotnet test")
                    recommended_commands.setdefault("build", "dotnet build")
                    add_unique(test_runners, "dotnet test")
                elif cand_dir == resolved and cs_suffix == ".html" and html_entries_added < 5:
                    add_unique(languages, "html")
                    add_unique(manifests_found, _rel_file(cs_file.name))
                    html_entries_added += 1
                elif cs_suffix in (".wasm", ".wat"):
                    add_unique(frameworks, "wasm")
                elif (
                    rel_dir
                    and rel_dir != "tools"
                    and cs_suffix in (".mjs", ".cjs", ".js")
                    and (
                        cs_name_low.endswith(("-test.mjs", "-test.js", "-test.cjs", "-check.mjs", "-check.js", "-check.cjs"))
                        or cs_name_low in ("test.mjs", "test.js", "test.cjs")
                        or ".test." in cs_name_low
                    )
                ):
                    add_unique(test_runners, f"node {_rel_file(cs_file.name)}")
        except OSError:
            pass

    for py_manifest in ("pyproject.toml", "requirements.txt", "setup.py"):
        py_path = resolved / py_manifest
        if py_path.is_file() and not py_path.is_symlink():
            add_unique(manifests_found, py_manifest)
            add_unique(languages, "python")
            py_text = py_path.read_text(encoding="utf-8", errors="replace").lower()
            for fw_token in ("fastapi", "django", "flask", "pydantic", "pytest", "sqlalchemy"):
                if fw_token in py_text:
                    add_unique(frameworks, fw_token)
            if "pytest" in py_text:
                recommended_commands.setdefault("test", "pytest")
                add_unique(test_runners, "pytest")
            else:
                recommended_commands.setdefault("test", "python -m unittest discover")
                add_unique(test_runners, "python -m unittest discover")

    gomod_path = resolved / "go.mod"
    if gomod_path.is_file() and not gomod_path.is_symlink():
        add_unique(manifests_found, "go.mod")
        add_unique(languages, "go")
        recommended_commands.setdefault("test", "go test ./...")
        recommended_commands.setdefault("lint", "go vet ./...")
        recommended_commands.setdefault("build", "go build ./...")
        add_unique(test_runners, "go test ./...")

    for jvm_manifest in ("build.gradle", "build.gradle.kts", "pom.xml"):
        jvm_path = resolved / jvm_manifest
        if jvm_path.is_file() and not jvm_path.is_symlink():
            add_unique(manifests_found, jvm_manifest)
            add_unique(languages, "kotlin" if "kts" in jvm_manifest else "java")
            jvm_test_cmd = "./gradlew test" if "gradle" in jvm_manifest else "mvn test"
            recommended_commands.setdefault("test", jvm_test_cmd)
            add_unique(test_runners, jvm_test_cmd)

    pubspec_path = resolved / "pubspec.yaml"
    if pubspec_path.is_file() and not pubspec_path.is_symlink():
        add_unique(manifests_found, "pubspec.yaml")
        add_unique(languages, "dart")
        add_unique(frameworks, "flutter")
        ui_stack_detected = True
        recommended_commands.setdefault("test", "flutter test")
        add_unique(test_runners, "flutter test")

    tools_dir = resolved / "tools"
    if tools_dir.is_dir() and not tools_dir.is_symlink():
        try:
            for tool_script in sorted(tools_dir.iterdir()):
                if tool_script.is_file() and not tool_script.is_symlink() and tool_script.suffix.lower() in (".mjs", ".cjs", ".js"):
                    rel_script = tool_script.relative_to(resolved).as_posix()
                    add_unique(manifests_found, rel_script)
                    add_unique(languages, "javascript")
                    runner_cmd = f"node {rel_script}"
                    add_unique(test_runners, runner_cmd)
                    if "test" in tool_script.name.lower() or "check" in tool_script.name.lower() or "verify" in tool_script.name.lower():
                        recommended_commands.setdefault("test", runner_cmd)
            if "test" not in recommended_commands and test_runners:
                recommended_commands["test"] = test_runners[0]
        except OSError:
            pass

    for mono_marker in ("pnpm-workspace.yaml", "turbo.json", "nx.json", "lerna.json"):
        if (resolved / mono_marker).is_file():
            add_unique(manifests_found, mono_marker)
            is_monorepo = True

    if len(workspace_packages) > 1:
        is_monorepo = True

    source_files: list[str] = []
    test_files: list[str] = []
    for fpath in _iter_auditable_files(resolved):
        rel = fpath.relative_to(resolved).as_posix()
        suffix = fpath.suffix.lower()
        if suffix in (".tsx", ".jsx", ".vue", ".svelte"):
            ui_stack_detected = True
        if suffix not in _AUDIT_EXTENSIONS:
            continue
        if suffix == ".py":
            add_unique(languages, "python")
        elif suffix in (".ts", ".tsx"):
            add_unique(languages, "typescript")
        elif suffix in (".js", ".jsx", ".mjs", ".cjs"):
            add_unique(languages, "javascript")
        elif suffix == ".go":
            add_unique(languages, "go")
        elif suffix == ".rs":
            add_unique(languages, "rust")
        elif suffix in (".java", ".kt"):
            add_unique(languages, "kotlin" if suffix == ".kt" else "java")
        elif suffix in (".cpp", ".hpp", ".c", ".h", ".mm", ".m"):
            add_unique(languages, "cpp")
        elif suffix == ".cs":
            add_unique(languages, "csharp")
        elif suffix == ".swift":
            add_unique(languages, "swift")

        if _is_test_or_check_file(rel, fpath):
            test_files.append(rel)
        else:
            source_files.append(rel)

    sdd_ledger = sdd_engine.build_sdd_ledger(resolved)
    req_count = len(sdd_ledger["requirements"])  # type: ignore[arg-type]
    if req_count > 0:
        project_mode = "sdd-ready"
    elif len(source_files) > 0 or len(manifests_found) > 0:
        project_mode = "brownfield"
    else:
        project_mode = "greenfield"

    recommended_rigor = "full" if project_mode == "sdd-ready" else ("standard" if test_files else "nano")
    profile_rel = f"{state_dir}/memory/project-profile.json"
    discovered_rel = f"{state_dir}/discovered-project.json"
    baseline_rel = f"{state_dir}/memory/brownfield-baseline.md"
    bootstrapped = False

    if apply:
        ensure_local_git_exclude(resolved)
        if bootstrap_sdd and project_mode == "brownfield":
            bf_path = resolved / baseline_rel
            bf_path.parent.mkdir(parents=True, exist_ok=True)
            linked_test_line = "TEST-0900"
            bf_content = (
                "# 브라운필드 자동 온보딩 베이스라인 명세\n\n"
                "# REQ-0900: 브라운필드 기존 아키텍처 및 핵심 기능 회귀 방지 (approved, PASS)\n"
                f"- 연계 작업 및 테스트: TASK-0900 -> {linked_test_line}\n\n"
                "# TASK-0900: 브라운필드 모듈 변경 범위 및 인터페이스 정합성 유지 (approved, PASS)\n"
                f"- 연계 요구 및 테스트: REQ-0900 -> {linked_test_line}\n\n"
                f"# {linked_test_line}: 브라운필드 기존 테스트 스위트 및 증분 검증 (approved, PASS)\n"
                "- 연계 작업: TASK-0900\n"
            )
            bf_path.write_text(bf_content, encoding="utf-8")
            refreshed = sdd_engine.build_sdd_ledger(resolved)
            ledger_out = resolved / sdd_engine.DEFAULT_SDD_LEDGER_REL
            ledger_out.parent.mkdir(parents=True, exist_ok=True)
            ledger_out.write_text(json.dumps(refreshed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            req_count = len(refreshed["requirements"])  # type: ignore[arg-type]
            project_mode = "sdd-ready"
            bootstrapped = True

        if not (has_tailwind or has_lucide_react):
            rules_rel = _resolve_project_rules_rel(resolved)
            rules_file = resolved / rules_rel
            existing_doc: dict[str, object] = {}
            if rules_file.is_file():
                try:
                    loaded_r = json.loads(rules_file.read_text(encoding="utf-8"))
                    if isinstance(loaded_r, dict):
                        existing_doc = loaded_r
                except ValueError:
                    existing_doc = {}
            if "enforce_ui_rules" not in existing_doc:
                existing_doc["schema_version"] = 1
                existing_doc["engine_version"] = AUTOPILOT_VERSION
                existing_doc["enforce_ui_rules"] = False
                existing_doc.setdefault("rules", [])
                rules_file.parent.mkdir(parents=True, exist_ok=True)
                rules_file.write_text(json.dumps(existing_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stacks: list[str] = []
    for item in [*languages, *frameworks]:
        add_unique(stacks, item)

    profile_doc: dict[str, object] = {
        "schema_version": 1,
        "engine_version": AUTOPILOT_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "project_mode": project_mode,
        "recommended_rigor_tier": recommended_rigor,
        "languages": languages,
        "frameworks": frameworks,
        "stacks": stacks,
        "manifests_found": manifests_found,
        "is_monorepo": is_monorepo,
        "workspace_packages": workspace_packages,
        "test_runners": test_runners,
        "ui_stack_detected": ui_stack_detected,
        "has_tailwind": has_tailwind,
        "has_lucide_react": has_lucide_react,
        "repo_rule_files": repo_rule_files,
        "chat_language": "ko",
        "code_identifier_policy": "repo-convention",
        "source_file_count": len(source_files),
        "test_file_count": len(test_files),
        "sdd_requirement_count": req_count,
        "sdd_bootstrapped": bootstrapped,
        "recommended_commands": recommended_commands,
    }

    if apply:
        prof_path = resolved / profile_rel
        prof_path.parent.mkdir(parents=True, exist_ok=True)
        serialized_prof = json.dumps(profile_doc, ensure_ascii=False, indent=2) + "\n"
        prof_path.write_text(serialized_prof, encoding="utf-8")
        disc_path = resolved / discovered_rel
        disc_path.parent.mkdir(parents=True, exist_ok=True)
        disc_path.write_text(serialized_prof, encoding="utf-8")
        disc_mem_path = resolved / f"{state_dir}/memory/discovered-project.json"
        disc_mem_path.parent.mkdir(parents=True, exist_ok=True)
        disc_mem_path.write_text(serialized_prof, encoding="utf-8")

    return {
        "action": "discover",
        "status": "PASS",
        "applied": apply,
        "profile_path": profile_rel if apply else None,
        "discovered_project_path": discovered_rel if apply else None,
        "baseline_spec_path": baseline_rel if bootstrapped else None,
        **profile_doc,
        "message_ko": (
            f"프로젝트 자동 탐색 완료: 모드={project_mode}, 언어={','.join(languages) or 'none'}, "
            f"소스={len(source_files)}개, 테스트={len(test_files)}개, Tailwind={has_tailwind}, Lucide={has_lucide_react}"
            + (f" ({profile_rel} 저장 완료)" if apply else " (미리보기 상태, 저장하려면 --apply 추가)")
        ),
    }


_RUST_HOLLOW_TEST_RE = re.compile(r"\b(?:assert!\s*\(\s*true\s*\)|assert_eq!\s*\(\s*true\s*,\s*true\s*\))")
_RUST_UNIMPLEMENTED_RE = re.compile(r"\b(todo!|unimplemented!)\s*\(")
_RUST_TEST_FN_RE = re.compile(
    r"#\[(?:tokio::)?test[^\]]*\](?:\s*#\[[^\]]*\])*\s*(?:async\s+)?fn\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*(->\s*[^{]+)?\{"
)
_RUST_REAL_ASSERT_RE = re.compile(
    r"(?:\b(?:assert|assert_eq|assert_ne|debug_assert|debug_assert_eq|debug_assert_ne|matches|panic)!\s*\("
    r"|\b(?:assert\w*|expect\w*|verify\w*|check\w*)\s*\()"
)
_GO_ANY_RE = re.compile(r"\b(interface\s*\{\s*\})")
_GO_HOLLOW_TEST_RE = re.compile(
    r"\b(?:assert|require)\.(?:True|Equal)\s*\(\s*[A-Za-z0-9_]+\s*,\s*true(?:\s*,\s*true)?\s*\)"
)
_GO_TEST_FN_RE = re.compile(r"\bfunc\s+(Test[A-Za-z0-9_]*)\s*\(\s*[A-Za-z0-9_]+\s+\*testing\.T\s*\)\s*\{")
_GO_REAL_ASSERT_RE = re.compile(
    r"(?:\b(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow|Run)\s*\("
    r"|\b(?:assert|require)\.[A-Za-z0-9_]+\s*\("
    r"|\b(?:assert\w*|expect\w*|verify\w*|check\w*)\s*\()"
)


def _should_auto_incremental_audit(
    resolved: Path,
    changed_only: bool | None,
    force_all: bool,
    base_ref: str,
    *,
    precomputed_changed_list: list[str] | None = None,
    precomputed_sdd_ledger: dict[str, object] | None = None,
) -> tuple[bool, list[str]]:
    """브라운필드 Git 저장소에서 변경 파일이 존재할 때 자동으로 changed_only=True 증분 감사를 활성화할지 판별한다."""
    if force_all or changed_only is False:
        return False, precomputed_changed_list or []
    git_changed = (
        precomputed_changed_list
        if precomputed_changed_list is not None
        else (collect_git_changed_files(resolved, base_ref=base_ref) if (resolved / ".git").exists() else [])
    )
    if changed_only is True:
        return True, git_changed
    # changed_only is None (auto mode): enable incremental audit for brownfield Git repos with modified/added files
    if (resolved / ".git").exists() and git_changed and not (resolved / "docs" / "01_PRD_REQUIREMENTS.md").is_file():
        sdd_doc = precomputed_sdd_ledger if precomputed_sdd_ledger is not None else sdd_engine.build_sdd_ledger(resolved)
        sdd_reqs = sdd_doc.get("requirements", [])
        if not isinstance(sdd_reqs, list) or len(sdd_reqs) == 0:
            return True, git_changed
    return False, git_changed


def audit_project_code(
    root: Path,
    *,
    check_return_types: bool = True,
    check_ui_rules: bool | None = None,
    changed_only: bool | None = None,
    force_all: bool = False,
    base_ref: str = "HEAD",
    apply: bool = False,
    precomputed_changed_list: list[str] | None = None,
) -> dict[str, object]:
    """Inquisitor(인퀴지터/심판관) 정적 감사기: 가짜 TDD 테스트(assert True/빈 테스트), any 타입, 반환 타입 누락, UI 아이콘/버튼 규칙 및 자가 학습 규칙을 검사한다 (브라운필드 Git 저장소 또는 changed_only 활성 시 변경 파일만 증분 감사)."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    ui_caps = route_planner.detect_ui_rule_capabilities(resolved)
    if check_ui_rules is True:
        enforce_tailwind = True
        enforce_lucide = True
        eff_ui_rules = True
    elif check_ui_rules is False:
        enforce_tailwind = False
        enforce_lucide = False
        eff_ui_rules = False
    else:
        enforce_tailwind = bool(ui_caps["enforce_tailwind"])
        enforce_lucide = bool(ui_caps["enforce_lucide_react"])
        eff_ui_rules = bool(ui_caps["enforce_ui_rules"])

    eff_changed_only, git_changed_list = _should_auto_incremental_audit(
        resolved,
        changed_only,
        force_all,
        base_ref,
        precomputed_changed_list=precomputed_changed_list,
    )
    findings: list[AuditFinding] = []
    scanned_files: list[str] = []
    changed_set: set[str] | None = set(git_changed_list) if eff_changed_only else None
    learned_rules = load_project_rules(resolved)
    compiled_custom_rules: list[tuple[dict[str, object], re.Pattern[str]]] = []
    for r_item in learned_rules:
        pat_str = str(r_item.get("forbidden_regex") or "").strip()
        if pat_str:
            try:
                compiled_custom_rules.append((r_item, re.compile(pat_str)))
            except re.error:
                continue

    for fpath in _iter_auditable_files(
        resolved,
        changed_only=eff_changed_only,
        base_ref=base_ref,
        precomputed_changed=changed_set,
    ):
        rel = fpath.relative_to(resolved).as_posix()
        if changed_set is not None and rel not in changed_set:
            continue
        suffix = fpath.suffix.lower()
        if suffix not in _AUDIT_EXTENSIONS:
            continue
        scanned_files.append(rel)
        text = fpath.read_text(encoding="utf-8", errors="replace")
        is_test_file = _is_test_or_check_file(rel, fpath)

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
                        weak_line = _find_weak_only_assertion_in_py_func(node) if (has_assert and taut_line is None) else None
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
                        elif weak_line is not None:
                            findings.append(
                                AuditFinding(
                                    severity="HIGH",
                                    rule_id="hollow-tdd-weak-assertion",
                                    evidence=f"{rel}:{weak_line}",
                                    issue_ko=f"테스트 함수 '{node.name}'에 구체적 값 비교 없이 단순 존재 확인(is not None)만 단독으로 사용되었습니다.",
                                    fix_ko="반환값의 실제 값, 필드 상태 또는 경계 조건을 검증하는 구체적 단언문(assert actual == expected)을 추가하십시오.",
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

        elif suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            comment_masked = _mask_c_comments(text)
            code_skeleton = _mask_c_comments_and_strings(text)
            skeleton_lines = code_skeleton.splitlines()
            comment_masked_lines = comment_masked.splitlines()

            for idx, skel_line in enumerate(skeleton_lines, start=1):
                if suffix in (".ts", ".tsx") and _TS_ANY_RE.search(skel_line):
                    findings.append(
                        AuditFinding(
                            severity="HIGH",
                            rule_id="forbidden-any-type",
                            evidence=f"{rel}:{idx}",
                            issue_ko="TypeScript 코드에 금지된 'any' 타입이 사용되었습니다.",
                            fix_ko="명시적 인터페이스(Props/Contract) 또는 구체적인 유니온/제네릭 타입으로 교체하십시오.",
                        )
                    )
                if is_test_file and _TS_HOLLOW_TEST_RE.search(skel_line):
                    findings.append(
                        AuditFinding(
                            severity="HIGH",
                            rule_id="hollow-tdd-assert-true",
                            evidence=f"{rel}:{idx}",
                            issue_ko="가짜 테스트 단언문(expect(true).toBe(true))이 감지되었습니다.",
                            fix_ko="실제 컴포넌트/함수 동작을 검증하는 단언문으로 교체하십시오.",
                        )
                    )

            if enforce_lucide:
                for idx, cm_line in enumerate(comment_masked_lines, start=1):
                    if _FORBIDDEN_ICON_RE.search(cm_line):
                        findings.append(
                            AuditFinding(
                                severity="MEDIUM",
                                rule_id="forbidden-icon-library",
                                evidence=f"{rel}:{idx}",
                                issue_ko="허용되지 않은 외부 아이콘 라이브러리가 사용되었습니다.",
                                fix_ko="아이콘 라이브러리 통일 규칙에 따라 'lucide-react'만 사용하십시오.",
                            )
                        )

            if is_test_file:
                for t_match in _TS_TEST_CALL_RE.finditer(code_skeleton):
                    prefix_start = t_match.start()
                    if prefix_start > 0 and code_skeleton[prefix_start - 1] in (".", "$", "_"):
                        continue
                    open_paren = t_match.end() - 1
                    close_paren = _find_matching_delimiter(code_skeleton, open_paren, "(", ")")
                    if close_paren is None:
                        continue
                    call_skel = code_skeleton[open_paren + 1 : close_paren]
                    if not _TS_CALLBACK_MARKER_RE.search(call_skel):
                        continue
                    if not _TS_HOLLOW_TEST_RE.search(call_skel) and not _TS_REAL_ASSERT_RE.search(call_skel):
                        line_no = code_skeleton[:prefix_start].count("\n") + 1
                        findings.append(
                            AuditFinding(
                                severity="HIGH",
                                rule_id="hollow-tdd-no-assertion",
                                evidence=f"{rel}:{line_no}",
                                issue_ko="TS/JS 테스트 블록에 실제 검증 단언문(expect/assert)이 없습니다.",
                                fix_ko="정상·거부·경계 조건을 실제로 검증하는 expect() 또는 assert 단언문을 추가하십시오.",
                            )
                        )
                    elif (
                        not _TS_HOLLOW_TEST_RE.search(call_skel)
                        and _TS_WEAK_MATCHER_RE.search(call_skel)
                        and not _TS_STRONG_ASSERT_RE.search(call_skel)
                    ):
                        line_no = code_skeleton[:prefix_start].count("\n") + 1
                        findings.append(
                            AuditFinding(
                                severity="HIGH",
                                rule_id="hollow-tdd-weak-assertion",
                                evidence=f"{rel}:{line_no}",
                                issue_ko="TS/JS 테스트 블록에 구체적 값 비교 없이 단순 존재 확인(toBeDefined/not.toBeNull)만 단독으로 사용되었습니다.",
                                fix_ko="실제 반환값이나 상태를 비교하는 toBe(), toEqual(), toStrictEqual() 등의 구체적 단언문을 추가하십시오.",
                            )
                        )

            for c_match in _C_EMPTY_CATCH_RE.finditer(code_skeleton):
                open_brace = c_match.end() - 1
                close_brace = _find_matching_delimiter(code_skeleton, open_brace, "{", "}")
                if close_brace is not None and code_skeleton[open_brace + 1 : close_brace].strip() == "":
                    line_no = code_skeleton[: c_match.start()].count("\n") + 1
                    findings.append(
                        AuditFinding(
                            severity="HIGH",
                            rule_id="slop-bare-except-pass",
                            evidence=f"{rel}:{line_no}",
                            issue_ko="예외를 포착한 뒤 아무 처리도 하지 않고 묵살하는 AI 슬롭 패턴(빈 catch 블록)이 감지되었습니다.",
                            fix_ko="구체적인 예외 복구 로직, 에러 상태 갱신 또는 사용자 친화적인 한글 오류 처리를 작성하십시오.",
                        )
                    )

            if enforce_tailwind and suffix in (".tsx", ".jsx"):
                for start_offset, attrs in _iter_jsx_button_attrs(comment_masked):
                    if "className" in attrs and "bg-transparent" not in attrs:
                        line_no = comment_masked[:start_offset].count("\n") + 1
                        findings.append(
                            AuditFinding(
                                severity="LOW",
                                rule_id="button-bg-transparent-missing",
                                evidence=f"{rel}:{line_no}",
                                issue_ko="<button> 요소의 className에 기본 'bg-transparent' 스타일이 누락되었습니다.",
                                fix_ko="버튼 기본 스타일 규칙에 따라 'bg-transparent' 및 hover/focus 상태를 포함하십시오.",
                            )
                        )

        elif suffix == ".rs":
            code_skeleton = _mask_c_comments_and_strings(text, is_rust=True)
            for idx, skel_line in enumerate(code_skeleton.splitlines(), start=1):
                if _RUST_HOLLOW_TEST_RE.search(skel_line):
                    findings.append(
                        AuditFinding(
                            severity="HIGH",
                            rule_id="hollow-tdd-assert-true",
                            evidence=f"{rel}:{idx}",
                            issue_ko="Rust 테스트 코드에 가짜 단언문(assert!(true))이 감지되었습니다.",
                            fix_ko="assert_eq! 또는 실제 결과 검증 단언문으로 교체하십시오.",
                        )
                    )
                if not is_test_file and _RUST_UNIMPLEMENTED_RE.search(skel_line):
                    findings.append(
                        AuditFinding(
                            severity="HIGH",
                            rule_id="slop-unimplemented-macro",
                            evidence=f"{rel}:{idx}",
                            issue_ko="프로덕션 Rust 코드에 미완성 매크로(todo!/unimplemented!)가 남아 있습니다.",
                            fix_ko="실제 비즈니스 로직과 Result 기반 에러 처리를 구현하십시오.",
                        )
                    )
            for r_match in _RUST_TEST_FN_RE.finditer(code_skeleton):
                if "should_panic" in r_match.group(0) or r_match.group(2) is not None:
                    continue
                open_brace = r_match.end() - 1
                close_brace = _find_matching_delimiter(code_skeleton, open_brace, "{", "}")
                if close_brace is None:
                    continue
                fn_body = code_skeleton[open_brace + 1 : close_brace]
                if not _RUST_HOLLOW_TEST_RE.search(fn_body) and not _RUST_REAL_ASSERT_RE.search(fn_body):
                    fn_name = r_match.group(1)
                    line_no = code_skeleton[: r_match.start()].count("\n") + 1
                    findings.append(
                        AuditFinding(
                            severity="HIGH",
                            rule_id="hollow-tdd-no-assertion",
                            evidence=f"{rel}:{line_no}",
                            issue_ko=f"Rust 테스트 함수 '{fn_name}'에 실제 검증 단언문(assert!/assert_eq!)이 없습니다.",
                            fix_ko="실제 실행 결과를 검증하는 assert_eq! 또는 단언 매크로를 추가하십시오.",
                        )
                    )

        elif suffix == ".go":
            code_skeleton = _mask_c_comments_and_strings(text)
            for idx, skel_line in enumerate(code_skeleton.splitlines(), start=1):
                if not is_test_file and _GO_ANY_RE.search(skel_line):
                    findings.append(
                        AuditFinding(
                            severity="MEDIUM",
                            rule_id="forbidden-any-type",
                            evidence=f"{rel}:{idx}",
                            issue_ko="Go 코드에 비타입 빈 인터페이스(interface{})가 사용되었습니다.",
                            fix_ko="구체적인 구조체(struct) 또는 명시적 인터페이스/제네릭 타입을 사용하십시오.",
                        )
                    )
                if is_test_file and _GO_HOLLOW_TEST_RE.search(skel_line):
                    findings.append(
                        AuditFinding(
                            severity="HIGH",
                            rule_id="hollow-tdd-assert-true",
                            evidence=f"{rel}:{idx}",
                            issue_ko="Go 테스트 코드에 항상 참인 가짜 단언문이 감지되었습니다.",
                            fix_ko="실제 결과값을 비교하는 t.Errorf/t.Fatalf 또는 assert.Equal로 교체하십시오.",
                        )
                    )
            if is_test_file:
                for g_match in _GO_TEST_FN_RE.finditer(code_skeleton):
                    open_brace = g_match.end() - 1
                    close_brace = _find_matching_delimiter(code_skeleton, open_brace, "{", "}")
                    if close_brace is None:
                        continue
                    fn_body = code_skeleton[open_brace + 1 : close_brace]
                    if not _GO_HOLLOW_TEST_RE.search(fn_body) and not _GO_REAL_ASSERT_RE.search(fn_body):
                        fn_name = g_match.group(1)
                        line_no = code_skeleton[: g_match.start()].count("\n") + 1
                        findings.append(
                            AuditFinding(
                                severity="HIGH",
                                rule_id="hollow-tdd-no-assertion",
                                evidence=f"{rel}:{line_no}",
                                issue_ko=f"Go 테스트 함수 '{fn_name}'에 실제 검증 단언문(t.Error/t.Fatal/assert)이 없습니다.",
                                fix_ko="정상·오류 경계 조건을 검증하는 t.Fatalf 또는 단언문을 추가하십시오.",
                            )
                        )

        if not is_test_file:
            search_target = _mask_c_comments(text, is_rust=(suffix == ".rs")) if suffix != ".py" else text
            for custom_rule, custom_re in compiled_custom_rules:
                c_match = custom_re.search(search_target)
                if c_match:
                    line_no = search_target[: c_match.start()].count("\n") + 1
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
    scope_label = "changed_only" if eff_changed_only else "full"
    payload: dict[str, object] = {
        "status": "PASS" if passed else "FAIL",
        "auditor": "Inquisitor (reviewer)",
        "audit_scope": scope_label,
        "changed_files": sorted(changed_set) if changed_set is not None else None,
        "applied": apply,
        "report_path": DEFAULT_CODE_AUDIT_REL if apply else None,
        "ui_rules_enforced": eff_ui_rules,
        "has_tailwind": bool(ui_caps["has_tailwind"]),
        "has_lucide_react": bool(ui_caps["has_lucide_react"]),
        "enforce_tailwind": enforce_tailwind,
        "enforce_lucide_react": enforce_lucide,
        "scanned_file_count": len(scanned_files),
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "learned_rule_count": len(learned_rules),
        "findings": [f.to_dict() for f in findings],
        "message_ko": (
            (
                "Git 워킹트리에 변경·추가된 파일이 없어 증분 감사를 통과했습니다. 전체 저장소 레거시 감사가 필요하면 --all 옵션을 사용하십시오."
                if (eff_changed_only and len(scanned_files) == 0)
                else f"Inquisitor 코드·TDD·규칙 정적 감사({scope_label})를 통과했습니다. (검사 파일 {len(scanned_files)}개, 차단 결함 0건)"
            )
            if passed
            else f"Inquisitor 감사({scope_label})에서 차단 결함 {len(blocking)}건(전체 {len(findings)}건)이 발견되었습니다."
        ),
    }
    if apply:
        ensure_local_git_exclude(resolved)
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
    """Alchemist & Cleric 블랙박스 입출력 동등성(Golden I/O) 검증기."""
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
    scan = sdd_engine.scan_project_specs(resolved)
    sdd_res = sdd_engine.verify_sdd_compliance(resolved, require_tdd_files=False, precomputed_scan=scan)
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
        "protagonist": route_dec.get("protagonist"),
        "commander": route_dec["commander"],
        "quest_rank": route_dec.get("quest_rank"),
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
            "3. 테스트 함수에 assert True 같은 가짜 단언문을 작성하지 마십시오 (Inquisitor 감사기가 즉시 차단합니다).",
            "4. 클린룸 프로파일에서는 contaminated-zone 파일을 구현 코드에 직접 복사하지 마십시오.",
        ],
    }

    if apply:
        ensure_local_git_exclude(resolved)
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


def _split_chained_commands(raw: str) -> list[str]:
    """따옴표 내부는 보호하면서 '&&', ';', 줄바꿈 구분자로 체이닝된 다중 검증 명령어를 안전하게 분리한다."""
    text = raw.strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            loaded = json.loads(text)
            if isinstance(loaded, list):
                expanded: list[str] = []
                for item in loaded:
                    if isinstance(item, str):
                        expanded.extend(_split_chained_commands(item))
                return expanded
        except ValueError:
            pass

    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    idx = 0
    length = len(text)
    while idx < length:
        ch = text[idx]
        if escaped:
            buf.append(ch)
            escaped = False
            idx += 1
            continue
        if ch == "\\" and (in_single or in_double):
            buf.append(ch)
            escaped = True
            idx += 1
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            idx += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            idx += 1
            continue
        if not in_single and not in_double:
            if ch == "&" and idx + 1 < length and text[idx + 1] == "&":
                seg = "".join(buf).strip()
                if seg:
                    parts.append(seg)
                buf = []
                idx += 2
                continue
            if ch in (";", "\n", "\r"):
                seg = "".join(buf).strip()
                if seg:
                    parts.append(seg)
                buf = []
                idx += 1
                continue
        buf.append(ch)
        idx += 1

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def normalize_verify_commands(
    raw_commands: str | list[str] | tuple[str, ...] | None,
    *,
    root: Path | None = None,
) -> list[str]:
    """단일 문자열, 체이닝 문자열('&&', ';'), JSON 배열, 또는 문자열 시퀀스로 전달된 검증 명령어를 정규화한다."""
    normalized: list[str] = []

    def _add_cmd(cmd_str: str) -> None:
        for sub in _split_chained_commands(cmd_str):
            if sub and sub not in normalized:
                normalized.append(sub)

    if isinstance(raw_commands, str):
        _add_cmd(raw_commands)
    elif isinstance(raw_commands, (list, tuple)):
        for item in raw_commands:
            if isinstance(item, str):
                _add_cmd(item)

    if not normalized and root is not None:
        rules_rel = _resolve_project_rules_rel(root.resolve())
        rules_file = root.resolve() / rules_rel
        if rules_file.is_file() and not rules_file.is_symlink():
            try:
                loaded_cfg = json.loads(rules_file.read_text(encoding="utf-8"))
                if isinstance(loaded_cfg, dict):
                    saved_cmds = loaded_cfg.get("verify_commands")
                    if isinstance(saved_cmds, str):
                        _add_cmd(saved_cmds)
                    elif isinstance(saved_cmds, list):
                        for item in saved_cmds:
                            if isinstance(item, str):
                                _add_cmd(item)
            except ValueError:
                pass

    return normalized


def run_verify_commands(
    root: Path,
    commands: list[str] | tuple[str, ...],
    *,
    timeout_sec: int = 120,
) -> dict[str, object]:
    """Cleric 다중 검증 명령 실행기: 전달된 검증 명령 배열을 순차 실행하고 개별 종료 코드·소요 시간·표준 출력을 기록한다."""
    import shlex
    import shutil
    import subprocess
    import time

    resolved = root.resolve()
    cmd_list = normalize_verify_commands(list(commands))
    results: list[dict[str, object]] = []
    passed_count = 0

    _dangerous_verify_re = re.compile(
        r"(?i)(?:\brm\s+-[rf]{1,2}\b|\bgit\s+push\s+[^\n]*(?:--force|-f\b)|\bgit\s+reset\s+--hard\b"
        r"|\bgit\s+clean\s+-[fdqx]{2,}\b|\bsudo\s+|\bmkfs\b|\bformat\s+[a-z]:|\bdel\s+/[fsq]"
        r"|\bRemove-Item\b[^\n]*-Recurse|\b(?:Invoke-Expression|iex)\b|\bchmod\s+777\b"
        r"|\b(?:curl|wget)\b[^\n]*\|\s*(?:sh|bash|zsh|pwsh|powershell)\b)"
    )

    for cmd_str in cmd_list:
        t0 = time.monotonic()
        if _dangerous_verify_re.search(cmd_str):
            results.append(
                {
                    "command": cmd_str,
                    "status": "FAIL",
                    "returncode": 126,
                    "duration_ms": 0,
                    "stdout_tail": "",
                    "stderr_tail": "보안 정책상 파괴적 명령어(rm -rf, git push --force, sudo 등)는 검증 게이트에서 실행이 원천 차단됩니다.",
                }
            )
            continue

        try:
            raw_tokens = shlex.split(cmd_str, posix=(os.name != "nt"))
            argv = [tok.strip("\"'") if os.name == "nt" else tok for tok in raw_tokens if tok.strip()]
        except ValueError:
            argv = [tok for tok in cmd_str.split() if tok]

        if not argv:
            continue

        exe_cand = argv[0]
        local_cand = resolved / exe_cand
        if local_cand.is_file() and not local_cand.is_symlink():
            resolved_exe = str(local_cand)
        else:
            resolved_exe = shutil.which(exe_cand) or exe_cand

        try:
            proc = subprocess.run(
                [resolved_exe, *argv[1:]],
                cwd=str(resolved),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                check=False,
            )
            rc = proc.returncode
            out_tail = "\n".join((proc.stdout or "").strip().splitlines()[-20:])
            err_tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
        except subprocess.TimeoutExpired:
            rc = 124
            out_tail = ""
            err_tail = f"검증 명령 실행 제한 시간({timeout_sec}초)을 초과했습니다."
        except OSError as exc:
            rc = 127
            out_tail = ""
            err_tail = f"검증 명령 실행 실패: {exc}"

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        ok = rc == 0
        if ok:
            passed_count += 1
        results.append(
            {
                "command": cmd_str,
                "status": "PASS" if ok else "FAIL",
                "returncode": rc,
                "duration_ms": elapsed_ms,
                "stdout_tail": out_tail,
                "stderr_tail": err_tail,
            }
        )

    all_ok = len(results) > 0 and passed_count == len(results)
    return {
        "status": "PASS" if all_ok else "FAIL",
        "command_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "commands": [str(r["command"]) for r in results],
        "results": results,
        "message_ko": (
            f"다중 검증 명령 게이트({passed_count}/{len(results)}개 명령)를 모두 통과했습니다."
            if all_ok
            else f"다중 검증 명령 게이트 실패: 전체 {len(results)}개 중 {len(results) - passed_count}개 명령이 실패했습니다."
        ),
    }


def run_autopilot_gate(
    root: Path,
    goal: str = "",
    *,
    allow_doc_only: bool = False,
    changed_only: bool | None = None,
    force_all: bool = False,
    base_ref: str = "HEAD",
    verify_cmd: str | list[str] | tuple[str, ...] | None = None,
    apply: bool = False,
    max_iterations: int | None = None,
) -> dict[str, object]:
    """GuildMaster & Cleric 단일 오토파일럿 통합 게이트: 프로파일 및 작업 티어(rigor_tier)에 맞춰 지침·SDD·코드감사·다중검증명령·클린룸·Golden I/O를 원자적으로 연쇄 검증하며, 브라운필드 Git 저장소에서는 변경 파일 증분 감사를 기본 수행한다."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    eff_goal = goal.strip() or "프로젝트 기능 구현 및 품질 게이트 통합 검증"
    git_changed_list = collect_git_changed_files(resolved, base_ref=base_ref) if (resolved / ".git").exists() else []
    decision = (
        route_planner.plan_route(
            eff_goal,
            root=resolved,
            repo_dirty=bool(git_changed_list),
            repo_inspection_failed=False,
        )
        if (base_ref or "HEAD").strip().upper() == "HEAD" and (resolved / ".git").exists()
        else route_planner.plan_route(eff_goal, root=resolved)
    )
    initial_sdd_ledger = sdd_engine.build_sdd_ledger(resolved)
    eff_changed_only, _ = _should_auto_incremental_audit(
        resolved,
        changed_only,
        force_all,
        base_ref,
        precomputed_changed_list=git_changed_list,
        precomputed_sdd_ledger=initial_sdd_ledger,
    )
    eff_verify_cmds = normalize_verify_commands(verify_cmd, root=resolved)

    budget = max(1, min(5, max_iterations if max_iterations is not None else (3 if decision.continuous_loop else 1)))
    loop_history: list[dict[str, object]] = []
    stages: list[dict[str, object]] = []
    all_passed = False

    for attempt in range(1, budget + 1):
        stages = []

        # Stage 1: Instruction Drift Check
        inst_res = write_boundary.check_instruction_drift(resolved)
        stages.append(
            {
                "stage": "instruction-drift",
                "owner": "Guardian (privacy-guard)",
                "status": inst_res["status"],
                "detail": inst_res["message_ko"],
            }
        )

        # Stage 2: SDD + TDD Traceability Check (with Adaptive Nano / Brownfield Incremental support)
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
            precomputed_ledger=initial_sdd_ledger if attempt == 1 else None,
        )
        sdd_blockers: list[str] = list(sdd_res["blockers"])  # type: ignore[arg-type]
        brownfield_no_sdd = (
            sdd_res["requirement_count"] == 0
            and not (resolved / "docs" / "01_PRD_REQUIREMENTS.md").is_file()
            and ((resolved / ".git").exists() or eff_changed_only)
        )
        adaptive_nano_bypass = (
            (decision.rigor_tier == "nano" or brownfield_no_sdd)
            and sdd_res["requirement_count"] == 0
            and all(b in ("missing-sdd-requirements", "missing-executable-tdd-test-files") for b in sdd_blockers)
        )
        stages.append(
            {
                "stage": "sdd-tdd-traceability",
                "owner": "Sage (planner) & Cleric (verifier)",
                "status": "PASS" if (sdd_res["status"] == "PASS" or adaptive_nano_bypass) else "FAIL",
                "traceability_ratio": sdd_res["traceability_ratio"],
                "adaptive_nano_bypass": adaptive_nano_bypass,
                "blockers": [] if adaptive_nano_bypass else sdd_blockers,
                "detail": (
                    "Adaptive Brownfield/Nano Tier: 브라운필드 증분 변경 또는 경량 작업으로 전체 SDD 문서 스캐폴드 강제를 생략하고 코드·TDD 감사로 직결합니다."
                    if adaptive_nano_bypass
                    else sdd_res["message_ko"]
                ),
            }
        )

        # Stage 3: Inquisitor Code & Hollow-TDD Static Audit
        if not allow_doc_only:
            audit_res = audit_project_code(
                resolved,
                changed_only=eff_changed_only,
                force_all=force_all,
                base_ref=base_ref,
                precomputed_changed_list=git_changed_list,
            )
            stages.append(
                {
                    "stage": "inquisitor-code-audit",
                    "owner": "Inquisitor (reviewer)",
                    "status": audit_res["status"],
                    "audit_scope": audit_res["audit_scope"],
                    "scanned_file_count": audit_res["scanned_file_count"],
                    "blocking_count": audit_res["blocking_count"],
                    "finding_count": audit_res["finding_count"],
                    "findings": audit_res["findings"],
                    "detail": audit_res["message_ko"],
                }
            )

        # Stage 4: Custom Verification Commands Gate (single, chained '&&'/';', or array)
        if eff_verify_cmds and not allow_doc_only:
            verify_res = run_verify_commands(resolved, eff_verify_cmds)
            stages.append(
                {
                    "stage": "verify-gate",
                    "owner": "Cleric (verifier)",
                    "status": verify_res["status"],
                    "command_count": verify_res["command_count"],
                    "passed_count": verify_res["passed_count"],
                    "commands": verify_res["commands"],
                    "results": verify_res["results"],
                    "detail": verify_res["message_ko"],
                }
            )

        # Stage 5: Cleanroom Reconstruction & Golden I/O (when cleanroom profile or ledger exists)
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
                        "owner": "Alchemist (analyst) & Cleric (verifier)",
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
                        "owner": "Alchemist (analyst) & Cleric (verifier)",
                        "status": golden_res["status"],
                        "passed_count": golden_res["passed_count"],
                        "case_count": golden_res["case_count"],
                        "detail": golden_res["message_ko"],
                    }
                )

        # Stage 6: Visual Acceptance (when visual-manifest.json exists)
        vis_manifest = resolved / "visual-manifest.json"
        if vis_manifest.is_file():
            vis_res = visual_acceptance.verify_visual_acceptance(vis_manifest, root=resolved)
            stages.append(
                {
                    "stage": "visual-acceptance",
                    "owner": "Bard (ux-designer) & Cleric (verifier)",
                    "status": vis_res["status"],
                    "detail": vis_res["message_ko"],
                }
            )

        all_passed = decision.goal_kind != "unsupported" and all(s["status"] == "PASS" for s in stages)
        failed_stages = [str(s["stage"]) for s in stages if s["status"] != "PASS"]
        healed_actions: list[str] = []

        if not all_passed and attempt < budget and apply:
            # Self-healing action: if SDD ledger is stale, rebuild sdd-ledger.json and context-pack.json before next attempt
            if "sdd-tdd-traceability" in failed_stages:
                refreshed_ledger = sdd_engine.build_sdd_ledger(resolved)
                sdd_ledger_file.parent.mkdir(parents=True, exist_ok=True)
                sdd_ledger_file.write_text(
                    json.dumps(refreshed_ledger, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                healed_actions.append("refresh-sdd-ledger")
            compile_context_pack(resolved, eff_goal, apply=True)
            healed_actions.append("refresh-context-pack")

        loop_history.append(
            {
                "iteration": attempt,
                "status": "PASS" if all_passed else "FAIL",
                "failed_stages": failed_stages,
                "self_healing_actions": healed_actions,
            }
        )
        if all_passed or not healed_actions:
            break

    dec_dict = decision.to_dict()
    verdict_doc: dict[str, object] = {
        "schema_version": AUTOPILOT_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "PASS" if all_passed else "FAIL",
        "protagonist": dec_dict.get("protagonist"),
        "commander": dec_dict["commander"],
        "quest_rank": dec_dict.get("quest_rank"),
        "profile": decision.profile,
        "rigor_tier": decision.rigor_tier,
        "audit_scope": "changed_only" if eff_changed_only else "full",
        "verify_commands": eff_verify_cmds,
        "execution_mode": decision.execution_mode,
        "continuous_loop": decision.continuous_loop,
        "loop_iterations": loop_history,
        "risk_level": decision.risk_level,
        "agent_squad": dec_dict["agent_squad"],
        "stage_count": len(stages),
        "stages": stages,
        "message_ko": (
            f"GuildMaster & Cleric 오토파일럿 보스 관문({decision.profile}, 티어={decision.rigor_tier}) 전 단계({len(stages)}개) 검증을 통과했습니다."
            if all_passed
            else f"오토파일럿 보스 관문 차단: 실패 단계 {[s['stage'] for s in stages if s['status'] != 'PASS']}"
        ),
    }

    if apply:
        ensure_local_git_exclude(resolved)
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


evaluate_autopilot_gate = run_autopilot_gate


DEFAULT_BLAST_RADIUS_REL = "evidence/blast-radius-report.json"
DEFAULT_METRIC_CLIMB_LEDGER_REL = "evidence/metric-climb-ledger.json"
DEFAULT_METRIC_CLIMB_TSV_REL = "evidence/metric-climb-results.tsv"

_PY_TOP_SYMBOL_RE = re.compile(r"^(?:async\s+def|def|class)\s+([A-Za-z][A-Za-z0-9_]*)\b", re.MULTILINE)
_TS_EXPORT_SYMBOL_RE = re.compile(
    r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|class|interface|type|const|let|var|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_TS_EXPORT_LIST_RE = re.compile(r"\bexport\s+(?:type\s+)?\{([^}]+)\}")
_TS_IMPORT_FROM_RE = re.compile(r"""\b(?:import|export)\b[^;]*?\bfrom\s+['"]([^'"]+)['"]""")
_RUST_PUB_SYMBOL_RE = re.compile(
    r"\bpub(?:\s*\([^)]*\))?\s+(?:async\s+)?(?:fn|struct|enum|trait|type|const|mod)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_GO_EXPORT_SYMBOL_RE = re.compile(
    r"^(?:func(?:\s*\([^)]*\))?|type|var|const)\s+([A-Z][A-Za-z0-9_]*)\b",
    re.MULTILINE,
)
_BOUNDARY_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api-http", re.compile(r"\b(fetch|axios|urllib|http\.client|FastAPI|APIRouter|Response)\b")),
    ("database-sql", re.compile(r"\b(SELECT\s+|INSERT\s+INTO|UPDATE\s+|sqlite3|prisma|sqlalchemy)\b", re.IGNORECASE)),
    ("serialization-wire", re.compile(r"\b(json\.dumps|json\.loads|JSON\.stringify|JSON\.parse|protobuf)\b")),
    ("subprocess-cli", re.compile(r"\b(subprocess\.run|subprocess\.Popen|child_process|argparse)\b")),
    ("security-auth", re.compile(r"\b(jwt|token|password|secret|hmac|hashlib|authorization)\b", re.IGNORECASE)),
)


def _extract_defined_symbols(fpath: Path, text: str, *, precomputed_skeleton: str | None = None) -> list[str]:
    """파일에서 정의된 공개 함수·클래스·인터페이스·구조체 심볼 목록을 주석/문자열 오탐 없이 추출한다."""
    suffix = fpath.suffix.lower()
    symbols: list[str] = []
    if suffix == ".py":
        for m in _PY_TOP_SYMBOL_RE.finditer(text):
            sym = m.group(1)
            if sym not in symbols:
                symbols.append(sym)
    elif suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        skel = precomputed_skeleton if precomputed_skeleton is not None else _mask_c_comments_and_strings(text)
        for m in _TS_EXPORT_SYMBOL_RE.finditer(skel):
            sym = m.group(1)
            if sym not in symbols:
                symbols.append(sym)
        for m_list in _TS_EXPORT_LIST_RE.finditer(skel):
            for raw_item in m_list.group(1).split(","):
                cleaned = raw_item.strip()
                if not cleaned:
                    continue
                parts = [p.strip() for p in re.split(r"\bas\b", cleaned) if p.strip()]
                candidate = parts[-1].lstrip("type ").strip() if parts else ""
                if candidate and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", candidate) and candidate not in symbols:
                    symbols.append(candidate)
    elif suffix == ".rs":
        skel = (
            precomputed_skeleton
            if precomputed_skeleton is not None
            else _mask_c_comments_and_strings(text, is_rust=True)
        )
        for m in _RUST_PUB_SYMBOL_RE.finditer(skel):
            sym = m.group(1)
            if sym not in symbols:
                symbols.append(sym)
    elif suffix == ".go":
        skel = precomputed_skeleton if precomputed_skeleton is not None else _mask_c_comments_and_strings(text)
        for m in _GO_EXPORT_SYMBOL_RE.finditer(skel):
            sym = m.group(1)
            if sym not in symbols:
                symbols.append(sym)
    return symbols


def _matches_ts_import_target(importer_rel: str, import_spec: str, target_rels: list[str]) -> list[str]:
    """TS/JS import 경로(상대 경로 및 @/ 별칭)가 변경 대상 파일을 가리키는지 판별한다."""
    spec_clean = re.sub(r"\.(?:ts|tsx|js|jsx|mjs|cjs)$", "", import_spec.strip())
    if not spec_clean:
        return []
    importer_dir = PurePosixPath(importer_rel).parent
    resolved_spec: str | None = None
    if spec_clean.startswith("."):
        parts: list[str] = list(importer_dir.parts) if str(importer_dir) != "." else []
        for seg in PurePosixPath(spec_clean).parts:
            if seg == ".":
                continue
            if seg == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(seg)
        resolved_spec = "/".join(parts)
    elif spec_clean.startswith("@/") or spec_clean.startswith("~/"):
        resolved_spec = spec_clean[2:]

    matched_targets: list[str] = []
    for t_rel in target_rels:
        t_no_ext = re.sub(r"\.(?:ts|tsx|js|jsx|mjs|cjs)$", "", t_rel)
        t_stem = PurePosixPath(t_no_ext).name
        if resolved_spec is not None:
            if (
                t_no_ext == resolved_spec
                or t_no_ext == f"src/{resolved_spec}"
                or t_no_ext.endswith(f"/{resolved_spec}")
                or (t_stem == "index" and str(PurePosixPath(t_no_ext).parent) == resolved_spec)
            ):
                matched_targets.append(f"module:{PurePosixPath(t_rel).stem}")
    return matched_targets


def analyze_blast_radius(
    root: Path,
    *,
    target_files: list[str] | tuple[str, ...] = (),
    test_command: list[str] | tuple[str, ...] = (),
    apply: bool = False,
) -> dict[str, object]:
    """Archmage & Cleric 폭발 반경(Blast Radius) 분석기: 대상 파일의 심볼 참조(1-Hop/2-Hop), 시스템 경계 교차, 5단계 안전 증명 등급을 산출한다."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    all_files = _iter_auditable_files(resolved)
    code_files = [
        f for f in all_files if f.suffix.lower() in (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs", ".go")
    ]

    normalized_targets: list[str] = [PurePosixPath(t).as_posix() for t in target_files if t.strip()]
    if not normalized_targets:
        normalized_targets = [
            f.relative_to(resolved).as_posix()
            for f in code_files
            if "test" not in f.name.lower()
        ][:5]

    file_paths: dict[str, Path] = {}
    file_texts: dict[str, str] = {}
    file_skeletons: dict[str, str] = {}
    for fpath in code_files:
        rel = fpath.relative_to(resolved).as_posix()
        suffix = fpath.suffix.lower()
        txt = fpath.read_text(encoding="utf-8", errors="replace")
        file_paths[rel] = fpath
        file_texts[rel] = txt
        file_skeletons[rel] = (
            txt if suffix == ".py" else _mask_c_comments_and_strings(txt, is_rust=(suffix == ".rs"))
        )

    exported_by_targets: dict[str, list[str]] = {}
    target_symbol_set: set[str] = set()
    for t_rel in normalized_targets:
        t_path = file_paths.get(t_rel)
        t_txt = file_texts.get(t_rel)
        t_skel = file_skeletons.get(t_rel)
        syms = (
            _extract_defined_symbols(t_path, t_txt, precomputed_skeleton=t_skel)
            if (t_path is not None and t_txt is not None)
            else []
        )
        exported_by_targets[t_rel] = syms
        target_symbol_set.update(syms)

    direct_dependents: list[dict[str, object]] = []
    direct_rel_set: set[str] = set()
    linked_test_files: list[str] = []

    target_sym_re = (
        re.compile(r"\b(?:" + "|".join(re.escape(s) for s in sorted(target_symbol_set)) + r")\b")
        if target_symbol_set
        else None
    )

    for rel, txt in file_texts.items():
        if rel in normalized_targets:
            continue
        skel = file_skeletons[rel]
        matched_syms: list[str] = sorted(set(target_sym_re.findall(skel))) if target_sym_re is not None else []
        suffix = file_paths[rel].suffix.lower()
        if suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            cm_txt = _mask_c_comments(txt)
            for imp_m in _TS_IMPORT_FROM_RE.finditer(cm_txt):
                for mod_hit in _matches_ts_import_target(rel, imp_m.group(1), normalized_targets):
                    if mod_hit not in matched_syms:
                        matched_syms.append(mod_hit)
        if matched_syms:
            direct_rel_set.add(rel)
            is_test = _is_test_or_check_file(rel, file_paths[rel])
            if is_test:
                linked_test_files.append(rel)
            boundaries = [b_name for b_name, b_re in _BOUNDARY_SIGNALS if b_re.search(skel)]
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
            d_path = file_paths.get(d_rel)
            d_txt = file_texts.get(d_rel)
            d_skel = file_skeletons.get(d_rel)
            if d_path is not None and d_txt is not None:
                hop1_symbols.update(_extract_defined_symbols(d_path, d_txt, precomputed_skeleton=d_skel))

    transitive_dependents: list[str] = []
    hop1_rel_list = sorted(d_rel for d_rel in direct_rel_set if d_rel not in linked_test_files)
    hop1_sym_re = (
        re.compile(r"\b(?:" + "|".join(re.escape(s) for s in sorted(hop1_symbols)) + r")\b")
        if hop1_symbols
        else None
    )
    for rel, txt in file_texts.items():
        if rel in normalized_targets or rel in direct_rel_set:
            continue
        skel = file_skeletons[rel]
        hit = hop1_sym_re is not None and hop1_sym_re.search(skel) is not None
        if not hit and file_paths[rel].suffix.lower() in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs") and hop1_rel_list:
            cm_txt = _mask_c_comments(txt)
            for imp_m in _TS_IMPORT_FROM_RE.finditer(cm_txt):
                if _matches_ts_import_target(rel, imp_m.group(1), hop1_rel_list):
                    hit = True
                    break
        if hit:
            transitive_dependents.append(rel)
            if _is_test_or_check_file(rel, file_paths[rel]) and rel not in linked_test_files:
                linked_test_files.append(rel)

    recommended_test_commands: list[str] = []
    for t_file in sorted(linked_test_files):
        t_suf = PurePosixPath(t_file).suffix.lower()
        if t_suf == ".py":
            mod_name = t_file[:-3].replace("/", ".")
            cmd_str = f"python -m unittest {mod_name}"
        elif t_suf in (".ts", ".tsx", ".js", ".jsx"):
            cmd_str = f"npx vitest run {t_file}"
        elif t_suf == ".rs":
            cmd_str = "cargo test"
        elif t_suf == ".go":
            parent_p = str(PurePosixPath(t_file).parent)
            cmd_str = f"go test ./{parent_p}" if parent_p != "." else "go test ./..."
        else:
            continue
        if cmd_str not in recommended_test_commands:
            recommended_test_commands.append(cmd_str)

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
        "recommended_test_commands": recommended_test_commands,
        "safety_proof_level": proof_level,
        "safety_proof_label": proof_label,
        "message_ko": (
            f"폭발 반경 분석 완료: 1차 영향 파일 {len(direct_dependents)}개, "
            f"2차 전이 파일 {len(transitive_dependents)}개, 추천 타깃 테스트 {len(recommended_test_commands)}개, "
            f"안전 증명 등급 {proof_level}단계({proof_label})."
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
    auto_rollback: bool = False,
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

    norm_immutables = sorted({PurePosixPath(p).as_posix() for p in immutable_files if p.strip()} | set(immutable_baseline.keys()))
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

    rolled_back = False
    checkpoint_id: str | None = None
    if apply:
        try:
            from . import checkpoint_manager
        except ImportError:
            import checkpoint_manager  # type: ignore[no-redef]

        if verdict == "KEEP" and norm_targets:
            ckpt_res = checkpoint_manager.create_checkpoint(
                resolved,
                norm_targets,
                label=f"metric-keep-{config_hash}",
                apply=True,
            )
            ckpt_obj = ckpt_res.get("checkpoint")
            if isinstance(ckpt_obj, dict):
                checkpoint_id = str(ckpt_obj.get("checkpoint_id") or "")
        elif verdict == "DISCARD" and auto_rollback:
            try:
                rest_res = checkpoint_manager.restore_checkpoint(resolved, "latest", apply=True)
                rolled_back = rest_res.get("status") == "PASS"
                checkpoint_id = str(rest_res.get("checkpoint_id") or "")
            except ValueError:
                rolled_back = False

        entry_doc["auto_rolled_back"] = rolled_back
        entry_doc["checkpoint_id"] = checkpoint_id
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

