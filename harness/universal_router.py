"""Dreampia Universal Harness Router & Multi-Host Skill Materializer.

Dreampia Skill native router engine enabling ai-dev-execution to operate as a universal
router across any agent harness (Codex, Claude Code, Gemini/Antigravity, OpenCode,
DeepSeek, Hermes, Pi, Goose, Aider, Qwen, or local deterministic adapters) via CLI
or local loopback gateway endpoints.

SOLID Architecture:
- NodeCatalog: Single responsibility for agent host descriptors, loader paths, and truthful discovery
- ReasoningTierPolicy: Single responsibility for model and route-profile reasoning tier calculation
- SecretSanitizer: Single responsibility for scrubbing credentials from outputs, events, and ledgers
- HarnessMaterializer: Single responsibility for skill bundle, MCP config, and plugin materialization
- TaskDispatchEngine: Single responsibility for task routing, session continuity, and artifact tracking
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import time
from typing import Callable
import uuid

try:
    from . import process, route_planner, skill_bundle, write_boundary
except ImportError:
    import process  # type: ignore[no-redef]
    import route_planner  # type: ignore[no-redef]
    import skill_bundle  # type: ignore[no-redef]
    import write_boundary  # type: ignore[no-redef]

ROUTER_VERSION = "0.7.0"
SUPPORTED_ROUTER_VERSIONS: tuple[str, ...] = ("0.7.0", "0.6.0", "1.0.0")
DREAMPIA_PLUGIN_SCHEMA = "https://dreampia.dev/schemas/v1/plugin-manifest.json"
DEFAULT_AUTHORIZED_MODEL = "dreampia-default"
DEFAULT_REASONING_EFFORT = "medium"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROUTER_STATE_DIR = ".harness/router"

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9._-]")
_MCP_NAME_RE = re.compile(r"[^A-Za-z0-9_]")
_PLUGIN_EXEC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^bin/[^/]+$"),
    re.compile(r"^hooks/[^/]+\.sh$"),
)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})['\"]?"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-.=]{12,}"),
)


class RouterError(ValueError):
    """드림피아 라우터 표준 에러 엔벨로프를 표현하는 예외."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        error_type: str = "invalid_request_error",
        http_status: int = 400,
        param: str | None = None,
        detail: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.error_type = error_type
        self.http_status = http_status
        self.param = param
        self.detail = detail

    def to_envelope(self) -> dict[str, object]:
        return {
            "error": {
                "type": self.error_type,
                "code": self.code,
                "message": self.message,
                "param": self.param,
                "detail": self.detail,
            }
        }


@dataclass(frozen=True)
class HarnessSpec:
    """개별 에이전트 하네스 호스트의 경로·명령·MCP 설정 명세."""

    base: str
    base_label: str
    executables: tuple[str, ...]
    skill_roots: tuple[str, ...]
    entry_root: str
    instruction_files: tuple[str, ...]
    mcp_format: str
    default_model: str


HARNESS_SPECS: dict[str, HarnessSpec] = {
    "codex": HarnessSpec(
        base="codex",
        base_label="OpenAI Codex CLI",
        executables=("codex",),
        skill_roots=(".agents/skills", ".harness/home/.codex/skills"),
        entry_root=".agents/skills",
        instruction_files=("AGENTS.md", ".dreampia/WORK_CONTRACT.ko.md"),
        mcp_format="codex-toml",
        default_model="gpt-5-codex",
    ),
    "claude": HarnessSpec(
        base="claude",
        base_label="Claude Code CLI",
        executables=("claude",),
        skill_roots=(".claude/skills", ".harness/home/.claude/skills"),
        entry_root=".claude/skills",
        instruction_files=("CLAUDE.md", "AGENTS.md"),
        mcp_format="claude-json",
        default_model="claude-sonnet-4",
    ),
    "gemini": HarnessSpec(
        base="gemini",
        base_label="Gemini CLI / Antigravity",
        executables=("gemini", "agy"),
        skill_roots=(".gemini/skills", ".agents/skills", ".harness/home/.gemini/skills"),
        entry_root=".gemini/skills",
        instruction_files=("AGENTS.md",),
        mcp_format="gemini-json",
        default_model="gemini-2.5-pro",
    ),
    "opencode": HarnessSpec(
        base="opencode",
        base_label="OpenCode CLI",
        executables=("opencode",),
        skill_roots=(".harness/skills", ".agents/skills"),
        entry_root=".harness/skills",
        instruction_files=("AGENTS.md",),
        mcp_format="opencode-json",
        default_model="gpt-5-codex",
    ),
    "dsh": HarnessSpec(
        base="dsh",
        base_label="DeepSeek CLI",
        executables=("dsh", "deepseek"),
        skill_roots=(".harness/skills",),
        entry_root=".harness/skills",
        instruction_files=("AGENTS.md",),
        mcp_format="dsh-json",
        default_model="deepseek-r1",
    ),
    "hermes": HarnessSpec(
        base="hermes",
        base_label="Hermes Agent",
        executables=("hermes",),
        skill_roots=(".harness/home/.hermes/skills",),
        entry_root=".harness/home/.hermes/skills",
        instruction_files=("AGENTS.md",),
        mcp_format="hermes-json",
        default_model="claude-sonnet-4",
    ),
    "pi": HarnessSpec(
        base="pi",
        base_label="Pi Coding Agent",
        executables=("pi",),
        skill_roots=(".harness/home/.pi/agent/skills",),
        entry_root=".harness/home/.pi/agent/skills",
        instruction_files=("AGENTS.md",),
        mcp_format="pi-json",
        default_model="claude-sonnet-4",
    ),
    "goose": HarnessSpec(
        base="goose",
        base_label="Goose Agent",
        executables=("goose",),
        skill_roots=(".harness/goose/config/skills",),
        entry_root=".harness/goose/config/skills",
        instruction_files=("AGENTS.md",),
        mcp_format="goose-json",
        default_model="gpt-5-codex",
    ),
    "qwen": HarnessSpec(
        base="qwen",
        base_label="Qwen Code CLI",
        executables=("qwen",),
        skill_roots=(".harness/home/.qwen/skills",),
        entry_root=".harness/home/.qwen/skills",
        instruction_files=("AGENTS.md",),
        mcp_format="qwen-json",
        default_model="qwen3-coder",
    ),
    "aider": HarnessSpec(
        base="aider",
        base_label="Aider CLI",
        executables=("aider",),
        skill_roots=(".harness/skills",),
        entry_root=".harness/skills",
        instruction_files=("AGENTS.md",),
        mcp_format="claude-json",
        default_model="gpt-5-codex",
    ),
    "local": HarnessSpec(
        base="local",
        base_label="Dreampia Local Deterministic Harness",
        executables=("python3", "python"),
        skill_roots=(".agents/skills", ".harness/skills"),
        entry_root=".agents/skills",
        instruction_files=("AGENTS.md", ".dreampia/WORK_CONTRACT.ko.md"),
        mcp_format="claude-json",
        default_model=DEFAULT_AUTHORIZED_MODEL,
    ),
}

