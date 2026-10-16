---
description: 현재 프로젝트의 스킬 상태 폴더, UI 규칙 강제 여부, SDD ID 정규식, 학습 규칙 및 글로벌 5개 호스트 동기화 상태를 조회합니다.
argument-hint: "[--project <경로>]"
---

현재 프로젝트 및 글로벌 스킬의 통합 상태 대시보드를 조회하십시오.

실행 절차:
1. MCP 도구 `dreampia_status`를 호출하거나 CLI `python -m harness.team_cli status --project .` 명령을 실행하십시오.
2. 상태 디렉터리(`.dreampia` 또는 `.dreampia-skill`), 비관리 데이터 충돌 여부, UI 규칙 강제 여부(`ON`/`OFF`), SDD ID 정규식, 학습된 규칙 수, 글로벌 5개 호스트 동기화 상태를 별표 볼드 마커나 이모지 없이 평문 한글로 보고하십시오.
