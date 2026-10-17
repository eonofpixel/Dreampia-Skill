---
name: ai-dev-execution
description: Develop small projects, services, and substantial features with proportionate specs, TDD, real evidence, and resumable milestones. For user-facing UI tasks, also define product screens, visual direction, connected flows, and visual/interaction verification. Excludes isolated coding questions.
---

# AI 개발 실행 — 1.0.0

1.0.0의 실행·복구·로컬 앱·고객 export는 [내부 OS 실행 기준](references/internal-os.md)을 따른다. 실제 역할 명령 실행과 독립 AI 판단, 로컬 starter 검증과 운영 준비를 구별한다.

사용자 아이디어를 작은 기능·실제 검증·승인된 릴리스로 연결한다. 사용자의 언어와 기존 저장소 관례를 따른다. SDD는 Spec-Driven Development, Software Design Document는 상세 설계서로 구별한다.

## 시작과 범위

1. 초보자 친화적 3줄 작전 브리핑(Compact Prompt Expansion Echo): 작업을 시작할 때 사용자가 방금 한 말을 그대로 복창(원본 입력 반복 또는 ~만들어줘/~해줘 앵무새 인용)하지 않으며, 불필요한 이모지나 별표 강조 기호(**)를 쓰지 않는다. 답변 최상단에 [Dreampia 국문 프롬프트 고도화 & 퀘스트 작전 브리핑] 블록(퀘스트 등급 및 발주자 `Hero(주인공 영웅)`, 한 번 더 생각한 고도화 프롬프트, 자동 챙김 항목, 출정 길드 파티)을 심플하고 알기 쉽게 먼저 출력한 뒤 실행한다(dreampia_expand_prompt 또는 dreampia_route_plan 연동).
2. 지정된 프로젝트의 목표·지침·문서·현재 변경·도구를 먼저 읽고 보존한다. 이미 승인한 구현을 양식이나 관례 때문에 다시 승인받지 않는다.
3. 문서만 / 구현까지 / 승인된 배포까지와 한 기능 또는 승인된 마일스톤의 종료 조건을 정한다. 불명확한 제품 결정만 질문하고 독립적인 준비는 진행한다. 범위를 릴리스 전체로 확대하지 않는다.
4. 사용자용 UI가 포함되면 사용자가 열 화면·핵심 조작·보이는 성공 결과·대상 창/기기를 구현 초기에 명시하고 [선택적 디자인 절차](references/product-design.md)를 읽는다. 내부 런타임 화면이나 목업으로 제품 UI를 대체하지 않는다. backend/CLI만 요청된 작업에는 UI·디자인 문서를 만들지 않는다.
5. 기존 브랜드·참조·허용된 자료를 재사용한다. 필요한 문서만 읽고 기존 명세의 절에 합친다. 낮은 위험의 한 흐름은 [간편 원본](assets/templates/compact-project.md)의 명세·작업/테스트·증거면 충분하다. 문서 수가 목표가 아니다.
6. 프롬프트 단축어(Magic Shorthands)가 입력되면 해당 실행 모드를 즉시 활성화한다:
   - `ulw`(`ultrawork`/`풀가동`): 주인공 영웅(`Hero`)의 퀘스트를 받아 길드 파티(`GuildMaster` 지휘) + SDD·TDD·코드감사·통합 보스 관문(`autopilot-gate`) 원스톱 완주
   - `loop`(`until-pass`/`루프`/`완주`): 모든 SDD+TDD·코드감사·보스 관문이 `PASS`될 때까지 자가 수정 반복(`continuous-loop`)
   - `climb`(`hillclimb`/`성능등반`): 불변 평가 파일 가드·중복 실험 해시 차단·몬테카를로 유의성 기반 자율 지표 등반(`metric-climb`)
   - `blast`(`폭발반경`): 1-Hop/2-Hop 호출 의존성·시스템 경계 교차·5단계 안전 증명 등급 분석(`blast-radius`)
   - `interrogate`(`심문`): 다중 관점 적대적 코드 리뷰, `unslop`(`군더더기제거`): AI 슬롭 코드 및 빈 예외 처리 정화
   - `sharpen`(`고도화`/`생각`/`구체화`): 짧은 요청을 정밀 국문 엔지니어링 명세·엣지케이스·검증 게이트로 심층 확장(`prompt-sharpen`)
   - `btw`(`quick`/`잠깐`): 파일 변경 없이 현재 문맥을 보존하며 `Sage`가 사이드 질의에 즉답(`side-query`)
   - `sdd`(`plan`/`명세`), `tdd`(`티디디`), `re`(`cleanroom`/`역설계`), `audit`(`sec`/`감사`), `ui`(`화면`) — [상세 라우팅 기준](references/cleanroom-governance.md) 적용
