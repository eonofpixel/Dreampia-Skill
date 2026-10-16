# v0.3 독립 검토

검토 대상: `/Users/cube-mac/Documents/Codex/2026-10-08/task-3/work`. 구현 파일은 직접 수정하지 않았고, 재현은 임시 디렉터리에서 수행했다. 검토 보고와 테스트 로그만 evidence/v0.3에 저장했다. dev 원본 저장소, Git identity, 사용자 프로세스, 실제 모델 로그인 및 provider 호출은 변경하지 않았다.

## 발견 및 수정 재검증

1. **P1 — 롤백 자체 중단 후 회복 불가능**. 초기 `harness/team_cli.py`의 rollback은 복구 파일을 쓰기 전에 journal을 남기지 않았다. 설치 후 rollback의 두 번째 관리파일 쓰기에 OSError를 주입하면 첫 파일만 이전 상태로 돌아가고, 다음 rollback은 `Conflict: rollback file changed`로 차단되었다. doctor는 1개 파일 충돌을 보고했다. 수정 제안은 롤백 전 reverse write-ahead transaction을 기록하는 것이었다. 구현자가 수정한 현재 rollback은 reverse journal을 기록한다. 독립 재현에서 중단 후 unfinished_transaction=True → explicit rollback으로 이전 committed 설치 회복 → doctor healthy=True → 다음 explicit rollback으로 원래 상태 복구를 확인했다. `test_interrupted_rollback_can_recover_then_retry`도 PASS. **해결됨**.

2. **P2 — owner/owns 선언 검증 누락**. 초기 `harness/core.py:validate`는 owner와 owns를 허용 필드에만 추가하여 owner=False/None, owns=["../../outside"], 두 작업의 동일 소유 경로를 수용했다. WORK_CONTRACT의 코드 검사 주장과 불일치했다. 현재 구현은 owner/owns 쌍, owner ID, 상대·정규화 경로, 중복 및 작업 간 부모/하위 경로 겹침을 검사한다. 독립 재검증에서 잘못된 owner·escape·쌍 누락·src/src-child 겹침 모두 REJECTED, src/tests 독립 선언 ACCEPTED. strict 회귀도 PASS. 실제 파일 접근 격리는 제공하지 않는다는 문서 계약을 확인했다. **해결됨**.

3. **P2 — 매우 큰 유효 JSON 정수의 비정상 오류 종료**. 초기 manifest timeout=10**400은 math.isfinite의 float 변환에서 OverflowError를 일으켜 CLI exit=1과 traceback으로 종료되었다. eval budget 및 deterministic delay도 같은 검사 순서였다. 현재 범위 검사를 먼저 수행하여 유효 범위 밖 큰 정수를 float로 변환하지 않는다. 독립 CLI 재검증 exit=2, traceback=False. strict 회귀는 실행 한도 및 평가 예산 큰 정수를 ValueError로 거부했다. **해결됨**.

## 검토 결과 및 실제 증거

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -v`: 84 tests, 20.817s, OK. 로그: `independent-review-tests.txt`. 실행 도중 새 strict 테스트 파일이 추가되었으므로 이것을 최종 단일 전체 suite 수로 주장하지 않는다.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p test_strict.py -v`: 추가 8 tests, 2.101s, OK. 로그: `independent-review-strict-tests.txt`.
- 기존 3개 감사 회귀(오타로 부작용 2회, Infinity 평가예산, probe timeout 후 resistant descendant 잔존)는 전체 suite에서 PASS.
- 설치 preview 무변경, 재설치 멱등성, 관리파일 수정 충돌보존, 부분 설치 transaction 회복, update/rollback, managed-only uninstall, static symlink 탈출 거부, 설정 오타·bool 혼동 거부, 프로젝트 .env가 설치 manifest/backup에 복사되지 않음 회귀 PASS.
- `schema.py`의 중복 JSON 키 및 Infinity/NaN 토큰 거부와 core/eval/team 입력 연결을 확인했다.
- 모델은 manifest와 팀 정책에서 gpt-6.1-sol/medium으로 고정되며 다른 model 또는 high 요청은 strict 테스트로 REJECTED. Codex adapter의 argv도 medium이며 자동 모델 상향 코드는 발견하지 않았다.

