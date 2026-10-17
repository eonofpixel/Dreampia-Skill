"""Dreampia 무의존성 AST·렉서 기반 뮤테이션 테스팅 엔진 (Testing the AI's Tests).

AI가 작성한 테스트가 프로덕션 코드의 실제 로직 변조(산술, 비교, 불리언, 반환값 변이)를
잡아내는지 격리 샌드박스에서 검증하여 가짜 단언문(Self-Deception)을 적발한다.

SOLID 아키텍처:
- MutationSite / MutantTrialResult: 변이 후보 및 실행 결과 불변 값 객체 (SRP)
- SourceMutator: 언어별 변이 생성 추상 프로토콜 (OCP/DIP)
- PythonAstLineMutator: Python AST 기반 구문 안전 변이 생성기 (LSP)
- CFamilyLexicalMutator: 주석·문자열 마스킹 기반 TS/JS/Rust/Go 변이 생성기 (LSP)
- SandboxMutationRunner: 원본 작업 트리 100% 무오염 임시 샌드박스 실행기 (SRP/ISP)
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from typing import Protocol

try:
    from . import autopilot_engine
except ImportError:
    import autopilot_engine  # type: ignore[no-redef]

MUTATION_ENGINE_VERSION = "0.7.5"
DEFAULT_MUTATION_REPORT_REL = "evidence/mutation-report.json"

_SANDBOX_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".harness",
        ".dreampia-install",
        ".dreampia",
        ".dreampia-skill",
        "__pycache__",
        "node_modules",
        ".next",
        ".venv",
        "venv",
        "dist",
        "build",
        "target",
    }
)


@dataclass(frozen=True)
class MutationSite:
    """단일 코드 변이(Mutant) 후보 정의."""

    mutant_id: str
    file_path: str
    line: int
    operator: str
    description_ko: str
    original_snippet: str
    mutated_snippet: str
    mutated_source: str


@dataclass(frozen=True)
class MutantTrialResult:
    """단일 변이 테스트 실행 판정 결과."""

    mutant_id: str
    file_path: str
    line: int
    operator: str
    description_ko: str
    status: str
    original_snippet: str
    mutated_snippet: str
    elapsed_ms: float

    def to_dict(self) -> dict[str, object]:
        """판정 결과를 딕셔너리로 직렬화한다."""
        return {
            "mutant_id": self.mutant_id,
            "file_path": self.file_path,
            "line": self.line,
            "operator": self.operator,
            "description_ko": self.description_ko,
            "status": self.status,
            "original_snippet": self.original_snippet,
            "mutated_snippet": self.mutated_snippet,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


class SourceMutator(Protocol):
    """소스 코드에서 변이 후보를 생성하는 추상 인터페이스 (DIP/OCP)."""

    def generate_mutants(
        self,
        rel_path: str,
        source_text: str,
        max_mutants: int = 15,
    ) -> list[MutationSite]:
        """지정된 소스 파일에서 최대 max_mutants개의 구문 유효 변이를 생성한다."""
        ...


_PY_LINE_MUTATION_RULES: tuple[tuple[str, re.Pattern[str], str, str], ...] = (
    ("ROR", re.compile(r"(?<![=!<>])==(?!=)"), "!=", "동등 비교(==)를 부등 비교(!=)로 변이"),
    ("ROR", re.compile(r"!=(?!=)"), "==", "부등 비교(!=)를 동등 비교(==)로 변이"),
    ("ROR", re.compile(r">="), "<", "이상 비교(>=)를 미만 비교(<)로 변이"),
    ("ROR", re.compile(r"<="), ">", "이하 비교(<=)를 초과 비교(>)로 변이"),
    ("AOR", re.compile(r"(?<=[\w\)\s])\s\+\s(?=[\w\(])"), " - ", "덧셈(+) 연산을 뺄셈(-)으로 변이"),
    ("AOR", re.compile(r"(?<=[\w\)\s])\s-\s(?=[\w\(])"), " + ", "뺄셈(-) 연산을 덧셈(+)으로 변이"),
    ("AOR", re.compile(r"(?<=[\w\)\s])\s\*\s(?=[\w\(])"), " // ", "곱셈(*) 연산을 나눗셈(//)으로 변이"),
    ("LCR", re.compile(r"\bTrue\b"), "False", "불리언 True를 False로 변이"),
    ("LCR", re.compile(r"\bFalse\b"), "True", "불리언 False를 True로 변이"),
)


def _collect_py_executable_lines(tree: ast.AST) -> set[int]:
    """Python AST에서 실제 함수 내부의 실행 가능한 문장(산술/비교/반환/분기) 줄 번호를 수집한다."""
    target_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, (ast.BinOp, ast.Compare, ast.BoolOp, ast.Return, ast.If)):
                    lineno = getattr(child, "lineno", None)
                    if isinstance(lineno, int):
                        target_lines.add(lineno)
    return target_lines


class PythonAstLineMutator:
    """Python AST 검증을 결합해 구문 오류가 없는 안전한 변이만 생성하는 변이기."""

    def generate_mutants(
        self,
        rel_path: str,
        source_text: str,
        max_mutants: int = 15,
    ) -> list[MutationSite]:
        """Python 소스에서 실행 가능한 라인을 대상으로 구문 유효 변이를 생성한다."""
        try:
            tree = ast.parse(source_text, filename=rel_path)
        except SyntaxError:
            return []

        exec_lines = _collect_py_executable_lines(tree)
        lines = source_text.splitlines(keepends=True)
        mutants: list[MutationSite] = []

        for line_idx, raw_line in enumerate(lines):
            lineno = line_idx + 1
            if lineno not in exec_lines:
                continue
            stripped = raw_line.strip()
            if not stripped or stripped.startswith(("#", "def ", "async def ", "class ", "@")):
                continue
            code_part = raw_line.split("#", 1)[0]

            for op_kind, pattern, replacement, desc_ko in _PY_LINE_MUTATION_RULES:
                if len(mutants) >= max_mutants:
                    return mutants
                match = pattern.search(code_part)
                if not match:
                    continue
                mutated_code = code_part[: match.start()] + replacement + code_part[match.end() :]
                comment_suffix = raw_line[len(code_part) :]
                new_line = mutated_code + comment_suffix
                if new_line == raw_line:
                    continue
                candidate_lines = list(lines)
                candidate_lines[line_idx] = new_line
                mutated_source = "".join(candidate_lines)
                try:
                    ast.parse(mutated_source, filename=rel_path)
                except SyntaxError:
                    continue
                mutants.append(
                    MutationSite(
                        mutant_id=f"MUT-{len(mutants) + 1:03d}",
                        file_path=rel_path,
                        line=lineno,
                        operator=op_kind,
                        description_ko=desc_ko,
                        original_snippet=stripped,
                        mutated_snippet=new_line.strip(),
                        mutated_source=mutated_source,
                    )
                )
        return mutants


_CFAMILY_MUTATION_RULES: tuple[tuple[str, re.Pattern[str], str, str], ...] = (
    ("ROR", re.compile(r"==="), "!==", "엄격 동등(===)을 부등(!==)으로 변이"),
    ("ROR", re.compile(r"!=="), "===", "엄격 부등(!==)을 동등(===)으로 변이"),
    ("ROR", re.compile(r"(?<![=!<>])==(?!=)"), "!=", "동등(==)을 부등(!=)으로 변이"),
    ("ROR", re.compile(r"!=(?!=)"), "==", "부등(!=)을 동등(==)으로 변이"),
    ("ROR", re.compile(r">="), "<", "이상(>=)을 미만(<)으로 변이"),
    ("ROR", re.compile(r"<="), ">", "이하(<=)를 초과(>)로 변이"),
    ("AOR", re.compile(r"(?<=[\w\)\s])\s\+\s(?=[\w\(])"), " - ", "덧셈(+)을 뺄셈(-)으로 변이"),
    ("AOR", re.compile(r"(?<=[\w\)\s])\s-\s(?=[\w\(])"), " + ", "뺄셈(-)을 덧셈(+)으로 변이"),
    ("LCR", re.compile(r"\btrue\b"), "false", "불리언 true를 false로 변이"),
    ("LCR", re.compile(r"\bfalse\b"), "true", "불리언 false를 true로 변이"),
)


class CFamilyLexicalMutator:
    """TS/JS/Rust/Go 코드에서 주석과 문자열을 마스킹한 뒤 코드 영역 연산자만 안전하게 변이시킨다."""

    def generate_mutants(
        self,
        rel_path: str,
        source_text: str,
        max_mutants: int = 15,
    ) -> list[MutationSite]:
        """C-계열 소스에서 주석·문자열 밖의 연산자 위치를 찾아 변이 후보를 생성한다."""
        is_rust = rel_path.lower().endswith(".rs")
        skeleton = autopilot_engine._mask_c_comments_and_strings(source_text, is_rust=is_rust)
        orig_lines = source_text.splitlines(keepends=True)
        skel_lines = skeleton.splitlines(keepends=True)
        mutants: list[MutationSite] = []

        for line_idx, (orig_line, skel_line) in enumerate(zip(orig_lines, skel_lines)):
            lineno = line_idx + 1
            stripped_skel = skel_line.strip()
            if not stripped_skel or stripped_skel.startswith(("import ", "export type ", "type ", "interface ", "use ", "package ")):
                continue
            for op_kind, pattern, replacement, desc_ko in _CFAMILY_MUTATION_RULES:
                if len(mutants) >= max_mutants:
                    return mutants
                match = pattern.search(skel_line)
                if not match:
                    continue
                new_line = orig_line[: match.start()] + replacement + orig_line[match.end() :]
                if new_line == orig_line:
                    continue
                candidate_lines = list(orig_lines)
                candidate_lines[line_idx] = new_line
                mutants.append(
                    MutationSite(
                        mutant_id=f"MUT-{len(mutants) + 1:03d}",
                        file_path=rel_path,
                        line=lineno,
                        operator=op_kind,
                        description_ko=desc_ko,
                        original_snippet=orig_line.strip(),
                        mutated_snippet=new_line.strip(),
                        mutated_source="".join(candidate_lines),
                    )
                )
        return mutants


def _copy_project_to_sandbox(project_root: Path, sandbox_root: Path) -> None:
    """원본 워크스페이스 오염을 방지하기 위해 필수 소스/테스트 파일만 임시 샌드박스로 복사한다."""
    for current_root, dirs, filenames in os.walk(project_root, topdown=True, followlinks=False):
        rel_dir = Path(current_root).relative_to(project_root)
        dirs[:] = [
            d
            for d in dirs
            if d not in _SANDBOX_IGNORE_DIRS and not (Path(current_root) / d).is_symlink()
        ]
        target_dir = sandbox_root / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        for fname in filenames:
            src_file = Path(current_root) / fname
            if src_file.is_symlink() or not src_file.is_file():
                continue
            shutil.copy2(src_file, target_dir / fname)


def _execute_test_cmd(sandbox_root: Path, test_command: str, timeout_sec: float) -> tuple[int, float]:
    """샌드박스 디렉터리 내에서 테스트 명령을 실행하고 (종료코드, 소요시간 ms)를 반환한다."""
    raw_args = shlex.split(test_command, posix=(os.name != "nt"))
    args = [
        tok[1:-1] if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ("'", '"') else tok
        for tok in raw_args
    ]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    t0 = time.perf_counter()
    proc = subprocess.run(
        args,
        cwd=str(sandbox_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return proc.returncode, elapsed_ms


def _resolve_smart_test_command(
    project_root: Path,
    target_files: list[str],
    test_command: str,
) -> tuple[str, list[str]]:
    """전체 테스트 스위트 대신 변이 대상 모듈을 직접 검증하는 테스트 파일만 선별하여 실행 속도를 최적화한다."""
    cmd_norm = test_command.strip()
    if "unittest discover" not in cmd_norm:
        return cmd_norm, []

    matched_tests: list[str] = []
    for rel_raw in target_files:
        stem = Path(rel_raw).stem
        if not stem:
            continue
        for candidate in sorted(project_root.rglob(f"test_{stem}.py")):
            if candidate.is_file() and not candidate.is_symlink():
                rel_c = PurePosixPath(candidate.relative_to(project_root).as_posix()).as_posix()
                if rel_c not in matched_tests:
                    matched_tests.append(rel_c)

    if not matched_tests:
        return cmd_norm, []

    raw_args = shlex.split(cmd_norm, posix=(os.name != "nt"))
    py_exe = raw_args[0] if raw_args else "python"
    targeted_cmd = f"{py_exe} -m unittest " + " ".join(matched_tests)
    return targeted_cmd, matched_tests


class SandboxMutationRunner:
    """임시 샌드박스에서 변이를 하나씩 주입하며 테스트 스위트의 실제 방어력(Mutation Score)을 검증한다."""

    def __init__(self) -> None:
        self._py_mutator = PythonAstLineMutator()
        self._c_mutator = CFamilyLexicalMutator()

    def collect_mutants_for_files(
        self,
        project_root: Path,
        target_files: list[str],
        max_mutants: int = 15,
    ) -> list[MutationSite]:
        """대상 파일 목록에서 최대 max_mutants개의 변이 후보를 수집한다."""
        all_mutants: list[MutationSite] = []
        for rel_raw in target_files:
            if len(all_mutants) >= max_mutants:
                break
            rel_posix = PurePosixPath(rel_raw.replace("\\", "/")).as_posix()
            fpath = (project_root / rel_posix).resolve()
            if not fpath.is_file() or fpath.is_symlink():
                continue
            source_text = fpath.read_text(encoding="utf-8", errors="replace")
            remaining = max_mutants - len(all_mutants)
            mutator: SourceMutator = (
                self._py_mutator if fpath.suffix.lower() == ".py" else self._c_mutator
            )
            file_mutants = mutator.generate_mutants(rel_posix, source_text, max_mutants=remaining)
            for m in file_mutants:
                all_mutants.append(
                    MutationSite(
                        mutant_id=f"MUT-{len(all_mutants) + 1:03d}",
                        file_path=m.file_path,
                        line=m.line,
                        operator=m.operator,
                        description_ko=m.description_ko,
                        original_snippet=m.original_snippet,
                        mutated_snippet=m.mutated_snippet,
                        mutated_source=m.mutated_source,
                    )
                )
        return all_mutants

    def run_mutation_check(
        self,
        project_root: Path,
        target_files: list[str],
        test_command: str,
        *,
        max_mutants: int = 15,
        min_score: float = 0.8,
        timeout_sec: float = 10.0,
        apply: bool = False,
    ) -> dict[str, object]:
        """격리 샌드박스에서 뮤테이션 테스팅을 수행하고 생존 변이(가짜 테스트 구간) 리포트를 반환한다."""
        resolved = project_root.resolve()
        if not test_command.strip():
            raise ValueError("뮤테이션 검증을 실행할 테스트 명령(test_command)을 지정하십시오.")

        effective_cmd, matched_test_files = _resolve_smart_test_command(
            resolved, target_files, test_command
        )
        mutants = self.collect_mutants_for_files(resolved, target_files, max_mutants=max_mutants)
        trials: list[MutantTrialResult] = []

        with tempfile.TemporaryDirectory(prefix="dreampia-mut-") as tmp_dir:
            sandbox_root = Path(tmp_dir)
            _copy_project_to_sandbox(resolved, sandbox_root)

            try:
                base_rc, base_ms = _execute_test_cmd(sandbox_root, effective_cmd, timeout_sec)
            except subprocess.TimeoutExpired:
                base_rc, base_ms = -1, timeout_sec * 1000.0

            if base_rc != 0:
                return {
                    "action": "mutation-check",
                    "schema_version": MUTATION_ENGINE_VERSION,
                    "status": "FAIL",
                    "reason_code": "BASELINE_TEST_FAILED",
                    "baseline_elapsed_ms": round(base_ms, 2),
                    "message_ko": "변이 주입 전 원본 코드 기준 테스트가 이미 실패했습니다. 먼저 기본 테스트를 통과시키십시오.",
                }

            for site in mutants:
                sandbox_file = sandbox_root / site.file_path
                original_text = sandbox_file.read_text(encoding="utf-8", errors="replace")
                try:
                    sandbox_file.write_text(site.mutated_source, encoding="utf-8")
                    try:
                        rc, elapsed_ms = _execute_test_cmd(sandbox_root, effective_cmd, timeout_sec)
                        status = "KILLED" if rc != 0 else "SURVIVED"
                    except subprocess.TimeoutExpired:
                        status = "TIMEOUT"
                        elapsed_ms = timeout_sec * 1000.0
                finally:
                    sandbox_file.write_text(original_text, encoding="utf-8")

                trials.append(
                    MutantTrialResult(
                        mutant_id=site.mutant_id,
                        file_path=site.file_path,
                        line=site.line,
                        operator=site.operator,
                        description_ko=site.description_ko,
                        status=status,
                        original_snippet=site.original_snippet,
                        mutated_snippet=site.mutated_snippet,
                        elapsed_ms=elapsed_ms,
                    )
                )

        killed = sum(1 for t in trials if t.status == "KILLED")
        timed_out = sum(1 for t in trials if t.status == "TIMEOUT")
        survived = sum(1 for t in trials if t.status == "SURVIVED")
        total = len(trials)
        score = round((killed + timed_out) / total, 4) if total > 0 else 1.0
        passed = score >= min_score

        report: dict[str, object] = {
            "action": "mutation-check",
            "schema_version": MUTATION_ENGINE_VERSION,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": "PASS" if passed else "FAIL",
            "applied": apply,
            "report_path": DEFAULT_MUTATION_REPORT_REL if apply else None,
            "target_files": target_files,
            "test_command": test_command,
            "effective_test_command": effective_cmd,
            "targeted_test_files": matched_test_files,
            "total_mutants": total,
            "killed_count": killed,
            "timeout_count": timed_out,
            "survived_count": survived,
            "mutation_score": score,
            "min_required_score": min_score,
            "survived_mutants": [t.to_dict() for t in trials if t.status == "SURVIVED"],
            "trials": [t.to_dict() for t in trials],
            "message_ko": (
                f"뮤테이션 테스팅 통과: 변이 방어율(Mutation Score)={score * 100:.1f}% "
                f"(사살 {killed + timed_out}/{total}건, 생존 {survived}건)"
                if passed
                else (
                    f"뮤테이션 테스팅 실패(가짜·부실 테스트 경고): 변이 방어율={score * 100:.1f}% < 목표 {min_score * 100:.1f}% "
                    f"(생존 변이 {survived}건 — 코드가 변조되었음에도 테스트가 그대로 통과했습니다)"
                )
            ),
        }
        canonical = json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
        report["report_sha256"] = hashlib.sha256(canonical).hexdigest()

        if apply:
            autopilot_engine.ensure_local_git_exclude(resolved)
            out_path = resolved / DEFAULT_MUTATION_REPORT_REL
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return report


def run_mutation_check(
    project_root: Path,
    target_files: list[str],
    test_command: str,
    *,
    max_mutants: int = 15,
    min_score: float = 0.8,
    timeout_sec: float = 10.0,
    apply: bool = False,
) -> dict[str, object]:
    """뮤테이션 테스팅 실행 진입점."""
    runner = SandboxMutationRunner()
    return runner.run_mutation_check(
        project_root,
        target_files,
        test_command,
        max_mutants=max_mutants,
        min_score=min_score,
        timeout_sec=timeout_sec,
        apply=apply,
    )