_MODEL_REASONING_TIERS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (re.compile(r"^gpt-5|^o[34]|^dreampia-default"), ("low", "medium", "high", "max")),
    (re.compile(r"^claude-(sonnet|opus|haiku)"), ("none", "low", "medium", "high", "max")),
    (re.compile(r"^gemini-2\.5-pro"), ("low", "medium", "high")),
    (re.compile(r"^gemini-2\.5-flash"), ("none", "minimal", "low", "medium", "high")),
    (re.compile(r"^deepseek-r1"), ("low", "medium", "high", "max")),
    (re.compile(r"^qwen3"), ("none", "medium", "high")),
)
_ALL_EFFORT_ORDER: tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "max")


def normalize_reasoning_effort(model: str, requested: str = DEFAULT_REASONING_EFFORT) -> dict[str, object]:
    """모델군별 지원 추론 단계(reasoning_effort)를 계산하고 미지원 시 가장 가까운 유효 단계로 정규화한다."""
    bare = str(model or "").strip().lower().rsplit("/", 1)[-1]
    req = str(requested or DEFAULT_REASONING_EFFORT).strip().lower()
    if req == "xhigh":
        req = "max"
    if req not in _ALL_EFFORT_ORDER:
        raise RouterError(
            "invalid_input",
            f"지원하지 않는 reasoning_effort 값입니다: {requested}",
            param="reasoning_effort",
        )
    supported: tuple[str, ...] = ()
    for pattern, levels in _MODEL_REASONING_TIERS:
        if pattern.search(bare):
            supported = levels
            break
    if not supported:
        return {
            "model": bare,
            "requested_effort": req,
            "effective_effort": "default",
            "supported_levels": [],
            "substituted": req != "default",
        }
    if req in supported:
        return {
            "model": bare,
            "requested_effort": req,
            "effective_effort": req,
            "supported_levels": list(supported),
            "substituted": False,
        }
    req_idx = _ALL_EFFORT_ORDER.index(req)
    nearest = min(supported, key=lambda lvl: abs(_ALL_EFFORT_ORDER.index(lvl) - req_idx))
    return {
        "model": bare,
        "requested_effort": req,
        "effective_effort": nearest,
        "supported_levels": list(supported),
        "substituted": True,
    }


def _safe_join(root: Path, rel_path: str) -> Path:
    """루트 외부 탈출이나 심볼릭 링크를 허용하지 않고 안전한 하위 경로를 반환한다."""
    if not isinstance(rel_path, str) or not rel_path.strip() or "\\" in rel_path or "\x00" in rel_path:
        raise RouterError("plugin_invalid", "유효하지 않은 상대 경로입니다.", http_status=422, param="path")
    pure = PurePosixPath(rel_path.strip())
    if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
        raise RouterError("plugin_invalid", f"경로가 루트 외부로 벗어납니다: {rel_path}", http_status=422, param="path")
    current = root.resolve()
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise RouterError("plugin_invalid", f"심볼릭 링크 경로는 허용되지 않습니다: {rel_path}", http_status=422)
    return current