수정 재검증 이후 검토 범위에서 남은 실질 결함은 발견하지 않았다. 최종 패키징 이후 통합 suite·재추출 smoke는 구현 담당자가 현재 파일 기준으로 다시 확인해야 한다. 실제 유료 모델, AI 효과 A/B, Linux, remote CI, publication, deploy, Library 교체는 이 독립 검토에서 NOT_RUN이다. 정적 symlink 사전 검사 및 일반 단일 사용자 파일시스템을 검토했으며, 적대적 동시 파일시스템 교체를 통한 race 안전성까지 인증하지 않는다.

## 최종 변경 범위 추가 검토 — suite 검증

`eval_runner.read_suite`의 lock/suite/scenario strict fields, ID/split, 파일 경로 및 부모 파일 충돌 검증을 추가 검토했다. 다음 새 결함을 유효한 재계산 suite.lock과 /tmp prepare로 재현하여 구현자에게 전달했다.

- **P2 — 루트 또는 예약 request 파일의 하위 경로 허용**: files={".":"x"} 또는 {"request.txt/nested":"x"}가 read_suite에 수용된다. prepare는 out을 먼저 만든 뒤 IsADirectoryError로 실패한다. 전자는 빈 PurePosixPath parts를 거부하고, 후자는 request.txt와 그 하위 경로를 모두 거부해야 출력 생성 전 fail-closed가 된다.
- **P1/P2 — macOS의 대소문자 파일 경로 충돌**: files={"same":"A","SAME":"B"}가 read_suite 및 prepare에 수용되며 prepare SUCCESS지만 실제 출력은 same="B" 한 파일뿐이다. case_controls는 원본 두 파일을 포함하여 실제 생성 소스와 다른 initial_source를 기록한다. 같은 문제는 E1/e1 시나리오 디렉터리에도 적용될 수 있다. ID와 파일 이름 및 부모 경로 충돌을 casefold 기준으로 비교해 거부하되 원문 이름을 보존하는 최소수정을 제안했다. 이는 이 검토 macOS 임시 파일시스템에서 실제 재현한 문제다.

이 추가 검토는 최종 변경에서 발생한 경계만 대상으로 했으며 위 수정의 재검증이 완료되기 전에는 추가 검토 완료 PASS로 주장하지 않는다.

### 최종 변경 수정 재검증

위 suite 추가 검토에서 발견한 두 결함은 **해결됨**. 수정된 read_suite는 루트 파일 '.', request.txt 하위 경로, 대소문자 또는 NFC/NFD만 다른 파일명, 대소문자만 다른 부모파일/하위 경로 충돌, 시나리오 ID 대소문자 중복을 출력 디렉터리 생성 전에 거부한다. 기존 suite는 정상적으로 4개 시나리오·8개 arm을 준비했다. core 소유권도 NFC/casefold로 정규화한 부모/하위 경로 충돌을 독립 재현으로 거부함을 확인했다.

현재 파일 기준 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p test_strict.py -v`: **9 tests, 2.497s, OK**. 추가 독립 입력 재현 로그는 `independent-review-final-scope.txt`이며 root/request-child/case-files/unicode-files/parent-case가 모두 REJECTED_BEFORE_DESTINATION, 소유권 정규화 충돌 REJECTED, 정상 suite PREPARED를 기록한다. 요청한 최종 변경 범위에서 남은 실질 문제는 발견하지 않았다. 구현자가 보고한 전체 93+4 및 Python3.9/3.11 결과는 이 제한된 추가 검토에서 별도 재실행하지 않았다.

## 후속 최종 ZIP 검증 실패 및 v0.3.1 fixture 예산 변경 검토

이 후속 검토는 정상 Codex 프로토콜 fixture의 기본 예산 2→10초 변경과 timeout 회귀 유지에만 제한했다.

원본 ZIP `ai-dev-execution-harness.zip`의 실제 SHA256을 읽어 `aed4b82b5296ae22c9bcf85eb384ac6d197abc3f4ea77261f00e78fe4ce98d5f`로 확인했다. 해당 ZIP과 현재 작업본의 `harness/tests/test_codex.py`를 직접 비교한 결과 유일한 변경은 `def plan(self,exe,timeout=2)`에서 `timeout=10`으로의 변경이었다. 기존 결과 assertion은 모두 그대로다. `codex_adapter.py`와 `process.py`는 원본 ZIP과 byte-identical이었다.

`artifacts/post-delivery-verification/final-zip-python311.txt`는 실제 93개 시험 중 approval/auth/success 3개의 실패를 기록한다. approval/auth의 실제 category는 각각 APPROVAL_REQUIRED/AUTH_REQUIRED 대신 TIMEOUT이었다. 성공 fixture도 verified assertion에 실패했다. 이 실패는 삭제하거나 기존 버전 PASS로 재분류하면 안 된다. 별도 `codex-fixture-timing.json`은 동일 정상 fixture가 2초 및 10초 예산에서 올바른 오류/성공 분류를 반환하고, 전체 elapsed 0.661~1.2407초 및 version cold launch 0.4313~0.8417초를 기록했다. 이 측정은 실패한 실행의 실제 지연 원인을 확정하지는 않지만 여러 Python 프로세스를 시작하는 프로토콜 계약 시험에 2초 전체 예산이 환경 부하에 민감하다는 판단과 부합한다.

따라서 변경은 **정상 프로토콜 fixture의 실행 예산 보강으로 정당함**. 성공/오류 조건을 완화하거나 TIMEOUT을 SUCCESS로 변환하지 않았으며, runtime 실행 한도나 실제 timeout 회귀를 변경하지 않았다. `test_provider_timeout`은 명시적 timeout=.2, cancel 시험은 timeout=4를 그대로 유지한다. 정상 fixture 시험은 protocol/category/state 검증이 목적이며 2초 성능 인증이 아니다.

독립 실행: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p test_codex.py -v` → **13 tests, 18.180s, OK**. approval/auth/success와 별도 timeout/cancel 회귀 모두 PASS. 추가 임시 재현은 probe를 offline READY 응답으로만 mock하여 exec 단계의 10초 sleep fixture를 직접 timeout=.2로 실행했다. 결과 **FAIL/TIMEOUT, elapsed 0.229초**로, probe 지연에 의해 timeout 시험이 우연히 통과하는 경우와 별개로 실행단계 한도 유지도 확인했다. 실제 Codex 로그인·유료 모델 호출은 수행하지 않았다.