7. 표준 운영 슬래시·CLI 명령어(접두사 없는 `/명령어` 및 `npx dreampia <명령어>` 1:1 대응):
   - `/version` (`version --check-remote`): 로컬 버전·Git 커밋·원격 최신 여부 확인
   - `/status` (`status` / `dreampia_status`): 상태 디렉터리(`.dreampia` 또는 `.dreampia-skill`), UI 규칙 강제 여부, SDD 정규식, 글로벌 5개 호스트 동기화 대시보드
   - `/doctor` (`doctor --global --check-remote` / `dreampia_doctor`): 런타임·매니페스트·데이터 폴더 충돌·글로벌 호스트 무결성 통합 진단
   - `/config` (`config --ui-rules on|off --apply` / `dreampia_config`): 프로젝트별 UI 규칙 강제 여부·SDD ID 정규식·상태 폴더 설정
   - `/update` (`update --global --apply` / `self-update --apply` / `dreampia_self_update`): Git 최신화 + 번들 매니페스트 갱신 + 글로벌 5개 호스트 일괄 재배포
   - `/uninstall` (`uninstall --global --apply` / `uninstall --project . --apply`): 글로벌 또는 프로젝트 설치본 안전 제거 및 백업(`.pre-dreampia.bak`) 복원
   - `/release` (`release --to <X.Y.Z> --apply` / `dreampia_release`): 저장소 전 파일 버전 상수·문서·매니페스트·CHANGELOG 일괄 릴리즈
   - `/clean` (`clean --project . --apply` / `dreampia_clean`): 임시 스쿼드 워크트리 및 중단된 트랜잭션 저널 안전 정리

## 실행과 증거

1. 기본 단일 실행자, 요청 모델 `gpt-6.1-sol` 및 reasoning `medium`을 유지한다. 자동 상향은 하지 않는다. 사용자가 허용한 독립 작업만 파일 소유권을 분리해 병렬화한다.
2. 요구 → 계약/화면 → 작업 → 테스트 → 실제 증거를 연결한다. 소유 파일·의존성·입출력·완료/중단/재개 조건을 정의한다. 목표 상태와 실행 원장을 구별한다.
3. 핵심 동작·결함은 실제 행동 Red → 최소 Green → 영향받는 회귀 검증으로 진행한다. 문구나 탐색 목업에 형식적 TDD를 강요하지 않는다. 구현자와 검토자의 책임을 분리하고 수정 범위부터 재검토한다. 검토는 최대 두 차례다.
4. UI는 구현하고 실제 화면을 열어 조작·결과를 확인한다. 스크린샷은 시각 증거, 조작 기록은 동작 증거다. 저장/재조회가 요구되면 연결된 실제 경로까지 확인한다. mock·내부 런타임 PoC·연결된 UI·전체 제품 완료를 구별한다.
5. 실제 검증에 버전·환경·시각·명령/절차·기대·관찰·PASS/FAIL/NOT_RUN·증거 위치를 남긴다. 도구가 없거나 화면을 못 봤으면 시각 검증은 NOT_RUN이다. 필수 검증이 FAIL/NOT_RUN이면 해당 기능 전체 완료로 쓰지 않는다. 프로그램의 종료 코드가 명세 의미·화면 품질을 인증하지 않는다.
6. 한 기능/승인 마일스톤의 DoD까지 계속한다. 막힌 의존 작업은 blocked로 두고 원인·해제 조건·체크포인트를 남긴다. 재개 시 목표·현재 파일·과거 증거를 대조하고 외부 부작용을 자동 replay하지 않는다. 과거 PASS를 새 버전 결과로 복사하지 않는다.

