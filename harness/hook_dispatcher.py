"""Dreampia 네이티브 호스트 생애주기 훅 디스패처 (Lifecycle Hook Dispatcher: PreToolUse / PostToolUse / Stop / UserPromptSubmit).

에이전트가 자발적으로 검증 도구를 호출하길 기다리지 않고 호스트 이벤트 루프에 직접 개입하여:
1. PreToolUse: 보호 경로 쓰기 및 파괴적 셸 명령을 실행 전에 물리적으로 차단 (< 30ms)
2. PostToolUse: 파일 편집 직후 단일 파일 증분 감사를 수행해 다음 턴 컨텍스트에 교정 지침 자동 주입 (< 80ms)
3. Stop: 차단 등급(CRITICAL/HIGH) 결함이 남아 있을 때 조기 종료를 막는 Sisyphus Continuation Enforcer (< 120ms)
4. UserPromptSubmit: 프로젝트 핵심 자가 학습 규칙을 프롬프트 컨텍스트에 자동 주입

SOLID 아키텍처:
- HookEventPayload: 호스트별 상이한 훅 입력 JSON을 정규화하는 불변 값 객체 (SRP)
- HookPolicyHandler: 이벤트별 정책 처리 추상 인터페이스 (OCP/DIP)
- PreToolUseHandler / PostToolUseHandler / StopContinuationHandler / PromptSubmitHandler (LSP/SRP)
- HostHookConfigManager: 호스트 settings.json에 멱등성 있게 훅을 설치·제거하는 구성 관리자 (ISP)
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime
import json
from pathlib import Path, PurePosixPath
import re
import time

try:
    from . import autopilot_engine, route_planner
except ImportError:
    import autopilot_engine, route_planner  # type: ignore[no-redef]

HOOK_DISPATCHER_VERSION = "0.8.0"
MAX_STOP_CONTINUATION_RETRIES = 3

_DESTRUCTIVE_SHELL_RE = re.compile(
    r"(?:\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+(?:/|\.\.|~|\*)"
    r"|\bgit\s+reset\s+--hard\b"
    r"|\bgit\s+push\s+(?:--force|-f)\b"
    r"|\bgit\s+clean\s+-[a-zA-Z]*f[a-zA-Z]*d\b"
    r"|\bformat\s+[a-zA-Z]:"
    r"|\bdel\s+/[fFsS]\s+/[qQ])",
    re.IGNORECASE,
)

_PROTECTED_REL_PATHS: frozenset[str] = frozenset(
    {
        "ai-dev-execution/bundle-manifest.json",
        ".git/config",
        ".git/HEAD",
        ".dreampia-install/manifest.json",
    }
)

_WRITE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "Write",
        "Edit",
        "MultiEdit",
        "NotebookEdit",
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
    }
)

_SHELL_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "Bash",
        "run_command",
        "execute_command",
        "shell",
    }
)


@dataclass(frozen=True)
class HookEventPayload:
    """정규화된 생애주기 훅 이벤트 입력 객체."""

    event_name: str
    tool_name: str
    file_path: str
    command_line: str
    stop_hook_active: bool
    user_prompt: str


def parse_hook_payload(event_name: str, raw_payload: dict[str, object]) -> HookEventPayload:
    """호스트(Claude Code, Antigravity, Cursor 등)의 훅 JSON 페이로드를 표준 구조로 정규화한다."""
    ev = (event_name or str(raw_payload.get("hook_event_name") or raw_payload.get("event") or "PreToolUse")).strip()
    tool_name = str(raw_payload.get("tool_name") or raw_payload.get("tool") or "").strip()
    tool_input = raw_payload.get("tool_input") or raw_payload.get("arguments") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    file_path = str(
        tool_input.get("file_path")
        or tool_input.get("TargetFile")
        or tool_input.get("path")
        or raw_payload.get("file_path")
        or ""
    ).strip()
    command_line = str(
        tool_input.get("command")
        or tool_input.get("CommandLine")
        or tool_input.get("cmd")
        or raw_payload.get("command")
        or ""
    ).strip()
    stop_active = bool(raw_payload.get("stop_hook_active", False))
    user_prompt = str(raw_payload.get("prompt") or raw_payload.get("user_prompt") or "").strip()

    return HookEventPayload(
        event_name=ev,
        tool_name=tool_name,
        file_path=file_path,
        command_line=command_line,
        stop_hook_active=stop_active,
        user_prompt=user_prompt,
    )


def _handle_pre_tool_use(project_root: Path, payload: HookEventPayload) -> dict[str, object]:
    """PreToolUse: 경계 밖 쓰기, 보호 파일 직접 변조, 파괴적 셸 명령을 실행 전에 차단한다."""
    resolved = project_root.resolve()

    if payload.tool_name in _SHELL_TOOL_NAMES or payload.command_line:
        if _DESTRUCTIVE_SHELL_RE.search(payload.command_line):
            reason = (
                f"파괴적 셸 명령 패턴이 감지되어 실행이 사전 차단되었습니다: '{payload.command_line[:80]}'. "
                "작업 트리 보호를 위해 안전한 대안 명령이나 체크포인트를 사용하십시오."
            )
            return {
                "action": "hook-dispatch",
                "event": "PreToolUse",
                "status": "BLOCKED",
                "decision": "block",
                "permissionDecision": "deny",
                "reason": reason,
                "message_ko": reason,
            }

    if payload.tool_name in _WRITE_TOOL_NAMES or payload.file_path:
        if payload.file_path:
            cand = Path(payload.file_path)
            abs_target = cand.resolve() if cand.is_absolute() else (resolved / cand).resolve()
            if abs_target != resolved and resolved not in abs_target.parents:
                reason = (
                    f"프로젝트 워크스페이스({resolved}) 외부 경로('{abs_target}')에 대한 파일 쓰기가 차단되었습니다."
                )
                return {
                    "action": "hook-dispatch",
                    "event": "PreToolUse",
                    "status": "BLOCKED",
                    "decision": "block",
                    "permissionDecision": "deny",
                    "reason": reason,
                    "message_ko": reason,
                }
            rel_posix = abs_target.relative_to(resolved).as_posix()
            if rel_posix in _PROTECTED_REL_PATHS:
                reason = (
                    f"보호 대상 매니페스트/설정 파일('{rel_posix}')의 직접 수정이 차단되었습니다. "
                    "전용 CLI 명령(release, setup 등)을 통해 갱신하십시오."
                )
                return {
                    "action": "hook-dispatch",
                    "event": "PreToolUse",
                    "status": "BLOCKED",
                    "decision": "block",
                    "permissionDecision": "deny",
                    "reason": reason,
                    "message_ko": reason,
                }

    return {
        "action": "hook-dispatch",
        "event": "PreToolUse",
        "status": "PASS",
        "decision": "approve",
        "permissionDecision": "allow",
        "message_ko": "PreToolUse 보안 및 경계 검사를 통과했습니다.",
    }


def _handle_post_tool_use(project_root: Path, payload: HookEventPayload) -> dict[str, object]:
    """PostToolUse: 파일 수정 직후 단일 파일 증분 감사를 실행해 위반 시 즉시 피드백을 주입한다."""
    resolved = project_root.resolve()
    if not payload.file_path:
        return {
            "action": "hook-dispatch",
            "event": "PostToolUse",
            "status": "PASS",
            "decision": "approve",
            "message_ko": "검사할 대상 파일 경로가 없어 PostToolUse 감사를 생략했습니다.",
        }

    cand = Path(payload.file_path)
    abs_target = cand.resolve() if cand.is_absolute() else (resolved / cand).resolve()
    if not abs_target.is_file() or (abs_target != resolved and resolved not in abs_target.parents):
        return {
            "action": "hook-dispatch",
            "event": "PostToolUse",
            "status": "PASS",
            "decision": "approve",
            "message_ko": "대상 파일이 워크스페이스 내에 존재하지 않아 PostToolUse 감사를 생략했습니다.",
        }

    rel_posix = PurePosixPath(abs_target.relative_to(resolved).as_posix()).as_posix()
    audit_res = autopilot_engine.audit_project_code(
        resolved,
        changed_only=True,
        precomputed_changed_list=[rel_posix],
        apply=False,
    )
    findings = audit_res.get("findings", [])
    if not isinstance(findings, list) or len(findings) == 0:
        return {
            "action": "hook-dispatch",
            "event": "PostToolUse",
            "status": "PASS",
            "decision": "approve",
            "scanned_file": rel_posix,
            "finding_count": 0,
            "message_ko": f"PostToolUse 증분 감사 통과: '{rel_posix}' (결함 0건)",
        }

    summary_lines = [f"[Dreampia PostToolUse 즉시 감사 경고 — {rel_posix}]"]
    for item in findings[:5]:
        if isinstance(item, dict):
            summary_lines.append(
                f"- [{item.get('severity')}] {item.get('rule_id')} ({item.get('evidence')}): "
                f"{item.get('issue')} -> 해결: {item.get('fix')}"
            )
    context_msg = "\n".join(summary_lines)
    return {
        "action": "hook-dispatch",
        "event": "PostToolUse",
        "status": "WARN",
        "decision": "approve",
        "scanned_file": rel_posix,
        "finding_count": len(findings),
        "findings": findings,
        "additionalContext": context_msg,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context_msg,
        },
        "message_ko": context_msg,
    }


def _load_and_bump_stop_counter(project_root: Path, reset: bool = False) -> int:
    state_file = project_root / ".dreampia-skill" / "hook-stop-state.json"
    if reset:
        if state_file.is_file():
            try:
                state_file.unlink()
            except OSError:
                pass
        return 0
    count = 0
    if state_file.is_file():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                count = int(data.get("consecutive_blocks") or 0)
        except (OSError, ValueError, TypeError):
            count = 0
    count += 1
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "consecutive_blocks": count,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return count


def _handle_stop_continuation(project_root: Path, _payload: HookEventPayload) -> dict[str, object]:
    """Stop: 차단 등급(CRITICAL/HIGH) 결함이 남아 있을 때 에이전트의 조기 종료를 차단한다 (최대 3회 연속)."""
    resolved = project_root.resolve()
    has_git = (resolved / ".git").exists()
    audit_res = autopilot_engine.audit_project_code(
        resolved,
        changed_only=True if has_git else False,
        apply=False,
    )
    blocking_count = int(audit_res.get("blocking_count") or 0)  # type: ignore[arg-type]
    if blocking_count == 0:
        _load_and_bump_stop_counter(resolved, reset=True)
        return {
            "action": "hook-dispatch",
            "event": "Stop",
            "status": "PASS",
            "decision": "approve",
            "blocking_count": 0,
            "message_ko": "미해결 차단 결함이 없어 턴 종료(Stop)를 승인합니다.",
        }

    attempt = _load_and_bump_stop_counter(resolved, reset=False)
    if attempt > MAX_STOP_CONTINUATION_RETRIES:
        _load_and_bump_stop_counter(resolved, reset=True)
        return {
            "action": "hook-dispatch",
            "event": "Stop",
            "status": "PASS",
            "decision": "approve",
            "blocking_count": blocking_count,
            "escape_hatch_triggered": True,
            "message_ko": f"최대 연속 종료 방어 횟수({MAX_STOP_CONTINUATION_RETRIES}회)에 도달하여 무한 루프 방지를 위해 종료를 허용합니다.",
        }

    findings = audit_res.get("findings", [])
    blocking_items = [
        f for f in (findings if isinstance(findings, list) else [])
        if isinstance(f, dict) and f.get("severity") in ("CRITICAL", "HIGH")
    ]
    details = "; ".join(
        f"{f.get('rule_id')}({f.get('evidence')})" for f in blocking_items[:3]
    )
    reason = (
        f"[Sisyphus Continuation Enforcer ({attempt}/{MAX_STOP_CONTINUATION_RETRIES})] "
        f"미해결 차단 결함 {blocking_count}건({details})이 남아 있어 턴을 종료할 수 없습니다. "
        "결함을 먼저 수정한 뒤 다시 완료하십시오."
    )
    return {
        "action": "hook-dispatch",
        "event": "Stop",
        "status": "BLOCKED",
        "decision": "block",
        "blocking_count": blocking_count,
        "attempt": attempt,
        "reason": reason,
        "message_ko": reason,
    }


def _handle_user_prompt_submit(project_root: Path, _payload: HookEventPayload) -> dict[str, object]:
    """UserPromptSubmit: 프로젝트에 학습된 핵심 불변 규칙을 프롬프트 컨텍스트에 자동 첨부한다."""
    resolved = project_root.resolve()
    rules = autopilot_engine.load_project_rules(resolved)
    if not rules:
        return {
            "action": "hook-dispatch",
            "event": "UserPromptSubmit",
            "status": "PASS",
            "decision": "approve",
            "injected_rule_count": 0,
            "message_ko": "주입할 프로젝트 학습 규칙이 없습니다.",
        }
    top_rules = [str(r.get("rule_ko") or "") for r in rules[:10] if r.get("rule_ko")]
    context_str = "[Dreampia 핵심 프로젝트 규칙]\n" + "\n".join(f"- {r}" for r in top_rules)
    return {
        "action": "hook-dispatch",
        "event": "UserPromptSubmit",
        "status": "PASS",
        "decision": "approve",
        "injected_rule_count": len(top_rules),
        "additionalContext": context_str,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context_str,
        },
        "message_ko": f"프로젝트 핵심 학습 규칙 {len(top_rules)}건을 컨텍스트에 주입했습니다.",
    }


def dispatch_hook_event(
    project_root: Path,
    event_name: str = "PreToolUse",
    raw_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """호스트 생애주기 훅 이벤트를 실행하고 표준 응답 JSON과 소요 시간(ms)을 반환한다."""
    t0 = time.perf_counter()
    payload = parse_hook_payload(event_name, raw_payload or {})
    ev_norm = payload.event_name.lower()

    if ev_norm in ("pretooluse", "pre-tool-use", "pre"):
        res = _handle_pre_tool_use(project_root, payload)
    elif ev_norm in ("posttooluse", "post-tool-use", "post"):
        res = _handle_post_tool_use(project_root, payload)
    elif ev_norm in ("stop", "subagentstop"):
        res = _handle_stop_continuation(project_root, payload)
    elif ev_norm in ("userpromptsubmit", "prompt-submit", "prompt"):
        res = _handle_user_prompt_submit(project_root, payload)
    else:
        raise ValueError(f"지원하지 않는 생애주기 훅 이벤트입니다: {payload.event_name}")

    res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
    return res


def install_host_hooks(
    settings_path: Path,
    cli_invoke_prefix: str,
    *,
    apply: bool = False,
) -> dict[str, object]:
    """Claude Code 등 호스트의 settings.json에 Dreampia 생애주기 훅(PreToolUse, PostToolUse, Stop)을 멱등성 있게 등록한다."""
    existing: dict[str, object] = {}
    if settings_path.is_file() and not settings_path.is_symlink():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except ValueError:
            existing = {}

    hooks_obj = existing.get("hooks")
    if not isinstance(hooks_obj, dict):
        hooks_obj = {}
        existing["hooks"] = hooks_obj

    event_specs = (
        ("PreToolUse", "Write|Edit|MultiEdit|Bash", f"{cli_invoke_prefix} hook-dispatch --mode PreToolUse"),
        ("PostToolUse", "Write|Edit|MultiEdit", f"{cli_invoke_prefix} hook-dispatch --mode PostToolUse"),
        ("Stop", "", f"{cli_invoke_prefix} hook-dispatch --mode Stop"),
    )

    for ev_name, matcher, cmd_str in event_specs:
        ev_list = hooks_obj.get(ev_name)
        if not isinstance(ev_list, list):
            ev_list = []
        filtered = [
            entry for entry in ev_list
            if not (isinstance(entry, dict) and "hook-dispatch" in json.dumps(entry))
        ]
        new_entry: dict[str, object] = {
            "hooks": [{"type": "command", "command": cmd_str}],
        }
        if matcher:
            new_entry["matcher"] = matcher
        filtered.append(new_entry)
        hooks_obj[ev_name] = filtered

    if apply:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "status": "PASS",
        "applied": apply,
        "settings_path": str(settings_path),
        "registered_events": ["PreToolUse", "PostToolUse", "Stop"],
    }


def uninstall_host_hooks(settings_path: Path, *, apply: bool = False) -> dict[str, object]:
    """호스트 settings.json에서 Dreampia hook-dispatch 항목만 안전하게 제거한다."""
    if not settings_path.is_file() or settings_path.is_symlink():
        return {"status": "PASS", "applied": apply, "removed": False, "settings_path": str(settings_path)}

    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except ValueError:
        return {"status": "PASS", "applied": apply, "removed": False, "settings_path": str(settings_path)}

    if not isinstance(existing, dict) or not isinstance(existing.get("hooks"), dict):
        return {"status": "PASS", "applied": apply, "removed": False, "settings_path": str(settings_path)}

    hooks_obj = existing["hooks"]
    assert isinstance(hooks_obj, dict)
    removed_any = False
    for ev_name in list(hooks_obj.keys()):
        ev_list = hooks_obj.get(ev_name)
        if isinstance(ev_list, list):
            kept = [
                entry for entry in ev_list
                if not (isinstance(entry, dict) and "hook-dispatch" in json.dumps(entry))
            ]
            if len(kept) != len(ev_list):
                removed_any = True
            if kept:
                hooks_obj[ev_name] = kept
            else:
                del hooks_obj[ev_name]

    if apply and removed_any:
        settings_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "status": "PASS",
        "applied": apply,
        "removed": removed_any,
        "settings_path": str(settings_path),
    }
