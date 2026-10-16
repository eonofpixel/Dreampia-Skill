# 예약 기능 작업과 테스트 계획

[예약 명세](appointment-spec.md)를 만족하는 최소 수직 기능을 정의한다. 테스트 ID의 유일한 정의는 아래 테스트 표다. 다른 문서는 ID를 참조하며, 실제 결과의 기준은 [증거 기록](appointment-evidence.md)이다. 앱·테스트 파일은 생성하지 않았고 모든 실행 결과는 NOT_RUN이다.

## 작업 단위

| ID | 사용자 결과와 범위 | 요구사항·계약 | 검증 참조 | 선행 조건·완료 조건 | 상태 |
| --- | --- | --- | --- | --- | --- |
| TASK-001 | 인증된 사용자가 시간 목록을 보고 상태와 시간대를 이해한다. 목록 UI → API → DB fixture를 연결한다. | PRD-R001, PRD-R006; UX-S001, UX-S004; API-001 | TEST-001의 API-001 사례, TEST-007의 목록 사례, TEST-010 | 목표 테스트 DB·인증 fixture 준비. 세 검증의 관련 사례가 현재 코드에서 PASS | draft |
| TASK-002 | 한 시간을 예약하고 완료 화면에서 재조회한다. 충돌·재시도·소유자 접근까지 같은 사용자 여정 안에서 구현한다. | PRD-R002~PRD-R006; UX-S002~UX-S004; API-002, API-003 | TEST-001의 나머지 사례, TEST-002~TEST-009 | TASK-001 완료와 계약 준비. 모든 관련 필수 사례 PASS, DB 불변식·E2E 증거 확보 | draft |

각 작업의 예측 파일 범위는 UI, API handler, 예약 repository, DB migration, 해당 테스트다. 실제 저장소를 검사한 뒤 경로를 확정한다. 기존 코드가 있다면 필요한 부분만 수정한다. 문서만 모드에서는 위 작업을 계획으로 남기고 앱·DB를 실행하지 않는다.

## 테스트 단일 정의

모든 테스트는 필수다. 아래의 “예상”은 수용 기준이며 관찰된 실행 결과가 아니다. 독립 테스트마다 빈 예약 상태와 명세의 고정 fixture를 준비한다. fixture 초기화는 명시적으로 승인한 격리 테스트 DB에서만 허용하며 운영 데이터 삭제 명령을 사용하지 않는다.

| ID | 수준·관련 요구사항 | 준비와 자극 | 예상 결과 |
| --- | --- | --- | --- |
| TEST-001 | API 보안; PRD-R001, PRD-R002, PRD-R005 | 인증 없이 API-001~API-003을 각각 호출. POST에는 유효한 payload와 키 사용. | 모두 401 UNAUTHENTICATED. 예약·멱등 레코드 변화 없음 |
| TEST-002 | E2E; PRD-R002, PRD-R006 | user-a로 목록에서 slot-001 선택 → 예약 → 완료 화면 → 새로고침·재조회 | 최초 POST 201, GET 200. 동일 booking ID와 slotId, DB 예약 1건, 소유자는 user-a. UI에 2030년 1월 15일 10:00~10:30과 Asia/Seoul 표시 |
| TEST-003 | 실제 DB 통합; PRD-R003 | 별도 연결의 user-a/key-a와 user-b/key-b가 barrier를 통과해 같은 slot-001에 POST. 처음 예약 0건 | 결과 상태를 정렬하면 [201,409]. 409의 code는 SLOT_UNAVAILABLE. slot-001 예약은 정확히 1건이고 성공 사용자 소유. 멱등 결과도 성공 사용자 것 1건 |
| TEST-004 | 실제 DB 통합; PRD-R004 | user-a가 같은 key와 slot-001로 순차 2회 POST | [201,200], 동일 booking ID·응답 본문. 예약 1건, 해당 멱등 결과 1건 |
| TEST-005 | API·DB 통합; PRD-R004 | user-a/key-a/slot-001 성공 후 같은 user/key로 slot-002 요청 | 두 번째는 409 IDEMPOTENCY_KEY_REUSED. 첫 예약 보존, slot-002 예약 0건, 기존 멱등 결과 변경 없음 |
| TEST-006 | API 보안; PRD-R005 | user-a 예약을 user-b가 GET. 별도 사례로 인증된 사용자가 없는 ID를 GET | 각각 403 FORBIDDEN, 404 BOOKING_NOT_FOUND. 응답에 booking 세부 정보가 없고 DB 변화 없음 |
| TEST-007 | 계약·UI; PRD-R006 | API-001과 예약 후 API-002/003의 시간 필드를 검사하고 동일 슬롯의 UI 표시 확인 | startsAt/endsAt가 명세 fixture와 같은 Z 포함 ISO 문자열. 시간대 지원 DB 값과 동일 instant. UI에서 한 번만 Asia/Seoul 변환하며 날짜·시간대 표시 일치 |
| TEST-008 | API 검증; PRD-R002, PRD-R004 | POST의 키 누락, 빈 키, 129자 키, 비ASCII 키, slotId 누락, 추가 ownerId, 없는 slotId를 각각 독립 요청 | 마지막은 404 SLOT_NOT_FOUND, 나머지는 400 INVALID_REQUEST. 모두 booking·멱등 결과 0건 |
| TEST-009 | 실제 DB 통합; PRD-R004 | 같은 user-a/key-a/slot-001 요청 2개를 별도 연결에서 barrier로 동시 시작 | [200,201], 동일 booking ID·응답. 예약 1건, 해당 멱등 결과 1건. 409나 500이 나오면 실패 |
| TEST-010 | UI 상태; PRD-R001 | API-001을 테스트 더블로 지연·빈 목록·500·회복 응답 순서의 독립 사례로 제공 | loading, empty, error가 구별되고 오류에서 재시도 후 ready로 이동. 더블 사용이므로 실제 DB 통합 증거로 사용하지 않음 |