## 전문 역할·인계·완료 검증 보강

전문 역할 분리, 증거 수집, 구조화된 인계 계약을 적용한다. [인계 기준](references/role-handoff.md)에 따라 파일 소유권·수신자·수용기준·최종 해시 증거·미해결 사항을 인계하며, 완료 전 verifier가 실제 결과를 대조한다. 역할 전체를 설치하거나 역할 명칭을 독립 AI 실행 인증으로 쓰지 않는다. 선택형 인계 checker는 드림피아 저장소에서 실행하며 기존 workflow를 자동 대체하지 않는다.

## 필요한 참조만 읽기

| 작업 | 참조 |
| --- | --- |
| UI 범위·시각 방향·구현·검증 | [공통 디자인](references/product-design.md) + 해당 [웹](references/design-web.md)/[데스크톱](references/design-desktop.md)/[모바일](references/design-mobile.md), 필요한 [증거 검수](references/design-verification.md); 기존 UX가 없고 필요한 경우만 [UX 원본](assets/templates/02-ia-ux.md) |
| 계획·명세·문서 소유권 | [workflow](references/workflow.md), [자료 지도](references/resources.md), [실행 상세 §1~4](references/execution-guide.md) |
| TDD·검증·재개·변경 | [실행 상세 §5~9](references/execution-guide.md), [게이트](references/quality-gates.md), [리뷰 기준](references/review-and-evaluation.md) |
| 완료 전 로컬 검사·게시 대상 일치 | [로컬 검증](references/local-verification.md) |
| 팀 책임·코드 강제 경계 | [팀 계약](references/team-contract.md), [거버넌스·클린룸·시각 검증](references/cleanroom-governance.md) |
| 선택 하네스/호스트 연동 | [하네스 연동](references/harness-integration.md), [실행 상세 §10](references/execution-guide.md) |

## 권한과 전달

스킬은 ChatGPT·Claude·DeepSeek·CLI 등 호스트가 제공하는 도구 안에서 적용할 공통 지침이다. 특정 모델/API/상용 디자인 도구·업로드는 필수 의존성이 아니다. 도구·로그인·권한을 가정하거나 다른 환경으로 몰래 전환하지 않는다. 없는 도구의 검증은 NOT_RUN과 해제 조건으로 남긴다.

설치/갱신/제거는 미리보기 후 명시 `--apply`이며 충돌을 보존한다. 계정·키·SSH·전역 설정·유료 inference·외부 공유·배포는 별도 승인 범위를 따른다. 비밀을 산출물에 복제하지 않는다. 커밋은 요청된 경우만 한다.

마지막에는 완료한 기능과 실제 경로, 실행한 검증과 미실행 범위, 남은 차단·필요한 결정만 짧게 보고하고, 답변 최하단에 [Dreampia 다음 추천 작업 가이드 (Next Actions)] 블록을 이모지나 별표 강조 기호(**) 없이 초보자도 한눈에 읽을 수 있는 짧은 1줄 요약 3개 + 자연스러운 한글 입력 예시(dreampia_next_actions 연동)로 깔끔하게 안내한다. 출시 준비를 실제 배포로, mock/PoC를 제품 완료로, 링크 검사를 효과 입증으로 주장하지 않는다.

