"""Pure Korean/English goal classification, risk escalation, and profile route planner.

Dreampia Skill native goal and risk routing module.
Follows SOLID principles:
- GoalClassifier: Single responsibility for deterministic natural-language goal classification
- RiskClassifier: Single responsibility for security/destructive/repository risk classification
- RoutePlanner: Single responsibility for mapping goal + risk to Dreampia profiles, roles, and gates
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import unicodedata

GOAL_KINDS = ("change", "test", "review", "explain", "operate", "unsupported")
RISK_LEVELS = ("low", "medium", "high")
PROFILE_NAMES = ("quick", "team", "controlled", "cleanroom")

UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+.*(secret|token|password|api[_\s-]?key)", re.IGNORECASE),
    re.compile(r"exfiltrate|steal\s+credentials|dump\s+env", re.IGNORECASE),
    re.compile(r"rm\s+-rf\s+/|format\s+disk|drop\s+database\s+production", re.IGNORECASE),
    re.compile(r"bypass\s+(verification|evidence|security|gate)", re.IGNORECASE),
    re.compile(r"이전\s*지시.*무시|시스템\s*프롬프트.*유출|검증\s*게이트.*우회|비밀키.*유출"),
)

OPERATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(deploy|release|publish|migrate\s+prod|production\s+rollout|rollback\s+prod)\b", re.IGNORECASE),
    re.compile(r"배포|릴리즈|운영\s*반영|프로덕션\s*적용|실서버"),
)

REVIEW_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(review|audit|inspect\s+diff|code\s+review|security\s+review)\b", re.IGNORECASE),
    re.compile(r"리뷰|코드\s*검토|감사|점검|진단|봐줘"),
)

TEST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(run\s+tests?|pytest|unit\s+test|verify|verification|check\s+tests?)\b", re.IGNORECASE),
    re.compile(r"테스트\s*(실행|돌려|확인|검증)?|검증(\s*실행|해)?"),
)

EXPLAIN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(explain|summarize|describe|what\s+does|how\s+does|where\s+is|architecture)\b", re.IGNORECASE),
    re.compile(r"설명|요약|알려줘|안내해|비교해|무엇인가|어떻게\s*동작|구조\s*분석"),
)

CHANGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(fix|implement|add|update|refactor|remove|delete|rename|patch|create|build|modify|design|plan|optimize|setup|configure|upgrade|enhance|improve|strengthen|evolve|proceed|continue|polish|refine)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"수정|구현|추가|변경|리팩터링|리팩토링|삭제|제거|개선|고쳐|고치|작성|만들어|설계|기획|구축|개발|적용|연동|최적화|셋팅|세팅|설정|고도화|업그레이드|보강|강화|완성|정비|다듬|확장|패치|수리|바꿔|바꾸|넣어|붙여|진행|작업"
    ),
)

SECURITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(auth|authentication|authorization|permission|rbac|token|jwt|session|secret|credential|"
        r"password|crypto|encryption|signing|signature|webhook|payment|billing|firewall|privilege|"
        r"sandbox|boundary|escape|symlink|cleanroom|license|copyright)\b",
        re.IGNORECASE,
    ),
    re.compile(r"인증|인가|권한|비밀번호|암호화|토큰|세션|결제|보안|서명|경계|샌드박스|클린룸|저작권|라이선스"),
)

DESTRUCTIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(delete|remove|drop|purge|truncate|destroy|wipe|reset|revoke|migration|schema\s+change|"
        r"breaking\s+change|force\s+push|overwrite)\b",
        re.IGNORECASE,
    ),
    re.compile(r"삭제|제거|초기화|폐기|마이그레이션|스키마\s*변경|덮어쓰기|파괴적"),
)

CLEANROOM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(cleanroom|clean-room|reverse\s+engineer|decompile|reconstruct|contaminated)\b", re.IGNORECASE),
    re.compile(r"클린룸|역공학|리버스\s*엔지니어링|디컴파일|오염\s*격리|재구현"),
)

UI_DOMAIN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(ui|ux|button|modal|dialog|screen|page|component|view|layout|navbar|sidebar|form|input|icon|tailwind|css)\b",
        re.IGNORECASE,
    ),
    re.compile(r"버튼|화면|컴포넌트|모달|페이지|뷰|아이콘|디자인|레이아웃|입력창|폼|배너|메뉴"),
)


AGENT_CALLSIGNS: dict[str, dict[str, str]] = {
    "router": {
        "callsign": "Morpheus",
        "name_ko": "모피어스",
        "title_ko": "총괄 라우터 및 작전 지휘관",
    },
    "planner": {
        "callsign": "Oracle",
        "name_ko": "오라클",
        "title_ko": "제품 기획 및 요구사항·백로그 설계자",
    },
    "architect": {
        "callsign": "Architect",
        "name_ko": "아키텍트",
        "title_ko": "시스템·데이터·신뢰 경계 설계자",
    },
    "ux-designer": {
        "callsign": "Niobe",
        "name_ko": "니오베",
        "title_ko": "사용자 경험·화면 흐름·뷰포트 디자이너",
    },
    "analyst": {
        "callsign": "Keymaker",
        "name_ko": "키메이커",
        "title_ko": "바이너리·레거시 역설계 및 복원 원장 분석가",
    },
    "executor": {
        "callsign": "Neo",
        "name_ko": "네오",
        "title_ko": "TDD 기반 핵심 코드 구현자",
    },
    "implementer": {
        "callsign": "Neo",
        "name_ko": "네오",
        "title_ko": "클린룸 명세 기반 핵심 구현자",
    },
    "reviewer": {
        "callsign": "Trinity",
        "name_ko": "트리니티",
        "title_ko": "SOLID 원칙·설계 정합성·결함 수석 리뷰어",
    },
    "verifier": {
        "callsign": "Tank",
        "name_ko": "탱크",
        "title_ko": "실행 증거·시각 픽셀·원장 커버리지 검증 오퍼레이터",
    },
    "privacy-guard": {
        "callsign": "Seraph",
        "name_ko": "세라프",
        "title_ko": "개인정보·비밀키·클린룸 무오염 경계 수호자",
    },
    "design-critic": {
        "callsign": "Mouse",
        "name_ko": "마우스",
        "title_ko": "UI/UX 컴포넌트·반응형 레이아웃·시각 규격 구현 및 비평자",
    },
}

_SKILL_OWNED_DREAMPIA_ENTRIES: frozenset[str] = frozenset(
    {
        "memory",
        "worktrees",
        "generated",
        "team.json",
        "project.json",
        "WORK_CONTRACT.ko.md",
        "DELIVERABLE_STANDARDS.ko.md",
    }
)


def has_unmanaged_dreampia_data_dir(root: Path | None) -> bool:
    """대상 프로젝트의 .dreampia/ 폴더가 스킬 설정이 아닌 사용자/애플리케이션 고유 데이터 폴더인지 판별한다."""
    if root is None or root.is_symlink() or not root.is_dir():
        return False
    resolved = root.resolve()
    dp_dir = resolved / ".dreampia"
    if not dp_dir.is_dir() or dp_dir.is_symlink():
        return False
    if (resolved / ".dreampia-install" / "manifest.json").is_file() or (dp_dir / "team.json").is_file():
        return False
    try:
        entries = [p.name for p in dp_dir.iterdir()]
    except OSError:
        return False
    if not entries:
        return False
    return any(name not in _SKILL_OWNED_DREAMPIA_ENTRIES for name in entries)


def resolve_skill_state_dir(root: Path | None = None) -> str:
    """스킬 상태/메모리/워크트리 저장 폴더 상대 경로를 반환한다. 기존 .dreampia/가 사용자 데이터 폴더이면 .dreampia-skill로 자동 격리한다."""
    import os

    env_dir = os.environ.get("DREAMPIA_SKILL_DIR", "").strip()
    if env_dir and "/" not in env_dir and "\\" not in env_dir and env_dir not in (".", ".."):
        return env_dir
    if root is not None and not root.is_symlink() and root.is_dir():
        resolved = root.resolve()
        if (resolved / ".dreampia-skill").is_dir():
            return ".dreampia-skill"
        if has_unmanaged_dreampia_data_dir(resolved):
            return ".dreampia-skill"
    return ".dreampia"


def is_ui_rule_enforced(root: Path | None = None) -> bool:
    """프로젝트 설정(.dreampia/project.json 또는 memory/project-rules.json)에서 기본 UI 규칙(bg-transparent, lucide-react) 강제 여부를 확인한다."""
    import json as _json

    if root is None or root.is_symlink() or not root.is_dir():
        return True
    resolved = root.resolve()
    state_dir = resolve_skill_state_dir(resolved)
    candidates = (
        resolved / state_dir / "project.json",
        resolved / ".dreampia" / "project.json",
        resolved / state_dir / "memory" / "project-rules.json",
        resolved / ".dreampia" / "memory" / "project-rules.json",
    )
    for cfg_path in candidates:
        if cfg_path.is_file() and not cfg_path.is_symlink():
            try:
                data = _json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("enforce_ui_rules") is False:
                    return False
            except (OSError, ValueError, TypeError):
                pass
    return True


def is_briefing_enabled(root: Path | None) -> bool:
    """프로젝트 설정(enforce_briefing)에서 상단 작전 브리핑 출력 활성화 여부를 확인한다. 기본값은 True."""
    if root is None or root.is_symlink() or not root.is_dir():
        return True
    import json as _json

    resolved = root.resolve()
    state_dir = resolve_skill_state_dir(resolved)
    candidates = (
        resolved / state_dir / "memory" / "project-rules.json",
        resolved / ".dreampia-skill" / "memory" / "project-rules.json",
        resolved / ".dreampia" / "memory" / "project-rules.json",
        resolved / state_dir / "project.json",
        resolved / ".dreampia" / "project.json",
    )
    for cfg_path in candidates:
        if cfg_path.is_file() and not cfg_path.is_symlink():
            try:
                data = _json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("enforce_briefing") is False:
                    return False
            except (OSError, ValueError, TypeError):
                pass
    return True


def resolve_role_alias(name_or_callsign: str) -> str:

    """역할 ID 또는 매트릭스 코드네임(영문/한글)을 표준 역할 ID로 변환한다."""
    token = str(name_or_callsign or "").strip().lower()
    if token in AGENT_CALLSIGNS:
        return token
    for role_id, meta in AGENT_CALLSIGNS.items():
        if token in (meta["callsign"].lower(), meta["name_ko"].lower()):
            return "executor" if role_id == "implementer" else role_id
    raise ValueError(f"알 수 없는 에이전트 역할 또는 코드네임입니다: {name_or_callsign}")


def describe_agent_squad(roles: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
    """역할 목록에 대응하는 매트릭스 에이전트 스쿼드 메타데이터 목록을 반환한다."""
    squad: list[dict[str, str]] = []
    for r in roles:
        meta = AGENT_CALLSIGNS.get(r, {"callsign": r.title(), "name_ko": r, "title_ko": r})
        squad.append(
            {
                "role": r,
                "callsign": meta["callsign"],
                "name_ko": meta["name_ko"],
                "title_ko": meta["title_ko"],
            }
        )
    return squad


@dataclass(frozen=True)
class GoalClassification:
    goal_kind: str
    normalized_goal: str
    matched_signals: tuple[str, ...]
    message_ko: str

    def to_dict(self) -> dict[str, object]:
        return {
            "goal_kind": self.goal_kind,
            "normalized_goal": self.normalized_goal,
            "matched_signals": list(self.matched_signals),
            "message_ko": self.message_ko,
        }


@dataclass(frozen=True)
class RiskClassification:
    risk_level: str
    reasons: tuple[str, ...]
    cleanroom_required: bool
    message_ko: str

    def to_dict(self) -> dict[str, object]:
        return {
            "risk_level": self.risk_level,
            "reasons": list(self.reasons),
            "cleanroom_required": self.cleanroom_required,
            "message_ko": self.message_ko,
        }


@dataclass(frozen=True)
class RouteDecision:
    goal_kind: str
    profile: str
    risk_level: str
    risk_reasons: tuple[str, ...]
    roles: tuple[str, ...]
    required_gates: tuple[str, ...]
    requires_write_boundary: bool
    cleanroom_isolation: bool
    reason: str
    message_ko: str
    magic_shorthands: tuple[str, ...] = ()
    execution_mode: str = "standard"
    continuous_loop: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "commander": AGENT_CALLSIGNS["router"],
            "goal_kind": self.goal_kind,
            "profile": self.profile,
            "risk_level": self.risk_level,
            "risk_reasons": list(self.risk_reasons),
            "roles": list(self.roles),
            "agent_squad": describe_agent_squad(self.roles),
            "required_gates": list(self.required_gates),
            "requires_write_boundary": self.requires_write_boundary,
            "cleanroom_isolation": self.cleanroom_isolation,
            "magic_shorthands": list(self.magic_shorthands),
            "execution_mode": self.execution_mode,
            "continuous_loop": self.continuous_loop,
            "reason": self.reason,
            "message_ko": self.message_ko,
        }


MAGIC_PREFIX_MAP: dict[str, str] = {
    "ulw": "ulw",
    "ultrawork": "ulw",
    "autopilot": "ulw",
    "풀가동": "ulw",
    "오토파일럿": "ulw",
    "loop": "loop",
    "until-pass": "loop",
    "루프": "loop",
    "완주": "loop",
    "끝까지": "loop",
    "btw": "btw",
    "quick": "btw",
    "eco": "btw",
    "잠깐": "btw",
    "빠르게": "btw",
    "sdd": "sdd",
    "plan": "sdd",
    "spec": "sdd",
    "명세": "sdd",
    "설계": "sdd",
    "tdd": "tdd",
    "red-green": "tdd",
    "티디디": "tdd",
    "re": "re",
    "cleanroom": "re",
    "역설계": "re",
    "클린룸": "re",
    "audit": "audit",
    "trinity": "audit",
    "sec": "audit",
    "감사": "audit",
    "보안점검": "audit",
    "ui": "ui",
    "niobe": "ui",
    "화면": "ui",
    "디자인": "ui",
    "climb": "climb",
    "hillclimb": "climb",
    "성능등반": "climb",
    "자율실험": "climb",
    "blast": "blast",
    "blast-radius": "blast",
    "폭발반경": "blast",
    "영향도": "blast",
    "interrogate": "interrogate",
    "심문": "interrogate",
    "적대적리뷰": "interrogate",
    "unslop": "unslop",
    "deslop": "unslop",
    "군더더기제거": "unslop",
    "슬롭제거": "unslop",
    "sharpen": "sharpen",
    "boost": "sharpen",
    "interview": "sharpen",
    "고도화": "sharpen",
    "구체화": "sharpen",
    "생각": "sharpen",
    "부스트": "sharpen",
    "인터뷰": "sharpen",
}

_INLINE_MAGIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ulw", re.compile(r"\b(ulw|ultrawork|autopilot)\b", re.IGNORECASE)),
    ("loop", re.compile(r"\b(until-pass)\b", re.IGNORECASE)),
    ("btw", re.compile(r"\bbtw\b", re.IGNORECASE)),
    ("sdd", re.compile(r"\b(sdd)\b", re.IGNORECASE)),
    ("tdd", re.compile(r"\btdd\b", re.IGNORECASE)),
    ("climb", re.compile(r"\b(hillclimb)\b", re.IGNORECASE)),
    ("blast", re.compile(r"\bblast-radius\b", re.IGNORECASE)),
    ("interrogate", re.compile(r"\binterrogate\b", re.IGNORECASE)),
    ("unslop", re.compile(r"\b(unslop|deslop)\b", re.IGNORECASE)),
    ("sharpen", re.compile(r"\b(sharpen)\b", re.IGNORECASE)),
)


def _normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    collapsed = " ".join(normalized.strip().split())
    return collapsed[:1024]


def parse_magic_shorthands(goal: str) -> tuple[str, ...]:
    """사용자 프롬프트 앞부분 프리픽스(`ulw`, `loop`, `btw` 등) 및 명시적 단축 토큰을 추출한다."""
    normalized = _normalize(goal)
    if not normalized:
        return ()
    detected: list[str] = []
    tokens = normalized.split()
    # Leading 1~3 tokens can be shorthand prefixes (e.g. "ulw loop 결제 구현", "/btw 질문", "$ulw-loop 결제")
    for raw_tok in tokens[:3]:
        cleaned = raw_tok.strip("/$[]:,!-").lower()
        canonical = MAGIC_PREFIX_MAP.get(cleaned)
        if canonical and canonical not in detected:
            detected.append(canonical)
        else:
            break

    for canonical, pattern in _INLINE_MAGIC_PATTERNS:
        if pattern.search(normalized) and canonical not in detected:
            detected.append(canonical)

    return tuple(detected)


def strip_magic_shorthands(goal: str) -> str:
    """프롬프트 선두의 매직 단축어 토큰을 제거하고 순수 작업 대상 텍스트를 반환한다."""
    normalized = _normalize(goal)
    if not normalized:
        return ""
    tokens = normalized.split()
    idx = 0
    for raw_tok in tokens[:3]:
        cleaned = raw_tok.strip("/$[]:,!-").lower()
        if cleaned in MAGIC_PREFIX_MAP:
            idx += 1
        else:
            break
    remainder = " ".join(tokens[idx:]).strip()
    return remainder if remainder else normalized


def _matches(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in patterns)


def classify_goal(goal: str) -> GoalClassification:
    """사용자 목표(한글/영문) 및 단축어를 부작용 없이 결정론적으로 분류한다."""
    normalized = _normalize(goal)
    if not normalized or len(normalized) < 2:
        return GoalClassification(
            goal_kind="unsupported",
            normalized_goal=normalized,
            matched_signals=("empty-or-too-short",),
            message_ko="목표 설명이 비어 있거나 너무 짧아 실행할 수 없습니다.",
        )

    if _matches(UNSAFE_PATTERNS, normalized):
        return GoalClassification(
            goal_kind="unsupported",
            normalized_goal=normalized,
            matched_signals=("unsafe-or-injection-pattern",),
            message_ko="보안 정책 또는 검증 우회 패턴이 감지되어 실행이 거부되었습니다.",
        )

    shorthands = parse_magic_shorthands(normalized)
    signals: list[str] = [f"magic:{s}" for s in shorthands]

    if "btw" in shorthands:
        return GoalClassification(
            goal_kind="explain",
            normalized_goal=normalized,
            matched_signals=tuple(signals + ["explain"]),
            message_ko="사이드 질의/즉답(btw) 단축어가 감지되어 문맥 보존 설명 목표로 분류되었습니다.",
        )

    if _matches(OPERATE_PATTERNS, normalized):
        signals.append("operate")
    if _matches(CHANGE_PATTERNS, normalized):
        signals.append("change")
    if _matches(REVIEW_PATTERNS, normalized):
        signals.append("review")
    if _matches(TEST_PATTERNS, normalized):
        signals.append("test")
    if _matches(EXPLAIN_PATTERNS, normalized):
        signals.append("explain")

    if any(s in shorthands for s in ("audit", "blast", "interrogate")) and "change" not in signals and "operate" not in signals:
        if "review" not in signals:
            signals.append("review")

    if any(s in shorthands for s in ("ulw", "loop", "sdd", "tdd", "re", "ui", "climb", "unslop", "sharpen")) and not any(
        k in signals for k in ("operate", "change", "review", "test", "explain")
    ):
        signals.append("change")

    if "operate" in signals:
        return GoalClassification(
            goal_kind="operate",
            normalized_goal=normalized,
            matched_signals=tuple(signals),
            message_ko="운영/배포 관련 목표로 분류되었습니다.",
        )
    if "change" in signals:
        return GoalClassification(
            goal_kind="change",
            normalized_goal=normalized,
            matched_signals=tuple(signals),
            message_ko="코드/문서 변경 및 구현 목표로 분류되었습니다.",
        )
    if "review" in signals:
        return GoalClassification(
            goal_kind="review",
            normalized_goal=normalized,
            matched_signals=tuple(signals),
            message_ko="코드 리뷰 및 감사 목표로 분류되었습니다.",
        )
    if "test" in signals:
        return GoalClassification(
            goal_kind="test",
            normalized_goal=normalized,
            matched_signals=tuple(signals),
            message_ko="테스트 및 검증 실행 목표로 분류되었습니다.",
        )
    if "explain" in signals:
        return GoalClassification(
            goal_kind="explain",
            normalized_goal=normalized,
            matched_signals=tuple(signals),
            message_ko="설명 및 구조 분석 목표로 분류되었습니다.",
        )

    return GoalClassification(
        goal_kind="unsupported",
        normalized_goal=normalized,
        matched_signals=("ambiguous-goal",),
        message_ko="목표 의도가 모호하여 구체적인 작업 지시가 필요합니다.",
    )


def classify_risk(
    goal: str,
    goal_kind: str,
    *,
    repo_dirty: bool = False,
    repo_inspection_failed: bool = False,
) -> RiskClassification:
    """목표 텍스트, 분류된 의도, 저장소 상태를 기반으로 위험도를 산정한다."""
    normalized = _normalize(goal)
    shorthands = parse_magic_shorthands(normalized)
    reasons: list[str] = []
    cleanroom_required = False

    if "btw" in shorthands and goal_kind != "unsupported":
        return RiskClassification(
            risk_level="low",
            reasons=("magic-shorthand:btw", "read-only-or-bounded-check"),
            cleanroom_required=False,
            message_ko="사이드 질의(btw) 단축어로 읽기 전용 저위험 작업으로 분류되었습니다.",
        )

    if goal_kind in ("operate", "unsupported"):
        reasons.append(f"goal-kind:{goal_kind}")

    if "re" in shorthands or _matches(CLEANROOM_PATTERNS, normalized):
        reasons.append("cleanroom-sensitive")
        cleanroom_required = True

    if "ulw" in shorthands:
        reasons.append("magic-shorthand:ulw")

    if _matches(SECURITY_PATTERNS, normalized):
        reasons.append("security-sensitive")

    if _matches(DESTRUCTIVE_PATTERNS, normalized):
        reasons.append("destructive-change")

    if repo_inspection_failed:
        reasons.append("repository-inspection-failed")
    elif repo_dirty:
        reasons.append("repository-dirty")

    if (
        cleanroom_required
        or "magic-shorthand:ulw" in reasons
        or "security-sensitive" in reasons
        or "destructive-change" in reasons
        or "repository-inspection-failed" in reasons
        or goal_kind in ("operate", "unsupported")
    ):
        return RiskClassification(
            risk_level="high",
            reasons=tuple(reasons) if reasons else ("high-risk-policy",),
            cleanroom_required=cleanroom_required,
            message_ko="고위험 또는 풀가동(ulw) 작업으로 분류되어 엄격한 통제 또는 클린룸 프로파일이 필요합니다.",
        )

    if goal_kind == "change" or repo_dirty:
        if not reasons:
            reasons.append("code-or-state-change")
        return RiskClassification(
            risk_level="medium",
            reasons=tuple(reasons),
            cleanroom_required=False,
            message_ko="일반 변경 작업으로 분류되어 팀 역할 분리 및 검증 게이트가 적용됩니다.",
        )

    return RiskClassification(
        risk_level="low",
        reasons=("read-only-or-bounded-check",),
        cleanroom_required=False,
        message_ko="저위험 읽기 전용 또는 단일 검증 작업으로 분류되었습니다.",
    )


def inspect_repo_status(root: Path) -> tuple[bool, bool]:
    """Git 작업 트리 상태를 점검하여 (repo_dirty, repo_inspection_failed)를 반환한다."""
    git_dir = root / ".git"
    if not git_dir.exists():
        return False, False
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return False, True
        return bool(proc.stdout.strip()), False
    except (OSError, subprocess.TimeoutExpired):
        return False, True


def _apply_shorthand_overrides(
    base: RouteDecision,
    shorthands: tuple[str, ...],
) -> RouteDecision:
    """감지된 매직 단축어(ulw, loop, btw, sdd, tdd, re, audit, ui)를 RouteDecision에 반영한다."""
    if not shorthands or base.goal_kind == "unsupported":
        return base

    if "btw" in shorthands:
        return RouteDecision(
            goal_kind="explain",
            profile="quick",
            risk_level="low",
            risk_reasons=base.risk_reasons,
            roles=("planner",),
            required_gates=(),
            requires_write_boundary=False,
            cleanroom_isolation=False,
            reason="magic-shorthand-btw",
            message_ko="btw(잠깐/빠르게) 단축어가 활성화되어 파일 변경 없이 Oracle이 즉시 답변하는 quick 모드로 동작합니다.",
            magic_shorthands=shorthands,
            execution_mode="side-query",
            continuous_loop=False,
        )

    roles_list = list(base.roles)
    gates_list = list(base.required_gates)
    profile = base.profile
    cleanroom_iso = base.cleanroom_isolation
    write_bound = base.requires_write_boundary
    continuous = any(s in shorthands for s in ("loop", "climb"))
    exec_mode = "standard"

    def ensure_role(r: str) -> None:
        if r not in roles_list:
            roles_list.append(r)

    def ensure_gate(g: str) -> None:
        if g not in gates_list:
            gates_list.append(g)

    if "re" in shorthands:
        profile = "cleanroom"
        cleanroom_iso = True
        write_bound = True
        exec_mode = "cleanroom-reconstruct"
        for r in ("planner", "analyst", "executor", "reviewer", "verifier", "privacy-guard"):
            ensure_role(r)
        for g in ("before-dev-start", "before-claim-complete", "before-client-send", "reconstruct-verify", "golden-io"):
            ensure_gate(g)

    if "ulw" in shorthands:
        if profile != "cleanroom":
            profile = "controlled"
        write_bound = True
        exec_mode = "ultrawork"
        for r in ("planner", "architect", "executor", "reviewer", "verifier", "privacy-guard"):
            ensure_role(r)
        for g in ("before-dev-start", "sdd-check", "audit-code", "autopilot-gate", "before-claim-complete"):
            ensure_gate(g)

    if "loop" in shorthands:
        if exec_mode == "standard":
            exec_mode = "continuous-loop"
        write_bound = True
        for r in ("planner", "executor", "reviewer", "verifier"):
            ensure_role(r)
        for g in ("sdd-check", "audit-code", "autopilot-gate", "before-claim-complete"):
            ensure_gate(g)

    if "climb" in shorthands:
        if exec_mode == "standard":
            exec_mode = "metric-climb"
        write_bound = True
        for r in ("planner", "executor", "reviewer", "verifier"):
            ensure_role(r)
        for g in ("metric-climb", "audit-code", "before-claim-complete"):
            ensure_gate(g)

    if "sdd" in shorthands:
        if exec_mode == "standard":
            exec_mode = "sdd-spec"
        for r in ("planner", "architect", "verifier"):
            ensure_role(r)
        for g in ("before-dev-start", "sdd-check"):
            ensure_gate(g)

    if "tdd" in shorthands:
        if exec_mode == "standard":
            exec_mode = "strict-tdd"
        write_bound = True
        for r in ("executor", "reviewer", "verifier"):
            ensure_role(r)
        for g in ("sdd-check", "audit-code", "before-claim-complete"):
            ensure_gate(g)

    if "audit" in shorthands:
        if exec_mode == "standard":
            exec_mode = "deep-audit"
        for r in ("reviewer", "privacy-guard", "verifier"):
            ensure_role(r)
        for g in ("audit-code", "instruction-check"):
            ensure_gate(g)

    if "blast" in shorthands:
        if exec_mode == "standard":
            exec_mode = "blast-radius"
        for r in ("architect", "analyst", "reviewer", "verifier"):
            ensure_role(r)
        for g in ("blast-radius", "audit-code"):
            ensure_gate(g)

    if "interrogate" in shorthands:
        if exec_mode == "standard":
            exec_mode = "adversarial-interrogate"
        for r in ("architect", "reviewer", "privacy-guard", "verifier"):
            ensure_role(r)
        for g in ("audit-code", "blast-radius", "instruction-check"):
            ensure_gate(g)

    if "unslop" in shorthands:
        if exec_mode == "standard":
            exec_mode = "unslop-clean"
        write_bound = True
        for r in ("executor", "reviewer", "verifier"):
            ensure_role(r)
        for g in ("audit-code", "before-claim-complete"):
            ensure_gate(g)

    if "ui" in shorthands:
        if exec_mode == "standard":
            exec_mode = "visual-ui"
        for r in ("ux-designer", "executor", "verifier"):
            ensure_role(r)
        for g in ("visual-check", "ui-evidence"):
            ensure_gate(g)

    if "sharpen" in shorthands:
        if exec_mode == "standard":
            exec_mode = "prompt-sharpen"
        for r in ("planner", "architect", "executor", "reviewer", "verifier"):
            ensure_role(r)
        for g in ("before-dev-start", "audit-code", "before-claim-complete"):
            ensure_gate(g)

    return RouteDecision(
        goal_kind=base.goal_kind,
        profile=profile,
        risk_level=base.risk_level,
        risk_reasons=base.risk_reasons,
        roles=tuple(roles_list),
        required_gates=tuple(gates_list),
        requires_write_boundary=write_bound,
        cleanroom_isolation=cleanroom_iso,
        reason=f"magic-shorthand:{'+'.join(shorthands)}",
        message_ko=f"단축어({', '.join(shorthands)})가 감지되어 '{exec_mode}' 실행 모드(프로파일: {profile}, 연속 루프: {continuous})를 적용합니다.",
        magic_shorthands=shorthands,
        execution_mode=exec_mode,
        continuous_loop=continuous,
    )


def plan_route(
    goal: str,
    *,
    root: Path | None = None,
    repo_dirty: bool | None = None,
    repo_inspection_failed: bool | None = None,
) -> RouteDecision:
    """목표와 위험도를 바탕으로 Dreampia 실행 프로파일, 필수 역할, 검증 게이트를 결정한다."""
    goal_cls = classify_goal(goal)
    shorthands = parse_magic_shorthands(goal)
    if root is not None and (repo_dirty is None or repo_inspection_failed is None):
        detected_dirty, detected_failed = inspect_repo_status(root)
        if repo_dirty is None:
            repo_dirty = detected_dirty
        if repo_inspection_failed is None:
            repo_inspection_failed = detected_failed

    risk_cls = classify_risk(
        goal,
        goal_cls.goal_kind,
        repo_dirty=bool(repo_dirty),
        repo_inspection_failed=bool(repo_inspection_failed),
    )

    if goal_cls.goal_kind == "unsupported":
        return RouteDecision(
            goal_kind="unsupported",
            profile="controlled",
            risk_level="high",
            risk_reasons=risk_cls.reasons,
            roles=("planner", "reviewer"),
            required_gates=("before-dev-start",),
            requires_write_boundary=True,
            cleanroom_isolation=False,
            reason="unsupported-or-unsafe-goal",
            message_ko=goal_cls.message_ko,
        )

    if risk_cls.cleanroom_required:
        base_dec = RouteDecision(
            goal_kind=goal_cls.goal_kind,
            profile="cleanroom",
            risk_level="high",
            risk_reasons=risk_cls.reasons,
            roles=("planner", "analyst", "executor", "reviewer", "verifier", "privacy-guard"),
            required_gates=("before-dev-start", "before-claim-complete", "before-client-send"),
            requires_write_boundary=True,
            cleanroom_isolation=True,
            reason="cleanroom-isolation-required",
            message_ko="역공학/오염 격리 대상이므로 분석가(Keymaker/analyst)와 구현자(Neo/executor) 번들을 분리하는 cleanroom 프로파일을 적용합니다.",
        )
        return _apply_shorthand_overrides(base_dec, shorthands)

    if goal_cls.goal_kind == "operate" or risk_cls.risk_level == "high":
        base_dec = RouteDecision(
            goal_kind=goal_cls.goal_kind,
            profile="controlled",
            risk_level="high",
            risk_reasons=risk_cls.reasons,
            roles=("planner", "executor", "reviewer", "verifier", "privacy-guard"),
            required_gates=("before-dev-start", "app-static", "before-claim-complete", "before-client-send"),
            requires_write_boundary=True,
            cleanroom_isolation=False,
            reason="high-risk-or-operational-goal",
            message_ko="고위험 또는 운영 작업이므로 쓰기 경계 강제와 전체 검증 게이트를 포함한 controlled 프로파일을 적용합니다.",
        )
        return _apply_shorthand_overrides(base_dec, shorthands)

    if goal_cls.goal_kind in ("explain", "review"):
        base_dec = RouteDecision(
            goal_kind=goal_cls.goal_kind,
            profile="quick",
            risk_level=risk_cls.risk_level,
            risk_reasons=risk_cls.reasons,
            roles=("planner", "reviewer") if goal_cls.goal_kind == "review" else ("planner",),
            required_gates=(),
            requires_write_boundary=False,
            cleanroom_isolation=False,
            reason=f"{goal_cls.goal_kind}-goal",
            message_ko="읽기 전용 분석/리뷰 작업이므로 빠른 quick 프로파일을 적용합니다.",
        )
        return _apply_shorthand_overrides(base_dec, shorthands)

    if goal_cls.goal_kind == "test":
        base_dec = RouteDecision(
            goal_kind="test",
            profile="quick" if risk_cls.risk_level == "low" else "team",
            risk_level=risk_cls.risk_level,
            risk_reasons=risk_cls.reasons,
            roles=("verifier",) if risk_cls.risk_level == "low" else ("executor", "verifier"),
            required_gates=("before-claim-complete",),
            requires_write_boundary=False,
            cleanroom_isolation=False,
            reason="verification-goal",
            message_ko="검증 및 테스트 실행 작업이므로 증거 기반 완료 게이트를 적용합니다.",
        )
        return _apply_shorthand_overrides(base_dec, shorthands)

    base_dec = RouteDecision(
        goal_kind="change",
        profile="team",
        risk_level=risk_cls.risk_level,
        risk_reasons=risk_cls.reasons,
        roles=("planner", "executor", "reviewer", "verifier"),
        required_gates=("before-dev-start", "app-static", "before-claim-complete"),
        requires_write_boundary=True,
        cleanroom_isolation=False,
        reason="bounded-change-goal",
        message_ko="일반 기능 구현/수정 작업이므로 역할이 분리된 team 프로파일과 소유 경로 쓰기 경계를 적용합니다.",
    )
    return _apply_shorthand_overrides(base_dec, shorthands)


@dataclass(frozen=True)
class PromptExpansionBrief:
    """사용자의 짧은 입력을 한 번 더 생각하여 구조화된 국문 엔지니어링 프롬프트 및 가시적 브리핑으로 변환한 결과."""

    raw_goal: str
    core_subject: str
    goal_kind: str
    profile: str
    execution_mode: str
    expanded_prompt_ko: str
    injected_constraints_ko: tuple[str, ...]
    edge_cases_to_check_ko: tuple[str, ...]
    completion_criteria_ko: tuple[str, ...]
    squad_pipeline_ko: str
    echo_markdown_ko: str
    ambiguity_level: str = "low"
    clarifying_questions_ko: tuple[str, ...] = ()
    recommended_next_actions_ko: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_goal": self.raw_goal,
            "core_subject": self.core_subject,
            "goal_kind": self.goal_kind,
            "profile": self.profile,
            "execution_mode": self.execution_mode,
            "ambiguity_level": self.ambiguity_level,
            "expanded_prompt_ko": self.expanded_prompt_ko,
            "injected_constraints_ko": list(self.injected_constraints_ko),
            "edge_cases_to_check_ko": list(self.edge_cases_to_check_ko),
            "completion_criteria_ko": list(self.completion_criteria_ko),
            "clarifying_questions_ko": list(self.clarifying_questions_ko),
            "recommended_next_actions_ko": [dict(item) for item in self.recommended_next_actions_ko],
            "squad_pipeline_ko": self.squad_pipeline_ko,
            "echo_markdown_ko": self.echo_markdown_ko,
        }


def _format_squad_pipeline_ko(roles: tuple[str, ...]) -> str:
    parts: list[str] = ["Morpheus(라우터)"]
    for r in roles:
        meta = AGENT_CALLSIGNS.get(r, {"callsign": r.title(), "name_ko": r})
        parts.append(f"{meta['callsign']}({meta['name_ko']})")
    return " -> ".join(parts)


_LEADING_FILLER_PREFIXES_KO: tuple[str, ...] = (
    "지금 우리가 ",
    "지금 우리 ",
    "지금은 ",
    "지금 ",
    "이번에는 우리가 ",
    "이번에는 ",
    "이번에 ",
    "일단 우리가 ",
    "일단 ",
    "먼저 ",
    "자 이제 ",
    "이제 우리가 ",
    "이제 ",
    "우리가 ",
)

_TRAILING_REQUEST_SUFFIXES_KO: tuple[str, ...] = (
    "하는 작업부터 진행하자",
    "하는 작업 진행하자",
    "하는 작업하자",
    "하는 작업해줘",
    "하는 작업",
    "작업부터 진행하자",
    "작업 진행하자",
    "작업하자",
    "작업해줘",
    "작업해",
    "진행하자",
    "진행해보자",
    "해보자",
    "해 보자",
    "만들어보자",
    "만들자",
    "고도화하자",
    "구현하자",
    "개선하자",
    "수정하자",
    "점검하자",
    "만들어주세요",
    "만들어 주세요",
    "만들어줘요",
    "만들어줘",
    "만들어 줘",
    "만들어",
    "만들기",
    "구현해주세요",
    "구현해 주세요",
    "구현해줘요",
    "구현해줘",
    "구현해 줘",
    "구현해",
    "구현하기",
    "고쳐주세요",
    "고쳐 주세요",
    "고쳐줘요",
    "고쳐줘",
    "고쳐 줘",
    "고쳐",
    "수정해주세요",
    "수정해 주세요",
    "수정해줘요",
    "수정해줘",
    "수정해 줘",
    "수정해",
    "추가해주세요",
    "추가해 주세요",
    "추가해줘요",
    "추가해줘",
    "추가해 줘",
    "추가해",
    "작성해주세요",
    "작성해 주세요",
    "작성해줘요",
    "작성해줘",
    "작성해 줘",
    "작성해",
    "분석해주세요",
    "분석해 주세요",
    "분석해줘요",
    "분석해줘",
    "분석해 줘",
    " 분석해",
    "점검해주세요",
    "점검해 주세요",
    "점검해줘요",
    "점검해줘",
    "점검해 줘",
    " 점검해",
    "확인해주세요",
    "확인해 주세요",
    "확인해줘요",
    "확인해줘",
    "확인해 줘",
    " 확인해",
    "설명해주세요",
    "설명해 주세요",
    "설명해줘요",
    "설명해줘",
    "설명해 줘",
    " 설명해",
    "진행해주세요",
    "진행해 주세요",
    "진행해줘",
    "진행해 줘",
    "진행해",
    "진행",
    "해주세요",
    "해 주세요",
    "해줘요",
    "해줘",
    "해 줘",
    "해봐",
    "해 봐",
    "부탁해",
    "하자",
    "해",
    "좀",
)


def _extract_clean_topic_ko(subject: str) -> str:
    """사용자 입력에서 구어체 서두('지금 우리가 ' 등)와 명령/청유형 어미('~만들어줘', '~작업하자' 등)를 제거해 핵심 명사구 주제를 추출한다."""
    cleaned = subject.strip().strip("'\"`").strip()
    prefix_changed = True
    while prefix_changed and cleaned:
        prefix_changed = False
        for prefix in _LEADING_FILLER_PREFIXES_KO:
            if cleaned.startswith(prefix):
                candidate = cleaned[len(prefix) :].strip()
                if candidate:
                    cleaned = candidate
                    prefix_changed = True
                    break

    changed = True
    while changed and cleaned:
        changed = False
        for suffix in _TRAILING_REQUEST_SUFFIXES_KO:
            if cleaned.endswith(suffix):
                candidate = cleaned[: -len(suffix)].strip()
                if candidate:
                    cleaned = candidate
                    changed = True
                    break
    if (
        not cleaned
        or len(cleaned) <= 1
        or cleaned in ("다음", "계속", "이어서", "바로", "그대로", "우선", "먼저", "다음꺼", "다음거")
        or re.fullmatch(r"[0-9,\s번.]+", cleaned)
    ):
        return "현재 요청 작업"
    return cleaned


def _build_socratic_interview_questions_ko(
    subject: str,
    goal_kind: str,
    execution_mode: str,
    *,
    has_ui: bool,
    has_sec: bool,
    has_cleanroom: bool,
    has_climb: bool,
) -> tuple[str, tuple[str, ...]]:
    """요구사항의 모호성 수준(low/medium/high)을 판정하고 초보자도 답하기 쉬운 국문 핵심 질문 3개를 생성한다."""
    stripped = subject.strip()
    has_concrete_anchor = any(ch in stripped for ch in ("/", ".", "-", "_", ":"))
    if goal_kind == "unsupported" or execution_mode == "prompt-sharpen" or len(stripped) <= 10:
        ambiguity = "high"
    elif len(stripped) <= 22 and not has_concrete_anchor:
        ambiguity = "medium"
    else:
        ambiguity = "low"

    pool: list[str] = []
    if has_cleanroom:
        pool.extend(
            (
                "분석할 원본 아티팩트(파일/폴더) 경로와 복원할 핵심 기능 범위는 어디까지인가요?",
                "동작 일치 여부를 비교할 기준 입출력 예시(golden-io.json)가 준비되어 있나요?",
                "원본 저작권 보호를 위해 제외해야 할 외부 라이브러리나 독점 규격이 있나요?",
            )
        )
    if has_climb:
        pool.extend(
            (
                "개선할 목표 수치(예: 응답 속도 단축, 처리량 향상)와 측정 명령어는 무엇인가요?",
                "실험 중 절대 수정하면 안 되는 채점/벤치마크 파일 경로는 어디인가요?",
                "메모리 사용량이나 기존 기능 호환성에서 꼭 지켜야 할 제한선이 있나요?",
            )
        )
    if has_ui:
        pool.extend(
            (
                "주로 사용할 화면 크기(뷰포트: PC/모바일)와 버튼 중복 클릭·로딩 중 화면 처리는 어떻게 할까요?",
                "입력이 잘못되었거나 완료되었을 때 알림(인라인 문구·토스트·팝업)을 어떻게 보여줄까요?",
                "꼭 맞춰야 하는 기준 디자인이나 기존 화면 컴포넌트 스타일이 있나요?",
            )
        )
    if has_sec:
        pool.extend(
            (
                "권한이 없거나 만료된 요청이 들어오면 어떤 한글 안내 문구를 띄우고 차단할까요?",
                "비밀키나 토큰은 어떤 환경변수(설정 파일)에서 불러오도록 연결할까요?",
                "중복 결제나 비정상 접근을 막기 위해 추가로 확인할 조건이 있나요?",
            )
        )

    general_fallbacks = (
        "수정이 필요한 핵심 파일(또는 폴더) 위치와 그대로 유지해야 할 기존 기능이 있나요?",
        "빈 값이나 잘못된 입력이 들어왔을 때 어떤 한글 안내 문구를 보여줄까요?",
        "작업이 잘 끝났는지 확인할 핵심 테스트 시나리오는 무엇인가요?",
    )
    for q in general_fallbacks:
        if len(pool) >= 3:
            break
        if q not in pool:
            pool.append(q)

    return ambiguity, tuple(pool[:3])


def _inspect_project_state_snapshot(
    root: Path | None,
    *,
    repo_dirty: bool | None = None,
) -> dict[str, object]:
    """프로젝트 디렉터리 상태(Git, SDD 명세/원장, 클린룸, 오토파일럿 판정, 학습 규칙)를 부작용 없이 스냅샷으로 수집한다."""
    snapshot: dict[str, object] = {
        "project_root": str(root.resolve()) if root is not None and root.exists() else None,
        "repo_dirty": False,
        "has_sdd_prd": False,
        "has_sdd_ledger": False,
        "sdd_unverified_count": 0,
        "has_contaminated_zone": False,
        "has_cleanroom_spec": False,
        "has_autopilot_verdict": False,
        "autopilot_status": "NOT_RUN",
        "learned_rule_count": 0,
        "learned_rules": [],
    }
    if root is None or root.is_symlink() or not root.is_dir():
        return snapshot

    resolved = root.resolve()
    if repo_dirty is None:
        dirty, _ = inspect_repo_status(resolved)
    else:
        dirty = repo_dirty
    snapshot["repo_dirty"] = dirty

    prd_file = resolved / "docs" / "01_PRD_REQUIREMENTS.md"
    if prd_file.is_file() and not prd_file.is_symlink():
        try:
            prd_text = prd_file.read_text(encoding="utf-8", errors="ignore")
            snapshot["has_sdd_prd"] = bool(re.search(r"\b(?:PRD-R|REQ-)[A-Za-z0-9_-]+", prd_text))
        except OSError:
            pass

    import json as _json

    sdd_ledger_file = resolved / "evidence" / "sdd-ledger.json"
    if sdd_ledger_file.is_file() and not sdd_ledger_file.is_symlink():
        snapshot["has_sdd_ledger"] = True
        try:
            ledger_data = _json.loads(sdd_ledger_file.read_text(encoding="utf-8"))
            if isinstance(ledger_data, dict):
                reqs = ledger_data.get("requirements", [])
                if isinstance(reqs, list):
                    unverified = sum(
                        1
                        for r in reqs
                        if isinstance(r, dict)
                        and (
                            not r.get("linked_tasks")
                            or not r.get("linked_tests")
                            or str(r.get("verdict", "")).upper() == "FAIL"
                        )
                    )
                    snapshot["sdd_unverified_count"] = unverified
        except (OSError, ValueError, TypeError):
            pass

    cz_dir = resolved / "contaminated-zone"
    if cz_dir.is_dir() and not cz_dir.is_symlink():
        try:
            snapshot["has_contaminated_zone"] = any(p.is_file() for p in cz_dir.rglob("*"))
        except OSError:
            pass

    cleanroom_spec_file = resolved / "approved-spec" / "00_CLEANROOM_SPEC.md"
    snapshot["has_cleanroom_spec"] = cleanroom_spec_file.is_file() and not cleanroom_spec_file.is_symlink()

    verdict_file = resolved / "evidence" / "autopilot-verdict.json"
    if verdict_file.is_file() and not verdict_file.is_symlink():
        snapshot["has_autopilot_verdict"] = True
        try:
            verdict_data = _json.loads(verdict_file.read_text(encoding="utf-8"))
            if isinstance(verdict_data, dict):
                snapshot["autopilot_status"] = str(verdict_data.get("status", "UNKNOWN"))
        except (OSError, ValueError, TypeError):
            pass

    state_dir = resolve_skill_state_dir(resolved)
    rules_file = resolved / state_dir / "memory" / "project-rules.json"
    if not rules_file.is_file() and state_dir != ".dreampia":
        rules_file = resolved / ".dreampia" / "memory" / "project-rules.json"
    if rules_file.is_file() and not rules_file.is_symlink():
        try:
            rules_data = _json.loads(rules_file.read_text(encoding="utf-8"))
            if isinstance(rules_data, dict) and isinstance(rules_data.get("rules"), list):
                valid_rules = [r for r in rules_data["rules"] if isinstance(r, dict) and r.get("rule_ko")]
                snapshot["learned_rule_count"] = len(valid_rules)
                snapshot["learned_rules"] = valid_rules
        except (OSError, ValueError, TypeError):
            pass

    return snapshot


def recommend_next_actions(
    *,
    root: Path | None = None,
    goal: str = "",
    decision: RouteDecision | None = None,
    repo_dirty: bool | None = None,
) -> dict[str, object]:
    """현재 프로젝트 상태(SDD, 클린룸, Git, 코드 감사, 학습 규칙)와 목표를 분석해 초보자 친화적인 다음 추천 작업(Next Actions)을 반환한다."""
    normalized_goal = _normalize(goal) if goal else ""
    subject = strip_magic_shorthands(normalized_goal) if normalized_goal else "핵심 기능"
    if not subject:
        subject = "핵심 기능"
    clean_topic = _extract_clean_topic_ko(subject)
    eff_decision = decision if decision is not None else (plan_route(normalized_goal, root=root) if normalized_goal else None)
    shorthands = eff_decision.magic_shorthands if eff_decision is not None else ()
    exec_mode = eff_decision.execution_mode if eff_decision is not None else "standard"
    inferred_dirty = (
        repo_dirty
        if repo_dirty is not None
        else (("dirty-working-tree" in eff_decision.risk_reasons) if eff_decision is not None else None)
    )
    state = _inspect_project_state_snapshot(root, repo_dirty=inferred_dirty)

    actions: list[dict[str, str]] = []

    def add_action(
        shorthand: str,
        title_ko: str,
        reason_ko: str,
        prompt_example_ko: str,
        cli_command: str,
    ) -> None:
        if any(a["title_ko"] == title_ko for a in actions):
            return
        rank = f"{len(actions) + 1}순위"
        actions.append(
            {
                "priority": rank,
                "shorthand": shorthand,
                "title_ko": title_ko,
                "reason_ko": reason_ko,
                "prompt_example_ko": prompt_example_ko,
                "cli_command": cli_command,
            }
        )

    # 1. 클린룸 역공학 흐름 감지
    if bool(state.get("has_contaminated_zone")) and not bool(state.get("has_cleanroom_spec")):
        add_action(
            "re",
            "클린룸 명세서 초안 자동 생성",
            "분석 폴더(contaminated-zone)에서 안전하게 기능 명세서만 추출합니다.",
            "re 클린룸 명세서 초안부터 뽑아줘",
            "python -m harness.team_cli reconstruct-spec --project . --source contaminated-zone --apply",
        )
    elif "re" in shorthands or exec_mode == "cleanroom-reconstruct":
        add_action(
            "re",
            "클린룸 복원율 및 무오염 검증",
            "원본 코드 복사 없이 모든 기능이 재구현되었는지 확인합니다.",
            "re 클린룸 복원율이랑 입출력 일치 여부 검증해줘",
            "python -m harness.team_cli reconstruct-verify --project . --source contaminated-zone --target implementation",
        )

    # 2. 프롬프트 고도화(sharpen/구체화) 또는 SDD 미비 상태 감지
    if exec_mode == "prompt-sharpen" or "sharpen" in shorthands:
        add_action(
            "sdd",
            "질문 답변으로 기획서·할일 목록 자동 생성",
            "위 질문에 편하게 답해주시면 기획서와 작업 목록을 바로 만들어 드립니다.",
            "sdd 위 질문 답변 반영해서 기획서랑 할일 목록 만들어줘",
            f'python -m harness.team_cli interview-compile --project . --goal "{clean_topic}" --answers "답변1,답변2,답변3" --apply',
        )
    elif not bool(state.get("has_sdd_prd")) and root is not None:
        add_action(
            "sdd",
            "요구사항 기획서 및 테스트 계획 수립",
            "구현 전에 핵심 기능 목록과 테스트 기준을 간단히 정리합니다.",
            "sdd 요구사항 정리하고 테스트 계획부터 세워줘",
            f'python -m harness.team_cli interview-compile --project . --goal "{clean_topic}" --answers "핵심모듈,예외방어,단위테스트" --apply',
        )
    elif int(state.get("sdd_unverified_count", 0)) > 0:
        unv = int(state.get("sdd_unverified_count", 0))
        add_action(
            "tdd",
            f"미완료 요구사항({unv}건) 테스트 마무리",
            f"아직 테스트로 확인되지 않은 기능 {unv}건을 마저 검증합니다.",
            "tdd 남은 요구사항 테스트 작성하고 검증해줘",
            "python -m harness.team_cli sdd-check --project .",
        )

    # 3. 코드 변경/리뷰/일반 상태에 따른 폭발 반경 & 정적 코드 감사 추천
    if eff_decision is not None and eff_decision.goal_kind in ("change", "operate"):
        add_action(
            "audit",
            "방금 작성한 코드 품질·규칙 자동 점검",
            "타입 누락, 버튼 스타일, SOLID 원칙 위반이 없는지 빠르게 확인합니다.",
            "audit 방금 짠 코드 규칙 위반 없는지 점검해줘",
            "python -m harness.team_cli audit-code --project .",
        )
        add_action(
            "blast",
            "연결된 다른 파일 영향도 확인",
            "수정한 코드 때문에 다른 화면이나 기능이 깨지지 않는지 살핍니다.",
            "blast 수정한 파일과 연결된 곳에 영향 없는지 봐줘",
            "python -m harness.team_cli blast-radius --project .",
        )
    else:
        add_action(
            "ulw",
            "구현부터 테스트까지 원스톱 자동 완주",
            "설계된 내용을 바탕으로 코드 작성과 테스트 검증까지 한 번에 진행합니다.",
            "ulw 코드 구현하고 테스트 통과까지 끝내줘",
            "python -m harness.team_cli autopilot-gate --project .",
        )
        add_action(
            "audit",
            "전체 코드 품질·규칙 자동 점검",
            "프로젝트 내 타입 안전성과 코딩 규칙 준수 여부를 스캔합니다.",
            "audit 프로젝트 코드 품질 점검해줘",
            "python -m harness.team_cli audit-code --project .",
        )

    # 4. 자가 학습 규칙 또는 최종 완료 점검 안내 (여유 슬롯 보충)
    if len(actions) < 3:
        if int(state.get("learned_rule_count", 0)) == 0:
            add_action(
                "learn",
                "우리 프로젝트만의 코딩 규칙 기억시키기",
                "자주 쓰는 스타일이나 금지 규칙을 알려주시면 다음부터 자동으로 지킵니다.",
                "앞으로 이 프로젝트에서 꼭 지켜야 할 규칙 등록해줘",
                'python -m harness.team_cli learn-rule --project . --rule "금액 계산 시 float 금지" --forbidden-regex "\\bfloat\\s*\\(" --apply',
            )
        else:
            add_action(
                "loop",
                "최종 완료 게이트 통합 점검",
                "기획·테스트·코드 품질이 모두 통과되었는지 최종 확인합니다.",
                "loop 모든 점검 통과할 때까지 마무리해줘",
                "python -m harness.team_cli autopilot-gate --project .",
            )

    top_actions = actions[:3]
    md_lines = ["[Dreampia 다음 추천 작업 가이드 (Next Actions)]"]
    for idx, act in enumerate(top_actions, start=1):
        md_lines.append(
            f"{idx}. {act['title_ko']} ({act['reason_ko']}) -> 입력 예시: \"{act['prompt_example_ko']}\""
        )

    return {
        "action": "next-actions",
        "status": "PASS",
        "goal": normalized_goal,
        "execution_mode": exec_mode,
        "project_state": state,
        "next_actions": top_actions,
        "markdown_ko": "\n".join(md_lines),
        "message_ko": f"현재 프로젝트 상태와 작업 맥락을 분석하여 {len(top_actions)}개의 다음 추천 작업을 도출했습니다.",
    }


def expand_prompt_brief(
    goal: str,
    *,
    root: Path | None = None,
    decision: RouteDecision | None = None,
) -> PromptExpansionBrief:
    """사용자 원본 입력을 받아 앵무새 반복 없이 초보자 친화적인 국문 작전 브리핑을 생성한다."""
    normalized = _normalize(goal)
    eff_decision = decision if decision is not None else plan_route(goal, root=root)
    subject = strip_magic_shorthands(normalized) or normalized
    clean_topic = _extract_clean_topic_ko(subject)
    shorthands = eff_decision.magic_shorthands
    has_ui = "ui" in shorthands or _matches(UI_DOMAIN_PATTERNS, normalized)
    ui_rule_enforced = is_ui_rule_enforced(root)
    has_sec = "security-sensitive" in eff_decision.risk_reasons or _matches(SECURITY_PATTERNS, normalized)
    has_cleanroom = eff_decision.cleanroom_isolation or "re" in shorthands
    has_climb = "climb" in shorthands
    has_blast = "blast" in shorthands

    constraints: list[str] = []
    edge_cases: list[str] = []
    criteria: list[str] = []

    if eff_decision.goal_kind == "unsupported":
        expanded = (
            "요청하신 내용이 모호하거나 안전 정책에 맞지 않아 잠시 멈추었습니다. "
            "원하시는 작업 대상과 범위를 조금만 더 구체적으로 알려주세요."
        )
        constraints.append("보안 정책 및 검증 게이트 우회 요청은 Fail-Closed 원칙에 따라 무조건 차단")
        edge_cases.append("프롬프트 인젝션 및 비인가 시스템 명령 실행 차단 확인")
        criteria.append("안전하고 명확한 요구사항 재정의 후 라우팅 재실행")
    elif eff_decision.goal_kind == "explain":
        expanded = (
            f"[{clean_topic}] 관련 파일은 건드리지 않고(읽기 전용), "
            "핵심 동작 원리와 연결된 파일 구조만 알기 쉽게 정리해 드립니다."
        )
        constraints.append("읽기 전용(Read-Only) 문맥 보존 모드: 소스 코드 및 설정 파일 수정 금지")
        constraints.append("추측성 답변을 배제하고 실제 파일·심볼 경로를 근거로 한글 설명 작성")
        edge_cases.append("질문 대상 모듈과 연결된 상위/하위 의존성 누락 여부 확인")
        criteria.append("파일 변경 0건 유지 및 핵심 근거(파일/함수 링크) 포함 국문 답변 제시")
    elif eff_decision.goal_kind == "review":
        expanded = (
            f"[{clean_topic}] 코드에서 SOLID 5원칙, 타입 안전성(any 금지·반환 타입 명시), "
            "연결된 파일 영향도(Blast Radius), 숨은 예외 처리 누락까지 꼼꼼히 점검해 개선점을 알려드립니다."
        )
        constraints.append("SOLID 5원칙 및 타입 안전성(any 금지, 반환 타입 명시) 기준 정밀 대조")
        constraints.append("단순 스타일 지적이 아닌 실제 런타임 결함·경계 위반·폭발 반경 중심 분석")
        edge_cases.append("변경 시 연쇄 파급되는 1-Hop/2-Hop 상위 호출자(Dependents) 계약 깨짐 여부")
        edge_cases.append("빈 예외 처리(bare except: pass) 및 가짜 단언문(assert True) 은폐 여부")
        criteria.append("결함 심각도 분류, 근거 경로/라인 명시, 실행 가능한 국문 개선안 도출")
    elif eff_decision.goal_kind == "test":
        expanded = (
            f"[{clean_topic}]의 정상 동작뿐 아니라 빈 값·경계값·오류 상황까지 실제 테스트로 검증하고 결과를 명확히 정리해 드립니다."
        )
        constraints.append("형식적 통과용 가짜 테스트(assert True, 단언문 없는 테스트) 엄격 금지")
        constraints.append("실제 함수 호출 결과와 예외 발생 메시지를 단언문으로 직접 대조")
        edge_cases.append("빈 문자열/Null 입력, 0/음수/최대치 경계값, 중복 요청 시 예외 처리 검증")
        criteria.append("전체 단위/통합 테스트 PASS 및 검증 증거(명령어·결과·통과 건수) 확보")
    else:
        # change or operate
        domain_clause = "연결된 다른 파일이 깨지지 않도록 입출력 경계를 깔끔하게 분리하며,"
        if has_cleanroom:
            domain_clause = (
                "원본 코드(contaminated-zone)를 복사하지 않고 승인된 명세서만으로 깨끗하게 독립 재구현하며,"
            )
        elif has_climb:
            domain_clause = (
                "채점 기준 파일을 건드리지 않고 실제 성능 수치가 개선된 변경만 남기며,"
            )
        elif has_ui and ui_rule_enforced:
            domain_clause = (
                "버튼 기본 스타일(bg-transparent + hover/focus)과 lucide-react 아이콘 규격을 준수하고 중복 클릭·로딩·오류 상태를 매끄럽게 처리하며,"
            )
        elif has_ui:
            domain_clause = (
                "프로젝트 고유 디자인 시스템(목업·디자인 토큰 정본)을 준수하고 중복 클릭·로딩·오류 상태를 매끄럽게 처리하며,"
            )

        expanded = (
            f"[{clean_topic}] 작업 시 기본 동작뿐 아니라 입력값 검증·예외 방어·상태 일관성까지 함께 챙깁니다. "
            f"{domain_clause} SOLID 5원칙과 타입 안전성(any 금지·반환 타입 명시), 친절한 한글 안내 문구, 실제 테스트 검증까지 한 번에 적용합니다."
        )

        constraints.append("SOLID 5원칙(단일책임·개방폐쇄·리스코프치환·인터페이스분리·의존성역전) 필수 적용")
        constraints.append("타입 안전성 보장: any 타입 금지, 모든 함수 반환 타입 및 Props/데이터 인터페이스 명시")
        constraints.append("한글 우선 정책: 사용자 친화적 한글 에러 메시지 작성 및 빈 예외 무시(except: pass) 금지")
        if has_ui and ui_rule_enforced:
            constraints.append("UI 규격 강제: 버튼 기본 bg-transparent + hover/focus 상태 포함, 아이콘은 lucide-react 통일")
        elif has_ui:
            constraints.append("UI 규격: 프로젝트 고유 디자인 시스템(목업·토큰 정본) 준수 및 중복 클릭 방지")
        if has_sec:
            constraints.append("보안/인증 경계: 비밀키·토큰 하드코딩 금지 및 권한/세션 검증 Fail-Closed 적용")
        if has_cleanroom:
            constraints.append("클린룸 무오염 격리: contaminated-zone 직접 import/복사 차단 및 의무 원장 100% 커버리지")
        if has_climb:
            constraints.append("자율 등반 규율: 불변 평가 파일 변조 차단(Immutable Guard) 및 통계적 유의성 미달 시 즉시 폐기")

        edge_cases.append("빈 입력값(Empty/Whitespace)·경계값(0, 음수, 상한선 초과) 및 비정상 입력 방어")
        edge_cases.append("중복 호출(연타)·이미 처리된 상태·존재하지 않는 대상 요청 시 상태 일관성 보장")
        if has_ui:
            edge_cases.append("로딩/비활성화 상태 중 버튼 중복 클릭 방지 및 반응형 뷰포트 깨짐 점검")
        if has_sec:
            edge_cases.append("만료·위변조 토큰, 권한 없는 사용자의 우회 접근 시 안전한 한글 오류 반환")
        if has_blast:
            edge_cases.append("시그니처 변경 시 1-Hop/2-Hop 상위 호출 모듈의 하위 호환성 유지")

        criteria.append("핵심 정상 동작 + 예외/엣지케이스를 검증하는 실제 TDD 단위 테스트 작성 및 통과")
        criteria.append("Trinity 정적 코드 감사(audit-code: 가짜 테스트·any·반환타입·슬롭·UI 규칙) 위반 0건")
        if eff_decision.required_gates:
            criteria.append(f"필수 품질 게이트({', '.join(eff_decision.required_gates)}) 전원 PASS 판정")

    next_actions_payload = recommend_next_actions(root=root, goal=normalized, decision=eff_decision)
    proj_state = next_actions_payload.get("project_state", {})
    if isinstance(proj_state, dict):
        for r_obj in (proj_state.get("learned_rules", []) if isinstance(proj_state.get("learned_rules"), list) else []):
            if isinstance(r_obj, dict) and r_obj.get("rule_ko"):
                constraints.append(f"프로젝트 학습 규칙({r_obj.get('rule_id', 'custom')}): {r_obj['rule_ko']}")

    ambiguity_level, clarifying_questions = _build_socratic_interview_questions_ko(
        subject,
        eff_decision.goal_kind,
        eff_decision.execution_mode,
        has_ui=has_ui,
        has_sec=has_sec,
        has_cleanroom=has_cleanroom,
        has_climb=has_climb,
    )

    raw_next_list = next_actions_payload.get("next_actions", [])
    next_actions_tuple: tuple[dict[str, str], ...] = tuple(
        item for item in (raw_next_list if isinstance(raw_next_list, list) else []) if isinstance(item, dict)
    )

    squad_str = _format_squad_pipeline_ko(eff_decision.roles)
    auto_care_tags: list[str] = ["SOLID/타입 안전성", "예외/경계값 방어", "실제 테스트 검증"]
    if has_ui and ui_rule_enforced:
        auto_care_tags.insert(1, "UI 규격(투명 버튼/lucide 아이콘/연타 방지)")
    elif has_ui:
        auto_care_tags.insert(1, "UI 규격(프로젝트 디자인 정본/연타 방지)")
    if has_sec:
        auto_care_tags.insert(1, "보안/권한 차단")
    if has_cleanroom:
        auto_care_tags.insert(0, "클린룸 무오염 격리")
    if has_climb:
        auto_care_tags.insert(0, "불변 벤치마크 기반 성능 개선")

    echo_lines = [
        "[Dreampia 국문 프롬프트 고도화 & 작전 브리핑]",
        f"- 한 번 더 생각한 고도화 프롬프트: {expanded}",
        f"- 자동 챙김 항목: {', '.join(auto_care_tags)}",
        f"- 담당 스쿼드: {squad_str}",
    ]
    if eff_decision.execution_mode == "prompt-sharpen" or ambiguity_level == "high":
        questions_md = "\n".join(f"  {idx}. {q}" for idx, q in enumerate(clarifying_questions, start=1))
        echo_lines.append("- Oracle(오라클) 사전 인터뷰 핵심 질문:")
        echo_lines.append(questions_md)

    if next_actions_tuple:
        echo_lines.append("- 다음 추천 작업 (Next Actions):")
        for idx, act in enumerate(next_actions_tuple, start=1):
            echo_lines.append(
                f"  {idx}. {act.get('title_ko', '')} -> 입력 예시: \"{act.get('prompt_example_ko', '')}\""
            )

    echo_md = "\n".join(echo_lines) if is_briefing_enabled(root) else ""

    return PromptExpansionBrief(
        raw_goal=normalized,
        core_subject=subject,
        goal_kind=eff_decision.goal_kind,
        profile=eff_decision.profile,
        execution_mode=eff_decision.execution_mode,
        expanded_prompt_ko=expanded,
        injected_constraints_ko=tuple(constraints),
        edge_cases_to_check_ko=tuple(edge_cases),
        completion_criteria_ko=tuple(criteria),
        squad_pipeline_ko=squad_str,
        echo_markdown_ko=echo_md,
        ambiguity_level=ambiguity_level,
        clarifying_questions_ko=clarifying_questions,
        recommended_next_actions_ko=next_actions_tuple,
    )



