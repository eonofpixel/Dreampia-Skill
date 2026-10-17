"""Dreampia Standard Library MCP (Model Context Protocol) JSON-RPC 2.0 Server.

Provides zero-dependency STDIO MCP tool & resource serving so any MCP-capable host
(Antigravity, Claude Code, Codex, Gemini CLI, Cursor, OpenCode) can invoke Dreampia's
route planner, cleanroom reconstruction engine, visual acceptance verifier, and gates.

SOLID Architecture:
- McpToolDefinition: Single-responsibility immutable schema descriptor for each MCP tool
- McpToolExecutor: Single-responsibility adapter mapping MCP tool calls to Dreampia engines
- McpProtocolHandler: Open-closed JSON-RPC 2.0 protocol dispatcher (initialize, tools/list, tools/call, resources/list, resources/read, ping)
- StdioMcpTransport: Dual-framing STDIO transport supporting both newline-delimited JSON-RPC and Content-Length framed streams
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
from pathlib import Path
import sys
from typing import BinaryIO, Callable

try:
    from . import reconstruct_engine, route_planner, team_cli, universal_router, visual_acceptance, write_boundary
except ImportError:
    import reconstruct_engine  # type: ignore[no-redef]
    import route_planner  # type: ignore[no-redef]
    import team_cli  # type: ignore[no-redef]
    import universal_router  # type: ignore[no-redef]
    import visual_acceptance  # type: ignore[no-redef]
    import write_boundary  # type: ignore[no-redef]

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "dreampia-skill-mcp"
SERVER_VERSION = "0.7.0"


@dataclass(frozen=True)
class McpToolDefinition:
    """MCP 도구 메타데이터 및 입력 JSON 스키마 정의."""

    name: str
    description: str
    input_schema: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


MCP_TOOLS: tuple[McpToolDefinition, ...] = (
    McpToolDefinition(
        name="dreampia_route_plan",
        description="자연어 목표(한글/영문)를 분석하여 최적 실행 프로필(tiny-fix/standard/complex/cleanroom/visual-ui), 필수 역할, 검증 게이트를 결정론적으로 산출합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로 (생략 시 기본 프로젝트 루트 사용)"},
                "goal": {"type": "string", "description": "수행할 작업 목표 설명"},
            },
            "required": ["goal"],
        },
    ),
    McpToolDefinition(
        name="dreampia_reconstruct_inspect",
        description="네이티브 바이너리(PE, ELF, Mach-O, WASM), 패키지 아카이브(ASAR, APK/ZIP), 또는 소스 디렉터리의 구조와 공개 표면(심볼, 라우트, IPC)을 초고속으로 정적 분석합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "target": {"type": "string", "description": "프로젝트 내 분석 대상 파일 또는 디렉터리 상대 경로"},
            },
            "required": ["target"],
        },
    ),
    McpToolDefinition(
        name="dreampia_reconstruct_ledger",
        description="참조/오염 영역(contaminated-zone)에서 클린룸 재구축 의무 원장(Obligation Ledger)을 도출하고 선택적으로 evidence/reconstruction-ledger.json에 기록합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "source": {"type": "string", "description": "참조 아티팩트 또는 디렉터리 상대 경로 (예: contaminated-zone)"},
                "apply": {"type": "boolean", "description": "true 지정 시 evidence/reconstruction-ledger.json 파일로 저장"},
            },
            "required": ["source"],
        },
    ),
    McpToolDefinition(
        name="dreampia_reconstruct_verify",
        description="재구축 의무 원장(Obligation Ledger) 대비 구현체(implementation)의 100% 커버리지 달성 여부와 클린룸 3-영역 오염 분리 경계를 Fail-Closed 방식으로 검증합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "candidate": {"type": "string", "description": "검증할 구현 디렉터리 상대 경로 (기본값: implementation)"},
                "ledger": {"type": "string", "description": "원장 파일 상대 경로 (기본값: evidence/reconstruction-ledger.json)"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_reconstruct_compare",
        description="원본 아티팩트와 재구축 대상 간의 공개 심볼·API 라우트·IPC 채널 표면 일치율(Parity Ratio)과 누락 항목을 비교합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "source": {"type": "string", "description": "원본 참조 경로"},
                "candidate": {"type": "string", "description": "재구축 대상 경로"},
            },
            "required": ["source", "candidate"],
        },
    ),
    McpToolDefinition(
        name="dreampia_visual_check",
        description="UI 시각 수용 매니페스트 또는 기준/후보 PNG 스크린샷의 해상도, 뷰포트 예산, 픽셀 차이율을 검증합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "manifest": {"type": "string", "description": "시각 수용 매니페스트 상대 경로"},
                "baseline": {"type": "string", "description": "기준 PNG 상대 경로"},
                "candidate": {"type": "string", "description": "후보 PNG 상대 경로"},
                "max_diff_ratio": {"type": "number", "description": "허용 최대 픽셀 변경 비율 (0.0 ~ 1.0)"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_verify_gate",
        description="드림피아 개발 단계별 품질 게이트(before-dev-start, before-claim-complete, before-client-send, app-static, ui-evidence) 통과 여부를 검증합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "gate": {
                    "type": "string",
                    "enum": list(team_cli.VERIFY_GATES),
                    "description": "검증할 게이트 이름",
                },
            },
            "required": ["gate"],
        },
    ),
    McpToolDefinition(
        name="dreampia_router_discover",
        description="현재 시스템과 프로젝트에서 사용 가능한 멀티 에이전트 하네스 노드(Codex, Claude, Gemini, OpenCode 등) 및 스킬 설치 상태를 탐색합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_sdd_ledger",
        description="프로젝트의 SDD 명세서(PRD-R*, REQ-*, API-*, UX-S*)와 TDD 작업·테스트(TASK-*, TEST-*) 추적 원장을 생성하고 선택적으로 evidence/sdd-ledger.json에 저장합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "apply": {"type": "boolean", "description": "true 지정 시 evidence/sdd-ledger.json 파일로 저장"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_sdd_check",
        description="SDD 명세 주도 개발 요구사항-작업-TDD 테스트 추적률, 고아 요구사항(Orphan Spec), 명세 변경 드리프트(STALE), 실제 테스트 코드 존재 여부를 Fail-Closed로 검증합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "ledger": {"type": "string", "description": "기준 SDD 원장 상대 경로 (기본값: evidence/sdd-ledger.json)"},
                "allow_doc_only": {"type": "boolean", "description": "문서 전용 단계에서 실제 테스트 코드 파일 필수 검사를 생략할지 여부"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_audit_code",
        description="Trinity(QA/감사) 정적 AST 및 코드 규칙 감사기: 가짜 TDD 테스트(assert True 등), any 타입 사용, 반환 타입 누락, 비표준 아이콘 import, 버튼 bg-transparent 누락을 Fail-Closed로 감사하고 선택적으로 evidence/code-audit.json에 저장합니다 (changed_only 지정 시 Git 변경 파일만 증분 감사).",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "check_ui_rules": {"type": "boolean", "description": "선택적: 기본 UI 규칙(bg-transparent, lucide-react) 검사 여부 (생략 시 프로젝트 설정 따름)"},
                "changed_only": {"type": "boolean", "description": "true 지정 시 Git 변경·신규 파일만 증분 감사하여 레거시 기술 부채와 분리"},
                "base_ref": {"type": "string", "description": "changed_only 기준 Git 커밋/브랜치 참조 (기본값 HEAD)"},
                "apply": {"type": "boolean", "description": "true 지정 시 evidence/code-audit.json 파일로 저장"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_context_pack",
        description="장기 세션 문맥 망각(Context Rot) 방지를 위해 활성 SDD 요구사항, 미완료 작업, ADR/RISK 불변 조건을 초압축 브리핑 패킷(evidence/context-pack.json)으로 컴파일합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "apply": {"type": "boolean", "description": "기본값 true (evidence/context-pack.json 저장)"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_golden_io",
        description="클린룸 역공학/재구축 시 approved-spec/golden-io.json의 입출력 벡터를 기반으로 구현체(implementation)의 블랙박스 동치성을 검증합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "spec": {"type": "string", "description": "골든 입출력 명세 파일 상대 경로 (기본값: approved-spec/golden-io.json)"},
                "apply": {"type": "boolean", "description": "true 지정 시 evidence/golden-io-verification.json 파일로 저장"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_autopilot_gate",
        description="Morpheus & Tank 통합 자율 완주 게이트: 지침 동기화, SDD+TDD 추적성(Adaptive Nano 티어 지원), Trinity 코드 감사(증분 감사 지원), 다중 검증 명령(verify_cmd/verify_commands), 클린룸/Golden I/O/시각 수용 검증을 단일 파이프라인으로 실행하고 변조 방지 판정서(evidence/autopilot-verdict.json)를 발급합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "goal": {"type": "string", "description": "작업 목표 설명 (작업 규모별 nano/standard/full 탄력 티어 판정에 사용)"},
                "allow_doc_only": {"type": "boolean", "description": "문서 전용 단계에서 실제 테스트 코드 파일 필수 검사를 생략할지 여부"},
                "changed_only": {"type": "boolean", "description": "true 지정 시 코드 감사를 Git 변경 파일로만 한정"},
                "base_ref": {"type": "string", "description": "changed_only 기준 Git 참조 (기본값 HEAD)"},
                "verify_cmd": {"type": "string", "description": "실행할 검증 명령 문자열 ('&&' 또는 ';' 체이닝 및 JSON 배열 문자열 지원)"},
                "verify_commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "순차 실행할 다중 검증 명령 배열 (예: ['node tools/inventory-check.mjs', 'node native/windows/ai-control-test.mjs'])",
                },
                "apply": {"type": "boolean", "description": "기본값 true (evidence/autopilot-verdict.json 저장)"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_blast_radius",
        description="Architect & Tank 폭발 반경(Blast Radius) 분석기: 변경 대상 파일의 심볼 의존성(1-Hop/2-Hop), 시스템 경계(API/DB/직렬화/CLI/보안) 교차 여부, 5단계 안전 증명 등급을 산출합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "target": {"type": "string", "description": "쉼표로 구분된 분석 대상 상대 경로 목록"},
                "apply": {"type": "boolean", "description": "true 지정 시 evidence/blast-radius-report.json 저장"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_metric_climb",
        description="Dreampia 자율 지표 등반(Metric Climb) 엔진: 불변 평가 파일 변조 차단(Immutable Guard), 중복 코드 해시 차단(never-repeat), Fast-Fail, 몬테카를로 통계적 유의성 및 코드 단순성 기준(Simplicity Criterion)을 검증하고 원장(evidence/metric-climb-results.tsv)에 기록합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "cmd": {"type": "string", "description": "실행할 벤치마크/측정 명령어 문자열"},
                "metric_regex": {"type": "string", "description": "숫자 지표를 추출할 정규식 (기본값: metric:\\s*([0-9]+(?:\\.[0-9]+)?))"},
                "direction": {"type": "string", "enum": ["minimize", "maximize"], "description": "지표 최적화 방향 (minimize 또는 maximize)"},
                "target": {"type": "string", "description": "쉼표로 구분된 실험 대상 코드 파일 상대 경로"},
                "immutable": {"type": "string", "description": "쉼표로 구분된 수정 금지(채점/평가용) 파일 상대 경로"},
                "trials": {"type": "integer", "description": "반복 측정 횟수 (기본값 3)"},
                "confidence": {"type": "number", "description": "몬테카를로 승률 임계치 (기본값 0.90)"},
                "hypothesis": {"type": "string", "description": "이번 실험의 가설 설명"},
                "apply": {"type": "boolean", "description": "true 지정 시 실제 벤치마크 실행 및 원장 기록 (기본값 false: 미리보기)"},
            },
            "required": ["cmd"],
        },
    ),
    McpToolDefinition(
        name="dreampia_expand_prompt",
        description="Dreampia 국문 프롬프트 고도화(Prompt Expansion) 엔진: 사용자의 짧은 한 줄 채팅 입력을 분석하여 한 번 더 생각한 국문 엔지니어링 프롬프트, 자동 주입 제약조건(SOLID/타입/UI/보안), 방어할 엣지케이스, 완료 기준(DoD), 그리고 채팅창 상단에 즉시 출력할 가시적 국문 작전 브리핑 마크다운(echo_markdown_ko)을 생성합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로 (생략 시 기본 프로젝트 루트 사용)"},
                "goal": {"type": "string", "description": "사용자가 입력한 원본 요청 텍스트"},
            },
            "required": ["goal"],
        },
    ),
    McpToolDefinition(
        name="dreampia_reconstruct_doctor",
        description="Dreampia 2-Tier 클린룸 역공학 진단기: Tier 1(내장 무의존성 엔진) 및 Tier 2(선택적 외부 리버싱 부스터: objdump, nm, rizin, jadx, wasm2wat, ghidra, adb) 가용 상태와 패키지 매니저(winget/scoop/brew/apt)를 진단하고 설치 명령 미리보기를 반환합니다. (보안상 MCP를 통한 자동 설치 실행은 차단됩니다.)",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로 (생략 가능)"},
                "install_tool": {"type": "string", "description": "설치 계획을 확인할 Tier 2 도구 ID (예: rizin, jadx, ghidra, wasm2wat, objdump, nm, adb, all)"},
                "apply": {"type": "boolean", "description": "보안상 MCP 호출에서는 항상 미리보기(false)로 동작하며 실제 설치는 터미널 CLI에서만 수행됩니다."},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_learn_rule",
        description="프로젝트 자가 학습 메모리(learn-rule): 사용자 피드백이나 팀 규칙을 .dreampia/memory/project-rules.json에 영구 등록하여 이후 프롬프트 고도화(expand-prompt) 및 정적 감사(audit-code)에 자동 반영합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "rule": {"type": "string", "description": "학습할 프로젝트 규칙 설명(한글)"},
                "forbidden_regex": {"type": "string", "description": "선택적: 정적 코드 감사(audit-code)에서 차단할 정규식 패턴"},
                "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"], "description": "위반 심각도 (기본값 HIGH)"},
                "apply": {"type": "boolean", "description": "기본값 true (.dreampia/memory/project-rules.json 파일에 실제 저장)"},
            },
            "required": ["rule"],
        },
    ),
    McpToolDefinition(
        name="dreampia_interview_compile",
        description="Oracle 소크라테스식 인터뷰 컴파일러(interview-compile): 작업 목표(goal)와 역질문 답변(answers)을 결합해 PRD 요구사항(PRD-R*), 작업(TASK-*), 테스트 계획(TEST-*) 마크다운 문서 및 SDD 원장(evidence/sdd-ledger.json)을 자동 생성합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "goal": {"type": "string", "description": "작업 목표 설명"},
                "answers": {"type": "string", "description": "세미콜론(;) 또는 줄바꿈으로 구분된 역질문 3개에 대한 답변"},
                "apply": {"type": "boolean", "description": "true 지정 시 docs/01_PRD_REQUIREMENTS.md, 06_TEST_PLAN.md, 07_BACKLOG.md 및 SDD 원장에 실제 기록"},
            },
            "required": ["goal"],
        },
    ),
    McpToolDefinition(
        name="dreampia_reconstruct_spec",
        description="Keymaker 클린룸 한글 명세 자동 추출기(reconstruct-spec): 참조 아티팩트(Tier 1 + Tier 2 심층 심볼)를 분석하여 오염 없는 한글 기능 명세서(approved-spec/00_CLEANROOM_SPEC.md), Golden I/O 템플릿, 의무 원장을 자동 생성합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "source": {"type": "string", "description": "참조 영역 상대 경로 (기본값: contaminated-zone)"},
                "apply": {"type": "boolean", "description": "true 지정 시 approved-spec/00_CLEANROOM_SPEC.md 및 원장 파일 저장"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_squad_worktree",
        description="병렬 스쿼드 Git Worktree 오케스트레이터(squad-worktree): Neo(백엔드), Mouse(UI), Trinity(테스트) 트랙별 물리적 격리 작업 트리(.dreampia/worktrees/*)를 계획·생성·정리합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "goal": {"type": "string", "description": "병렬 수행할 작업 목표"},
                "mode": {"type": "string", "enum": ["plan", "create", "cleanup"], "description": "실행 모드 (plan, create, cleanup)"},
                "apply": {"type": "boolean", "description": "true 지정 시 실제 Worktree/격리 폴더 생성 또는 정리 실행"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_next_actions",
        description="다음 추천 작업 네비게이터(next-actions): 현재 프로젝트 상태(Git, SDD 명세/원장, 클린룸, 코드 감사, 학습 규칙)와 목표를 분석해 우선순위별 다음 추천 작업(1~3순위), 매직 단축어 채팅 프롬프트 예시, CLI 명령어를 안내합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "goal": {"type": "string", "description": "선택적: 방금 수행했거나 진행 중인 작업 목표 설명"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_status",
        description="통합 상태 대시보드(/status): 현재 프로젝트의 스킬 상태 디렉터리(.dreampia 또는 .dreampia-skill), UI 규칙 강제 여부, SDD ID 정규식, 학습 규칙 수, 글로벌 5개 호스트 동기화 상태를 한눈에 조회합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_doctor",
        description="통합 환경·무결성·보안 진단기(/doctor): Python 런타임, 번들 SHA-256 매니페스트, 비관리 .dreampia/ 충돌 여부, 글로벌 5개 호스트 스킬 동기화 상태 및 원격 최신 버전을 점검합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "include_global": {"type": "boolean", "description": "글로벌 5개 호스트 스킬 폴더 및 MCP 등록 상태 포함 점검 (기본값 true)"},
                "check_remote": {"type": "boolean", "description": "원격 origin/main 최신 커밋 일치 여부 점검 (기본값 false)"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_config",
        description="프로젝트별 설정 관리(/config): UI 규칙(bg-transparent, lucide-react) 강제 여부(on/off), 상하단 브리핑 출력 여부(on/off), 상태 폴더(.dreampia-skill), SDD ID 정규식(req_pattern, task_pattern, test_pattern)을 조회하거나 설정합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "ui_rules": {"type": "string", "enum": ["on", "off"], "description": "기본 UI 규칙 강제 여부 (on 또는 off)"},
                "briefing": {"type": "string", "enum": ["on", "off"], "description": "상단 작전 브리핑 출력 여부 (on 또는 off)"},
                "state_dir": {"type": "string", "enum": [".dreampia", ".dreampia-skill"], "description": "스킬 상태 저장 폴더"},
                "req_pattern": {"type": "string", "description": "SDD 요구사항 ID 정규식"},
                "task_pattern": {"type": "string", "description": "SDD 작업 ID 정규식 (예: \\bT\\d{3,6}\\b)"},
                "test_pattern": {"type": "string", "description": "SDD 테스트 ID 정규식"},
                "apply": {"type": "boolean", "description": "true 지정 시 project-rules.json에 실제 저장"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_self_update",
        description="스킬 자체 업데이트 및 글로벌 동기화(/update): Dreampia-Skill 저장소 git pull 최신화, 번들 매니페스트 갱신 및 5개 글로벌 호스트 스킬 폴더 재배포를 일괄 수행합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "apply": {"type": "boolean", "description": "true 지정 시 실제 git pull 및 글로벌 스킬 재설치 수행 (기본값 false 미리보기)"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_clean",
        description="임시 작업 공간 정리(/clean): 병렬 스쿼드 워크트리, 중단된 트랜잭션 저널 및 선택적 임시 증거 캐시를 안전하게 정리합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "clean_evidence": {"type": "boolean", "description": "evidence/*.json 임시 파일도 함께 정리할지 여부 (기본값 false)"},
                "apply": {"type": "boolean", "description": "true 지정 시 실제 삭제 수행 (기본값 false 미리보기)"},
            },
        },
    ),
    McpToolDefinition(
        name="dreampia_release",
        description="일괄 버전 릴리즈(/release): 저장소 내 모든 버전 상수·문서·번들 매니페스트(bundle-manifest.json)·CHANGELOG.md를 새 시맨틱 버전(X.Y.Z)으로 일괄 동기화합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "target_version": {"type": "string", "description": "릴리즈할 새 버전 (예: 0.7.0)"},
                "notes": {"type": "string", "description": "CHANGELOG.md에 기록할 한글 변경 요약"},
                "apply": {"type": "boolean", "description": "true 지정 시 실제 파일 및 매니페스트 일괄 갱신 (기본값 false 미리보기)"},
            },
            "required": ["target_version"],
        },
    ),
    McpToolDefinition(
        name="dreampia_discover",
        description="브라운필드/폴리글랏/모노레포 자동 탐색 및 온보딩(/discover): 프로젝트 매니페스트(package.json, pyproject.toml, Cargo.toml, go.mod 등)와 소스/테스트 파일을 스캔해 스택 프로필(project-profile.json)을 생성하고, 선택적으로 브라운필드 SDD 베이스라인 명세(brownfield-baseline.md)를 자동 부트스트랩합니다.",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "대상 프로젝트 루트 경로"},
                "bootstrap_sdd": {"type": "boolean", "description": "true 지정 시 SDD 문서가 없는 브라운필드 저장소에 최소 SDD 베이스라인 명세 및 원장을 자동 생성"},
                "apply": {"type": "boolean", "description": "true 지정 시 project-profile.json 및 선택적 베이스라인 명세 실제 저장"},
            },
        },
    ),
)

_FORBIDDEN_MCP_ROOT_NAMES: frozenset[str] = frozenset(
    {"etc", "bin", "sbin", "usr", "var", "proc", "sys", "dev", "windows", "program files", "program files (x86)", "system32"}
)


def _resolve_project_root(default_root: Path, requested: object) -> Path:
    resolved_default = default_root.resolve()
    if isinstance(requested, str) and requested.strip():
        cand = Path(requested.strip()).resolve()
    else:
        cand = resolved_default
    if cand.is_symlink() or not cand.is_dir():
        raise ValueError(f"유효하지 않은 프로젝트 디렉터리입니다: {cand}")
    forbidden_roots = {Path("/").resolve(), Path(cand.anchor).resolve(), Path.home().resolve()}
    if cand in forbidden_roots or cand.name.lower() in _FORBIDDEN_MCP_ROOT_NAMES:
        raise ValueError(f"보안 정책상 시스템 루트 또는 홈 디렉터리는 직접 지정할 수 없습니다: {cand}")
    if resolved_default != team_cli.PACKAGE.resolve():
        if cand != resolved_default and resolved_default not in cand.parents:
            raise ValueError(
                f"보안 정책상 MCP 서버에 바인딩된 프로젝트 루트({resolved_default}) 외부 경로({cand})는 접근할 수 없습니다."
            )
    return cand


def execute_mcp_tool(default_root: Path, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
    """요청된 MCP 도구를 실행하고 결정론적 JSON 결과 사전을 반환한다."""
    root = _resolve_project_root(default_root, arguments.get("project"))

    if tool_name == "dreampia_status":
        return team_cli.project_status(root)

    if tool_name == "dreampia_discover":
        bootstrap_flag = bool(arguments.get("bootstrap_sdd", False))
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.discover_project_check(root, bootstrap_sdd=bootstrap_flag, apply=apply_flag)

    if tool_name == "dreampia_doctor":
        inc_global = bool(arguments.get("include_global", True))
        chk_remote = bool(arguments.get("check_remote", False))
        return team_cli.doctor(root, include_global=inc_global, check_remote=chk_remote)

    if tool_name == "dreampia_config":
        ui_rules = str(arguments["ui_rules"]).strip() if arguments.get("ui_rules") else None
        briefing_arg = str(arguments["briefing"]).strip() if arguments.get("briefing") else None
        state_dir = str(arguments["state_dir"]).strip() if arguments.get("state_dir") else None
        req_pat = str(arguments["req_pattern"]).strip() if arguments.get("req_pattern") else None
        task_pat = str(arguments["task_pattern"]).strip() if arguments.get("task_pattern") else None
        test_pat = str(arguments["test_pattern"]).strip() if arguments.get("test_pattern") else None
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.manage_project_config(
            root,
            ui_rules=ui_rules,
            briefing=briefing_arg,
            state_dir=state_dir,
            req_pattern=req_pat,
            task_pattern=task_pat,
            test_pattern=test_pat,
            apply=apply_flag,
        )

    if tool_name == "dreampia_self_update":
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.self_update(apply=apply_flag)

    if tool_name == "dreampia_clean":
        clean_ev = bool(arguments.get("clean_evidence", False))
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.clean_workspace(root, clean_evidence=clean_ev, apply=apply_flag)

    if tool_name == "dreampia_release":
        target_ver = str(arguments.get("target_version") or "").strip()
        notes = str(arguments.get("notes") or "").strip()
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.release_version(target_ver, notes_ko=notes, apply=apply_flag)

    if tool_name == "dreampia_route_plan":
        goal = str(arguments.get("goal") or "").strip()
        return team_cli.route_plan_check(root, goal)

    if tool_name == "dreampia_expand_prompt":
        goal = str(arguments.get("goal") or "").strip()
        return team_cli.expand_prompt_check(root, goal)

    if tool_name == "dreampia_next_actions":
        goal = str(arguments.get("goal") or "").strip()
        return team_cli.next_actions_check(root, goal)

    if tool_name == "dreampia_reconstruct_doctor":
        install_tool = str(arguments["install_tool"]).strip() if arguments.get("install_tool") else None
        requested_apply = bool(arguments.get("apply", False))
        res = team_cli.reconstruct_doctor_check(install_tool=install_tool, apply=False)
        if requested_apply:
            res["mcp_install_blocked"] = True
            res["security_notice_ko"] = (
                "보안 정책상 MCP를 통한 외부 패키지 자동 설치는 차단되며 미리보기(apply=False)만 제공됩니다. "
                "실제 설치는 사용자가 터미널 CLI에서 직접 실행해야 합니다."
            )
        return res

    if tool_name == "dreampia_learn_rule":
        rule_ko = str(arguments.get("rule") or "").strip()
        forbidden_re = str(arguments.get("forbidden_regex") or "").strip()
        sev = str(arguments.get("severity") or "HIGH").strip()
        apply_flag = bool(arguments.get("apply", True))
        return team_cli.learn_rule_check(root, rule_ko, forbidden_regex=forbidden_re, severity=sev, apply=apply_flag)

    if tool_name == "dreampia_interview_compile":
        goal = str(arguments.get("goal") or "").strip()
        answers = str(arguments.get("answers") or "").strip()
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.interview_compile_check(root, goal, answers=answers, apply=apply_flag)

    if tool_name == "dreampia_reconstruct_spec":
        source = str(arguments.get("source") or "contaminated-zone").strip()
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.reconstruct_spec_check(root, source_rel=source, apply=apply_flag)

    if tool_name == "dreampia_squad_worktree":
        goal = str(arguments.get("goal") or "").strip()
        mode = str(arguments.get("mode") or "plan").strip()
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.squad_worktree_check(root, goal=goal, mode=mode, apply=apply_flag)

    if tool_name == "dreampia_reconstruct_inspect":
        target = str(arguments.get("target") or "").strip()
        return team_cli.reconstruct_inspect_check(root, target)

    if tool_name == "dreampia_reconstruct_ledger":
        source = str(arguments.get("source") or "").strip()
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.reconstruct_ledger_check(root, source, apply=apply_flag)

    if tool_name == "dreampia_reconstruct_verify":
        ledger = str(arguments.get("ledger") or "evidence/reconstruction-ledger.json").strip()
        candidate = str(arguments.get("candidate") or "implementation").strip()
        return team_cli.reconstruct_verify_check(root, ledger, candidate)

    if tool_name == "dreampia_reconstruct_compare":
        source = str(arguments.get("source") or "").strip()
        candidate = str(arguments.get("candidate") or "").strip()
        return team_cli.reconstruct_compare_check(root, source, candidate)

    if tool_name == "dreampia_visual_check":
        manifest = str(arguments["manifest"]).strip() if arguments.get("manifest") else None
        baseline = str(arguments["baseline"]).strip() if arguments.get("baseline") else None
        candidate = str(arguments["candidate"]).strip() if arguments.get("candidate") else None
        max_diff = float(arguments.get("max_diff_ratio") or 0.0)  # type: ignore[arg-type]
        return team_cli.visual_check(root, manifest, baseline, candidate, max_diff)

    if tool_name == "dreampia_verify_gate":
        gate = str(arguments.get("gate") or "before-dev-start").strip()
        return team_cli.verify_gate(root, gate)

    if tool_name == "dreampia_router_discover":
        return team_cli.router_discover_check(root)

    if tool_name == "dreampia_sdd_ledger":
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.sdd_ledger_check(root, apply=apply_flag)

    if tool_name == "dreampia_sdd_check":
        ledger_arg = str(arguments["ledger"]).strip() if arguments.get("ledger") else None
        allow_doc_only = bool(arguments.get("allow_doc_only", False))
        return team_cli.sdd_verify_check(root, ledger_rel=ledger_arg, require_tdd_files=not allow_doc_only)

    if tool_name == "dreampia_audit_code":
        apply_flag = bool(arguments.get("apply", False))
        raw_ui = arguments.get("check_ui_rules")
        ui_flag = raw_ui if isinstance(raw_ui, bool) else None
        raw_co = arguments.get("changed_only")
        force_all_flag = bool(arguments.get("all", False))
        changed_only_flag: bool | None = False if force_all_flag else (raw_co if isinstance(raw_co, bool) else None)
        base_ref_arg = str(arguments.get("base_ref") or "HEAD").strip()
        return team_cli.audit_code_check(
            root,
            check_ui_rules=ui_flag,
            changed_only=changed_only_flag,
            force_all=force_all_flag,
            base_ref=base_ref_arg,
            apply=apply_flag,
        )

    if tool_name == "dreampia_context_pack":
        goal_arg = str(arguments.get("goal") or "").strip()
        apply_flag = bool(arguments.get("apply", True))
        return team_cli.context_pack_check(root, goal=goal_arg, apply=apply_flag)

    if tool_name == "dreampia_golden_io":
        spec_arg = str(arguments.get("spec") or "approved-spec/golden-io.json").strip()
        return team_cli.golden_io_check(root, golden_rel=spec_arg)

    if tool_name == "dreampia_autopilot_gate":
        goal_arg = str(arguments.get("goal") or "").strip()
        allow_doc_only = bool(arguments.get("allow_doc_only", False))
        raw_co = arguments.get("changed_only")
        force_all_flag = bool(arguments.get("all", False))
        changed_only_flag = False if force_all_flag else (raw_co if isinstance(raw_co, bool) else None)
        base_ref_arg = str(arguments.get("base_ref") or "HEAD").strip()
        raw_vcmd = arguments.get("verify_commands") or arguments.get("verify_cmd")
        verify_cmd_arg: str | list[str] | None = None
        if isinstance(raw_vcmd, str) and raw_vcmd.strip():
            verify_cmd_arg = raw_vcmd.strip()
        elif isinstance(raw_vcmd, list):
            verify_cmd_arg = [str(x).strip() for x in raw_vcmd if str(x).strip()]
        apply_flag = bool(arguments.get("apply", True))
        return team_cli.autopilot_gate_check(
            root,
            goal=goal_arg,
            allow_doc_only=allow_doc_only,
            changed_only=changed_only_flag,
            force_all=force_all_flag,
            base_ref=base_ref_arg,
            verify_cmd=verify_cmd_arg,
            apply=apply_flag,
        )

    if tool_name == "dreampia_blast_radius":
        target_arg = str(arguments.get("target") or "").strip()
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.blast_radius_check(root, target_rel=target_arg, apply=apply_flag)

    if tool_name == "dreampia_metric_climb":
        cmd_arg = str(arguments.get("cmd") or "").strip()
        regex_arg = str(arguments.get("metric_regex") or r"metric:\s*([0-9]+(?:\.[0-9]+)?)")
        dir_arg = str(arguments.get("direction") or "minimize").strip()
        target_arg = str(arguments.get("target") or "").strip()
        immut_arg = str(arguments.get("immutable") or "").strip()
        trials_arg = int(arguments.get("trials") or 3)  # type: ignore[call-overload]
        conf_arg = float(arguments.get("confidence") or 0.90)  # type: ignore[arg-type]
        hyp_arg = str(arguments.get("hypothesis") or "candidate-experiment").strip()
        apply_flag = bool(arguments.get("apply", False))
        return team_cli.metric_climb_check(
            root,
            benchmark_cmd_str=cmd_arg,
            metric_regex=regex_arg,
            direction=dir_arg,
            target_rel=target_arg,
            immutable_rel=immut_arg,
            trials=trials_arg,
            confidence=conf_arg,
            hypothesis=hyp_arg,
            apply=apply_flag,
        )

    raise KeyError(f"등록되지 않은 MCP 도구입니다: {tool_name}")


def handle_jsonrpc_message(default_root: Path, message: dict[str, object]) -> dict[str, object] | None:
    """단일 JSON-RPC 2.0 요청/알림 메시지를 처리하고 응답 객체(알림인 경우 None)를 반환한다."""
    method = str(message.get("method") or "")
    msg_id = message.get("id")
    params = message.get("params")
    params_dict: dict[str, object] = params if isinstance(params, dict) else {}

    # Notifications have no 'id' and must not produce a response
    if "id" not in message:
        return None

    if method == "initialize":
        req_proto = str(params_dict.get("protocolVersion") or MCP_PROTOCOL_VERSION)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": req_proto,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [t.to_dict() for t in MCP_TOOLS],
            },
        }

    if method == "tools/call":
        tool_name = str(params_dict.get("name") or "").strip()
        raw_args = params_dict.get("arguments")
        args_dict: dict[str, object] = raw_args if isinstance(raw_args, dict) else {}
        try:
            payload = execute_mcp_tool(default_root, tool_name, args_dict)
            is_error = payload.get("status") == "FAIL"
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload, ensure_ascii=False, indent=2),
                        }
                    ],
                    "isError": is_error,
                },
            }
        except KeyError as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": str(exc)},
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"status": "FAIL", "error": str(exc), "type": type(exc).__name__},
                                ensure_ascii=False,
                            ),
                        }
                    ],
                    "isError": True,
                },
            }

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "resources": [
                    {
                        "uri": "dreampia://skill/ai-dev-execution/SKILL.md",
                        "name": "Dreampia AI Dev Execution Skill",
                        "description": "드림피아 AI 개발 실행 및 클린룸·시각 검증 핵심 지침서",
                        "mimeType": "text/markdown",
                    }
                ]
            },
        }

    if method == "resources/read":
        uri = str(params_dict.get("uri") or "")
        if uri == "dreampia://skill/ai-dev-execution/SKILL.md":
            skill_md = (team_cli.PACKAGE / "ai-dev-execution" / "SKILL.md").read_text(encoding="utf-8")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/markdown",
                            "text": skill_md,
                        }
                    ]
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32602, "message": f"지원하지 않는 리소스 URI입니다: {uri}"},
        }

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"지원하지 않는 JSON-RPC 메서드입니다: {method}"},
    }


def serve_stdio(
    default_root: Path,
    in_stream: BinaryIO | None = None,
    out_stream: BinaryIO | None = None,
) -> int:
    """표준 입출력(STDIO) 스트림에서 줄바꿈 구분 또는 Content-Length 프레임 JSON-RPC 메시지를 처리한다."""
    reader = in_stream if in_stream is not None else sys.stdin.buffer
    writer = out_stream if out_stream is not None else sys.stdout.buffer

    while True:
        line = reader.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue

        use_content_length = False
        if stripped.lower().startswith(b"content-length:"):
            use_content_length = True
            length = int(stripped.split(b":", 1)[1].strip())
            while True:
                hdr_line = reader.readline()
                if not hdr_line or hdr_line in (b"\r\n", b"\n"):
                    break
            raw_body = reader.read(length)
        else:
            raw_body = stripped

        try:
            msg = json.loads(raw_body.decode("utf-8"))
        except Exception:  # noqa: BLE001
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "유효하지 않은 JSON 페이로드입니다."},
            }
            out_bytes = json.dumps(err_resp, ensure_ascii=False).encode("utf-8") + b"\n"
            writer.write(out_bytes)
            writer.flush()
            continue

        if not isinstance(msg, dict):
            continue
        response = handle_jsonrpc_message(default_root, msg)
        if response is not None:
            payload_bytes = json.dumps(response, ensure_ascii=False).encode("utf-8")
            if use_content_length:
                header = f"Content-Length: {len(payload_bytes)}\r\n\r\n".encode("ascii")
                writer.write(header + payload_bytes)
            else:
                writer.write(payload_bytes + b"\n")
            writer.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dreampia Standard Library MCP STDIO Server")
    parser.add_argument("--project", default=".", help="기본 대상 프로젝트 루트 경로")
    args = parser.parse_args(argv)
    default_root = Path(args.project).resolve()
    return serve_stdio(default_root)


if __name__ == "__main__":
    raise SystemExit(main())
