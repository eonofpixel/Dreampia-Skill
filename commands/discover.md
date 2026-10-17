---
description: 프로젝트 자동 탐색 및 브라운필드 온보딩 (스택/모노레포 감지 및 SDD 베이스라인 부트스트랩)
---

현재 프로젝트의 언어, 프레임워크, 테스트/빌드 명령어, 모노레포 여부, UI 스택 유무를 자동 탐색하고 선택적으로 브라운필드 SDD 베이스라인 명세를 부트스트랩합니다.

1. MCP 도구 `dreampia_discover`가 연결되어 있다면 우선 호출하여 결과를 확인하십시오.
2. CLI로 실행할 경우 아래 명령어를 사용하십시오:
   - 미리보기 탐색: `python -m harness.team_cli discover --project .`
   - 프로필 저장 및 브라운필드 SDD 베이스라인 부트스트랩: `python -m harness.team_cli discover --project . --bootstrap-sdd --apply`
3. 결과 요약에는 감지된 프로젝트 모드(`sdd-ready`, `brownfield`, `greenfield`), 권장 실행 티어(`nano`, `standard`, `full`), 감지된 언어/프레임워크, 추천 테스트 명령어를 깔끔한 한글 평문(볼드 마커 및 이모지 금지)으로 보고하십시오.