def redact_secrets(text: str, extra_secrets: tuple[str, ...] = ()) -> str:
    """출력·이벤트·세션 기록에서 비밀키·토큰 값을 마스킹한다."""
    if not isinstance(text, str) or not text:
        return ""
    redacted = text
    for secret in extra_secrets:
        if secret and len(secret) >= 4:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _SECRET_PATTERNS[0].sub("[REDACTED_PRIVATE_KEY]", redacted)
    redacted = _SECRET_PATTERNS[1].sub(r"\1=[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[2].sub("Bearer [REDACTED]", redacted)
    return redacted


def _mcp_headers(server_cfg: dict[str, object]) -> dict[str, str]:
    """선언된 auth 필드를 Authorization 헤더로 변환하고 headers를 병합한다."""
    out: dict[str, str] = {}
    auth = server_cfg.get("auth")
    if isinstance(auth, str) and auth.strip():
        val = auth.strip()
        out["Authorization"] = val if val.lower().startswith("bearer ") else f"Bearer {val}"
    hdrs = server_cfg.get("headers")
    if isinstance(hdrs, dict):
        for k, v in hdrs.items():
            if isinstance(k, str) and k.strip() and v is not None:
                out[k.strip()] = str(v)
    return out


def discover_harnesses(
    root: Path | None = None,
    *,
    which_fn: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    """현재 시스템과 워크스페이스에서 사용 가능한 하네스 노드 및 라우터 기능을 결정론적으로 탐색한다."""
    harnesses: list[dict[str, object]] = []
    models_by_backend: dict[str, dict[str, object]] = {}
    resolved_root = root.resolve() if root is not None else None

    for base, spec in HARNESS_SPECS.items():
        found_exe: str | None = None
        for exe in spec.executables:
            resolved_exe = which_fn(exe)
            if resolved_exe:
                found_exe = resolved_exe
                break
        available = found_exe is not None or base == "local"
        skill_installed = False
        if resolved_root is not None:
            for sroot in spec.skill_roots:
                candidate = resolved_root / sroot / "ai-dev-execution" / "SKILL.md"
                if candidate.is_file() and not candidate.is_symlink():
                    skill_installed = True
                    break

        harness_id = f"dp_node_{base}"
        harnesses.append(
            {
                "id": harness_id,
                "object": "harness",
                "name": f"Dreampia ({spec.base_label})",
                "base": spec.base,
                "baseLabel": spec.base_label,
                "defaultModel": spec.default_model,
                "available": available,
                "executable": found_exe,
                "skillInstalled": skill_installed,
                "skillRoots": list(spec.skill_roots),
                "entrySkillPath": f"{spec.entry_root}/ai-dev-execution/SKILL.md",
                "mcpServers": [],
                "skills": [{"name": "ai-dev-execution", "installed": skill_installed}],
                "plugins": [],
            }
        )
        models_by_backend[base] = {
            "default": spec.default_model,
            "models": [
                {
                    "id": spec.default_model,
                    "label": spec.default_model,
                    "backend": base,
                    "available": available,
                    "default": True,
                }
            ],
        }

    return {
        "protocol": "DRP",
        "default_version": ROUTER_VERSION,
        "versions": list(SUPPORTED_ROUTER_VERSIONS),
        "capabilities": {
            "sessions": True,
            "files": True,
            "harness_management": True,
            "plugins": True,
            "write_boundary": True,
            "cleanroom": True,
        },
        "plugin_schemas": [DREAMPIA_PLUGIN_SCHEMA],
        "harnesses": harnesses,
        "backends": models_by_backend,
    }


def export_router_plugin(
    source: Path = PACKAGE_ROOT,
    *,
    mcp_servers: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """드림피아 스킬(ai-dev-execution)을 표준 플러그인 번들 객체로 내보낸다."""
    skill_dir = source.resolve() / "ai-dev-execution"
    bundle_files = skill_bundle.read(skill_dir)
    info = skill_bundle.validate(bundle_files, (source.resolve() / "VERSION").read_text(encoding="utf-8").strip())

    plugin_manifest = {
        "$schema": DREAMPIA_PLUGIN_SCHEMA,
        "name": "dreampia-ai-dev-execution",
        "version": info["version"],
        "description": "Dreampia AI Dev Execution Skill & Governance Router Bundle",
    }

    files_out: list[dict[str, str]] = [
        {"path": "plugin.json", "content": json.dumps(plugin_manifest, ensure_ascii=False, indent=2) + "\n"}
    ]

    skipped: list[dict[str, str]] = []
    exported_mcp: dict[str, dict[str, object]] = {}
    for srv in mcp_servers or []:
        if not isinstance(srv, dict) or srv.get("enabled") is False:
            continue
        raw_name = str(srv.get("name") or "").strip()
        safe_name = _MCP_NAME_RE.sub("_", raw_name).strip("_") or "mcp"
        url = srv.get("url")
        command = srv.get("command")
        if isinstance(url, str) and url.strip():
            transport = "sse" if str(srv.get("transport") or "http").lower() == "sse" else "streamable-http"
            exported_mcp[safe_name] = {"type": transport, "url": url.strip()}
            if srv.get("auth") or srv.get("headers"):
                skipped.append(
                    {
                        "path": f"mcp.json#/mcpServers/{safe_name}",
                        "reason": "Credential fields (auth/headers) are omitted on bundle export by Dreampia security policy.",
                    }
                )
        elif isinstance(command, str) and command.strip():
            exported_mcp[safe_name] = {
                "type": "stdio",
                "command": command.strip(),
                "args": list(srv.get("args") or []) if isinstance(srv.get("args"), list) else [],
            }

    if exported_mcp:
        mcp_doc = {
            "$schema": DREAMPIA_PLUGIN_SCHEMA,
            "mcpServers": exported_mcp,
        }
        files_out.append({"path": "mcp.json", "content": json.dumps(mcp_doc, ensure_ascii=False, indent=2) + "\n"})

    for rel_path, raw_bytes in sorted(bundle_files.items()):
        plugin_rel = f"skills/ai-dev-execution/{rel_path}"
        try:
            text_content = raw_bytes.decode("utf-8")
            files_out.append({"path": plugin_rel, "content": text_content})
        except UnicodeDecodeError:
            files_out.append({"path": plugin_rel, "content_b64": base64.b64encode(raw_bytes).decode("ascii")})

    return {
        "name": "dreampia-ai-dev-execution",
        "enabled": True,
        "manifest": plugin_manifest,
        "mcpServers": [
            {"name": k, **v, "enabled": True} for k, v in sorted(exported_mcp.items())
        ],
        "skills": [
            {
                "name": "ai-dev-execution",
                "description": "Develop small projects, services, and substantial features with proportionate specs, TDD, real evidence, and resumable milestones.",
            }
        ],
        "skipped": skipped,
        "files": files_out,
    }


def _render_mcp_for_backend(
    root: Path,
    base: str,
    mcp_servers: list[dict[str, object]],
    *,
    apply: bool = False,
) -> list[str]:
    """각 하네스 호스트의 고유 포맷에 맞춰 MCP 서버 설정 파일을 렌더링한다."""
    if not mcp_servers:
        return []
    spec = HARNESS_SPECS.get(base)
    if spec is None:
        raise RouterError("unsupported_base", f"지원하지 않는 하네스 백엔드입니다: {base}", http_status=422)

    written_paths: list[str] = []
    if spec.mcp_format == "codex-toml":
        blocks: list[str] = ["# Dreampia Managed MCP Configuration"]
        for srv in mcp_servers:
            if srv.get("enabled") is False:
                continue
            name = _MCP_NAME_RE.sub("_", str(srv.get("name") or "mcp")).strip("_") or "mcp"
            url = srv.get("url")
            cmd = srv.get("command")
            if isinstance(url, str) and url.strip():
                lines = [f"[mcp_servers.{name}]", f'url = "{url.strip()}"']
                hdrs = _mcp_headers(srv)
                if hdrs:
                    pairs = ", ".join(f'"{k}" = "{v}"' for k, v in sorted(hdrs.items()))
                    lines.append(f"http_headers = {{ {pairs} }}")
                blocks.append("\n".join(lines))
            elif isinstance(cmd, str) and cmd.strip():
                args_list = [f'"{str(a)}"' for a in (srv.get("args") or []) if isinstance(srv.get("args"), list)]
                blocks.append(
                    f"[mcp_servers.{name}]\ncommand = \"{cmd.strip()}\"\nargs = [{', '.join(args_list)}]"
                )
        rel = ".harness/codex-mcp.toml"
        if apply:
            target = _safe_join(root, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(blocks) + "\n", encoding="utf-8")
        written_paths.append(rel)
    elif spec.mcp_format in ("gemini-json", "qwen-json"):
        entries: dict[str, dict[str, object]] = {}
        for srv in mcp_servers:
            if srv.get("enabled") is False:
                continue
            name = _MCP_NAME_RE.sub("_", str(srv.get("name") or "mcp")).strip("_") or "mcp"
            url = srv.get("url")
            if isinstance(url, str) and url.strip():
                transport = str(srv.get("transport") or "http").lower()
                key = "url" if transport == "sse" else "httpUrl"
                entry: dict[str, object] = {key: url.strip()}
                hdrs = _mcp_headers(srv)
                if hdrs:
                    entry["headers"] = hdrs
                entries[name] = entry
        folder = ".gemini" if spec.mcp_format == "gemini-json" else ".qwen"
        rel = f"{folder}/settings.json"
        if apply and entries:
            target = _safe_join(root, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"mcpServers": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if entries:
            written_paths.append(rel)
    else:
        entries_std: dict[str, dict[str, object]] = {}
        for srv in mcp_servers:
            if srv.get("enabled") is False:
                continue
            name = _MCP_NAME_RE.sub("_", str(srv.get("name") or "mcp")).strip("_") or "mcp"
            url = srv.get("url")
            cmd = srv.get("command")
            if isinstance(url, str) and url.strip():
                transport = "sse" if str(srv.get("transport") or "http").lower() == "sse" else "http"
                entry_std: dict[str, object] = {"type": transport, "url": url.strip()}
                hdrs = _mcp_headers(srv)
                if hdrs:
                    entry_std["headers"] = hdrs
                entries_std[name] = entry_std
            elif isinstance(cmd, str) and cmd.strip():
                entries_std[name] = {
                    "type": "stdio",
                    "command": cmd.strip(),
                    "args": list(srv.get("args") or []) if isinstance(srv.get("args"), list) else [],
                }
        rel = ".mcp.json" if base == "claude" else ".harness/mcp.json"
        if apply and entries_std:
            target = _safe_join(root, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps({"mcpServers": entries_std}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if entries_std:
            written_paths.append(rel)
    return written_paths


def materialize_harness(
    root: Path,
    harness_target: str = "all",
    *,
    source: Path = PACKAGE_ROOT,
    mcp_servers: list[dict[str, object]] | None = None,
    include_plugin: bool = True,
    apply: bool = False,
) -> dict[str, object]:
    """지정된 하네스(또는 전체 하네스)의 고유 스킬 로더 경로와 플러그인 루트에 드림피아 스킬을 배치한다."""
    if root.is_symlink() or not root.is_dir():
        raise RouterError("invalid_input", "유효한 프로젝트 디렉터리가 필요합니다.")
    resolved_root = root.resolve()
    skill_dir = source.resolve() / "ai-dev-execution"
    bundle_files = skill_bundle.read(skill_dir)
    version = (source.resolve() / "VERSION").read_text(encoding="utf-8").strip()
    skill_bundle.validate(bundle_files, version)

    if harness_target == "all":
        bases = tuple(HARNESS_SPECS.keys())
    elif harness_target in HARNESS_SPECS:
        bases = (harness_target,)
    else:
        raise RouterError(
            "unsupported_base",
            f"지원하지 않는 하네스 대상입니다: {harness_target}",
            http_status=422,
            param="harness",
        )

    planned_files: list[str] = []
    entry_points: dict[str, str] = {}
    for base in bases:
        spec = HARNESS_SPECS[base]
        entry_points[base] = f"{spec.entry_root}/ai-dev-execution/SKILL.md"
        for sroot in spec.skill_roots:
            for rel_path, raw_bytes in sorted(bundle_files.items()):
                full_rel = f"{sroot}/ai-dev-execution/{rel_path}"
                if full_rel not in planned_files:
                    planned_files.append(full_rel)
                if apply:
                    dest = _safe_join(resolved_root, full_rel)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(raw_bytes)
        if mcp_servers:
            for mcp_rel in _render_mcp_for_backend(resolved_root, base, mcp_servers, apply=apply):
                if mcp_rel not in planned_files:
                    planned_files.append(mcp_rel)

    plugin_root_rel = ".harness/plugins/dreampia_ai_dev_execution"
    plugin_data_rel = ".harness/plugin-data/dreampia_ai_dev_execution"
    if include_plugin:
        plugin_obj = export_router_plugin(source, mcp_servers=mcp_servers)
        for fitem in plugin_obj["files"]:  # type: ignore[index]
            fdict: dict[str, str] = fitem  # type: ignore[assignment]
            prel = f"{plugin_root_rel}/{fdict['path']}"
            planned_files.append(prel)
            if apply:
                dest = _safe_join(resolved_root, prel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if "content_b64" in fdict:
                    dest.write_bytes(base64.b64decode(fdict["content_b64"]))
                else:
                    dest.write_text(fdict["content"], encoding="utf-8")
                if any(pat.match(fdict["path"]) for pat in _PLUGIN_EXEC_PATTERNS):
                    dest.chmod(0o755)
        if apply:
            data_dir = _safe_join(resolved_root, plugin_data_rel)
            data_dir.mkdir(parents=True, exist_ok=True)

    ledger_rel = f"{ROUTER_STATE_DIR}/materialized-ledger.json"
    if apply:
        route_planner.ensure_local_git_exclude(resolved_root)
        ledger_path = _safe_join(resolved_root, ledger_rel)
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_doc = {
            "schema_version": 1,
            "router_version": ROUTER_VERSION,
            "package_version": version,
            "targets": list(bases),
            "entry_points": entry_points,
            "files_count": len(planned_files),
        }
        ledger_path.write_text(json.dumps(ledger_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "action": "router-materialize",
        "status": "PASS",
        "applied": apply,
        "targets": list(bases),
        "entry_points": entry_points,
        "plugin_root": plugin_root_rel if include_plugin else None,
        "plugin_data": plugin_data_rel if include_plugin else None,
        "files_count": len(planned_files),
        "sample_files": planned_files[:12],
    }


def build_plugin_stdio_launchers(
    root: Path,
    plugin_name: str,
    stdio_servers: list[dict[str, object]],
) -> list[dict[str, object]]:
    """플러그인 실행 경계 규격에 맞춰 PLUGIN_ROOT와 PLUGIN_DATA를 주입·치환하는 안전한 실행 브릿지를 생성한다."""
    resolved_root = root.resolve()
    safe_plugin = _MCP_NAME_RE.sub("_", plugin_name).strip("_")
    if not safe_plugin:
        return []
    plugin_root = _safe_join(resolved_root, f".harness/plugins/{safe_plugin}")
    plugin_data = _safe_join(resolved_root, f".harness/plugin-data/{safe_plugin}")
    if not plugin_root.is_dir():
        return []
    plugin_data.mkdir(parents=True, exist_ok=True)

    launchers: list[dict[str, object]] = []
    for srv in stdio_servers:
        raw_name = str(srv.get("name") or "").strip()
        safe_srv = _MCP_NAME_RE.sub("_", raw_name).strip("_")
        cmd = str(srv.get("command") or "").strip()
        if not safe_srv or not cmd:
            continue
        if cmd.startswith("./"):
            cmd_path = (plugin_root / cmd[2:]).resolve()
            try:
                cmd_path.relative_to(plugin_root.resolve())
            except ValueError:
                continue
            if cmd_path.is_file():
                cmd_path.chmod(0o755)
            resolved_cmd = str(cmd_path)
        elif "/" in cmd or "\\" in cmd:
            continue
        else:
            resolved_cmd = cmd

        def _expand(val: str) -> str:
            return val.replace("${PLUGIN_ROOT}", str(plugin_root)).replace("${PLUGIN_DATA}", str(plugin_data))

        raw_cwd = str(srv.get("cwd") or "").strip()
        if raw_cwd:
            expanded_cwd = Path(_expand(raw_cwd)).resolve()
            in_root = False
            for allowed_base in (plugin_root.resolve(), plugin_data.resolve()):
                try:
                    expanded_cwd.relative_to(allowed_base)
                    in_root = True
                    break
                except ValueError:
                    pass
            if not in_root:
                continue
            expanded_cwd.mkdir(parents=True, exist_ok=True)
            work_cwd = str(expanded_cwd)
        else:
            work_cwd = str(plugin_root)

        raw_args = srv.get("args")
        expanded_args = [_expand(str(a)) for a in raw_args] if isinstance(raw_args, list) else []

        env_lines = [
            f"export PLUGIN_ROOT={json.dumps(str(plugin_root))}",
            f"export PLUGIN_DATA={json.dumps(str(plugin_data))}",
        ]
        raw_env = srv.get("env")
        if isinstance(raw_env, dict):
            for k, v in sorted(raw_env.items()):
                k_str = str(k).strip()
                if k_str.upper() in ("PLUGIN_ROOT", "PLUGIN_DATA") or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k_str):
                    continue
                env_lines.append(f"export {k_str}={json.dumps(_expand(str(v)))}")

        launcher_path = plugin_data / f"dreampia_bridge_{safe_srv}.sh"
        script = (
            "#!/bin/sh\n"
            + "\n".join(env_lines)
            + f"\ncd {json.dumps(work_cwd)} || exit 1\n"
            + f"exec {json.dumps(resolved_cmd)} \"$@\"\n"
        )
        launcher_path.write_text(script, encoding="utf-8")
        launcher_path.chmod(0o755)
        launchers.append(
            {
                "name": safe_srv,
                "plugin": plugin_name,
                "command": str(launcher_path),
                "args": expanded_args,
            }
        )
    return launchers


def _extract_input_text(input_val: object) -> str:
    """요청 input(문자열 또는 메시지 배열)에서 작업 지시 텍스트를 추출한다."""
    if isinstance(input_val, str):
        return input_val.strip()
    if isinstance(input_val, list):
        parts: list[str] = []
        for item in input_val:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            parts.append(block["text"])
        return "\n".join(p.strip() for p in parts if p.strip())
    raise RouterError("invalid_input", "input 필드는 비어 있지 않은 문자열이거나 메시지 배열이어야 합니다.", param="input")


def _load_router_store(root: Path) -> dict[str, dict[str, object]]:
    store_path = _safe_join(root, f"{ROUTER_STATE_DIR}/sessions.json")
    if not store_path.is_file():
        return {"sessions": {}, "responses": {}}
    data = json.loads(store_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"sessions": {}, "responses": {}}
    return {
        "sessions": dict(data.get("sessions") or {}),
        "responses": dict(data.get("responses") or {}),
    }


def _save_router_store(root: Path, store: dict[str, dict[str, object]]) -> None:
    store_path = _safe_join(root, f"{ROUTER_STATE_DIR}/sessions.json")
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_harness_cli_argv(
    base: str,
    prompt: str,
    *,
    model: str | None = None,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    sandbox: str = "workspace-write",
    executable: str | None = None,
) -> list[str]:
    """각 하네스 호스트(codex, claude, gemini, opencode, dsh, qwen, aider, goose, hermes, pi, local)의 표준 비대화형 실행 명령줄(argv)을 생성한다."""
    if base not in HARNESS_SPECS:
        raise RouterError("unsupported_base", f"지원하지 않는 하네스 백엔드입니다: {base}", http_status=422)
    spec = HARNESS_SPECS[base]
    exe = executable or (spec.executables[0] if spec.executables else base)
    eff_model = model or spec.default_model
    norm_effort = str(normalize_reasoning_effort(eff_model, reasoning_effort)["effective_effort"])

    if base == "codex":
        argv = [exe, "exec", "--full-auto", "-s", sandbox, "-m", eff_model]
        if norm_effort != "default":
            argv.extend(["-c", f'model_reasoning_effort="{norm_effort}"'])
        argv.append(prompt)
        return argv
    if base == "claude":
        argv = [exe, "-p", prompt, "--model", eff_model, "--output-format", "json"]
        if norm_effort in ("low", "medium", "high"):
            argv.extend(["--effort", norm_effort])
        return argv
    if base == "gemini":
        return [exe, "-p", prompt, "-m", eff_model, "--output-format", "json"]
    if base == "opencode":
        return [exe, "run", "-m", eff_model, prompt]
    if base == "dsh":
        return [exe, "run", "--model", eff_model, prompt]
    if base == "qwen":
        return [exe, "-p", prompt, "-m", eff_model]
    if base == "aider":
        return [exe, "--yes-always", "--no-auto-commits", "--model", eff_model, "--message", prompt]
    if base == "goose":
        return [exe, "run", "--text", prompt]
    if base == "hermes":
        return [exe, "run", "--prompt", prompt]
    if base == "pi":
        return [exe, "-p", prompt]
    return ["python3", "-m", "harness.team_cli", "route-plan", "--project", ".", "--goal", prompt]


def dispatch_router_task(
    root: Path,
    request_body: dict[str, object],
    *,
    executor_argv: list[str] | None = None,
    allow_live: bool = False,
    extra_secrets: tuple[str, ...] = (),
) -> dict[str, object]:
    """요청을 라우팅·실행하고 세션 연속성, 모델 대체, 산출물 컨테이너를 기록한다."""
    if root.is_symlink() or not root.is_dir():
        raise RouterError("invalid_input", "유효한 프로젝트 루트 디렉터리가 필요합니다.")
    resolved_root = root.resolve()
    if not isinstance(request_body, dict):
        raise RouterError("invalid_input", "요청 본문은 JSON 객체여야 합니다.")

    known_fields = {
        "input",
        "model",
        "metadata",
        "stream",
        "previous_response_id",
        "instructions",
        "store",
        "max_output_tokens",
        "max_step",
        "timeout_seconds",
        "environment",
        "tools",
        "include",
        "background",
        "reasoning_effort",
    }
    ignored_fields: list[str] = []
    for k in sorted(request_body.keys()):
        if k in ("tools", "include") or k not in known_fields:
            ignored_fields.append(k)

    input_text = _extract_input_text(request_body.get("input"))
    if not input_text:
        raise RouterError("invalid_input", "input 텍스트가 비어 있습니다.", param="input")

    metadata_in = request_body.get("metadata")
    if metadata_in is not None and not isinstance(metadata_in, dict):
        raise RouterError("invalid_input", "metadata는 객체여야 합니다.", param="metadata")
    meta_dict: dict[str, object] = dict(metadata_in) if isinstance(metadata_in, dict) else {}

    requested_harness_id = str(meta_dict.get("harness_id") or "").strip()
    store = _load_router_store(resolved_root)
    prev_resp_id = request_body.get("previous_response_id")
    session_id: str
    turn_index = 1

    if prev_resp_id is not None:
        if not isinstance(prev_resp_id, str) or prev_resp_id not in store["responses"]:
            raise RouterError(
                "response_not_found",
                f"이전 응답 ID를 찾을 수 없습니다: {prev_resp_id}",
                http_status=404,
                param="previous_response_id",
            )
        prev_resp = store["responses"][prev_resp_id]
        session_id = str(prev_resp["session_id"])
        prev_harness_id = str(prev_resp["harness_id"])
        if requested_harness_id and requested_harness_id != prev_harness_id:
            raise RouterError(
                "harness_mismatch",
                f"세션의 하네스({prev_harness_id})와 요청된 하네스({requested_harness_id})가 일치하지 않습니다.",
                http_status=409,
                param="metadata.harness_id",
            )
        requested_harness_id = prev_harness_id
        sess_obj = store["sessions"].get(session_id, {})
        turn_index = int(sess_obj.get("turns", 1)) + 1
    else:
        session_id = f"dp_sess_{uuid.uuid4().hex[:24]}"

    if not requested_harness_id or requested_harness_id == "auto":
        selected_base = "local"
        effective_harness_id = "dp_node_local"
    else:
        normalized_hid = requested_harness_id
        if normalized_hid.startswith("dp_node_"):
            candidate_base = normalized_hid[len("dp_node_") :]
        else:
            candidate_base = normalized_hid
        if candidate_base not in HARNESS_SPECS:
            raise RouterError(
                "harness_not_found",
                f"등록되지 않은 하네스 ID입니다: {requested_harness_id}",
                http_status=404,
                param="metadata.harness_id",
            )
        selected_base = candidate_base
        effective_harness_id = f"dp_node_{selected_base}"

    spec = HARNESS_SPECS[selected_base]
    route_decision = route_planner.plan_route(input_text, root=resolved_root)

    requested_model = str(request_body.get("model") or "").strip()
    effective_model = spec.default_model
    model_fallback = False
    model_fallback_reason: str | None = None
    if requested_model and requested_model != effective_model:
        model_fallback = True
        model_fallback_reason = (
            f"요청된 모델 '{requested_model}' 대신 하네스 기본 승인 모델 '{effective_model}'로 대체되었습니다."
        )

    reasoning_info = normalize_reasoning_effort(
        effective_model,
        str(request_body.get("reasoning_effort") or DEFAULT_REASONING_EFFORT),
    )

    planned_argv = build_harness_cli_argv(
        selected_base,
        input_text,
        model=effective_model,
        reasoning_effort=str(reasoning_info["effective_effort"]),
    )
    active_argv = executor_argv
    if active_argv is None and allow_live and selected_base != "local":
        found_exe: str | None = None
        for exe_cand in spec.executables:
            resolved_exe = shutil.which(exe_cand)
            if resolved_exe:
                found_exe = resolved_exe
                break
        if found_exe:
            active_argv = build_harness_cli_argv(
                selected_base,
                input_text,
                model=effective_model,
                reasoning_effort=str(reasoning_info["effective_effort"]),
                executable=found_exe,
            )

    before_inv = write_boundary.capture_inventory(resolved_root)
    response_id = f"dp_exec_{uuid.uuid4().hex[:24]}"
    container_id = f"dp_box_{session_id[8:]}"
    created_at = int(time.time())

    status = "completed"
    error_obj: dict[str, object] | None = None
    output_text = ""

    if route_decision.goal_kind == "unsupported":
        status = "failed"
        error_obj = {
            "type": "harness_error",
            "code": "harness_error",
            "message": route_decision.message_ko,
        }
        output_text = route_decision.message_ko
    elif active_argv:
        timeout_sec = float(request_body.get("timeout_seconds") or 60.0)
        env = {
            **os.environ,
            "DREAMPIA_SESSION_ID": session_id,
            "DREAMPIA_RESPONSE_ID": response_id,
            "DREAMPIA_HARNESS_BASE": selected_base,
            "DREAMPIA_PROFILE": route_decision.profile,
        }
        cap = process.capture(active_argv, env, timeout_sec, cwd=resolved_root)
        raw_stdout = cap["stdout"].decode("utf-8", errors="replace").strip()
        raw_stderr = cap["stderr"].decode("utf-8", errors="replace").strip()
        output_text = redact_secrets(raw_stdout or raw_stderr, extra_secrets=extra_secrets)
        if cap["reason"] == "TIMEOUT":
            status = "incomplete"
            error_obj = {"type": "harness_error", "code": "timeout", "message": "작업 시간 한도를 초과했습니다."}
        elif cap["exit_code"] != 0:
            status = "failed"
            error_obj = {
                "type": "harness_error",
                "code": "harness_error",
                "message": redact_secrets(raw_stderr or "하네스 실행이 0이 아닌 종료 코드로 실패했습니다.", extra_secrets),
            }
    else:
        output_text = redact_secrets(
            json.dumps(
                {
                    "routed_harness": effective_harness_id,
                    "base": selected_base,
                    "turn": turn_index,
                    "route": route_decision.to_dict(),
                    "reasoning": reasoning_info,
                    "planned_cli_argv": planned_argv,
                },
                ensure_ascii=False,
            ),
            extra_secrets=extra_secrets,
        )

    after_inv = write_boundary.capture_inventory(resolved_root)
    excluded_prefixes = (".harness/", ".dreampia-install/", ".git/", ".agents/", ".claude/", ".gemini/", ".qwen/")
    artifacts: list[dict[str, object]] = []
    for rel_path, entry in sorted(after_inv.items()):
        if any(rel_path.startswith(pfx) for pfx in excluded_prefixes):
            continue
        if before_inv.get(rel_path) != entry and entry.get("kind") == "regular":
            file_id = "dp_art_" + hashlib.sha256(f"{session_id}:{rel_path}".encode("utf-8")).hexdigest()[:24]
            artifacts.append(
                {
                    "id": file_id,
                    "object": "file",
                    "filename": rel_path,
                    "bytes": entry.get("size", 0),
                    "sha256": entry.get("sha256", ""),
                    "container_id": container_id,
                }
            )

    response_metadata: dict[str, object] = {
        **meta_dict,
        "harness_id": effective_harness_id,
        "harness_base": selected_base,
        "session_id": session_id,
        "container_id": container_id,
        "turn": turn_index,
        "route_profile": route_decision.profile,
        "goal_kind": route_decision.goal_kind,
        "risk_level": route_decision.risk_level,
        "required_roles": list(route_decision.roles),
        "required_gates": list(route_decision.required_gates),
        "reasoning_effort": reasoning_info["effective_effort"],
        "planned_cli_argv": planned_argv,
    }
    if requested_model:
        response_metadata["requested_model"] = requested_model
    if model_fallback:
        response_metadata["model_fallback"] = True
        response_metadata["model_fallback_reason"] = model_fallback_reason
    if ignored_fields:
        response_metadata["ignored_fields"] = ignored_fields

    response_obj: dict[str, object] = {
        "id": response_id,
        "object": "response",
        "created_at": created_at,
        "status": status,
        "model": effective_model,
        "previous_response_id": prev_resp_id,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": output_text}],
            }
        ],
        "artifacts": artifacts,
        "error": error_obj,
        "metadata": response_metadata,
    }

    if request_body.get("store", True) is not False:
        store["sessions"][session_id] = {
            "id": session_id,
            "object": "session",
            "harness_id": effective_harness_id,
            "container_id": container_id,
            "turns": turn_index,
            "last_response_id": response_id,
            "updated_at": created_at,
        }
        store["responses"][response_id] = {
            "id": response_id,
            "session_id": session_id,
            "harness_id": effective_harness_id,
            "response": response_obj,
        }
        _save_router_store(resolved_root, store)

    return response_obj


def create_router_http_server(
    root: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    *,
    api_key: str | None = None,
) -> ThreadingHTTPServer:
    """표준 라이브러리만으로 동작하는 로컬 루프백 드림피아 라우터 HTTP 서버를 생성한다."""
    resolved_root = root.resolve()

    class RouterRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def _send_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Dreampia-Router-Version", ROUTER_VERSION)
            self.end_headers()
            self.wfile.write(body)

        def _check_auth_and_version(self) -> bool:
            if api_key is not None:
                auth_hdr = self.headers.get("Authorization", "")
                if auth_hdr != f"Bearer {api_key}":
                    err = RouterError(
                        "invalid_credential" if auth_hdr else "missing_credential",
                        "유효한 Bearer 인증 토큰이 필요합니다.",
                        error_type="authentication_error",
                        http_status=401,
                    )
                    self._send_json(401, err.to_envelope())
                    return False
            router_ver = self.headers.get("X-Dreampia-Router-Version")
            if router_ver and router_ver not in SUPPORTED_ROUTER_VERSIONS:
                err = RouterError(
                    "unsupported_protocol_version",
                    f"지원하지 않는 X-Dreampia-Router-Version 헤더입니다: {router_ver}",
                    http_status=400,
                    detail={"supported": list(SUPPORTED_ROUTER_VERSIONS)},
                )
                self._send_json(400, err.to_envelope())
                return False
            return True

        def do_GET(self) -> None:  # noqa: N802
            if not self._check_auth_and_version():
                return
            disc = discover_harnesses(resolved_root)
            if self.path in ("/v1/capabilities", "/v1/discovery"):
                self._send_json(
                    200,
                    {
                        "default_version": disc["default_version"],
                        "versions": disc["versions"],
                        "capabilities": disc["capabilities"],
                        "plugin_schemas": disc["plugin_schemas"],
                    },
                )
                return
            if self.path == "/v1/harnesses":
                self._send_json(200, {"harnesses": disc["harnesses"]})
                return
            if self.path == "/v1/models":
                self._send_json(200, {"backends": disc["backends"]})
                return
            if self.path.startswith("/v1/harnesses/") and self.path.endswith("/plugin"):
                hid = self.path[len("/v1/harnesses/") : -len("/plugin")].strip("/")
                matched = [h for h in disc["harnesses"] if isinstance(h, dict) and h.get("id") == hid]  # type: ignore[union-attr]
                if not matched:
                    err = RouterError("harness_not_found", f"하네스를 찾을 수 없습니다: {hid}", http_status=404)
                    self._send_json(404, err.to_envelope())
                    return
                self._send_json(200, export_router_plugin(PACKAGE_ROOT))
                return
            if self.path.startswith("/v1/responses/"):
                rid = self.path[len("/v1/responses/") :].strip("/")
                store = _load_router_store(resolved_root)
                if rid not in store["responses"]:
                    err = RouterError("response_not_found", f"응답을 찾을 수 없습니다: {rid}", http_status=404)
                    self._send_json(404, err.to_envelope())
                    return
                self._send_json(200, store["responses"][rid]["response"])  # type: ignore[arg-type]
                return
            err = RouterError("invalid_input", f"지원하지 않는 엔드포인트입니다: {self.path}", http_status=404)
            self._send_json(404, err.to_envelope())

        def do_POST(self) -> None:  # noqa: N802
            if not self._check_auth_and_version():
                return
            if self.path == "/v1/responses":
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                    resp = dispatch_router_task(resolved_root, payload)
                    self._send_json(200, resp)
                except RouterError as exc:
                    self._send_json(exc.http_status, exc.to_envelope())
                except (ValueError, TypeError) as exc:
                    err = RouterError("invalid_input", str(exc), http_status=400)
                    self._send_json(400, err.to_envelope())
                return
            err = RouterError("invalid_input", f"지원하지 않는 POST 경로입니다: {self.path}", http_status=404)
            self._send_json(404, err.to_envelope())

    return ThreadingHTTPServer((host, port), RouterRequestHandler)


def _is_reparse_or_symlink(path: Path) -> bool:
    """심볼릭 링크 또는 Windows 정션(Junction/Reparse Point) 여부를 안전하게 판별한다."""
    if path.is_symlink() or os.path.islink(str(path)):
        return True
    is_junc = getattr(os.path, "isjunction", None)
    if callable(is_junc) and bool(is_junc(str(path))):
        return True
    return False


def _safe_rmtree_without_following_junctions(target: Path) -> None:
    """Windows 정션이나 심볼릭 링크를 따라가지 않고 대상 작업 트리 폴더만 안전하게 제거한다."""
    if not target.exists() and not _is_reparse_or_symlink(target):
        return
    if _is_reparse_or_symlink(target):
        try:
            target.unlink()
        except OSError:
            try:
                os.rmdir(str(target))
            except OSError:
                pass
        return

    for cur_root, dirs, _ in os.walk(str(target), topdown=True, followlinks=False):
        retained_dirs: list[str] = []
        for d in dirs:
            d_path = Path(cur_root) / d
            if _is_reparse_or_symlink(d_path):
                try:
                    os.rmdir(str(d_path))
                except OSError:
                    try:
                        d_path.unlink()
                    except OSError:
                        pass
            else:
                retained_dirs.append(d)
        dirs[:] = retained_dirs

    shutil.rmtree(target, ignore_errors=True)


def plan_or_manage_squad_worktrees(
    root: Path,
    goal: str = "",
    *,
    mode: str = "plan",
    apply: bool = False,
) -> dict[str, object]:
    """GuildMaster & Paladin/Archer/Inquisitor 병렬 길드 파티 Git Worktree 오케스트레이터: 길드원별 물리적 격리 던전 인스턴스(.dreampia/worktrees/*)를 계획·생성·정리한다."""
    import subprocess

    if root.is_symlink() or not root.is_dir():
        raise RouterError("invalid_project_root", "유효하지 않은 프로젝트 디렉터리입니다.")
    resolved = root.resolve()
    eff_goal = goal.strip() or "ulw 병렬 스쿼드 기능 구현 및 검증"
    decision = route_planner.plan_route(eff_goal, root=resolved)

    state_dir = route_planner.resolve_skill_state_dir(resolved)
    worktree_base_rel = f"{state_dir}/worktrees"
    worktree_base = resolved / worktree_base_rel
    git_bin = shutil.which("git")
    is_git_repo = (resolved / ".git").exists()

    track_specs = (
        {
            "track_id": "paladin-executor",
            "callsign": "Paladin",
            "role": "executor",
            "title_ko": "성기사 · 핵심 비즈니스 로직·API·백엔드 TDD 구현 트랙",
            "branch": "dreampia/squad-paladin",
            "worktree_rel": f"{worktree_base_rel}/paladin-executor",
            "owned_paths": ["src/", "implementation/", "harness/"],
        },
        {
            "track_id": "archer-ui",
            "callsign": "Archer",
            "role": "design-critic",
            "title_ko": "궁수 · UI/UX 화면·반응형 레이아웃·버튼/아이콘 규격 구현 트랙",
            "branch": "dreampia/squad-archer",
            "worktree_rel": f"{worktree_base_rel}/archer-ui",
            "owned_paths": ["app/", "components/", "docs/02_IA_UX.md"],
        },
        {
            "track_id": "inquisitor-test",
            "callsign": "Inquisitor",
            "role": "reviewer",
            "title_ko": "심판관 · 적대적 엣지케이스·통합 TDD 테스트 및 정적 감사 트랙",
            "branch": "dreampia/squad-inquisitor",
            "worktree_rel": f"{worktree_base_rel}/inquisitor-test",
            "owned_paths": ["tests/", "harness/tests/", "docs/06_TEST_PLAN.md"],
        },
    )

    norm_mode = mode.strip().lower() if mode else "plan"
    if norm_mode not in ("plan", "create", "cleanup"):
        norm_mode = "plan"

    tracks_out: list[dict[str, object]] = []

    if norm_mode == "cleanup":
        removed_tracks: list[str] = []
        if apply and worktree_base.exists():
            for spec in track_specs:
                wt_path = resolved / str(spec["worktree_rel"])
                if is_git_repo and git_bin and wt_path.exists() and not _is_reparse_or_symlink(wt_path):
                    subprocess.run(
                        [git_bin, "worktree", "remove", str(wt_path)],
                        cwd=str(resolved),
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                if wt_path.exists() or _is_reparse_or_symlink(wt_path):
                    _safe_rmtree_without_following_junctions(wt_path)
                removed_tracks.append(str(spec["track_id"]))
            if is_git_repo and git_bin:
                subprocess.run(
                    [git_bin, "worktree", "prune"],
                    cwd=str(resolved),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            _safe_rmtree_without_following_junctions(worktree_base)
        return {
            "action": "squad-worktree",
            "status": "PASS",
            "mode": "cleanup",
            "applied": apply,
            "removed_tracks": removed_tracks,
            "message_ko": (
                f"병렬 길드 파티 Worktree({len(removed_tracks)}개 트랙)가 안전하게 정리(cleanup)되었습니다."
                if apply
                else "[미리보기] 병렬 길드 파티 Worktree 정리 계획입니다. 실제 삭제하려면 --apply를 추가하십시오."
            ),
        }

    for spec in track_specs:
        tid = str(spec["track_id"])
        branch = str(spec["branch"])
        wt_rel = str(spec["worktree_rel"])
        wt_abs = resolved / wt_rel
        git_cmd = f"git worktree add -b {branch} {wt_rel} HEAD"
        track_status = "PLANNED"

        if apply:
            wt_abs.parent.mkdir(parents=True, exist_ok=True)
            if wt_abs.exists():
                track_status = "WORKTREE_REUSED"
            elif is_git_repo and git_bin:
                ref_check = subprocess.run(
                    [git_bin, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                    cwd=str(resolved),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                wt_argv = (
                    [git_bin, "worktree", "add", str(wt_abs), branch]
                    if ref_check.returncode == 0
                    else [git_bin, "worktree", "add", "-b", branch, str(wt_abs), "HEAD"]
                )
                proc = subprocess.run(
                    wt_argv,
                    cwd=str(resolved),
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                if proc.returncode == 0:
                    track_status = "WORKTREE_CREATED"
                else:
                    wt_abs.mkdir(parents=True, exist_ok=True)
                    track_status = "ISOLATED_DIR_CREATED"
            else:
                wt_abs.mkdir(parents=True, exist_ok=True)
                track_status = "ISOLATED_DIR_CREATED"

        tracks_out.append(
            {
                "track_id": tid,
                "callsign": spec["callsign"],
                "role": spec["role"],
                "title_ko": spec["title_ko"],
                "branch": branch,
                "worktree_path": wt_rel,
                "owned_paths": spec["owned_paths"],
                "git_command": git_cmd,
                "status": track_status,
            }
        )

    manifest_rel = f"{worktree_base_rel}/manifest.json"
    if apply:
        route_planner.ensure_local_git_exclude(resolved)
        worktree_base.mkdir(parents=True, exist_ok=True)
        manifest_doc = {
            "schema_version": 1,
            "router_version": ROUTER_VERSION,
            "goal": eff_goal,
            "profile": decision.profile,
            "is_git_repo": is_git_repo,
            "tracks": tracks_out,
        }
        (resolved / manifest_rel).write_text(
            json.dumps(manifest_doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "action": "squad-worktree",
        "status": "PASS",
        "mode": norm_mode,
        "applied": apply,
        "goal": eff_goal,
        "profile": decision.profile,
        "is_git_repo": is_git_repo,
        "manifest_path": manifest_rel if apply else None,
        "tracks_count": len(tracks_out),
        "tracks": tracks_out,
        "merge_gate_ko": "전 트랙이 독립 Worktree에서 구현 완료 후 Cleric의 autopilot-gate PASS 시 메인 브랜치로 병합(Merge)합니다.",
        "message_ko": (
            f"병렬 길드 파티 격리 Worktree {len(tracks_out)}개 트랙(Paladin·Archer·Inquisitor)이 생성되었습니다."
            if apply
            else f"[미리보기] 병렬 길드 파티 격리 Worktree {len(tracks_out)}개 트랙(Paladin·Archer·Inquisitor) 구성 계획입니다. 실제 생성하려면 --apply를 추가하십시오."
        ),
    }



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dreampia Universal Harness Router"
    )
    parser.add_argument(
        "action",
        choices=("discover", "materialize", "export-plugin", "dispatch"),
        help="라우터 실행 동작",
    )
    parser.add_argument("--project", required=True, help="대상 프로젝트 루트 경로")
    parser.add_argument("--harness", default="all", help="대상 하네스 백엔드 (codex, claude, gemini, opencode, dsh, all 등)")
    parser.add_argument("--apply", action="store_true", help="미리보기가 아닌 실제 파일 기록 수행")
    parser.add_argument("--input", default="", help="dispatch 실행 시 작업 지시문")
    parser.add_argument("--model", default="", help="dispatch 실행 시 요청 모델 ID")
    parser.add_argument("--previous-response-id", default=None, help="연속 세션을 위한 이전 응답 ID")
    args = parser.parse_args(argv)

    try:
        root = Path(args.project).resolve()
        if args.action == "discover":
            out = discover_harnesses(root)
        elif args.action == "materialize":
            out = materialize_harness(root, args.harness, apply=args.apply)
        elif args.action == "export-plugin":
            out = export_router_plugin(PACKAGE_ROOT)
        else:
            req: dict[str, object] = {
                "input": args.input,
                "metadata": {"harness_id": args.harness if args.harness != "all" else "auto"},
            }
            if args.model:
                req["model"] = args.model
            if args.previous_response_id:
                req["previous_response_id"] = args.previous_response_id
            out = dispatch_router_task(root, req)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("status") != "failed" else 1
    except RouterError as exc:
        print(json.dumps(exc.to_envelope(), ensure_ascii=False, indent=2))
        return 2
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": {"code": "ROUTER_ERROR", "message": str(exc)}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

