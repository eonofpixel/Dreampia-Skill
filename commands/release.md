---
description: 저장소 내 모든 버전 상수, 문서, 번들 매니페스트(bundle-manifest.json) 및 CHANGELOG.md를 새 시맨틱 버전으로 일괄 릴리즈합니다.
argument-hint: "--to <X.Y.Z> [--notes <한글요약>] [--apply]"
---

Dreampia-Skill 저장소의 버전을 일괄 릴리즈하십시오.

실행 절차:
1. MCP 도구 `dreampia_release`를 호출하거나 CLI `python -m harness.team_cli release --to <버전> --apply` 명령을 실행하십시오.
2. 갱신된 파일 목록(`updated_files`), 번들 매니페스트 갱신 여부 및 글로벌 호스트 동기화 상태를 별표 볼드 마커나 이모지 없이 평문 한글로 보고하십시오.