이 한 줄 시험 변경에서 실패 은폐 또는 timeout 보호 약화를 발견하지 않았다. v0.3.1 최종 ZIP 전체 CI 결과는 구현 담당자가 새 ZIP 기준으로 기록해야 하며, 이 제한된 검토는 이전 v0.3.0 ZIP의 실제 실패를 덮어쓰지 않는다.

## v0.3.1 첫 후보 ZIP의 orphan 잠금 시험 동기화 후속 검토

검토 범위는 `test_process.py:test_orphan_holds_lock_after_runner_kill`의 동기화 변경으로 제한했다. 첫 후보 ZIP `post-delivery-verification/ai-dev-execution-harness-0.3.1-first-candidate.zip`과 직접 비교하여 test_process 변경이 이 함수 안에만 있음을 확인했고, `core.py`, `process.py`, `codex_adapter.py`는 byte-identical이었다.

`post-delivery-verification/final-031-python311.txt`의 실제 결과는 93개 중 1개 FAIL이며, orphan 잠금 시험의 contender 반환값이 기대 2 대신 0이었다. 초기 자식은 marker를 쓴 뒤 1초만 sleep했으므로 contender CLI가 잠금을 확인하기 전에 자식이 끝나는 환경에서는 올바른 runtime도 이 assertion을 통과할 수 없었다.

수정은 명시적 `.harness/release` gate로 자식을 contender assertion 완료까지 유지하고, 비정상 시험 종료에도 최대 20초로 대기를 제한한다. contender의 returncode=2 assertion은 그대로 유지한다. finally에서 gate를 해제하고 실제 fcntl LOCK_EX|LOCK_NB 성공으로 잠금 해제를 확인한 뒤 다음 run의 returncode=0을 검사한다. 따라서 잠금 보장을 완화하지 않고 과거 sleep 기반 가정을 명시적 사건 동기화로 대체한다. runtime 코드 변경이나 FAIL을 PASS로 분류하는 처리도 없다.

독립 실행 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s harness/tests -p test_process.py -v` → **10 tests, 14.196s, OK**. 추가 임시 재현은 해당 함수의 첫 contender 호출만 의도적으로 1.5초 지연시켰다(기존 자식 생존 1초보다 긴 지연). 결과 **PASS, elapsed 2.346초**이며 contention rejection, lock release, next-run success가 모두 검사되었다.

이 변경은 정당한 시험 동기화 수정이며 요청한 변경 범위에서 실질 결함을 발견하지 않았다. 첫 후보 ZIP의 1개 실패는 보존하고, 수정 후 source 및 exact final ZIP full CI는 별도 결과로 기록해야 한다. 이 독립 검토는 해당 10개 시험과 지연 재현만 수행했으며 새 ZIP 전체 CI 완료를 주장하지 않는다.
