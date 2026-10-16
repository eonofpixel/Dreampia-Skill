# 상담 예약 서비스 명세

가상 사용자가 한 개의 상담 시간을 선택해 예약하고 자신의 예약을 확인한다. 가장 중요한 불변식은 “한 슬롯의 확정 예약은 최대 한 건”이다. 이 문서는 예제 명세이며 상태는 **draft**다. 실제 서비스, 사용자 승인, 구현, 테스트 실행은 없다. [작업·테스트](appointment-tasks-tests.md)와 [증거 기록](appointment-evidence.md)을 함께 읽는다.

## 범위와 성공 기준

- 대상: 가상 사용자 `user-a`, `user-b`; 둘 다 인증된 성인 테스트 계정이다. 실제 개인정보는 사용하지 않는다.
- 포함: 시간 조회, 예약 생성, 내 예약 조회, 충돌·재시도·접근 오류 처리
- 제외: 회원가입·로그인 제공자 구현, 결제, 취소·변경, 알림, 관리자, 다인 정원, 운영 배포
- 성공 기준: 사용자가 UI에서 예약 후 재조회할 수 있고, 동시 예약에서도 정원과 멱등성이 보존되며, 비인증·다른 사용자 접근이 차단된다. 아직 측정하지 않았다.
- 전제: 테스트 인증 fixture가 인증 주체를 서버에 제공한다. 실제 인증 제공자 연동 검증은 별도 범위다.

## 요구사항의 기준

모든 요구의 공통 소유자는 가상의 예제 제품 책임자이며, 출처는 이 패키지의 학습용 가정이다. 상태는 모두 draft이고 실제 사용자 승인 근거는 없다. 실제 프로젝트에서는 각 요구의 담당자·출처·승인 기록으로 바꾼다.

| ID | 요구사항과 수용 기준 | 관련 계약·상태 |
| --- | --- | --- |
| PRD-R001 | 인증된 사용자가 슬롯 목록과 가용 상태를 본다. 비인증 요청은 401이다. | API-001, UX-S001, UX-S004 |
| PRD-R002 | 가용 슬롯을 예약하면 소유자는 인증 주체로 결정되고, 성공 결과와 내 예약 재조회가 일치한다. 클라이언트가 소유자를 지정할 수 없다. | API-002, API-003, UX-S002, UX-S003 |
| PRD-R003 | 동일 슬롯에 두 인증 사용자가 서로 다른 키로 동시에 예약하면 정확히 한 요청만 201이고 나머지는 409 SLOT_UNAVAILABLE이다. DB에는 한 건만 남는다. | API-002, UX-S002 |
| PRD-R004 | 같은 인증 주체·키·정규화된 payload를 재요청하면 같은 booking ID와 내용을 반환한다. 첫 커밋은 201, 성공한 재시도는 200이다. 이미 성공한 키에 다른 payload면 409 IDEMPOTENCY_KEY_REUSED다. | API-002 |
| PRD-R005 | 예약 조회는 소유자만 가능하다. 비인증은 401, 다른 인증 사용자는 403, 존재하지 않는 ID는 404다. | API-003, UX-S004 |
| PRD-R006 | 날짜·시간은 DB의 시간대 지원 타입에 같은 instant로 저장하고 API는 ISO 8601 UTC 문자열로 반환한다. UI는 Asia/Seoul로 명시하여 표시한다. 시간대 없는 문자열을 생성·전달하지 않는다. | API-001, API-002, API-003, UX-S001, UX-S003 |

## UX 상태의 기준

| ID | 화면·상태 | 행동과 확인 기준 |
| --- | --- | --- |
| UX-S001 | 슬롯 선택: loading / empty / ready / error | 로딩 중 중복 조회 표시를 피한다. 빈 목록과 오류를 구분한다. 가용 시간만 선택 가능하며 Asia/Seoul 표시를 붙인다. 오류 시 명시적 재시도가 가능하다. |
| UX-S002 | 예약 확인: ready / submitting / conflict / error | 한 제출의 네트워크 재시도는 동일 멱등 키를 쓴다. 제출 중 버튼을 비활성화하되 서버 불변식에 의존한다. SLOT_UNAVAILABLE이면 목록 갱신 후 재선택한다. payload를 바꾼 새 예약 의도에는 새 키를 발급한다. |
| UX-S003 | 완료와 내 예약: loading / confirmed / error | POST 결과의 booking ID로 GET을 수행한다. 재로딩 후에도 같은 예약·시간이 보인다. GET 실패를 확정된 표시로 숨기지 않는다. |
| UX-S004 | 접근 오류: unauthenticated / forbidden / not_found | 401은 인증 필요, 403은 조회 권한 없음, 404는 찾을 수 없음으로 구분한다. 예약 세부 정보를 오류 응답에 담지 않는다. |

