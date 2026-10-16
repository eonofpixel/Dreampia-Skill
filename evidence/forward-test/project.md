# 작은 예약 규칙 — 현재 명세 v1

## 현재 명세

- 목적: 호출자가 슬롯을 예약하고 안전하게 같은 요청을 재시도하도록 개발을 준비한다.
- 첫 사용자: 예약 기능을 호출하는 클라이언트 개발자. 실행 모드: **문서만**, 간편 모드.
- 허용: 요구·계약·작업·테스트 계획·문서 정적 검증. 제외: 앱 구현/실행, 추가 설치, AI 호출, 외부 변경, 배포, 취소·결제·시간표·인증 시스템.
- 종료 조건: 세 요구가 계약→작업→테스트→현재 증거로 연결되고 미실행 검증과 재개 조건이 명시된다.
- 출처: 위임된 사용자 요청(2026-10-07). 요구 범위는 사용자 지정이며 세부 계약은 아래 ADR의 draft 기술 가정이다.
- 환경: macOS 호스트, zsh, 작업 경로 `forward-test`. 상위 cwd는 Git 저장소가 아니므로 브랜치·커밋·미커밋 차이는 해당 없음. 기존 skill/harness는 읽기만 했다. 새로운 대상 폴더였으며 기존 파일을 덮어쓰지 않았다.
- 문서 지도: 요구·계약·설계=`project.md#현재-명세`, 기대 결과=`project.md#작업과-테스트`, 작업·결정=`project.md#작업과-테스트`, 실제 증거·인계=`handoff.md`, 원시 검사=`evidence/doc-check.txt`.

### 요구와 인수 조건 (draft)

- PRD-R001 필수 입력: slot과 user가 모두 유효하면 예약 판단을 진행한다. 누락/null/빈 문자열/공백뿐/문자열 외 입력은 INVALID_INPUT으로 거부하며 상태를 바꾸지 않는다. 둘 다 잘못되면 같은 INVALID_INPUT을 반환한다.
- PRD-R002 동일 요청 멱등성: 빈 슬롯에 (slot,user)를 처음 요청하면 CREATED와 예약 레코드를 반환한다. 같은 (slot,user)를 다시 요청하면 EXISTING과 동일 reservationId를 반환하고 레코드 수는 증가하지 않는다. 재시도 전에 응답이 유실되어도 동일하다.
- PRD-R003 다른 사용자 중복 거부: 이미 A에게 예약된 slot에 B가 요청하면 SLOT_TAKEN을 반환하며 소유자와 레코드 수는 바뀌지 않는다. 같은 슬롯의 동시 요청에서도 소유자는 최대 한 명이다.

### API-001 계약과 상세 설계 (draft)

개발 경계는 UI 없는 예약 명령 `reserve({slot,user})`와 저장소 재조회다. HTTP·프레임워크를 확정하지 않는다. 입력은 대소문자를 구별하는 비어 있지 않은 문자열이며 앞뒤 공백은 거부한다. 길이 제한은 현재 범위에서 두지 않는다. 응답은 성공 `{status: CREATED|EXISTING, reservation:{reservationId,slot,user}}`, 실패 `{error: INVALID_INPUT|SLOT_TAKEN}`이다. 실패에 다른 사용자의 식별자를 노출하지 않는다. 예약 ID는 불투명하고 유일하며 재시도에도 유지된다.

저장 모델은 slot 고유 키와 reservationId 고유 키, user를 갖는다. 상태는 비어 있음→예약됨이며 삭제/취소가 없으므로 이 기능 수명 동안 멱등성이 유지된다. (slot,user)가 요청 정체성이며 별도 requestId가 필요하지 않다. 서로 다른 문자열은 서로 다른 식별자다. 슬롯은 불투명 식별자이므로 시각·시간대·금액 단위는 미적용이다.

검증 후 원자적 생성 또는 기존 레코드 읽기/비교를 수행한다. slot 고유성은 저장소가 원자적으로 강제한다. 생성 충돌은 재조회하여 같은 user면 EXISTING, 다른 user면 SLOT_TAKEN으로 처리한다. 조회 실패/저장 실패를 성공이나 SLOT_TAKEN으로 숨기지 않는다. 구현 스택 선정 시 저장 오류 계약과 트랜잭션 방법을 확정해야 한다. 단순한 사전 조회 후 무제약 삽입은 허용하지 않는다.

user는 호출자가 제공한 식별자이며 실제 인증/소유 권한의 증거가 아니다. 이 준비 문서는 격리된 규칙 개발용이다. 외부 공개 서비스로 확대되면 인증 주체에서 user를 도출하는 계약과 권한 테스트를 먼저 추가해야 한다.

### 결정과 위험

