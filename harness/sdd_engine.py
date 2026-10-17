"""Dreampia Spec-Driven Development (SDD) & TDD Traceability Governance Engine.

Bridges Sage/Archmage specifications (PRD-R*, REQ-*, API-*, UX-S*) with Paladin's TDD
execution (TASK-*, TEST-*, real test files) and Cleric's evidence verification.

SOLID Architecture:
- SpecItem: Single-responsibility immutable value object for SDD entities
- SpecDocumentScanner: Multi-line Markdown section context & test file scanner with template placeholder filtering
- SpecLedgerBuilder: Hierarchical BFS traceability builder (Requirement -> UX/Contract -> Task -> Test)
- SpecTraceabilityVerifier: Fail-closed verifier checking orphan specs, spec drift (STALE), and TDD coverage
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

SDD_LEDGER_VERSION = "1.0.0"
DEFAULT_SDD_LEDGER_REL = "evidence/sdd-ledger.json"

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
        ".venv",
        "venv",
        "dist",
        "build",
        "target",
    }
)

_ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "requirement": re.compile(r"\b(PRD-R\d{3,4}|REQ-\d{3,4}|SPEC-\d{3,5})\b"),
    "contract": re.compile(r"\b(API-\d{3,4})\b"),
    "ux": re.compile(r"\b(UX-S\d{3,4})\b"),
    "task": re.compile(r"\b(TASK-\d{3,4}|T\d{3,5})\b"),
    "test": re.compile(r"\b(TEST-\d{3,4})\b"),
    "decision": re.compile(r"\b(ADR-\d{3,4})\b"),
    "risk": re.compile(r"\b(RISK-\d{3,4})\b"),
}

_KIND_RANK: dict[str, int] = {
    "requirement": 0,
    "ux": 1,
    "contract": 1,
    "task": 2,
    "test": 3,
    "decision": 4,
    "risk": 4,
}

_ALL_ID_RE = re.compile(
    r"\b(PRD-R\d{3,4}|REQ-\d{3,4}|SPEC-\d{3,5}|API-\d{3,4}|UX-S\d{3,4}|TASK-\d{3,4}|T\d{3,5}|TEST-\d{3,4}|ADR-\d{3,4}|RISK-\d{3,4})\b"
)
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}|첫\s*요구용\s*자리|작성\s*예시만")
_STATUS_RE = re.compile(r"\b(draft|approved|inprogress|blocked|verified|deferred)\b", re.IGNORECASE)
_VERDICT_RE = re.compile(r"\b(PASS|FAIL|NOT_RUN)\b")
_TEST_FILE_RE = re.compile(
    r"(^test_.*|.*_test\.(py|go|rs)$|.*\.(test|spec)\.(ts|tsx|js|jsx)$|.*Test\.(java|kt)$)",
    re.IGNORECASE,
)


class SddEngineError(ValueError):
    """SDD 명세 파싱 또는 추적성 검증 중 발생하는 예외."""

    code = "SDD_ENGINE_ERROR"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    normalized = " ".join(text.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def resolve_sdd_id_patterns(root: Path | None = None) -> dict[str, str]:
    """프로젝트 설정 또는 기본값에서 요구사항(req_pattern), 작업(task_pattern), 테스트(test_pattern) ID 정규식을 반환한다."""
    defaults = {
        "req_pattern": r"\b(PRD-R\d{3,4}|REQ-\d{3,4}|SPEC-\d{3,5})\b",
        "task_pattern": r"\b(TASK-\d{3,4}|T\d{3,5})\b",
        "test_pattern": r"\b(TEST-\d{3,4})\b",
    }
    if root is None:
        return defaults
    for rel in (
        ".dreampia-skill/memory/project-rules.json",
        ".dreampia/memory/project-rules.json",
        ".dreampia-skill/project.json",
        ".dreampia/project.json",
    ):
        cand = root / rel
        if cand.is_file() and not cand.is_symlink():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("sdd"), dict):
                    sdd_cfg = data["sdd"]
                    for k in ("req_pattern", "task_pattern", "test_pattern"):
                        val = sdd_cfg.get(k)
                        if isinstance(val, str) and val.strip():
                            defaults[k] = val.strip()
                    return defaults
            except (OSError, ValueError):
                pass
    return defaults


def _classify_id(item_id: str) -> str:
    for kind, pattern in _ID_PATTERNS.items():
        if pattern.fullmatch(item_id):
            return kind
    return "unknown"


@dataclass(frozen=True)
class SpecItem:
    """개별 SDD 명세/계약/작업/테스트 항목 메타데이터."""

    item_id: str
    kind: str
    source_path: str
    statement: str
    spec_sha256: str
    linked_ids: tuple[str, ...]
    status: str
    verdict: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.item_id,
            "kind": self.kind,
            "source_path": self.source_path,
            "statement": self.statement,
            "spec_sha256": self.spec_sha256,
            "linked_ids": list(self.linked_ids),
            "status": self.status,
            "verdict": self.verdict,
        }


def _iter_project_files(root: Path) -> list[Path]:
    resolved = root.resolve()
    files: list[Path] = []
    for current_root, dirs, filenames in os.walk(resolved, topdown=True, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in _IGNORED_DIRS and not (Path(current_root) / d).is_symlink())
        for fname in sorted(filenames):
            fpath = Path(current_root) / fname
            if not fpath.is_symlink() and fpath.is_file():
                files.append(fpath)
    for baseline_rel in (
        ".dreampia/memory/brownfield-baseline.md",
        ".dreampia-skill/memory/brownfield-baseline.md",
    ):
        bf_path = resolved / baseline_rel
        if bf_path.is_file() and not bf_path.is_symlink() and bf_path not in files:
            files.append(bf_path)
    return files


def _resolve_hierarchical_links(
    start_id: str,
    adjacency: dict[str, set[str]],
    items_by_id: dict[str, SpecItem],
) -> tuple[str, ...]:
    """요구사항(0) -> UX/계약(1) -> 작업(2) -> 테스트(3) 계층 방향을 따라 다단계 연결을 BFS로 추적한다."""
    start_item = items_by_id.get(start_id)
    if start_item is None:
        return ()
    start_rank = _KIND_RANK.get(start_item.kind, 0)
    visited: set[str] = set()

    # Forward BFS (towards higher or equal rank, e.g. PRD -> UX -> API -> TASK -> TEST)
    queue: deque[tuple[str, int]] = deque([(start_id, start_rank)])
    while queue:
        curr_id, curr_rank = queue.popleft()
        for nb_id in adjacency.get(curr_id, ()):
            if nb_id == start_id or nb_id in visited:
                continue
            nb_item = items_by_id.get(nb_id)
            nb_rank = _KIND_RANK.get(nb_item.kind, 0) if nb_item else curr_rank
            if curr_id == start_id or nb_rank >= curr_rank:
                visited.add(nb_id)
                if nb_rank >= curr_rank:
                    queue.append((nb_id, nb_rank))

    return tuple(sorted(visited))


def scan_project_specs(root: Path) -> dict[str, object]:
    """프로젝트 내 마크다운 명세서(다줄 헤딩 컨텍스트 포함), 변경분(change-delta), 테스트 코드, 증거 파일을 스캔한다."""
    if root.is_symlink() or not root.is_dir():
        raise SddEngineError("유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    items_by_id: dict[str, SpecItem] = {}
    delta_modified_ids: set[str] = set()
    test_files: list[str] = []
    test_id_to_files: dict[str, list[str]] = {}
    evidence_files: dict[str, str] = {}

    for fpath in _iter_project_files(resolved):
        rel = fpath.relative_to(resolved).as_posix()
        parts = PurePosixPath(rel).parts

        if parts[0] == "evidence" and fpath.suffix.lower() in (".json", ".log", ".txt", ".png"):
            if rel != DEFAULT_SDD_LEDGER_REL:
                evidence_files[rel] = _sha256_bytes(fpath.read_bytes())
            continue

        if _TEST_FILE_RE.search(fpath.name) or "tests" in parts:
            if fpath.suffix.lower() in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt"):
                test_files.append(rel)
                text = fpath.read_text(encoding="utf-8", errors="replace")
                for match in _ALL_ID_RE.findall(text):
                    test_id_to_files.setdefault(match, [])
                    if rel not in test_id_to_files[match]:
                        test_id_to_files[match].append(rel)
            continue

        if fpath.suffix.lower() != ".md":
            continue
        if parts[0] in (".agents", ".claude", ".gemini", ".qwen", ".dreampia", ".dreampia-skill"):
            if fpath.name != "brownfield-baseline.md":
                continue

        text = fpath.read_text(encoding="utf-8", errors="replace")
        is_delta_doc = "change-delta" in fpath.name.lower()
        active_heading_id: str | None = None

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            is_heading = _HEADING_RE.match(line) is not None
            if _TEMPLATE_PLACEHOLDER_RE.search(line):
                if is_heading:
                    active_heading_id = None
                continue

            found_ids = list(dict.fromkeys(_ALL_ID_RE.findall(line)))
            if is_heading:
                active_heading_id = found_ids[0] if found_ids else None

            if not found_ids:
                # Even if a child bullet has no new IDs, it may declare status/verdict for active_heading_id
                if active_heading_id and active_heading_id in items_by_id:
                    st_m = _STATUS_RE.search(line)
                    vd_m = _VERDICT_RE.search(line)
                    if st_m or vd_m:
                        prev = items_by_id[active_heading_id]
                        items_by_id[active_heading_id] = SpecItem(
                            item_id=prev.item_id,
                            kind=prev.kind,
                            source_path=prev.source_path,
                            statement=prev.statement,
                            spec_sha256=prev.spec_sha256,
                            linked_ids=prev.linked_ids,
                            status=st_m.group(1).lower() if st_m else prev.status,
                            verdict=vd_m.group(1).upper() if vd_m else prev.verdict,
                        )
                continue

            if is_delta_doc:
                for fid in found_ids:
                    delta_modified_ids.add(fid)
                continue

            if active_heading_id and active_heading_id not in found_ids:
                found_ids = [active_heading_id, *found_ids]

            status_match = _STATUS_RE.search(line)
            verdict_match = _VERDICT_RE.search(line)
            line_status = status_match.group(1).lower() if status_match else "approved"
            line_verdict = verdict_match.group(1).upper() if verdict_match else "NOT_RUN"

            canonical_stmt = _VERDICT_RE.sub("", _STATUS_RE.sub("", line))
            stmt_hash = _sha256_text(canonical_stmt)

            for primary_id in found_ids:
                kind = _classify_id(primary_id)
                others = tuple(sorted(x for x in found_ids if x != primary_id))
                existing = items_by_id.get(primary_id)
                if existing is None:
                    items_by_id[primary_id] = SpecItem(
                        item_id=primary_id,
                        kind=kind,
                        source_path=rel,
                        statement=line[:240],
                        spec_sha256=stmt_hash,
                        linked_ids=others,
                        status=line_status,
                        verdict=line_verdict,
                    )
                else:
                    merged_links = tuple(sorted(set(existing.linked_ids).union(others)))
                    eff_verdict = line_verdict if existing.verdict == "NOT_RUN" else existing.verdict
                    eff_status = line_status if existing.status == "approved" and status_match else existing.status
                    items_by_id[primary_id] = SpecItem(
                        item_id=existing.item_id,
                        kind=existing.kind,
                        source_path=existing.source_path,
                        statement=existing.statement,
                        spec_sha256=existing.spec_sha256,
                        linked_ids=merged_links,
                        status=eff_status,
                        verdict=eff_verdict,
                    )

    adjacency: dict[str, set[str]] = {k: set(v.linked_ids) for k, v in items_by_id.items()}
    for item_id, neighbors in list(adjacency.items()):
        for nb in list(neighbors):
            if nb in adjacency:
                adjacency[nb].add(item_id)

    resolved_items: dict[str, SpecItem] = {}
    for item_id, item in items_by_id.items():
        linked = _resolve_hierarchical_links(item_id, adjacency, items_by_id)
        resolved_items[item_id] = SpecItem(
            item_id=item.item_id,
            kind=item.kind,
            source_path=item.source_path,
            statement=item.statement,
            spec_sha256=item.spec_sha256,
            linked_ids=linked,
            status=item.status,
            verdict=item.verdict,
        )

    return {
        "items": resolved_items,
        "delta_modified_ids": sorted(delta_modified_ids),
        "test_files": sorted(test_files),
        "test_id_to_files": test_id_to_files,
        "evidence_files": evidence_files,
    }


def build_sdd_ledger(
    root: Path,
    *,
    precomputed_scan: dict[str, object] | None = None,
) -> dict[str, object]:
    """프로젝트의 SDD 요구사항·계약·작업·TDD 테스트 추적 원장을 생성한다."""
    scan = precomputed_scan if precomputed_scan is not None else scan_project_specs(root)
    items: dict[str, SpecItem] = scan["items"]  # type: ignore[assignment]
    test_id_to_files: dict[str, list[str]] = scan["test_id_to_files"]  # type: ignore[assignment]

    requirements: list[dict[str, object]] = []
    contracts: list[dict[str, object]] = []
    tasks: list[dict[str, object]] = []
    tests: list[dict[str, object]] = []

    for item_id in sorted(items):
        item = items[item_id]
        entry = item.to_dict()
        if item.kind == "requirement":
            linked_contracts = [x for x in item.linked_ids if _classify_id(x) in ("contract", "ux")]
            linked_tasks = [x for x in item.linked_ids if _classify_id(x) == "task"]
            linked_tests = [x for x in item.linked_ids if _classify_id(x) == "test"]
            if not linked_tests:
                direct_req_files = list(test_id_to_files.get(item_id, []))
                for t_id in linked_tasks:
                    for tf in test_id_to_files.get(t_id, []):
                        if tf not in direct_req_files:
                            direct_req_files.append(tf)
                if direct_req_files:
                    linked_tests = [f"FILE:{tf}" for tf in direct_req_files]
            entry["linked_contracts"] = linked_contracts
            entry["linked_tasks"] = linked_tasks
            entry["linked_tests"] = linked_tests
            requirements.append(entry)
        elif item.kind in ("contract", "ux"):
            contracts.append(entry)
        elif item.kind == "task":
            linked_tests = [x for x in item.linked_ids if _classify_id(x) == "test"]
            direct_task_files = test_id_to_files.get(item_id, [])
            if not linked_tests and direct_task_files:
                linked_tests = [f"FILE:{tf}" for tf in direct_task_files]
            entry["linked_tests"] = linked_tests
            entry["test_files"] = direct_task_files
            tasks.append(entry)
        elif item.kind == "test":
            bound_files = test_id_to_files.get(item_id, [])
            entry["test_files"] = bound_files
            tests.append(entry)

    return {
        "schema_version": SDD_LEDGER_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "squad_owners": {
            "protagonist": "Hero (주인공 영웅)",
            "spec_author": "Sage (planner) & Archmage (architect)",
            "tdd_executor": "Paladin (executor)",
            "evidence_verifier": "Cleric (verifier)",
        },
        "summary": {
            "requirement_count": len(requirements),
            "contract_count": len(contracts),
            "task_count": len(tasks),
            "test_count": len(tests),
            "test_file_count": len(scan["test_files"]),  # type: ignore[arg-type]
            "evidence_file_count": len(scan["evidence_files"]),  # type: ignore[arg-type]
            "delta_modified_count": len(scan["delta_modified_ids"]),  # type: ignore[arg-type]
        },
        "requirements": requirements,
        "contracts": contracts,
        "tasks": tasks,
        "tests": tests,
        "delta_modified_ids": scan["delta_modified_ids"],
        "test_files": scan["test_files"],
        "evidence_files": scan["evidence_files"],
    }


def verify_sdd_compliance(
    root: Path,
    *,
    saved_ledger: dict[str, object] | None = None,
    require_tdd_files: bool = True,
    precomputed_scan: dict[str, object] | None = None,
    precomputed_ledger: dict[str, object] | None = None,
) -> dict[str, object]:
    """SDD 명세-작업-TDD 테스트 추적성, 고아 요구사항, 명세 드리프트(STALE)를 Fail-Closed로 검증한다."""
    live = precomputed_ledger if precomputed_ledger is not None else build_sdd_ledger(root, precomputed_scan=precomputed_scan)
    requirements: list[dict[str, object]] = live["requirements"]  # type: ignore[assignment]
    tasks: list[dict[str, object]] = live["tasks"]  # type: ignore[assignment]
    test_files: list[str] = live["test_files"]  # type: ignore[assignment]
    delta_ids: list[str] = live["delta_modified_ids"]  # type: ignore[assignment]

    orphan_requirements: list[str] = []
    untested_requirements: list[str] = []
    untested_tasks: list[str] = []
    stale_specs: list[str] = []
    blockers: list[str] = []

    if not requirements:
        blockers.append("missing-sdd-requirements")

    saved_hashes: dict[str, str] = {}
    if isinstance(saved_ledger, dict):
        for saved_req in saved_ledger.get("requirements", []):  # type: ignore[union-attr]
            if isinstance(saved_req, dict) and isinstance(saved_req.get("id"), str):
                saved_hashes[str(saved_req["id"])] = str(saved_req.get("spec_sha256") or "")

    for req in requirements:
        req_id = str(req["id"])
        status = str(req.get("status") or "approved")
        if status == "deferred":
            continue
        linked_tasks: list[str] = req.get("linked_tasks", [])  # type: ignore[assignment]
        linked_tests: list[str] = req.get("linked_tests", [])  # type: ignore[assignment]
        if not linked_tasks:
            orphan_requirements.append(req_id)
        if not linked_tests:
            untested_requirements.append(req_id)
        if req_id in saved_hashes and saved_hashes[req_id] != str(req.get("spec_sha256") or ""):
            stale_specs.append(req_id)
        if req_id in delta_ids and str(req.get("verdict") or "NOT_RUN") != "PASS":
            if req_id not in stale_specs:
                stale_specs.append(req_id)

    for task in tasks:
        task_id = str(task["id"])
        status = str(task.get("status") or "approved")
        if status == "deferred":
            continue
        linked_tests_t: list[str] = task.get("linked_tests", [])  # type: ignore[assignment]
        if not linked_tests_t:
            untested_tasks.append(task_id)

    if orphan_requirements:
        blockers.append(f"orphan-requirements-without-task:{','.join(orphan_requirements)}")
    if untested_requirements:
        blockers.append(f"requirements-without-test:{','.join(untested_requirements)}")
    if untested_tasks:
        blockers.append(f"tasks-without-test:{','.join(untested_tasks)}")
    if stale_specs:
        blockers.append(f"stale-spec-drift:{','.join(stale_specs)}")
    if require_tdd_files and not test_files:
        blockers.append("missing-executable-tdd-test-files")

    total_reqs = len([r for r in requirements if r.get("status") != "deferred"])
    traced_reqs = total_reqs - len(set(orphan_requirements).union(untested_requirements))
    traceability_ratio = round(traced_reqs / total_reqs, 4) if total_reqs > 0 else 0.0

    passed = len(blockers) == 0
    return {
        "status": "PASS" if passed else ("STALE" if stale_specs and len(blockers) == 1 else "FAIL"),
        "traceability_ratio": traceability_ratio,
        "requirement_count": len(requirements),
        "task_count": len(tasks),
        "test_count": len(live["tests"]),  # type: ignore[arg-type]
        "test_file_count": len(test_files),
        "orphan_requirements": orphan_requirements,
        "untested_requirements": untested_requirements,
        "untested_tasks": untested_tasks,
        "stale_specs": stale_specs,
        "blockers": blockers,
        "ledger": live,
        "message_ko": (
            f"SDD 명세-작업-TDD 테스트 추적성 검증을 통과했습니다. (추적률 {traceability_ratio * 100:.1f}%)"
            if passed
            else f"SDD+TDD 추적성 게이트 차단: {', '.join(blockers)}"
        ),
    }


def compile_interview_to_sdd(
    root: Path,
    goal: str,
    answers: str | list[str] | tuple[str, ...] = "",
    *,
    apply: bool = False,
) -> dict[str, object]:
    """Sage 소크라테스식 인터뷰 질문과 주인공 영웅(사용자) 답변을 결합하여 SDD 퀘스트 저널(PRD-R*, TASK-*, TEST-*) 및 추적 원장으로 자동 컴파일한다."""
    import json
    try:
        from . import route_planner
    except ImportError:
        import route_planner  # type: ignore[no-redef]

    if root.is_symlink() or not root.is_dir():
        raise SddEngineError("유효하지 않은 프로젝트 디렉터리입니다.")
    cleaned_goal = " ".join(goal.strip().split())
    if not cleaned_goal:
        raise SddEngineError("컴파일할 작업 목표(--goal)를 입력해 주십시오.")

    resolved = root.resolve()
    brief = route_planner.expand_prompt_brief(cleaned_goal, root=resolved)
    questions = list(brief.clarifying_questions_ko)

    if isinstance(answers, (list, tuple)):
        raw_parts = [str(p).strip() for p in answers if str(p).strip()]
    else:
        raw_parts = [
            p.strip()
            for p in re.split(r"[;\n|]+", str(answers).strip())
            if p.strip()
        ]
        if len(raw_parts) == 1 and "," in raw_parts[0]:
            raw_parts = [p.strip() for p in raw_parts[0].split(",") if p.strip()]

    default_answers = [
        "기본 표준 경계 및 데스크톱/모바일 반응형 흐름 적용",
        "사용자 친화적 한글 오류 메시지 및 중복 요청(연타) 방어 적용",
        "Inquisitor 정적 코드 감사 위반 0건 및 핵심 엣지케이스 TDD 단언문 통과",
    ]
    qa_pairs: list[dict[str, str]] = []
    for idx, q_text in enumerate(questions):
        ans_text = raw_parts[idx] if idx < len(raw_parts) else default_answers[idx % len(default_answers)]
        qa_pairs.append({"question_ko": q_text, "answer_ko": ans_text})

    existing_scan = scan_project_specs(resolved)
    existing_items: dict[str, SpecItem] = existing_scan["items"]  # type: ignore[assignment]
    max_num = 0
    for item_id in existing_items:
        m = re.search(r"(\d+)$", item_id)
        if m:
            max_num = max(max_num, int(m.group(1)))
    next_num = max_num + 1

    req_id = f"PRD-R{next_num:03d}"
    task_id = f"TASK-{next_num:03d}"
    test_id = f"TEST-{next_num:03d}"

    clean_topic = route_planner._extract_clean_topic_ko(brief.core_subject)
    qa_md = "\n".join(
        f"  {idx}. 질문: {pair['question_ko']} -> 확정 답변: {pair['answer_ko']}"
        for idx, pair in enumerate(qa_pairs, start=1)
    )
    prd_section = (
        f"\n## {req_id}: {clean_topic}\n"
        f"- 상태: approved\n"
        f"- 연결 항목: {task_id}, {test_id}\n"
        f"- 고도화 명세: {brief.expanded_prompt_ko}\n"
        f"- 사전 인터뷰 확정 사항:\n"
        f"{qa_md}\n"
    )
    task_section = (
        f"\n## {task_id}: {clean_topic} 구현 및 방어 로직\n"
        f"- 상태: approved\n"
        f"- 연결 항목: {req_id}, {test_id}\n"
        f"- 핵심 제약: {'; '.join(brief.injected_constraints_ko[:3])}\n"
    )
    test_section = (
        f"\n## {test_id}: {clean_topic} TDD 단위/엣지케이스 검증\n"
        f"- 상태: approved\n"
        f"- 판정: NOT_RUN\n"
        f"- 연결 항목: {req_id}, {task_id}\n"
        f"- 검증할 엣지케이스: {'; '.join(brief.edge_cases_to_check_ko[:3])}\n"
    )

    target_docs = {
        "docs/01_PRD_REQUIREMENTS.md": ("# 01. PRD 요구사항 명세서\n", prd_section),
        "docs/07_BACKLOG.md": ("# 07. 구현 백로그 (Backlog)\n", task_section),
        "docs/06_TEST_PLAN.md": ("# 06. TDD 테스트 계획서\n", test_section),
    }
    updated_files: list[str] = []
    if apply:
        for rel_path, (header, section_md) in target_docs.items():
            fpath = resolved / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            if fpath.is_file():
                current = fpath.read_text(encoding="utf-8", errors="replace")
                if not current.endswith("\n"):
                    current += "\n"
                fpath.write_text(current + section_md, encoding="utf-8")
            else:
                fpath.write_text(header + section_md, encoding="utf-8")
            updated_files.append(rel_path)

        ledger = build_sdd_ledger(resolved)
        ledger_path = resolved / DEFAULT_SDD_LEDGER_REL
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        updated_files.append(DEFAULT_SDD_LEDGER_REL)

    return {
        "action": "interview-compile",
        "status": "PASS",
        "applied": apply,
        "goal": cleaned_goal,
        "core_subject": brief.core_subject,
        "generated_ids": {
            "requirement": req_id,
            "task": task_id,
            "test": test_id,
        },
        "qa_pairs": qa_pairs,
        "updated_files": updated_files,
        "preview_sections": {
            "prd_markdown": prd_section.strip(),
            "task_markdown": task_section.strip(),
            "test_markdown": test_section.strip(),
        },
        "message_ko": (
            f"인터뷰 결과가 SDD 명세({req_id} -> {task_id} -> {test_id}) 및 원장({DEFAULT_SDD_LEDGER_REL})으로 자동 컴파일되었습니다."
            if apply
            else f"[미리보기] 인터뷰 결과 SDD 명세({req_id} -> {task_id} -> {test_id}) 생성 계획입니다. 실제 파일에 기록하려면 --apply를 추가하십시오."
        ),
    }

