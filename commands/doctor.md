---
description: Python 런타임, 번들 SHA-256 매니페스트 무결성, 비관리 .dreampia/ 충돌, 글로벌 5개 호스트 스킬 동기화 및 역설계 체인 상태를 진단합니다.
argument-hint: "[--global] [--check-remote]"
---

현재 프로젝트와 글로벌 에이전트 호스트의 환경·무결성·보안 상태를 종합 진단하십시오.

실행 절차:
1. MCP 도구 `dreampia_doctor` (`include_global: true`, `check_remote: true`)를 호출하거나 CLI `python -m harness.team_cli doctor --project . --global --check-remote` 명령을 실행하십시오.
2. 역설계 도구 체인까지 함께 점검하려면 `dreampia_reconstruct_doctor` 또는 `python -m harness.team_cli reconstruct-doctor`를 추가로 실행하십시오.
3. 진단 결과(`healthy`, 충돌 목록, 글로벌 5개 호스트 버전 일치 여부, MCP 등록 여부)를 별표 볼드 마커나 이모지 없이 평문 한글로 보고하십시오.
