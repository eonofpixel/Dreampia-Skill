---
description: 임시 스쿼드 워크트리, 중단된 트랜잭션 저널 및 선택적 임시 증거 캐시를 안전하게 정리합니다.
argument-hint: "[--clean-evidence] [--apply]"
---

프로젝트의 임시 작업 공간(스쿼드 워크트리 및 트랜잭션 저널)을 안전하게 정리하십시오.

실행 절차:
1. MCP 도구 `dreampia_clean`을 호출하거나 CLI `python -m harness.team_cli clean --project . --apply` 명령을 실행하십시오.
2. 정리된 경로 목록(`cleaned_paths`)을 별표 볼드 마커나 이모지 없이 평문 한글로 보고하십시오.
