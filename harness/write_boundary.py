"""Pre/post write-boundary enforcement, cleanroom role-bundle isolation, and instruction drift check.

Dreampia Skill native write-boundary and cleanroom governance module.
Follows SOLID principles:
- WriteBoundaryVerifier: Single responsibility for pre/post filesystem inventory and owned_paths enforcement
- CleanroomBundleValidator: Single responsibility for analyst/implementer/verifier zone separation
- InstructionDriftChecker: Single responsibility for non-mutating AGENTS.md / CLAUDE.md / contract drift detection
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat

CONTROL_ROOTS: frozenset[str] = frozenset({".git", ".dreampia-install", ".harness", ".workflow"})
IGNORED_TRANSIENT_DIRS: frozenset[str] = frozenset({"__pycache__"})
CLEANROOM_ROLES: frozenset[str] = frozenset({"analyst", "implementer", "executor", "verifier"})


class BoundaryError(ValueError):
    """쓰기 경계 또는 클린룸 번들 검증 오류 예외."""

    code = "BOUNDARY_INPUT_INVALID"


@dataclass(frozen=True)
class BoundaryCheckResult:
    status: str
    owned_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]
    violations: tuple[str, ...]
    detail_codes: tuple[str, ...]
    message_ko: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "owned_paths": list(self.owned_paths),
            "changed_paths": list(self.changed_paths),
            "violations": list(self.violations),
            "detail_codes": list(self.detail_codes),
            "message_ko": self.message_ko,
        }


def normalize_owned_path(rel_path: str) -> str:
    """소유 경로(owned_path)를 정규화하고 탈출·제어 루트 여부를 검증한다."""
    if not isinstance(rel_path, str) or not rel_path.strip() or "\\" in rel_path or "\x00" in rel_path:
        raise BoundaryError("유효하지 않은 소유 경로 문자열입니다.")
    pure = PurePosixPath(rel_path.strip().rstrip("/"))
    if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
        raise BoundaryError("소유 경로가 프로젝트 루트 외부로 벗어납니다.")
    if pure.parts[0] in CONTROL_ROOTS:
        raise BoundaryError(f"보호된 제어 디렉터리는 소유 경로로 지정할 수 없습니다: {pure.parts[0]}")
    return pure.as_posix()


def _is_under_owned(rel_path: str, owned_paths: tuple[str, ...]) -> bool:
    for owned in owned_paths:
        if rel_path == owned or rel_path.startswith(owned + "/"):
            return True
    return False


def capture_inventory(root: Path) -> dict[str, dict[str, object]]:
    """프로젝트 루트의 파일시스템 상태(일반 파일 해시, 심볼릭 링크, 하드링크, 특수 파일)를 스냅샷으로 기록한다."""
    if root.is_symlink() or not root.is_dir():
        raise BoundaryError("스냅샷 대상 루트는 심볼릭 링크가 아닌 디렉터리여야 합니다.")
    resolved_root = root.resolve()
    inventory: dict[str, dict[str, object]] = {}

    for current_dir, dirnames, filenames in os.walk(resolved_root, topdown=True, followlinks=False):
        base_path = Path(current_dir)
        kept_dirs: list[str] = []
        for dname in sorted(dirnames):
            if dname in IGNORED_TRANSIENT_DIRS:
                continue
            dpath = base_path / dname
            rel = dpath.relative_to(resolved_root).as_posix()
            st = os.lstat(dpath)
            if stat.S_ISLNK(st.st_mode):
                inventory[rel] = {"kind": "symlink", "mode": st.st_mode}
                continue
            kept_dirs.append(dname)
        dirnames[:] = kept_dirs

        for fname in sorted(filenames):
            fpath = base_path / fname
            rel = fpath.relative_to(resolved_root).as_posix()
            st = os.lstat(fpath)
            if stat.S_ISLNK(st.st_mode):
                inventory[rel] = {"kind": "symlink", "mode": st.st_mode}
            elif stat.S_ISREG(st.st_mode):
                digest = hashlib.sha256(fpath.read_bytes()).hexdigest()
                inventory[rel] = {
                    "kind": "regular",
                    "sha256": digest,
                    "size": st.st_size,
                    "nlink": st.st_nlink,
                }
            else:
                inventory[rel] = {"kind": "special", "mode": st.st_mode}
    return inventory


def verify_write_boundary(
    before: dict[str, dict[str, object]],
    after: dict[str, dict[str, object]],
    owned_paths: list[str] | tuple[str, ...],
) -> dict[str, object]:
    """실행 전후 인벤토리를 비교하여 선언된 owned_paths 외부 변경 및 링크/특수파일 위반을 차단한다."""
    if not isinstance(owned_paths, (list, tuple)) or not owned_paths:
        raise BoundaryError("최소 1개 이상의 소유 경로(owned_paths)가 필요합니다.")
    normalized_owned = tuple(dict.fromkeys(normalize_owned_path(p) for p in owned_paths))

    all_paths = sorted(set(before) | set(after))
    changed_paths: list[str] = []
    violations: list[str] = []
    detail_codes: list[str] = []

    def add_violation(rel: str, code: str) -> None:
        if rel not in violations:
            violations.append(rel)
        if code not in detail_codes:
            detail_codes.append(code)

    for rel in all_paths:
        prev = before.get(rel)
        curr = after.get(rel)
        if prev == curr:
            continue
        changed_paths.append(rel)
        top_part = PurePosixPath(rel).parts[0]
        if top_part in CONTROL_ROOTS:
            add_violation(rel, "control-metadata-modified")
            continue
        if curr is not None:
            if curr.get("kind") == "symlink":
                add_violation(rel, "symlink-created-or-modified")
                continue
            if curr.get("kind") == "special":
                add_violation(rel, "special-file-created")
                continue
            nlink = curr.get("nlink")
            if isinstance(nlink, int) and nlink > 1:
                add_violation(rel, "hardlinked-file-forbidden")
                continue
        if not _is_under_owned(rel, normalized_owned):
            add_violation(rel, "write-outside-owned-paths")

    passed = len(violations) == 0
    return BoundaryCheckResult(
        status="PASS" if passed else "FAIL",
        owned_paths=normalized_owned,
        changed_paths=tuple(changed_paths),
        violations=tuple(violations),
        detail_codes=tuple(detail_codes),
        message_ko=(
            "모든 파일 변경이 선언된 소유 경로(owned_paths) 경계 내에 있습니다."
            if passed
            else "소유 경로 외부 변경 또는 허용되지 않는 링크/제어 파일 변경이 감지되었습니다."
        ),
    ).to_dict()


def validate_cleanroom_bundle(
    role: str,
    bundle_paths: list[str] | tuple[str, ...],
) -> dict[str, object]:
    """클린룸 역할별 번들 경로를 검증하여 구현자(implementer/executor)의 오염 영역 접근을 차단한다."""
    resolved_role = role
    if resolved_role not in CLEANROOM_ROLES:
        try:
            try:
                from . import route_planner
            except ImportError:
                import route_planner  # type: ignore[no-redef]
            resolved_role = route_planner.resolve_role_alias(role)
        except ValueError:
            resolved_role = role
    if resolved_role not in CLEANROOM_ROLES:
        raise BoundaryError(f"지원하지 않는 클린룸 역할입니다: {role}")
    role = resolved_role
    if not isinstance(bundle_paths, (list, tuple)) or not bundle_paths:
        raise BoundaryError("번들 경로 목록은 비어 있을 수 없습니다.")

    normalized_paths: list[str] = []
    violations: list[str] = []
    for raw in bundle_paths:
        if not isinstance(raw, str) or not raw.strip() or "\\" in raw or "\x00" in raw:
            raise BoundaryError("유효하지 않은 번들 경로가 포함되어 있습니다.")
        pure = PurePosixPath(raw.strip())
        if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
            raise BoundaryError("번들 경로가 루트 외부로 벗어납니다.")
        rel = pure.as_posix()
        normalized_paths.append(rel)
        is_contaminated = "contaminated-zone" in pure.parts
        if role in ("implementer", "executor", "verifier") and is_contaminated:
            violations.append(rel)

    has_approved_spec = any("approved-spec" in PurePosixPath(p).parts for p in normalized_paths)
    if role in ("implementer", "executor") and not has_approved_spec:
        violations.append("missing:approved-spec")

    passed = len(violations) == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "role": role,
        "bundle_paths": normalized_paths,
        "violations": violations,
        "message_ko": (
            "클린룸 역할 격리 검증을 통과했습니다."
            if passed
            else "구현자/검증자 번들에 오염 영역(contaminated-zone)이 포함되었거나 승인 명세(approved-spec)가 누락되었습니다."
        ),
    }


def check_instruction_drift(root: Path) -> dict[str, object]:
    """AGENTS.md, CLAUDE.md 및 .dreampia 계약 문서의 무결성과 드리프트 여부를 비파괴적으로 점검한다."""
    if root.is_symlink() or not root.is_dir():
        raise BoundaryError("점검 대상 프로젝트 루트가 유효하지 않습니다.")
    resolved = root.resolve()
    candidates = ("AGENTS.md", "CLAUDE.md", ".dreampia/WORK_CONTRACT.ko.md", ".dreampia/codex.ko.md")
    present: dict[str, str] = {}
    violations: list[str] = []

    for rel in candidates:
        path = resolved / rel
        if path.is_symlink():
            violations.append(f"symlink-forbidden:{rel}")
            continue
        if path.exists():
            if not path.is_file():
                violations.append(f"not-regular-file:{rel}")
                continue
            present[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    agents_text = (resolved / "AGENTS.md").read_text(encoding="utf-8", errors="replace") if "AGENTS.md" in present else None
    claude_text = (resolved / "CLAUDE.md").read_text(encoding="utf-8", errors="replace") if "CLAUDE.md" in present else None
    drift_detected = False
    if agents_text is not None and claude_text is not None:
        if (
            agents_text.strip() != claude_text.strip()
            and "AGENTS.md" not in claude_text
            and "CLAUDE.md" not in agents_text
        ):
            drift_detected = True
            violations.append("instruction-drift:AGENTS.md-vs-CLAUDE.md")

    passed = len(violations) == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "present_files": present,
        "drift_detected": drift_detected,
        "violations": violations,
        "message_ko": (
            "지침 문서 무결성 및 드리프트 점검을 통과했습니다."
            if passed
            else "지침 문서 간 불일치(드리프트) 또는 심볼릭 링크 위반이 감지되었습니다."
        ),
    }


def verify_cleanroom_separation(root: Path) -> dict[str, object]:
    """프로젝트의 클린룸 3-영역(contaminated-zone, approved-spec, implementation) 간 파일 해시 복제·심볼릭 링크 오염 여부를 검증한다."""
    if root.is_symlink() or not root.is_dir():
        raise BoundaryError("클린룸 검증 대상 루트가 유효하지 않습니다.")
    resolved = root.resolve()
    c_zone = resolved / "contaminated-zone"
    a_zone = resolved / "approved-spec"
    i_zone = resolved / "implementation"

    violations: list[str] = []
    contam_hashes: dict[str, str] = {}

    if c_zone.exists():
        for p in sorted(c_zone.rglob("*")):
            if p.is_symlink():
                violations.append(f"symlink-in-contaminated:{p.relative_to(resolved).as_posix()}")
            elif p.is_file() and p.name.lower() != "readme.md":
                raw = p.read_bytes()
                if len(raw.strip()) >= 16:
                    contam_hashes[hashlib.sha256(raw).hexdigest()] = p.relative_to(resolved).as_posix()

    for zone_name, zone_dir in (("approved-spec", a_zone), ("implementation", i_zone)):
        if not zone_dir.exists():
            continue
        for p in sorted(zone_dir.rglob("*")):
            rel = p.relative_to(resolved).as_posix()
            if p.is_symlink():
                violations.append(f"symlink-in-{zone_name}:{rel}")
            elif p.is_file() and p.name.lower() != "readme.md":
                digest = hashlib.sha256(p.read_bytes()).hexdigest()
                if digest in contam_hashes:
                    violations.append(f"verbatim-copy-from-contaminated:{rel}=={contam_hashes[digest]}")

    bundle_check = validate_cleanroom_bundle("implementer", ["approved-spec", "implementation"])
    if bundle_check.get("status") != "PASS":
        violations.extend(str(v) for v in (bundle_check.get("violations") or []))  # type: ignore[union-attr]

    passed = len(violations) == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "violations": violations,
        "message_ko": (
            "클린룸 3-영역(오염/승인명세/구현) 분리 및 무결성 검증을 통과했습니다."
            if passed
            else "오염 영역과 구현/명세 영역 간 직접 파일 복제 또는 심볼릭 링크 위반이 감지되었습니다."
        ),
    }

