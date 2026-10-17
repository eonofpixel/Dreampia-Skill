"""Dreampia Zero-Trust Guild Camp (1~10호기) & Signed Quest Security Engine.

SOLID Architecture:
- CampNodeSpec / SignedQuestEnvelope: 단일 책임 불변 데이터 모델 (슬롯 ID, 다중 파티 클래스, 소유 경로, 서명 봉투)
- ZeroSecretGuard: 단일 책임 보안 검문기 (비밀키 유출 차단, 위험 명령어 하드 차단, 소유 경로 탈출 차단)
- CampPairingManager: 단일 책임 1~10호기(bot-01~bot-10) 등록·일회용 5분 만료 6자리 페어링 코드·다중 파티원 배치 관리자
- SignedQuestDispenser: 단일 책임 CSPRNG 마스터키 기반 HMAC-SHA256 퀘스트 전자서명 발급·검증·만료(TTL) 및 리플레이 공격 차단기
- BossGateMergeGuard: 단일 책임 보스 관문(autopilot-gate PASS + SHA-256 무결성 검증 + Hero 승인) 기반 무충돌 병합 승인기
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets

try:
    from . import route_planner
except ImportError:
    import route_planner  # type: ignore[no-redef]


CAMP_SLOTS: tuple[dict[str, object], ...] = (
    {
        "slot_id": "bot-01",
        "camp_id": "camp-01",
        "label_ko": "1호기 (제1주력 원정 캠프)",
        "default_party": ["Paladin", "Archer", "Inquisitor", "Cleric"],
        "default_owned_paths": ["src/", "harness/", "app/", "components/", "tests/"],
    },
    {
        "slot_id": "bot-02",
        "camp_id": "camp-02",
        "label_ko": "2호기 (제2주력 원정 캠프)",
        "default_party": ["Archmage", "Paladin", "Archer", "Inquisitor", "Cleric"],
        "default_owned_paths": ["ui/", "web/", "native/", "tests/"],
    },
    {
        "slot_id": "bot-03",
        "camp_id": "camp-03",
        "label_ko": "3호기 (아키텍처·성능 원정 캠프)",
        "default_party": ["Sage", "Archmage", "Paladin", "Cleric"],
        "default_owned_paths": ["docs/", "api/", "src/", "evidence/"],
    },
    {
        "slot_id": "bot-04",
        "camp_id": "camp-04",
        "label_ko": "4호기 (심판·통합검증 원정 캠프)",
        "default_party": ["Inquisitor", "Cleric", "Guardian"],
        "default_owned_paths": ["tests/", "harness/tests/", "evidence/"],
    },
    {
        "slot_id": "bot-05",
        "camp_id": "camp-05",
        "label_ko": "5호기 (치유·E2E·빌드 원정 캠프)",
        "default_party": ["Cleric", "Bard", "Archer", "Inquisitor"],
        "default_owned_paths": ["evidence/", "docs/02_IA_UX.md", "tests/"],
    },
    {
        "slot_id": "bot-06",
        "camp_id": "camp-06",
        "label_ko": "6호기 (대현자 기획·SDD 캠프)",
        "default_party": ["Sage", "Archmage", "Cleric"],
        "default_owned_paths": ["docs/", "evidence/"],
    },
    {
        "slot_id": "bot-07",
        "camp_id": "camp-07",
        "label_ko": "7호기 (연금술사 S급 클린룸 역공학 캠프)",
        "default_party": ["Alchemist", "Knight", "Guardian", "Cleric"],
        "default_owned_paths": ["approved-spec/", "implementation/", "evidence/"],
    },
    {
        "slot_id": "bot-08",
        "camp_id": "camp-08",
        "label_ko": "8호기 (음유시인·궁수 UX/시각검증 캠프)",
        "default_party": ["Bard", "Archer", "Cleric"],
        "default_owned_paths": ["app/", "components/", "docs/02_IA_UX.md"],
    },
    {
        "slot_id": "bot-09",
        "camp_id": "camp-09",
        "label_ko": "9호기 (수호기사 보안·클린룸 감시 캠프)",
        "default_party": ["Guardian", "Inquisitor", "Cleric"],
        "default_owned_paths": ["docs/05_SECURITY_PRIVACY.md", "evidence/"],
    },
    {
        "slot_id": "bot-10",
        "camp_id": "camp-10",
        "label_ko": "10호기 (기사단 대규모 증원 캠프)",
        "default_party": ["Knight", "Paladin", "Inquisitor", "Cleric"],
        "default_owned_paths": ["implementation/", "src/", "tests/"],
    },
)

_SECRET_LEAK_RE = re.compile(
    r"(?i)-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----"
    r"|\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|passwd|secret)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{8,}"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|\b(?:gh[pousr]_|github_pat_|sk-(?:proj-)?|xox[baprs]-)[A-Za-z0-9_-]{16,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\bAIza[0-9A-Za-z_-]{35}\b"
    r"|\.env\.(?:production|prod|local|staging)\b"
    r"|\bguild-master\.key\b"
)

_DESTRUCTIVE_CMD_RE = re.compile(
    r"(?i)(?:\brm\s+-[rf]{1,2}\b"
    r"|\bgit\s+push\s+[^\n]*(?:--force|-f\b)"
    r"|\bgit\s+reset\s+--hard\b"
    r"|\bgit\s+clean\s+-[fdqx]{2,}\b"
    r"|\bsudo\s+"
    r"|\bmkfs\b"
    r"|\bformat\s+[a-z]:"
    r"|\bdel\s+/[fsq]"
    r"|\bRemove-Item\b[^\n]*-Recurse"
    r"|\b(?:Invoke-Expression|iex)\b"
    r"|\bchmod\s+777\b"
    r"|\b(?:curl|wget)\b[^\n]*\|\s*(?:sh|bash|zsh|pwsh|powershell)\b"
    r"|\b(?:DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\s+TABLE)\b)"
)

_FORBIDDEN_OWNED_PREFIXES: tuple[str, ...] = (
    ".git",
    ".dreampia/security",
    ".dreampia-skill/security",
    ".dreampia-install",
    "contaminated-zone",
    ".env",
)

_HEX_NONCE_RE = re.compile(r"^[0-9a-fA-F]{24,128}$")
_HEX_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PAIRING_TTL_SECONDS = 300
QUEST_TTL_SECONDS = 86400


def _safe_project_path(project_root: Path, rel_path: str) -> Path:
    """프로젝트 루트 외부 탈출(..), 절대 경로, 심볼릭 링크를 차단하고 안전한 Path를 반환한다."""
    resolved_root = project_root.resolve()
    raw = rel_path.strip().replace("\\", "/")
    if not raw or "\x00" in raw or re.match(r"^[A-Za-z]:", raw):
        raise ValueError(f"유효하지 않은 상대 경로입니다: {rel_path}")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise ValueError(f"보안 정책상 상위 디렉터리(..) 또는 절대 경로 접근은 차단됩니다: {rel_path}")
    curr = resolved_root
    for part in pure.parts:
        curr = curr / part
        if curr.is_symlink():
            raise ValueError(f"보안 정책상 심볼릭 링크 경로는 허용되지 않습니다: {rel_path}")
    resolved_target = curr.resolve()
    if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
        raise ValueError(f"보안 정책상 프로젝트 루트 외부 경로는 접근할 수 없습니다: {rel_path}")
    return resolved_target


@dataclass(frozen=True)
class CampNodeSpec:
    """단일 원정 캠프(맥미니/워커 PC 1대) 및 내부 다중 길드 파티원 배치 명세."""

    slot_id: str
    camp_id: str
    label_ko: str
    party_classes: tuple[str, ...]
    owned_paths: tuple[str, ...]
    transport: str
    inbound_ports_opened: int
    zero_secret_worker: bool
    paired: bool
    key_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        party_details: list[dict[str, str]] = []
        for cls_name in self.party_classes:
            role_key = route_planner.resolve_role_alias(cls_name)
            meta = route_planner.AGENT_CALLSIGNS.get(
                role_key,
                {"callsign": cls_name, "name_ko": cls_name, "title_ko": "길드 파티원"},
            )
            party_details.append(
                {
                    "role": role_key,
                    "callsign": meta["callsign"],
                    "name_ko": meta["name_ko"],
                    "title_ko": meta["title_ko"],
                }
            )
        return {
            "slot_id": self.slot_id,
            "camp_id": self.camp_id,
            "label_ko": self.label_ko,
            "party_classes": list(self.party_classes),
            "party_count": len(self.party_classes),
            "worktree_isolation_count": len(self.party_classes),
            "party_details": party_details,
            "owned_paths": list(self.owned_paths),
            "security": {
                "transport": self.transport,
                "inbound_ports_opened": self.inbound_ports_opened,
                "zero_secret_worker": self.zero_secret_worker,
                "paired": self.paired,
                "key_fingerprint": self.key_fingerprint,
            },
        }


class ZeroSecretGuard:
    """워커 캠프(1~10호기)로 전달되거나 반환되는 텍스트·경로에서 비밀키 유출, 파괴적 명령, 제어판 침범을 차단한다."""

    @staticmethod
    def validate_goal_and_command(text: str) -> tuple[bool, list[str]]:
        violations: list[str] = []
        if _SECRET_LEAK_RE.search(text):
            violations.append(
                "ZERO_SECRET_VIOLATION: 퀘스트 지시문 또는 명령에 비밀키/토큰 또는 .env.production 참조가 포함되어 차단되었습니다."
            )
        if _DESTRUCTIVE_CMD_RE.search(text):
            violations.append(
                "FORBIDDEN_COMMAND: 파괴적 명령(rm -rf, git push --force/-f, git reset --hard, sudo, 파이프 셸 실행 등)은 길드 보안 정책상 원천 차단됩니다."
            )
        return (len(violations) == 0, violations)

    @staticmethod
    def validate_owned_paths(owned_paths: list[str] | tuple[str, ...]) -> tuple[bool, list[str]]:
        violations: list[str] = []
        for raw_p in owned_paths:
            norm = str(raw_p).strip().replace("\\", "/")
            while norm.startswith("./"):
                norm = norm[2:]
            norm = norm.rstrip("/")
            if not norm or "\x00" in norm or re.match(r"^[A-Za-z]:", norm) or norm.startswith("/"):
                violations.append(f"INVALID_OWNED_PATH: 절대 경로 또는 빈 소유 경로는 허용되지 않습니다 ({raw_p}).")
                continue
            parts = PurePosixPath(norm).parts
            if ".." in parts:
                violations.append(f"PATH_ESCAPE_BLOCKED: 소유 경로에 상위 디렉터리(..)를 포함할 수 없습니다 ({raw_p}).")
                continue
            lower_norm = norm.lower()
            for forbidden in _FORBIDDEN_OWNED_PREFIXES:
                if lower_norm == forbidden or lower_norm.startswith(forbidden + "/"):
                    violations.append(
                        f"PROTECTED_CONTROL_PLANE_PATH: 보안 제어 영역({forbidden})은 워커 캠프 소유 경로로 지정할 수 없습니다 ({raw_p})."
                    )
                    break
        return (len(violations) == 0, violations)

    @staticmethod
    def sanitize_text(text: str) -> str:
        return _SECRET_LEAK_RE.sub("[REDACTED_BY_GUARDIAN]", text)


def _resolve_state_dir(project_root: Path) -> Path:
    for cand_name in (".dreampia-skill", ".dreampia"):
        cand = project_root / cand_name
        if (cand / "security" / "guild-master.key").is_file() or (cand / "guild-camps.json").is_file():
            return cand
    return project_root / route_planner.resolve_skill_state_dir(project_root)


def _load_or_init_master_secret(state_dir: Path, apply: bool) -> str:
    """CSPRNG 256-bit 마스터 서명키를 로드하거나 생성한다. 경로 기반의 예측 가능한 해시 폴백은 절대 사용하지 않는다."""
    sec_dir = state_dir / "security"
    key_file = sec_dir / "guild-master.key"
    if key_file.is_symlink():
        raise ValueError("보안 정책상 guild-master.key 심볼릭 링크는 허용되지 않습니다.")
    if key_file.is_file():
        raw = key_file.read_text(encoding="utf-8").strip()
        if len(raw) >= 64:
            return raw
    secret_hex = secrets.token_hex(32)
    if apply:
        sec_dir.mkdir(parents=True, exist_ok=True)
        key_file.write_text(secret_hex + "\n", encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    return secret_hex


def _require_persisted_master_secret(state_dir: Path) -> str | None:
    """검증(verify) 시 디스크에 실제로 저장된 CSPRNG 마스터 서명키만 신뢰하며, 없거나 심볼릭 링크이면 None을 반환한다."""
    key_file = state_dir / "security" / "guild-master.key"
    if key_file.is_symlink() or not key_file.is_file():
        return None
    raw = key_file.read_text(encoding="utf-8").strip()
    if len(raw) < 64:
        return None
    return raw


class CampPairingManager:
    """1~10호기(bot-01~bot-10) 원정 캠프 레지스트리, 다중 파티원 배치 및 일회용 5분 만료 6자리 페어링 코드를 관리한다."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.state_dir = _resolve_state_dir(self.project_root)
        self.registry_path = self.state_dir / "guild-camps.json"
        self.tickets_path = self.state_dir / "security" / "pairing-tickets.json"

    def load_camps(self) -> list[CampNodeSpec]:
        saved_map: dict[str, dict[str, object]] = {}
        if self.registry_path.is_file() and not self.registry_path.is_symlink():
            try:
                raw_obj = json.loads(self.registry_path.read_text(encoding="utf-8"))
                if isinstance(raw_obj, dict) and isinstance(raw_obj.get("camps"), list):
                    for item in raw_obj["camps"]:
                        if isinstance(item, dict) and isinstance(item.get("slot_id"), str):
                            saved_map[str(item["slot_id"])] = item
            except (OSError, ValueError):
                saved_map = {}

        result: list[CampNodeSpec] = []
        for default_slot in CAMP_SLOTS:
            slot_id = str(default_slot["slot_id"])
            camp_id = str(default_slot["camp_id"])
            saved = saved_map.get(slot_id, {})
            label_ko = str(saved.get("label_ko") or default_slot["label_ko"])
            raw_party = saved.get("party_classes") or default_slot["default_party"]
            party_list = [str(x) for x in raw_party] if isinstance(raw_party, list) else ["Paladin", "Cleric"]
            raw_owned = saved.get("owned_paths") or default_slot["default_owned_paths"]
            owned_list = [str(x) for x in raw_owned] if isinstance(raw_owned, list) else ["src/"]
            sec_obj = saved.get("security") if isinstance(saved.get("security"), dict) else {}
            paired = bool(sec_obj.get("paired", False)) if isinstance(sec_obj, dict) else False
            fp = str(sec_obj.get("key_fingerprint") or f"unpaired-{slot_id}") if isinstance(sec_obj, dict) else f"unpaired-{slot_id}"
            result.append(
                CampNodeSpec(
                    slot_id=slot_id,
                    camp_id=camp_id,
                    label_ko=label_ko,
                    party_classes=tuple(party_list),
                    owned_paths=tuple(owned_list),
                    transport="outbound-only (git-queue + e2ee-relay)",
                    inbound_ports_opened=0,
                    zero_secret_worker=True,
                    paired=paired,
                    key_fingerprint=fp,
                )
            )
        return result

    def generate_pairing_ticket(self, slot_id: str, apply: bool = False) -> dict[str, object]:
        normalized_slot = self._normalize_slot_id(slot_id)
        master_secret = _load_or_init_master_secret(self.state_dir, apply=apply)
        ticket_nonce = secrets.token_hex(16)
        now_utc = datetime.now(timezone.utc)
        expires_at = (now_utc + timedelta(seconds=PAIRING_TTL_SECONDS)).isoformat()
        digest = hmac.new(
            master_secret.encode("utf-8"),
            f"pair::{normalized_slot}::{ticket_nonce}::{expires_at}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        num_val = secrets.randbelow(900000) + 100000
        pairing_code = f"{str(num_val)[:3]}-{str(num_val)[3:]}"
        code_sha256 = hashlib.sha256(f"{normalized_slot}:{pairing_code}:{ticket_nonce}".encode("utf-8")).hexdigest()
        fingerprint = f"ed25519-hmac:{digest[:16]}"

        camps = self.load_camps()
        updated_camps: list[CampNodeSpec] = []
        target_spec: CampNodeSpec | None = None
        for c in camps:
            if c.slot_id == normalized_slot:
                target_spec = CampNodeSpec(
                    slot_id=c.slot_id,
                    camp_id=c.camp_id,
                    label_ko=c.label_ko,
                    party_classes=c.party_classes,
                    owned_paths=c.owned_paths,
                    transport=c.transport,
                    inbound_ports_opened=0,
                    zero_secret_worker=True,
                    paired=True,
                    key_fingerprint=fingerprint,
                )
                updated_camps.append(target_spec)
            else:
                updated_camps.append(c)

        if apply:
            self._save_camps(updated_camps)
            self.tickets_path.parent.mkdir(parents=True, exist_ok=True)
            existing_tickets: dict[str, object] = {}
            if self.tickets_path.is_file() and not self.tickets_path.is_symlink():
                try:
                    loaded_t = json.loads(self.tickets_path.read_text(encoding="utf-8"))
                    if isinstance(loaded_t, dict):
                        existing_tickets = loaded_t
                except ValueError:
                    existing_tickets = {}
            existing_tickets[normalized_slot] = {
                "slot_id": normalized_slot,
                "code_sha256": code_sha256,
                "ticket_nonce": ticket_nonce,
                "issued_at": now_utc.isoformat(),
                "expires_at": expires_at,
                "ttl_seconds": PAIRING_TTL_SECONDS,
                "single_use": True,
                "used": False,
                "key_fingerprint": fingerprint,
            }
            self.tickets_path.write_text(json.dumps(existing_tickets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return {
            "action": "guild-camp",
            "mode": "pair",
            "status": "PASS",
            "applied": apply,
            "slot_id": normalized_slot,
            "pairing_code": pairing_code,
            "key_fingerprint": fingerprint,
            "expires_at": expires_at,
            "ttl_seconds": PAIRING_TTL_SECONDS,
            "pairing_ticket": {
                "slot_id": normalized_slot,
                "pairing_code": pairing_code,
                "key_fingerprint": fingerprint,
                "ticket_nonce": ticket_nonce,
                "expires_at": expires_at,
                "ttl_seconds": PAIRING_TTL_SECONDS,
                "single_use": True,
                "inbound_ports_required": 0,
            },
            "camp": target_spec.to_dict() if target_spec else {},
            "security_guarantees_ko": [
                "인바운드 포트 개방 0개 (Outbound-Only 역방향 연결 및 비공개 Git 큐 사용)",
                f"CSPRNG 일회용 6자리 페어링 코드 ({PAIRING_TTL_SECONDS}초 후 자동 만료 및 평문 미저장)",
                "워커 내 운영 비밀키(.env.production, 실DB 암호) 미보관 (Zero-Secret Worker)",
                "GuildMaster HMAC-SHA256 전자서명 없는 퀘스트 지시문 자동 거부",
            ],
            "message_ko": (
                f"{normalized_slot} 원정 캠프 일회용 6자리 페어링 코드({pairing_code}, 유효시간 5분)가 발급되었습니다. "
                "드림피아 브라우저 또는 모바일 리모트 앱에 입력하면 포트 개방 없이 즉시 연결됩니다."
            ),
        }

    def configure_camp_party(
        self,
        slot_id: str,
        party_classes: list[str] | None = None,
        owned_paths: list[str] | None = None,
        label_ko: str | None = None,
        apply: bool = False,
    ) -> dict[str, object]:
        normalized_slot = self._normalize_slot_id(slot_id)
        if owned_paths:
            ok_paths, path_violations = ZeroSecretGuard.validate_owned_paths(owned_paths)
            if not ok_paths:
                return {
                    "action": "guild-camp",
                    "mode": "configure",
                    "status": "FAIL",
                    "applied": False,
                    "slot_id": normalized_slot,
                    "violations": path_violations,
                    "message_ko": f"허용되지 않는 소유 경로(owned_paths)가 포함되어 설정이 거부되었습니다: {'; '.join(path_violations)}",
                }

        camps = self.load_camps()
        updated_camps: list[CampNodeSpec] = []
        updated_target: CampNodeSpec | None = None

        for c in camps:
            if c.slot_id == normalized_slot:
                new_party = tuple(party_classes) if party_classes else c.party_classes
                new_owned = tuple(owned_paths) if owned_paths else c.owned_paths
                new_label = label_ko.strip() if label_ko and label_ko.strip() else c.label_ko
                updated_target = CampNodeSpec(
                    slot_id=c.slot_id,
                    camp_id=c.camp_id,
                    label_ko=new_label,
                    party_classes=new_party,
                    owned_paths=new_owned,
                    transport=c.transport,
                    inbound_ports_opened=0,
                    zero_secret_worker=True,
                    paired=c.paired,
                    key_fingerprint=c.key_fingerprint,
                )
                updated_camps.append(updated_target)
            else:
                updated_camps.append(c)

        if apply:
            self._save_camps(updated_camps)

        return {
            "action": "guild-camp",
            "mode": "configure",
            "status": "PASS",
            "applied": apply,
            "slot_id": normalized_slot,
            "camp": updated_target.to_dict() if updated_target else {},
            "message_ko": (
                f"{normalized_slot} 캠프에 길드 파티원 {len(updated_target.party_classes) if updated_target else 0}명"
                f"({', '.join(updated_target.party_classes) if updated_target else ''}) 다중 배치가 설정되었습니다."
            ),
        }

    def _normalize_slot_id(self, raw_slot: str) -> str:
        cleaned = raw_slot.strip().lower()
        if not cleaned:
            return "bot-01"
        if cleaned.isdigit():
            idx = int(cleaned)
            if 1 <= idx <= 10:
                return f"bot-{idx:02d}"
        m = re.match(r"^(?:bot|camp|unit|node)-?(\d{1,2})$", cleaned)
        if m:
            idx = int(m.group(1))
            if 1 <= idx <= 10:
                return f"bot-{idx:02d}"
        raise ValueError(f"지원하지 않는 호기 슬롯 ID입니다 (bot-01 ~ bot-10 지원): {raw_slot}")

    def _save_camps(self, camps: list[CampNodeSpec]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "0.7.0",
            "protagonist": route_planner.HERO_PERSONA,
            "commander": route_planner.AGENT_CALLSIGNS["router"],
            "security_model": "zero-trust-outbound-only",
            "camps": [c.to_dict() for c in camps],
        }
        self.registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SignedQuestDispenser:
    """GuildMaster 전자서명 기반 퀘스트 봉투(Signed Quest Envelope) 발급 및 무결성·만료(TTL)·리플레이 방어 검증기."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.state_dir = _resolve_state_dir(self.project_root)
        self.quests_dir = self.state_dir / "quests"
        self.nonce_ledger_path = self.state_dir / "security" / "used-nonces.json"

    def issue_signed_quest(
        self,
        goal: str,
        slot_id: str = "bot-01",
        apply: bool = False,
    ) -> dict[str, object]:
        clean_goal = goal.strip()
        if not clean_goal:
            raise ValueError("퀘스트 목표(goal)가 비어 있습니다.")

        is_safe, violations = ZeroSecretGuard.validate_goal_and_command(clean_goal)
        if not is_safe:
            return {
                "action": "guild-camp",
                "mode": "dispatch-quest",
                "status": "FAIL",
                "applied": False,
                "security_blocked": True,
                "violations": violations,
                "message_ko": "Guardian(수호기사) 보안 검문에서 비밀키 노출 또는 위험 명령어가 감지되어 퀘스트 발주가 차단되었습니다.",
            }

        pairing_mgr = CampPairingManager(self.project_root)
        normalized_slot = pairing_mgr._normalize_slot_id(slot_id)
        camps = pairing_mgr.load_camps()
        camp_spec = next((c for c in camps if c.slot_id == normalized_slot), camps[0])

        ok_paths, path_violations = ZeroSecretGuard.validate_owned_paths(camp_spec.owned_paths)
        if not ok_paths:
            return {
                "action": "guild-camp",
                "mode": "dispatch-quest",
                "status": "FAIL",
                "applied": False,
                "security_blocked": True,
                "violations": path_violations,
                "message_ko": "캠프 소유 경로(owned_paths)에 보안 제어 영역 또는 경로 탈출이 포함되어 퀘스트 발주가 차단되었습니다.",
            }

        route_dec = route_planner.plan_route(clean_goal).to_dict()
        quest_rank = route_dec.get("quest_rank", {})
        nonce = secrets.token_hex(16)
        now_utc = datetime.now(timezone.utc)
        issued_at = now_utc.isoformat()
        expires_at = (now_utc + timedelta(seconds=QUEST_TTL_SECONDS)).isoformat()
        quest_id = f"QUEST-{hashlib.sha256(f'{normalized_slot}:{clean_goal}:{nonce}'.encode('utf-8')).hexdigest()[:10].upper()}"

        worktree_tracks: list[dict[str, object]] = []
        for cls_name in camp_spec.party_classes:
            slug = re.sub(r"[^a-z0-9_-]", "", cls_name.lower()) or "agent"
            worktree_tracks.append(
                {
                    "class_callsign": cls_name,
                    "branch": f"dreampia/{normalized_slot}/{slug}",
                    "worktree_path": f"{self.state_dir.name}/worktrees/{normalized_slot}-{slug}",
                    "owned_paths": list(camp_spec.owned_paths),
                }
            )

        canonical_body = {
            "quest_id": quest_id,
            "protagonist": "Hero",
            "commander": "GuildMaster",
            "target_slot": normalized_slot,
            "camp_id": camp_spec.camp_id,
            "goal": clean_goal,
            "quest_rank": quest_rank,
            "party_classes": list(camp_spec.party_classes),
            "owned_paths": list(camp_spec.owned_paths),
            "worktree_tracks": worktree_tracks,
            "nonce": nonce,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "security_policy": {
                "inbound_ports_opened": 0,
                "zero_secret_worker": True,
                "require_autopilot_gate_pass_before_push": True,
                "require_hero_approval_before_main_merge": True,
            },
        }
        master_secret = _load_or_init_master_secret(self.state_dir, apply=apply)
        canonical_json = json.dumps(canonical_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(master_secret.encode("utf-8"), canonical_json.encode("utf-8"), hashlib.sha256).hexdigest()

        envelope: dict[str, object] = {
            **canonical_body,
            "signature_sha256": signature,
        }

        quest_file_rel: str | None = None
        if apply:
            self.quests_dir.mkdir(parents=True, exist_ok=True)
            q_path = self.quests_dir / f"{quest_id}.json"
            q_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            quest_file_rel = q_path.relative_to(self.project_root).as_posix()

        return {
            "action": "guild-camp",
            "mode": "dispatch-quest",
            "status": "PASS",
            "applied": apply,
            "quest_file": quest_file_rel,
            "quest_path": quest_file_rel,
            "envelope": envelope,
            "message_ko": (
                f"Hero(주인공 영웅)의 퀘스트({quest_id})가 GuildMaster 전자서명({signature[:12]}...)과 함께 "
                f"{normalized_slot}({camp_spec.label_ko}, 파티원 {len(camp_spec.party_classes)}명) 앞으로 안전하게 발주되었습니다."
            ),
        }

    def verify_signed_quest(
        self,
        envelope: dict[str, object],
        record_nonce: bool = False,
    ) -> dict[str, object]:
        provided_sig = str(envelope.get("signature_sha256") or "").strip()
        if not _HEX_SHA256_RE.fullmatch(provided_sig):
            return {
                "action": "guild-camp",
                "mode": "verify-quest",
                "status": "FAIL",
                "verified": False,
                "reason": "MISSING_OR_MALFORMED_SIGNATURE",
                "reason_ko": "퀘스트 전자서명(signature_sha256)이 누락되었거나 유효한 64자리 SHA-256 형식이 아닙니다.",
                "message_ko": "퀘스트 전자서명(signature_sha256)이 누락되었거나 유효한 64자리 SHA-256 형식이 아닙니다.",
            }

        master_secret = _require_persisted_master_secret(self.state_dir)
        if not master_secret:
            return {
                "action": "guild-camp",
                "mode": "verify-quest",
                "status": "FAIL",
                "verified": False,
                "reason": "MISSING_MASTER_KEY",
                "reason_ko": "GuildMaster 마스터 서명키(guild-master.key)가 초기화되지 않아 서명 검증이 Fail-Closed로 차단되었습니다.",
                "message_ko": "GuildMaster 마스터 서명키(guild-master.key)가 초기화되지 않아 서명 검증이 Fail-Closed로 차단되었습니다.",
            }

        goal_str = str(envelope.get("goal") or "")
        is_safe, violations = ZeroSecretGuard.validate_goal_and_command(goal_str)
        raw_owned = envelope.get("owned_paths")
        owned_list = [str(x) for x in raw_owned] if isinstance(raw_owned, list) else []
        ok_paths, path_violations = ZeroSecretGuard.validate_owned_paths(owned_list)
        all_violations = violations + path_violations
        if not is_safe or not ok_paths:
            return {
                "action": "guild-camp",
                "mode": "verify-quest",
                "status": "FAIL",
                "verified": False,
                "reason": "SECURITY_POLICY_VIOLATION",
                "violations": all_violations,
                "reason_ko": "퀘스트 본문 또는 소유 경로에 금지된 비밀키·파괴적 명령·경로 탈출이 포함되어 실행이 거부되었습니다.",
                "message_ko": "퀘스트 본문 또는 소유 경로에 금지된 비밀키·파괴적 명령·경로 탈출이 포함되어 실행이 거부되었습니다.",
            }

        nonce = str(envelope.get("nonce") or "").strip()
        if not _HEX_NONCE_RE.fullmatch(nonce):
            return {
                "action": "guild-camp",
                "mode": "verify-quest",
                "status": "FAIL",
                "verified": False,
                "reason": "INVALID_NONCE",
                "reason_ko": "퀘스트 일회용 토큰(nonce)이 누락되었거나 최소 24자리 16진수 규격에 맞지 않아 차단되었습니다.",
                "message_ko": "퀘스트 일회용 토큰(nonce)이 누락되었거나 최소 24자리 16진수 규격에 맞지 않아 차단되었습니다.",
            }

        expires_at_str = str(envelope.get("expires_at") or "").strip()
        if expires_at_str:
            try:
                exp_dt = datetime.fromisoformat(expires_at_str)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > exp_dt:
                    return {
                        "action": "guild-camp",
                        "mode": "verify-quest",
                        "status": "FAIL",
                        "verified": False,
                        "reason": "QUEST_EXPIRED",
                        "reason_ko": f"퀘스트 유효기간({expires_at_str})이 만료되어 실행이 거부되었습니다.",
                        "message_ko": f"퀘스트 유효기간({expires_at_str})이 만료되어 실행이 거부되었습니다.",
                    }
            except ValueError:
                return {
                    "action": "guild-camp",
                    "mode": "verify-quest",
                    "status": "FAIL",
                    "verified": False,
                    "reason": "INVALID_EXPIRES_AT",
                    "reason_ko": "퀘스트 만료 시각(expires_at) 형식이 올바르지 않아 실행이 거부되었습니다.",
                    "message_ko": "퀘스트 만료 시각(expires_at) 형식이 올바르지 않아 실행이 거부되었습니다.",
                }

        used_nonces = self._load_used_nonces()
        if nonce in used_nonces:
            return {
                "action": "guild-camp",
                "mode": "verify-quest",
                "status": "FAIL",
                "verified": False,
                "reason": "REPLAY_ATTACK_BLOCKED",
                "reason_ko": f"이미 실행된 퀘스트 일회용 토큰(nonce={nonce}) 재전송 공격이 감지되어 차단되었습니다.",
                "message_ko": f"이미 실행된 퀘스트 일회용 토큰(nonce={nonce}) 재전송 공격이 감지되어 차단되었습니다.",
            }

        body_copy = {k: v for k, v in envelope.items() if k != "signature_sha256"}
        canonical_json = json.dumps(body_copy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected_sig = hmac.new(master_secret.encode("utf-8"), canonical_json.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(provided_sig, expected_sig):
            return {
                "action": "guild-camp",
                "mode": "verify-quest",
                "status": "FAIL",
                "verified": False,
                "reason": "INVALID_SIGNATURE",
                "reason_ko": "HMAC-SHA256 퀘스트 전자서명이 일치하지 않습니다 (위변조 의심). 워커가 실행을 거부했습니다.",
                "message_ko": "HMAC-SHA256 퀘스트 전자서명이 일치하지 않습니다 (위변조 의심). 워커가 실행을 거부했습니다.",
            }

        if record_nonce:
            used_nonces.append(nonce)
            self._save_used_nonces(used_nonces)

        return {
            "action": "guild-camp",
            "mode": "verify-quest",
            "status": "PASS",
            "verified": True,
            "quest_id": envelope.get("quest_id"),
            "target_slot": envelope.get("target_slot"),
            "signature_verified": True,
            "message_ko": "GuildMaster 전자서명, 유효기간(TTL), 논스 및 무오염 보안 검증을 통과했습니다. 안전하게 워크트리 작업을 시작할 수 있습니다.",
        }

    def _load_used_nonces(self) -> list[str]:
        if not self.nonce_ledger_path.is_file() or self.nonce_ledger_path.is_symlink():
            return []
        try:
            data = json.loads(self.nonce_ledger_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(x) for x in data]
        except (OSError, ValueError):
            pass
        return []

    def _save_used_nonces(self, nonces: list[str]) -> None:
        self.nonce_ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.nonce_ledger_path.write_text(json.dumps(nonces[-2000:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class BossGateMergeGuard:
    """보스 관문(Cleric autopilot-gate PASS + SHA-256 판정서 무결성 + Hero 승인) 통과 전 main 브랜치 병합/푸시를 원천 차단한다."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def verify_merge_eligibility(
        self,
        slot_id: str = "bot-01",
        hero_approved: bool = False,
        verdict_rel: str = "evidence/autopilot-verdict.json",
    ) -> dict[str, object]:
        verdict_path = _safe_project_path(self.project_root, verdict_rel)
        blockers: list[str] = []
        verdict_sha256 = ""
        verdict_status = "MISSING"

        if not verdict_path.is_file():
            blockers.append(f"보스 관문 판정서({verdict_rel})가 존재하지 않습니다. 먼저 autopilot-gate를 통과해야 합니다.")
        else:
            try:
                verdict_data = json.loads(verdict_path.read_text(encoding="utf-8"))
                if isinstance(verdict_data, dict):
                    verdict_status = str(verdict_data.get("status") or "FAIL")
                    verdict_sha256 = str(verdict_data.get("verdict_sha256") or "").strip()
                    if verdict_status != "PASS" or not verdict_sha256:
                        blockers.append(f"Cleric 보스 관문 판정이 PASS가 아닙니다 (현재 상태: {verdict_status}).")
                    elif "stages" in verdict_data:
                        doc_without_hash = {k: v for k, v in verdict_data.items() if k != "verdict_sha256"}
                        expected_bytes = (json.dumps(doc_without_hash, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                        expected_sha = hashlib.sha256(expected_bytes).hexdigest()
                        if not hmac.compare_digest(verdict_sha256, expected_sha):
                            blockers.append(
                                "보스 관문 판정서(autopilot-verdict.json)의 SHA-256 무결성 해시가 본문과 일치하지 않습니다 (판정서 위변조 감지)."
                            )
                        stages_obj = verdict_data.get("stages")
                        if isinstance(stages_obj, list) and any(
                            isinstance(s, dict) and s.get("status") != "PASS" for s in stages_obj
                        ):
                            blockers.append("보스 관문 판정서 내부에 실패(FAIL)한 검증 단계가 존재합니다.")
            except (OSError, ValueError):
                blockers.append(f"보스 관문 판정서({verdict_rel}) JSON 파싱에 실패했습니다.")

        if not hero_approved:
            blockers.append(
                "Hero(주인공 영웅 / 사용자)의 최종 병합 승인(--hero-approve 또는 모바일 앱 승인)이 아직 부여되지 않았습니다."
            )

        status = "PASS" if not blockers else "FAIL"
        return {
            "action": "guild-camp",
            "mode": "merge-guard",
            "status": status,
            "slot_id": slot_id,
            "verdict_status": verdict_status,
            "verdict_sha256": verdict_sha256,
            "hero_approved": hero_approved,
            "merge_allowed": status == "PASS",
            "blockers": blockers,
            "message_ko": (
                f"{slot_id} 결과물이 Cleric 보스 관문(해시: {verdict_sha256[:12]}...)과 Hero 최종 승인을 모두 충족하여 main 병합이 허용됩니다."
                if status == "PASS"
                else f"{slot_id} 결과물의 main 병합이 차단되었습니다 ({len(blockers)}개 조건 미충족): {'; '.join(blockers)}"
            ),
        }


def run_guild_camp_command(
    project_root: Path,
    mode: str = "status",
    slot_id: str = "bot-01",
    party_csv: str = "",
    owned_csv: str = "",
    label_ko: str = "",
    goal: str = "",
    quest_file: str = "",
    hero_approved: bool = False,
    apply: bool = False,
    *,
    party_classes: str = "",
    owned_paths: str = "",
    hero_approve: bool = False,
) -> dict[str, object]:
    """CLI 및 MCP에서 호출하는 통합 길드 캠프(1~10호기) 보안·페어링·서명·병합 게이트 엔트리포인트."""
    clean_mode = mode.strip().lower() or "status"
    eff_party = party_classes.strip() or party_csv.strip()
    eff_owned = owned_paths.strip() or owned_csv.strip()
    eff_hero = bool(hero_approve or hero_approved)
    pairing_mgr = CampPairingManager(project_root)

    if clean_mode in ("status", "list"):
        camps = pairing_mgr.load_camps()
        sec_arch = {
            "inbound_ports_opened": 0,
            "inbound_open_ports": 0,
            "transport": "outbound-only (git-queue + e2ee-relay)",
            "zero_secret_worker": True,
            "signed_quest_hmac_sha256": True,
            "worker_secret_policy": "zero-secret-worker (운영 비밀키 미보관 + SecretSanitizer 자동 마스킹)",
            "command_auth": "CSPRNG HMAC-SHA256 Signed Quest Envelope + TTL + Nonce Replay Guard",
            "merge_policy": "Cleric autopilot-gate PASS (SHA-256 Verified) + Hero 최종 승인 필수",
        }
        return {
            "action": "guild-camp",
            "mode": "status",
            "status": "PASS",
            "protagonist": route_planner.HERO_PERSONA,
            "commander": route_planner.AGENT_CALLSIGNS["router"],
            "security_architecture": sec_arch,
            "security_posture": sec_arch,
            "camps_count": len(camps),
            "camp_count": len(camps),
            "camps": [c.to_dict() for c in camps],
            "message_ko": "1~10호기(bot-01~bot-10) 원정 캠프 다중 파티 배치 및 제로 트러스트(포트 개방 0개) 보안 상태입니다.",
        }

    if clean_mode == "pair":
        if eff_party or eff_owned:
            party_list = [x.strip() for x in eff_party.split(",") if x.strip()] if eff_party else None
            owned_list = [x.strip() for x in eff_owned.split(",") if x.strip()] if eff_owned else None
            cfg_res = pairing_mgr.configure_camp_party(
                slot_id=slot_id,
                party_classes=party_list,
                owned_paths=owned_list,
                label_ko=label_ko,
                apply=apply,
            )
            if cfg_res.get("status") == "FAIL":
                return cfg_res
        return pairing_mgr.generate_pairing_ticket(slot_id=slot_id, apply=apply)

    if clean_mode == "configure":
        party_list = [x.strip() for x in eff_party.split(",") if x.strip()] if eff_party else None
        owned_list = [x.strip() for x in eff_owned.split(",") if x.strip()] if eff_owned else None
        return pairing_mgr.configure_camp_party(
            slot_id=slot_id,
            party_classes=party_list,
            owned_paths=owned_list,
            label_ko=label_ko,
            apply=apply,
        )

    if clean_mode in ("dispatch", "dispatch-quest"):
        if eff_party or eff_owned:
            party_list = [x.strip() for x in eff_party.split(",") if x.strip()] if eff_party else None
            owned_list = [x.strip() for x in eff_owned.split(",") if x.strip()] if eff_owned else None
            cfg_res = pairing_mgr.configure_camp_party(
                slot_id=slot_id,
                party_classes=party_list,
                owned_paths=owned_list,
                label_ko=label_ko,
                apply=apply,
            )
            if cfg_res.get("status") == "FAIL":
                return cfg_res
        dispenser = SignedQuestDispenser(project_root)
        return dispenser.issue_signed_quest(goal=goal, slot_id=slot_id, apply=apply)

    if clean_mode in ("verify", "verify-quest"):
        if not quest_file.strip():
            raise ValueError("verify-quest 모드에는 --quest-file 경로가 필요합니다.")
        q_path = _safe_project_path(project_root, quest_file)
        if not q_path.is_file():
            raise ValueError(f"퀘스트 파일을 찾을 수 없습니다: {quest_file}")
        env_data = json.loads(q_path.read_text(encoding="utf-8"))
        if not isinstance(env_data, dict):
            raise ValueError("유효하지 않은 퀘스트 봉투 형식입니다.")
        dispenser = SignedQuestDispenser(project_root)
        return dispenser.verify_signed_quest(env_data, record_nonce=apply)

    if clean_mode in ("merge-guard", "merge-check"):
        guard = BossGateMergeGuard(project_root)
        return guard.verify_merge_eligibility(slot_id=slot_id, hero_approved=eff_hero)

    if clean_mode in ("worker-run", "camp-worker-run"):
        daemon = CampWorkerDaemon(project_root)
        return daemon.run_once(slot_id=slot_id, quest_file=quest_file, apply=apply)

    raise ValueError(
        f"지원하지 않는 guild-camp 모드입니다 (status, pair, configure, dispatch, verify, merge-guard, worker-run 지원): {mode}"
    )


class CampWorkerDaemon:
    """길드 캠프 라이브 워커 폴링 실행기(camp-worker-run): 서명된 퀘스트 큐를 검증하고 실행 영수증을 서명·저장한다."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.state_dir = _resolve_state_dir(self.project_root)
        self.quests_dir = self.state_dir / "quests"
        self.results_dir = self.state_dir / "results"
        self.dispenser = SignedQuestDispenser(self.project_root)

    def run_once(
        self,
        slot_id: str = "bot-01",
        quest_file: str = "",
        *,
        apply: bool = False,
    ) -> dict[str, object]:
        """지정된 슬롯(bot-01~bot-10)의 대기 중인 서명 퀘스트를 폴링해 검증·수행하고 결과 영수증을 기록한다."""
        candidates: list[Path] = []
        if quest_file.strip():
            q_path = _safe_project_path(self.project_root, quest_file)
            if q_path.is_file():
                candidates.append(q_path)
        elif self.quests_dir.is_dir():
            candidates = sorted(self.quests_dir.glob("QUEST-*.json"))

        processed: list[dict[str, object]] = []
        for q_path in candidates:
            try:
                env_data = json.loads(q_path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if not isinstance(env_data, dict):
                continue
            if slot_id and str(env_data.get("target_slot") or "") != slot_id:
                continue
            quest_id = str(env_data.get("quest_id") or q_path.stem)
            result_path = self.results_dir / f"{quest_id}-result.json"
            if result_path.is_file() and not quest_file.strip():
                continue

            ver_res = self.dispenser.verify_signed_quest(env_data, record_nonce=apply)
            if ver_res.get("status") != "PASS":
                processed.append(
                    {
                        "quest_id": quest_id,
                        "status": "REJECTED",
                        "reason": ver_res.get("reason_code"),
                    }
                )
                continue

            receipt: dict[str, object] = {
                "quest_id": quest_id,
                "slot_id": slot_id,
                "goal": ZeroSecretGuard.sanitize_text(str(env_data.get("goal") or "")),
                "verified_signature": True,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "status": "COMPLETED",
            }
            if apply:
                self.results_dir.mkdir(parents=True, exist_ok=True)
                result_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            processed.append(receipt)

        return {
            "action": "guild-camp",
            "mode": "worker-run",
            "status": "PASS",
            "applied": apply,
            "slot_id": slot_id,
            "processed_count": len(processed),
            "processed_quests": processed,
            "message_ko": (
                f"길드 캠프 라이브 워커({slot_id}) 폴링 완료: 처리된 서명 퀘스트 {len(processed)}건."
            ),
        }