## Red Green Refactor 완료 기준

| 단계 | 확인할 것 | 기록할 것 |
| --- | --- | --- |
| Red | TASK-001부터 시작한다. 동작을 정의한 테스트를 먼저 만들고 미구현 행동 때문에 실패함을 실제 실행으로 확인한다. TASK-002에서는 특히 동시성·멱등성의 실패 원인을 확인한다. | TEST ID, 명령, 코드 기준점, FAIL 출력, 예상 실패 원인과 실제 원인. 환경 오류만 있으면 Red 미확인 |
| Green | 명세의 최소 구현으로 대상 테스트를 통과시킨다. TASK-002에서는 API 응답뿐 아니라 DB 행 수·소유자·멱등 레코드를 확인한다. | 대상 테스트 PASS와 실제 출력. 실패·미실행이 있으면 verified로 바꾸지 않음 |
| Refactor | 계약을 유지하며 구조를 개선한다. 개선 필요가 없으면 이유를 남긴다. 최종 코드에서 대상·회귀·E2E 테스트를 실행한다. | 최종 코드 기준점과 재실행 결과. 이전 실행 로그를 새 코드의 성공 증거로 대체하지 않음 |

## 동시성 테스트 의사코드

아래는 TEST-003의 구현 예시다. **의사코드이며 NOT_RUN이다.** fixture와 API client, barrier, DB 조회 어댑터를 실제 테스트 도구에 맞게 구현해야 한다. `resetIsolatedFixture`는 승인된 격리 테스트 DB에만 연결되도록 안전장치가 필요하다. 최종 응답만 비교하지 않고 데이터 불변식도 확인한다.

```text
resetIsolatedFixture(clock = "2030-01-01T00:00:00Z")
barrier = createBarrier(parties = 2)

async request(user, key):
  client = createAuthenticatedTestClient(user, separateConnection = true)
  await barrier.wait()
  return await client.post("/v1/bookings",
    header = {"Idempotency-Key": key},
    body = {"slotId": "slot-001"})

responses = await all(
  request("user-a", "intent-a-001"),
  request("user-b", "intent-b-001")
)
assert sort(responses.status) == [201, 409]
assert failedResponse.error.code == "SLOT_UNAVAILABLE"
rows = db.bookingsForSlot("slot-001")
assert rows.length == 1
assert rows[0].id == successfulResponse.booking.id
assert rows[0].owner_id == successfulRequest.user
assert db.successfulIdempotencyResultsForSlot("slot-001").length == 1
```

동시 시작 barrier만으로 DB 경쟁이 충분히 발생하지 않을 수 있다. 필요하면 테스트 전용 동기화 지점으로 첫 트랜잭션이 슬롯 잠금을 보유한 상태에서 두 번째가 대기하는 것을 확인한다. 운영 코드를 임의로 지연시키거나 테스트용 비인가 API를 노출하지 않는다. 실제 DB 연결과 격리 수준을 증거에 남긴다.

TEST-009는 위 자극에서 사용자와 키를 동일하게 하고 예상 상태를 [200,201]로 바꾼 별도 테스트다. 두 응답의 booking ID와 전체 booking 값이 같아야 한다. TEST-005에서는 먼저 성공 커밋을 확인한 뒤 payload만 slot-002로 바꾼다.

## 수직 여정 E2E 의사코드

TEST-002는 다음 연결을 검증한다. **의사코드이며 NOT_RUN이다.** 인증은 테스트 fixture이며 실제 로그인 제공자 테스트를 대신하지 않는다.

```text
seed isolated DB; freeze server and UI clock to fixture instant
open app with authenticated fixture user-a
wait for real GET /v1/slots response
select slot-001; choose confirm
observe real POST /v1/bookings response == 201
remember returned booking.id
assert completion page reads that ID via real GET /v1/bookings/{id}
assert displayed local time and zone match spec
reload page
assert same booking ID and same displayed time remain
assert DB has one booking for slot-001 owned by user-a
```

실제 UI 실행 URL이 없으므로 open app의 주소는 정하지 않았다. 저장소를 확인한 뒤 실제 시작 명령·주소·테스트 runner·파일 경로를 확정하여 [증거 기록](appointment-evidence.md)에 남긴다. 명령을 예상해서 실행 완료처럼 적지 않는다.

## 추적 연결 요약

| 요구사항 참조 | 계약 참조 | 작업 참조 | 검증 참조 |
| --- | --- | --- | --- |
| PRD-R001 | API-001 | TASK-001 | TEST-001, TEST-010 |
| PRD-R002 | API-002, API-003 | TASK-002 | TEST-002, TEST-008 |
| PRD-R003 | API-002 | TASK-002 | TEST-003 |
| PRD-R004 | API-002 | TASK-002 | TEST-004, TEST-005, TEST-008, TEST-009 |
| PRD-R005 | API-003 | TASK-002 | TEST-001, TEST-006 |
| PRD-R006 | API-001~API-003 | TASK-001, TASK-002 | TEST-002, TEST-007 |

이 표는 참조 색인이다. 요구사항·계약의 정의는 예약 명세에 있고 테스트 정의는 이 문서의 테스트 표 한 곳에만 있다.
