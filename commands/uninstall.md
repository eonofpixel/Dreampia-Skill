---
description: 프로젝트 또는 글로벌 5개 호스트에서 Dreampia-Skill 설치본을 안전하게 제거하고 백업(.pre-dreampia.bak)을 복원합니다.
argument-hint: "[--global] [--apply]"
---

Dreampia-Skill 설치본을 안전하게 제거하십시오.

실행 절차:
1. 글로벌 5개 호스트 및 MCP 설정 제거: `python -m harness.team_cli uninstall --global --apply` (또는 `python -m harness.team_cli uninstall-global --apply`)
2. 현재 프로젝트 내 관리 파일만 제거: `python -m harness.team_cli uninstall --project . --apply`
3. 미리보기가 필요한 경우 `--apply` 없이 먼저 실행한 뒤 결과를 별표 볼드 마커나 이모지 없이 평문 한글로 보고하십시오.
