---
description: 로컬 Dreampia-Skill 버전, Git 커밋/브랜치 및 원격 최신 상태를 조회합니다.
argument-hint: "[--check-remote]"
---

현재 Dreampia-Skill 버전과 원격 최신 상태를 조회하십시오.

실행 절차:
1. CLI 명령 실행: `python -m harness.team_cli version --check-remote` (또는 `npx dreampia version --check-remote`)
2. 반환된 JSON에서 `version`, `commit`, `branch`, `remote_commit`, `up_to_date` 값을 요약하여 별표 볼드 마커나 이모지 없이 평문 한글로 보고하십시오.
