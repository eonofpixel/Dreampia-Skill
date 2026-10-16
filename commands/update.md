---
description: Dreampia-Skill 저장소 최신화(git pull), 번들 매니페스트 갱신 및 5개 글로벌 호스트 스킬 폴더 재배포를 일괄 수행합니다.
argument-hint: "[--apply]"
---

Dreampia-Skill 자체 업데이트 및 글로벌 5개 호스트 스킬 재동기화를 수행하십시오.

실행 절차:
1. MCP 도구 `dreampia_self_update` (`apply: true`)를 호출하거나 CLI `python -m harness.team_cli update --global --apply` (또는 `python -m harness.team_cli self-update --apply`) 명령을 실행하십시오.
2. 이전 버전, 현재 버전, Git 커밋 해시 및 글로벌 5개 호스트 재배포 결과를 별표 볼드 마커나 이모지 없이 평문 한글로 보고하십시오.