- ADR-001 (draft): 동일 요청을 (slot,user)로 정의. 이유: 지정된 작은 규칙에 필요한 필드만 사용. 취소·다중 예약·requestId가 추가되면 재검토한다.
- ADR-002 (draft): 원자적 slot 고유성으로 경쟁을 보호. 메모리 락은 단일 프로세스 실험에만 적합하며 영속/다중 프로세스 지원의 근거가 아니다.
- RISK-001: 저장소/런타임 미선정으로 동시성·장애 복구가 아직 검증되지 않음. 담당: 재개 개발자. 구현 시작 전에 실제 저장소와 격리 테스트 환경을 정한다.
- RISK-002: 요청 user를 신뢰하면 외부 서비스에서 사칭 가능. 현재 규칙 범위를 외부 공개로 확대하기 전에 인증 계약을 추가한다.

## 작업과 테스트

| 작업 / 상태 | 요구 / 계약 | 선행 | 예상 소유 파일 | 입출력·범위 / 완료·중단·재개 조건 |
|---|---|---|---|---|
| TASK-001 / verified | PRD-R001~003, API-001 | 없음 | project.md, handoff.md, evidence/doc-check.txt | 문서 작성과 연결 검토. 문서 검사 PASS로 완료. 기능 검증은 포함하지 않음. |
| TASK-002 / deferred | PRD-R001~003, API-001 | TASK-001, 구현 허용 범위·스택 확정 | 미래 src/reservation.*, tests/reservation.* (미생성) | 입력→원자 저장→재조회→결과의 단일 수직 기능. TEST-001~007 실제 Red→Green→Refactor 및 회귀 PASS로 완료. 승인된 구현 범위/격리 저장소 없으면 중단. |
| TASK-003 / deferred | PRD-R002~003, API-001 | TASK-002 | 미래 tests/reservation-integration.*, evidence/runtime-* (미생성) | 실제 저장소 재조회·경쟁·재시도 확인 및 자기 리뷰. TEST-008~010 PASS로 완료. backend 접근/도구 없으면 해당 검사 NOT_RUN. |

미래 파일은 계획 경로이며 현재 링크로 표시하지 않는다. 미래 명령은 스택 미선정으로 확정하지 않았으며 실제 실행 기록과 구별한다. 런타임 선택 후 TASK-002 착수 전에 정확한 테스트 명령·버전을 handoff에 기록한다.

| 테스트 | 요구 | 입력/절차 | 기대 결과 | 현재 결과 / 증거 |
|---|---|---|---|---|
| TEST-001 | PRD-R001 | slot과 user 각각 누락/null/빈 값/공백/숫자, 둘 다 잘못됨 | INVALID_INPUT, 저장 변경 0 | NOT_RUN / handoff.md |
| TEST-002 | PRD-R001 | 앞뒤 공백 입력, 문자열 대소문자 경계 | 공백은 거부; 대소문자는 별도 ID | NOT_RUN / handoff.md |
| TEST-003 | PRD-R001~002 | 빈 S에 A 요청, 재조회 | CREATED, 저장 S/A 1개 | NOT_RUN / handoff.md |
| TEST-004 | PRD-R002 | S/A 반복 호출 | EXISTING, 동일 ID, 1개 | NOT_RUN / handoff.md |
| TEST-005 | PRD-R003 | S/A 후 S/B | SLOT_TAKEN, S/A 유지 | NOT_RUN / handoff.md |
| TEST-006 | PRD-R001~003 | 다른 슬롯 S2/A | 독립 CREATED, 두 슬롯 각 1개 | NOT_RUN / handoff.md |
| TEST-007 | PRD-R001~003 | 거부 직후 유효한 다른 슬롯 요청 | 거부의 부작용 없이 성공 | NOT_RUN / handoff.md |
| TEST-008 | PRD-R002 | 저장 성공 뒤 응답 유실을 주입하고 같은 요청 재시도 | 동일 ID EXISTING, 1개 | NOT_RUN / handoff.md |
| TEST-009 | PRD-R003 | 실제 저장소에서 S/A와 S/B를 장벽으로 동시 시작·재조회 | CREATED 하나, SLOT_TAKEN 하나, 소유자 1명 | NOT_RUN / handoff.md |
| TEST-010 | PRD-R002 | 실제 저장소에서 S/A 동시 요청·재조회 | CREATED 하나, 나머지 EXISTING, 모두 동일 ID | NOT_RUN / handoff.md |

TEST-DOC-001: 로컬 문서의 요구→작업→테스트 ID·증거 경로 존재, 필수 요구 누락, 미실행 결과 구별을 정적 검사한다. 링크 존재만으로 의미가 보장되지 않아 위 기대 결과와 계약은 자기 검토한다. 앱이 없으므로 Red/Green/Refactor, 백엔드/성능/보안 실행 및 화면·접근성 검사는 NOT_RUN 또는 UI 미적용이다.