## 고정된 테스트 데이터

아래 값은 실행 시각이 아니라 재현 가능한 가상 fixture다. 각 독립 테스트는 초기 상태로 시작한다. 사용자 ID나 멱등 키에 비밀값을 넣지 않는다.

| 항목 | 값 |
| --- | --- |
| 가상 현재 시각 | `2030-01-01T00:00:00Z` |
| 첫 슬롯 | `slot-001`, 시작 `2030-01-15T01:00:00Z`, 종료 `2030-01-15T01:30:00Z`, capacity 1 |
| 두 번째 슬롯 | `slot-002`, 시작 `2030-01-15T02:00:00Z`, 종료 `2030-01-15T02:30:00Z`, capacity 1 |
| UI 기대 표시 | 첫 슬롯: 2030년 1월 15일 10:00~10:30, Asia/Seoul |
| 초기 예약 수 | 0 |
| 예시 멱등 키 | `intent-a-001`, `intent-b-001`; 비밀값이 아닌 테스트 식별자 |

## 공통 API 계약

- 경로만 정의한다. 배포 origin이나 실행 URL은 아직 없다.
- 모든 API는 인증 필요. 오류는 `{ "error": { "code": "...", "message": "..." } }` 형태다. 테스트는 안정된 code로 판정하고 메시지 문구에는 의존하지 않는다.
- 처리 순서: 인증 → 입력 형태 검증 → 해당 API 처리. 비인증은 자원 존재 확인보다 먼저 401 `UNAUTHENTICATED`를 반환한다.
- 예약 POST는 `Idempotency-Key` 헤더가 필수다. 이 예제의 키 길이는 1~128 ASCII 문자다. 누락·형식 오류는 400 `INVALID_REQUEST`다.
- POST JSON은 `{ "slotId": "slot-001" }`이며 slotId 외 필드는 400 `INVALID_REQUEST`다. ownerId·날짜·정원은 입력받지 않는다.
- POST의 정규화된 payload는 검증된 slotId 한 필드다. JSON 공백·키 순서는 payload 차이로 보지 않는다. 이 예제의 멱등성 보장은 성공 커밋에만 적용한다. 실패한 요청은 키를 점유하지 않는다.
- 인증 주체와 키의 조합으로 멱등성을 구분한다. 다른 사용자가 같은 키를 써도 서로의 예약 결과가 노출되지 않는다. 이 미니 예제에서는 성공 키를 만료시키지 않는다. 실제 제품의 보관 기간과 삭제 정책은 별도 결정이 필요하다.
- 예기치 못한 서버 실패는 500 `INTERNAL_ERROR`다. 내부 SQL·자격증명·스택은 반환하지 않는다. 이 응답만으로 예약이 없다고 단정하지 않으며 클라이언트는 같은 키로 안전하게 재시도한다.

| ID | 요청 | 성공 응답 | 실패 응답 |
| --- | --- | --- | --- |
| API-001 | GET `/v1/slots` | 200, `{items: [{id, startsAt, endsAt, capacity: 1, available}]}`. startsAt 오름차순. 빈 목록은 items: []. | 401; 예기치 못한 실패는 공통 500 |
| API-002 | POST `/v1/bookings` + 멱등 키 + slotId | 새 커밋 201, 성공한 동일 요청 재시도 200. 본문 `{booking: {id, slotId, startsAt, endsAt, status: "confirmed"}}`. | 400; 401; 없는 슬롯 404 `SLOT_NOT_FOUND`; 이미 찬 슬롯 409 `SLOT_UNAVAILABLE`; 성공 키의 payload 변경 409 `IDEMPOTENCY_KEY_REUSED`; 공통 500 |
| API-003 | GET `/v1/bookings/{id}` | 소유자에게 200, API-002와 같은 booking 구조 | 401; 다른 인증 사용자 403 `FORBIDDEN`; 없는 ID 404 `BOOKING_NOT_FOUND`; 공통 500 |

