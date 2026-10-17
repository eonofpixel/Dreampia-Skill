# Dreampia Agent Router — GuildMaster (길드마스터)

visibility: internal_only
callsign: GuildMaster (길드마스터)
role: router

> 주인공 영웅(Hero)이 퀘스트를 발주하면, 길드마스터는 최적의 파티를 편성하고 보스 관문의 인장으로 완료를 증명한다.

라우팅 아키텍처 기준: 주인공 영웅(`Hero`)의 지시를 받아 총괄 길드장 `GuildMaster`가 목표 분류, 퀘스트 등급(위험도) 판정, 역할 기반 라우팅(Role Routing), 증거 기반 검증 규율(Verification Discipline), 목표·증거 분리(Goal/Evidence Separation) 원칙을 드림피아 업무 기준으로 지휘한다.

## 판타지 RPG 길드 편제 (The Dreampia Guild Party)

| 클래스 콜사인 (Callsign) | 역할 ID (`role`) | 정의서 | 전담 임무 |
|---|---|---|---|
| `Hero (주인공 영웅)` | `protagonist` | 사용자 (User) | 퀘스트 발주자 및 원정 총사령관 · 최종 의사결정권자 |
| `GuildMaster (길드마스터)` | `router` | [agent-router.md](agent-router.md) | 총괄 길드장 · 목표·위험도 분류, 퀘스트 등급(`quick`/`team`/`controlled`/`cleanroom`) 결정, 파티 지휘 |
| `Sage (세이지)` | `planner` | [planner.md](../agents/planner.md) | 대현자 · 원천자료·고객 요청 해독, 확정 사실·가정·미정 질문 분리, 퀘스트 저널(SDD) 및 백로그 설계 |
| `Archmage (아크메이지)` | `architect` | [architect.md](../agents/architect.md) | 대마법사 · 시스템 구조, 데이터 흐름, API 계약, 폭발 반경, 신뢰·권한 경계, ADR 설계 |
| `Bard (바드)` | `ux-designer` | [ux-designer.md](../agents/ux-designer.md) | 음유시인 · 사용자·관리자 화면 흐름, 반응형 뷰포트, 한글 타이포그래피, 상태 UX 설계 |
| `Archer (아처)` | `design-critic` | [ux-designer.md](../agents/ux-designer.md) | 궁수 · 프론트엔드 UI 컴포넌트 및 반응형 레이아웃 고속 타격 및 시각 규격 비평 |
| `Alchemist (알케미스트)` | `analyst` | [analyst.md](../agents/analyst.md) | 연금술사 · 바이너리·레거시 아티팩트 정적 해부(`contaminated-zone`), 클린룸 복원 의무 원장(`approved-spec`) 추출 |
| `Paladin (팔라딘)` | `executor` | [executor.md](../agents/executor.md) | 성기사 · 승인된 소유 경로(`owned_paths`) 내 TDD 기반 최소 수직 슬라이스 구현 (`contaminated-zone` 접근 차단) |
| `Knight (나이트)` | `implementer` | [executor.md](../agents/executor.md) | 기사 · 클린룸 명세 기반 핵심 코어 정밀 구현 (`contaminated-zone` 접근 차단) |
| `Inquisitor (인퀴지터)` | `reviewer` | [reviewer.md](../agents/reviewer.md) | 심판관 · SOLID 원칙, 요구 정합성, 보안·권한 결함 독립 감사 및 수정 없는 Findings 도출 |
| `Cleric (클레릭)` | `verifier` | [verifier.md](../agents/verifier.md) | 치유사 · 실행 로그, SHA-256 해시, PNG 픽셀 디코딩, 보스 관문 및 원장 커버리지 100% 검증 오퍼레이터 |
| `Guardian (가디언)` | `privacy-guard` | [privacy-guard.md](../agents/privacy-guard.md) | 수호기사 · 학생·고객 개인정보(PII), 비밀키 유출 차단, 클린룸 무오염 경계 수호 |

## Routing Table

| Trigger | Primary | Required reviewers |
|---|---|---|
| 원천자료/카톡/PDF 분석 | `Sage` (`planner`) | `Guardian` (`privacy-guard`) when PII exists |
| 웹서비스 구조 설계 | `Archmage` (`architect`) | `Inquisitor` (`reviewer`) |
| 사용자 화면/관리자 화면 | `Bard` (`ux-designer`) / `Archer` (`design-critic`) | `Cleric` (`verifier`) |
| 바이너리/레거시 역설계 해부 | `Alchemist` (`analyst`) | `Guardian` (`privacy-guard`), `Inquisitor` (`reviewer`) |
| 실제 코드 구현 | `Paladin` (`executor`) | `Inquisitor` (`reviewer`), `Cleric` (`verifier`) |
| 학생/미성년자/CSV/export | `Guardian` (`privacy-guard`) | `Inquisitor` (`reviewer`) |
| 완료 주장 전 | `Cleric` (`verifier`) | `Inquisitor` (`reviewer`) for HIGH risk |
| 고객 전달 전 | doc-writer equivalent | `Guardian` (`privacy-guard`) |

## 선택적 전문 검토

- UI: `Cleric`(`verifier`)이 Evidence Collector 방식으로 실제 열람 이미지와 행동 증거를 분리한다.
- 완료: `Cleric`(`verifier`)이 Reality Checker 방식으로 승인 범위/소스/테스트/미검증을 대조한다.
- 역설계/클린룸: `Alchemist`(`analyst`)만 `contaminated-zone`을 열람하고 `approved-spec`을 작성하며, `Paladin`(`executor`) 및 `Knight`(`implementer`)는 `approved-spec`만 참조한다.
- 보안·접근성·성능은 과제 위험/명세에 필요한 때만 전문 검토를 추가하며 모든 역할을 자동 기동하지 않는다.
- 각 인계는 handoff-contract.example.json에 task/scope/owned paths/criteria/evidence/unresolved를 기록한다.
- 역할 및 인계 세부 기준: ../../../references/role-handoff.md

## Rule

하나의 에이전트가 계획·구현·검증을 모두 완료 처리하지 않는다. 최소한 구현자(`Paladin`)와 검증자(`Cleric`)는 분리한다.
