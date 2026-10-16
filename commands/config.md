---
description: 프로젝트별 설정(UI 규칙 on/off, 작전 브리핑 출력 on/off, 상태 디렉터리 .dreampia-skill, SDD ID 정규식)을 조회하거나 변경합니다.
argument-hint: "[--ui-rules on|off] [--briefing on|off] [--task-pattern <정규식>] [--apply]"
---

프로젝트별 Dreampia-Skill 설정을 조회하거나 안전하게 변경하십시오.

실행 절차:
1. 사용자 인자(`$ARGUMENTS`)에 따라 MCP 도구 `dreampia_config`를 호출하거나 CLI `python -m harness.team_cli config --project . $ARGUMENTS` 명령을 실행하십시오.
   - 기본 UI 규칙(`bg-transparent`, `lucide-react`) 끄기: `python -m harness.team_cli config --project . --ui-rules off --apply`
   - 기본 UI 규칙 켜기: `python -m harness.team_cli config --project . --ui-rules on --apply`
   - 상하단 작전 브리핑 블록 끄기: `python -m harness.team_cli config --project . --briefing off --apply`
   - SDD 작업 ID 정규식 지정: `python -m harness.team_cli config --project . --task-pattern "\\bT\\d{3,6}\\b" --apply`
2. 변경된 설정 파일 경로(`config_path`)와 적용 상태를 별표 볼드 마커나 이모지 없이 평문 한글로 보고하십시오.