API-002의 우선순위: 형태 검증 뒤 성공한 멱등 레코드를 먼저 확인한다. 같은 payload면 슬롯이 이미 찼어도 기존 결과 200을 반환한다. 다른 payload면 변경된 slotId의 존재·가용성 검사보다 먼저 키 충돌 409를 반환한다. 새로운 키일 때만 슬롯 존재와 정원을 검사한다. 성공 응답 본문과 GET 응답의 예약 필드는 동일하다.

## 데이터와 최소 구현 설계

가상 구현 선택은 PostgreSQL 트랜잭션과 웹 UI + API다. 특정 프레임워크나 실제 실행 환경을 설치·선정한 기록이 아니다.

- slots: id PK, starts_at / ends_at 시간대 지원 timestamp, capacity는 1로 제한, starts_at < ends_at
- bookings: id PK, slot_id FK, owner_id 인증 주체 ID, status는 confirmed; 이 범위에는 취소가 없으므로 slot_id UNIQUE
- idempotency_results: user_id + key UNIQUE, canonical_slot_id, booking_id FK, 성공 응답 snapshot
- booking과 idempotency 결과는 같은 트랜잭션에서 커밋한다. 에러·프로세스 중단은 둘 다 롤백한다. 한쪽만 남는 저장을 허용하지 않는다.
- 동일 사용자·키 요청은 DB 기반 트랜잭션 잠금으로 직렬화한다. 다음으로 슬롯 row를 잠근다. 모든 예약 경로의 잠금 순서를 같게 유지한다. 앱 프로세스 내부 mutex만 쓰지 않는다.
- API에서 주고받는 시간은 `Z`가 있는 ISO 문자열이다. DB의 시간대 지원 타입에서 명시적으로 UTC 직렬화하고, UI 표시 단계에서만 Asia/Seoul로 변환한다.

다음은 구현 방향을 설명하는 의사코드다. 실제 함수·파일·테스트는 아직 없다.

```text
createBooking(authenticatedUser, idempotencyKey, input):
  validate shape; normalize payload to slotId
  BEGIN transaction
  acquire transaction-scoped DB lock for (authenticatedUser.id, key)
  prior = read idempotency_result for that user and key
  if prior exists:
    if prior.canonical_slot_id != slotId: return conflict after ending transaction
    return 200 with prior response after ending transaction
  slot = SELECT slot FOR UPDATE
  if no slot: roll back; return 404
  if booking exists for slot: roll back; return 409 SLOT_UNAVAILABLE
  booking = INSERT booking(owner = authenticatedUser.id, slot = slot.id)
  INSERT idempotency_result(user, key, slotId, booking.id, responseSnapshot)
  COMMIT
  return 201 with responseSnapshot
```

DB의 UNIQUE 제약도 마지막 방어선으로 유지한다. 고유 제약 위반·deadlock 등은 실제 DB 동작에 맞게 처리해야 하며, 무조건 500을 삼키고 201로 바꾸지 않는다. API 응답 전에 커밋이 완료되어야 한다. 커밋은 됐지만 응답이 유실되면 같은 키 재시도가 저장된 결과를 돌려준다.

## 결정과 위험의 기준

| ID | 내용 | 상태와 후속 조건 |
| --- | --- | --- |
| ADR-001 | 앱 내 잠금 대신 DB 트랜잭션·슬롯 고유 제약·DB 키 잠금으로 동시성과 멱등성을 보장하는 설계안 | draft. 실제 목표 DB에서 검증 후 승인 기록 필요 |
| ADR-002 | 예제에서는 비소유자 403, 없는 자원 404로 구분 | draft. 실제 제품은 자원 존재 노출 위험을 검토해 통일할지 결정 |
| RISK-001 | 두 요청을 동시에 시작하는 것만으로 항상 경쟁 상황이 재현되지는 않음 | draft. 테스트 전용 시작 barrier와 별도 연결을 쓰고 실제 DB의 최종 행 수 확인 |
| RISK-002 | 403과 404 구분이 자원 존재 여부를 드러낼 수 있음 | draft. 실제 서비스의 접근 정책·ID 추측 방어·감사 요구 검토 |
| RISK-003 | 인증 fixture·고정 시각은 실제 인증 제공자와 운영 clock 검증을 대신하지 못함 | draft. 통합 환경 승인 후 별도 검증 범위 결정 |

계약·범위 변경은 [변경 요청 프롬프트](../prompts/change-request.md)로 처리한다. 실제 승인 없이 결제·공유·데이터 삭제·배포 또는 자격증명 작업으로 확대하지 않는다.
