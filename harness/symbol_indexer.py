"""Dreampia 무의존성 다국어 시맨틱 심볼 맵 및 슬라이서 (Serena MCP / ast-grep 패턴).

대용량 파일 전체를 컨텍스트로 읽어 토큰을 낭비(Blind Context Stuffing)하지 않도록:
1. symbol-map: 클래스·인터페이스·함수·메서드의 시그니처와 정확한 줄 범위(L10-L55) 목차만 추출해 토큰 75%+ 절감
2. symbol-slice: 특정 심볼 이름만 지정하면 해당 함수/클래스 본문 구간만 정확히 발췌 반환

SOLID 아키텍처:
- SymbolDescriptor: 단일 심볼 메타데이터 불변 값 객체 (SRP)
- LanguageSymbolExtractor: 언어별 심볼 추출 추상 프로토콜 (OCP/DIP)
- PythonAstSymbolExtractor: Python 표준 ast 기반 정밀 추출기 (LSP)
- CFamilySymbolExtractor: 주석 마스킹 및 중괄호 밸런스 파서 기반 TS/JS/Rust/Go 추출기 (LSP)
- SymbolNavigationService: 심볼 맵 생성 및 부분 슬라이싱 서비스 (SRP/ISP)
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import time
from typing import Protocol

try:
    from . import autopilot_engine
except ImportError:
    import autopilot_engine  # type: ignore[no-redef]

SYMBOL_INDEXER_VERSION = "0.8.0"


@dataclass(frozen=True)
class SymbolDescriptor:
    """소스 파일 내 단일 심볼(클래스, 인터페이스, 함수, 메서드) 명세."""

    name: str
    qualified_name: str
    kind: str
    signature: str
    start_line: int
    end_line: int
    line_count: int
    docstring_summary: str
    calls: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """심볼 명세를 JSON 직렬화 가능한 딕셔너리로 변환한다."""
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "signature": self.signature,
            "line_range": f"L{self.start_line}-L{self.end_line}",
            "start_line": self.start_line,
            "end_line": self.end_line,
            "line_count": self.line_count,
            "docstring_summary": self.docstring_summary,
            "calls": list(self.calls),
        }


class LanguageSymbolExtractor(Protocol):
    """소스 텍스트에서 심볼 목록을 추출하는 추상 프로토콜 (DIP/OCP)."""

    def extract_symbols(self, source_text: str, suffix: str) -> list[SymbolDescriptor]:
        """소스 코드에서 계층적 심볼 목록을 추출해 줄 번호 순으로 반환한다."""
        ...


def _collect_py_calls(node: ast.AST, max_calls: int = 8) -> tuple[str, ...]:
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            cname = ""
            if isinstance(child.func, ast.Name):
                cname = child.func.id
            elif isinstance(child.func, ast.Attribute):
                cname = child.func.attr
            if cname and cname not in calls:
                calls.append(cname)
                if len(calls) >= max_calls:
                    break
    return tuple(calls)


def _format_py_signature(node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str]) -> str:
    idx = max(0, node.lineno - 1)
    header = lines[idx].strip() if idx < len(lines) else f"def {node.name}(...):"
    if header.endswith(":"):
        header = header[:-1].strip()
    return header


class PythonAstSymbolExtractor:
    """Python 표준 ast.parse를 사용하여 클래스·함수·메서드 시그니처와 줄 범위를 추출한다."""

    def extract_symbols(self, source_text: str, _suffix: str = ".py") -> list[SymbolDescriptor]:
        """Python 코드에서 최상위 클래스, 메서드, 함수를 추출한다."""
        try:
            tree = ast.parse(source_text)
        except SyntaxError:
            return []

        lines = source_text.splitlines()
        symbols: list[SymbolDescriptor] = []

        for node in getattr(tree, "body", []):
            if isinstance(node, ast.ClassDef):
                start_l = node.lineno
                end_l = getattr(node, "end_lineno", None) or start_l
                doc = (ast.get_docstring(node) or "").splitlines()
                doc_first = doc[0].strip() if doc else ""
                sig = lines[start_l - 1].strip().rstrip(":") if start_l <= len(lines) else f"class {node.name}"
                symbols.append(
                    SymbolDescriptor(
                        name=node.name,
                        qualified_name=node.name,
                        kind="class",
                        signature=sig,
                        start_line=start_l,
                        end_line=end_l,
                        line_count=max(1, end_l - start_l + 1),
                        docstring_summary=doc_first,
                        calls=(),
                    )
                )
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_start = item.lineno
                        m_end = getattr(item, "end_lineno", None) or m_start
                        m_doc = (ast.get_docstring(item) or "").splitlines()
                        m_doc_first = m_doc[0].strip() if m_doc else ""
                        symbols.append(
                            SymbolDescriptor(
                                name=item.name,
                                qualified_name=f"{node.name}.{item.name}",
                                kind="method",
                                signature=_format_py_signature(item, lines),
                                start_line=m_start,
                                end_line=m_end,
                                line_count=max(1, m_end - m_start + 1),
                                docstring_summary=m_doc_first,
                                calls=_collect_py_calls(item),
                            )
                        )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f_start = node.lineno
                f_end = getattr(node, "end_lineno", None) or f_start
                f_doc = (ast.get_docstring(node) or "").splitlines()
                f_doc_first = f_doc[0].strip() if f_doc else ""
                symbols.append(
                    SymbolDescriptor(
                        name=node.name,
                        qualified_name=node.name,
                        kind="function",
                        signature=_format_py_signature(node, lines),
                        start_line=f_start,
                        end_line=f_end,
                        line_count=max(1, f_end - f_start + 1),
                        docstring_summary=f_doc_first,
                        calls=_collect_py_calls(node),
                    )
                )
        return symbols


_IDENT_PAT = r"[A-Za-z_$\uac00-\ud7a3][A-Za-z0-9_$\uac00-\ud7a3]*"

_CFAMILY_DECL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "class",
        re.compile(rf"^[ \t]*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+({_IDENT_PAT})[^{{]*\{{", re.MULTILINE),
    ),
    (
        "interface",
        re.compile(rf"^[ \t]*(?:export\s+)?interface\s+({_IDENT_PAT})[^{{]*\{{", re.MULTILINE),
    ),
    (
        "struct",
        re.compile(rf"^[ \t]*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|type)\s+({_IDENT_PAT})(?:\s+struct|\s+interface)?[^{{;]*\{{", re.MULTILINE),
    ),
    (
        "function",
        re.compile(
            rf"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:pub(?:\([^)]*\))?\s+)?(?:fn|function|func)\s+(?:\([^)]*\)\s*)?({_IDENT_PAT})\s*(?:<[^>]*>)?\s*\([^{{;]*\{{",
            re.MULTILINE,
        ),
    ),
    (
        "function",
        re.compile(
            rf"^[ \t]*(?:export\s+)?(?:const|let)\s+({_IDENT_PAT})\s*(?::[^=]+)?=\s*(?:async\s*)?\([^)]*\)\s*(?::[^=]+)?=>\s*\{{",
            re.MULTILINE,
        ),
    ),
)

_CALL_IDENT_RE = re.compile(rf"\b({_IDENT_PAT})\s*\(")
_CALL_STOPWORDS: frozenset[str] = frozenset(
    {"if", "for", "while", "switch", "catch", "return", "sizeof", "typeof", "function", "fn", "func"}
)


class CFamilySymbolExtractor:
    """주석·문자열 마스킹과 중괄호 밸런스 파서를 결합하여 TS/JS/Rust/Go 심볼 구간을 추출한다."""

    def extract_symbols(self, source_text: str, suffix: str) -> list[SymbolDescriptor]:
        """C-계열 언어 파일에서 선언부와 닫는 중괄호 라인 범위를 정확히 추출한다."""
        is_rust = suffix.lower() == ".rs"
        skeleton = autopilot_engine._mask_c_comments_and_strings(source_text, is_rust=is_rust)
        orig_lines = source_text.splitlines()
        symbols: list[SymbolDescriptor] = []
        seen_spans: set[tuple[str, int]] = set()

        for kind, pattern in _CFAMILY_DECL_PATTERNS:
            for match in pattern.finditer(skeleton):
                sym_name = match.group(1)
                open_brace = match.end() - 1
                close_brace = autopilot_engine._find_matching_delimiter(skeleton, open_brace, "{", "}")
                if close_brace is None:
                    continue
                start_line = skeleton[: match.start()].count("\n") + 1
                end_line = skeleton[:close_brace].count("\n") + 1
                key = (sym_name, start_line)
                if key in seen_spans:
                    continue
                seen_spans.add(key)

                sig_line = orig_lines[start_line - 1].strip() if start_line <= len(orig_lines) else sym_name
                if sig_line.endswith("{"):
                    sig_line = sig_line[:-1].strip()

                body_skel = skeleton[open_brace + 1 : close_brace]
                calls: list[str] = []
                for cm in _CALL_IDENT_RE.finditer(body_skel):
                    ident = cm.group(1)
                    if ident not in _CALL_STOPWORDS and ident != sym_name and ident not in calls:
                        calls.append(ident)
                        if len(calls) >= 8:
                            break

                symbols.append(
                    SymbolDescriptor(
                        name=sym_name,
                        qualified_name=sym_name,
                        kind=kind,
                        signature=sig_line,
                        start_line=start_line,
                        end_line=end_line,
                        line_count=max(1, end_line - start_line + 1),
                        docstring_summary="",
                        calls=tuple(calls),
                    )
                )

        symbols.sort(key=lambda s: (s.start_line, s.end_line))
        return symbols


def _extract_file_symbols(fpath: Path, source_text: str) -> list[SymbolDescriptor]:
    suffix = fpath.suffix.lower()
    extractor: LanguageSymbolExtractor = (
        PythonAstSymbolExtractor() if suffix == ".py" else CFamilySymbolExtractor()
    )
    return extractor.extract_symbols(source_text, suffix)


def build_symbol_map(project_root: Path, target_rel: str) -> dict[str, object]:
    """파일 전체를 읽지 않고도 구조를 파악할 수 있도록 심볼 목차(시그니처 및 줄 번호 범위)를 생성한다."""
    t0 = time.perf_counter()
    resolved = project_root.resolve()
    clean_rel = (target_rel or "").strip()
    if not clean_rel:
        raise ValueError("심볼 맵을 추출할 대상 파일 경로(--target)를 지정하십시오.")

    target_path = (resolved / clean_rel).resolve()
    if target_path.is_symlink() or not target_path.exists():
        raise ValueError(f"대상 경로를 찾을 수 없습니다: {clean_rel}")
    if target_path != resolved and resolved not in target_path.parents:
        raise ValueError("프로젝트 루트 외부 경로는 조회할 수 없습니다.")

    if target_path.is_dir():
        files = [
            p for p in sorted(target_path.rglob("*"))
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go")
        ][:25]
    else:
        files = [target_path]

    file_maps: list[dict[str, object]] = []
    total_raw_chars = 0
    total_toc_chars = 0
    total_symbols = 0

    for fpath in files:
        rel_posix = PurePosixPath(fpath.relative_to(resolved).as_posix()).as_posix()
        text = fpath.read_text(encoding="utf-8", errors="replace")
        total_raw_chars += len(text)
        syms = _extract_file_symbols(fpath, text)
        total_symbols += len(syms)
        toc_lines = [f"L{s.start_line}-L{s.end_line}: {s.signature}" for s in syms]
        toc_text = "\n".join(toc_lines)
        total_toc_chars += len(toc_text)
        file_maps.append(
            {
                "file": rel_posix,
                "total_lines": len(text.splitlines()),
                "symbol_count": len(syms),
                "toc_compact": toc_lines,
                "symbols": [s.to_dict() for s in syms],
            }
        )

    reduction_ratio = (
        round(max(0.0, 1.0 - (total_toc_chars / total_raw_chars)), 4)
        if total_raw_chars > 0
        else 0.0
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return {
        "action": "symbol-map",
        "schema_version": SYMBOL_INDEXER_VERSION,
        "status": "PASS",
        "target": clean_rel,
        "file_count": len(file_maps),
        "total_symbols": total_symbols,
        "raw_char_count": total_raw_chars,
        "compact_toc_char_count": total_toc_chars,
        "token_reduction_ratio": reduction_ratio,
        "elapsed_ms": elapsed_ms,
        "files": file_maps,
        "message_ko": (
            f"시맨틱 심볼 맵 추출 완료: 파일 {len(file_maps)}개, 심볼 {total_symbols}개 "
            f"(컨텍스트 크기 {reduction_ratio * 100:.1f}% 절감, 소요시간 {elapsed_ms}ms)"
        ),
    }


def extract_symbol_slice(
    project_root: Path,
    target_rel: str,
    symbol_query: str,
) -> dict[str, object]:
    """지정된 파일에서 요청한 심볼(함수·메서드·클래스)의 시작~종료 줄 본문만 정확히 슬라이싱하여 반환한다."""
    resolved = project_root.resolve()
    raw_target = (target_rel or "").strip()
    query = (symbol_query or "").strip()
    if "::" in raw_target and not query:
        raw_target, query = [p.strip() for p in raw_target.split("::", 1)]
    if not raw_target or not query:
        raise ValueError("대상 파일 경로(--target)와 추출할 심볼 이름(--goal 또는 파일::심볼명)을 지정하십시오.")

    fpath = (resolved / raw_target).resolve()
    if not fpath.is_file() or fpath.is_symlink() or (fpath != resolved and resolved not in fpath.parents):
        raise ValueError(f"유효하지 않은 대상 파일입니다: {raw_target}")

    rel_posix = PurePosixPath(fpath.relative_to(resolved).as_posix()).as_posix()
    text = fpath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    syms = _extract_file_symbols(fpath, text)

    matched: SymbolDescriptor | None = None
    for s in syms:
        if s.qualified_name == query or s.name == query:
            matched = s
            break
    if matched is None:
        q_low = query.lower()
        for s in syms:
            if s.qualified_name.lower() == q_low or s.name.lower() == q_low:
                matched = s
                break

    if matched is None:
        return {
            "action": "symbol-slice",
            "status": "FAIL",
            "file": rel_posix,
            "requested_symbol": query,
            "available_symbols": [s.qualified_name for s in syms],
            "message_ko": f"'{rel_posix}'에서 심볼 '{query}'을(를) 찾을 수 없습니다.",
        }

    slice_lines = lines[matched.start_line - 1 : matched.end_line]
    numbered_code = "\n".join(
        f"{line_no}: {line_str}"
        for line_no, line_str in enumerate(slice_lines, start=matched.start_line)
    )
    return {
        "action": "symbol-slice",
        "schema_version": SYMBOL_INDEXER_VERSION,
        "status": "PASS",
        "file": rel_posix,
        "symbol": matched.to_dict(),
        "total_file_lines": len(lines),
        "sliced_line_count": matched.line_count,
        "code_slice": "\n".join(slice_lines),
        "numbered_slice": numbered_code,
        "message_ko": (
            f"심볼 슬라이스 추출 완료: {rel_posix}::{matched.qualified_name} "
            f"(L{matched.start_line}-L{matched.end_line}, {matched.line_count}/{len(lines)}줄 발췌)"
        ),
    }
