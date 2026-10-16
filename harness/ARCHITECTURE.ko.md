# 구조와 계약 — 제품 0.2.0

## 구성과 상태
cli.py는 구조화된 결과/종료 코드를 다루고 core.py가 manifest 검증·순차 DAG·시도 제한·검사·상태/백업·잠금·복구를 담당한다. codex_adapter.py는 선택 공급자 JSONL 계약, eval_runner.py는 모델을 호출하지 않는 고정 평가 준비/집계다. 테스트는 격리 tempfile과 가짜 CLI만 사용한다.

상태는 pending→running→verifying→verified, 실패는 failed, 선행 실패는 blocked, 취소는 cancelled, 오래된 증거는 stale, 복구/계획 변경은 recovery_hold다. 검사 결과 PASS/FAIL/NOT_RUN/TIMEOUT/CANCELLED는 작업 상태와 구별한다. verified는 현재 필수 명령의 성공 증거이며 명세 의미·사용자 승인·제품 인수·시각 리뷰를 보장하지 않는다.

manifest v1: version=1, requirements(고유 ID), tasks(비어 있지 않은 배열). 각 task에는 고유 id, 기존 requirements 링크, depends_on DAG, adapter, 비어 있지 않은 checks가 있다. max_attempts 기본2/최대10, timeout 기본30/최대3600초. check에는 계획 전체에서 고유 id, nonempty argv 배열, 선택 inputs 상대 파일 배열이 있다. command 어댑터는 argv, deterministic은 fail_attempts/delay, codex는 CODEX_ADAPTER.ko.md 계약을 따른다.

## 저장·잠금·복구
state v1/v2의 알려진 스키마만 읽고 v2로 새 상태를 쓴다. 임시 exclusive 파일→0600→flush/fsync→os.replace→부모 fsync로 저장한다. 저장 전 이전 유효 상태를 state.backup.json에 같은 방식으로 보존한다. backup/state/event는 하나의 트랜잭션이 아니므로 현재 스냅샷과 실제 재검증을 기준으로 한다.

runner는 root/.harness/lock의 POSIX flock를 비차단 배타 획득한다. 자식에게 잠금 FD를 전달해 runner 크래시 뒤 foreground 자식이 끝날 때까지 중복 실행을 막는다. 실행 중 runtime 폴더/lock를 이동·삭제하거나 자식이 FD를 닫고 daemon으로 분리되면 보장이 적용되지 않는다. NFS·적대적 프로세스 격리는 지원하지 않는다.

recover는 잠금을 얻고 현재/백업 원문을 고유 quarantine 디렉터리에 보존한 뒤 모든 작업을 recovery_hold/replay_required로 만든다. valid backup이 있어도 과거 verified를 복원하지 않는다. 알 수 없는 시도 이력은 소진한 것으로 보수적으로 취급한다. run은 held 작업을 실행하지 않는다. reverify는 어댑터 없이 현재 필수 검사만 수행한다. authorize-replay --task ID --accept-side-effects는 특정 작업을 새 유한 예산의 pending으로 바꾸지만 명령은 아직 실행하지 않는다. manifest 변경도 모두 hold 처리하므로 설정 변경만으로 외부 부작용을 재실행하지 않는다.

SIGINT/SIGTERM과 별도 cancel 요청은 협조적 취소다. 새 run은 과거 취소 요청을 지우고 재개한다. 시작한 시도는 취소/크래시에도 소비된다. ordinary --retry-failed는 recovery_hold를 해제하지 않는다. 예산 소진의 자동 초기화나 사용자 소스 삭제는 없다.

## 소스·입력·증거
전체 프로젝트의 파일 상대 경로/내용/권한 비트와 디렉터리 구조/권한을 해시에 포함한다. **루트 .harness와 .git만 제외**하고 중첩 같은 이름 및 __pycache__는 포함한다. inode/mtime 자체는 digest 구성요소가 아니며 해시를 읽는 동안 변경 탐지에만 사용한다. Python 실행은 bytecode 생성을 끈다. check.inputs는 중요 파일의 경로·존재 계약이며 어댑터 생성 뒤 검사 직전에 확인한다. 이 배열이 해시 범위를 축소하지 않는다.

소스 탐색은 디렉터리 FD, O_DIRECTORY/O_NOFOLLOW와 dir_fd 상대 열기를 사용하며 심볼릭 링크/특수 파일·경로 탈출을 거부한다. 파일/디렉터리를 읽는 동안 stat 변화도 확인한다. 전후 소스 digest가 달라지면 실패하고 뒤 작업의 수정으로 오래된 앞 작업도 최종 소스로 재검증한다. 빈 디렉터리 삭제와 실행 권한 변경도 stale다.

원자적 전체 트리 스냅샷·서명·적대적 attestation은 제공하지 않는다. 실행 중 외부 작성자가 소스를 바꾸지 않는 신뢰 계약이며 수정 후 원복의 모든 타이밍은 탐지한다고 보장하지 않는다. 임의 명령의 외부 파일/원격 상태/전역 도구 버전/mtime 조건/루트 runtime 의존을 자동 추론하지 못한다. source hash의 보장은 명시한 파일 집합/메타데이터 범위다.

각 evidence는 source SHA256, checks_digest, check id/result/exit_code/UTC at/duration/argv_digest, at/run ID다. fresh는 필수 check의 순서/ID/명령 digest/PASS/exit 0과 현 소스를 모두 확인한다. state/evidence의 잘못된 타입·알 수 없는 필드·알 수 없는 상태·타이밍/해시 형식은 STATE_CORRUPT로 막는다. trace도 traceback 대신 구조화된 오류/rows=[]/exit2다.

## 범용 command 어댑터
cwd는 프로젝트 루트, stdin은 UTF-8 JSON: protocol=1, project 절대 경로, task manifest 객체, attempt, idempotency_key=manifest digest:TASK ID. stdout/stderr는 저장/파싱하지 않는다. exit0은 어댑터 성공일 뿐이며 필수 checks가 완료를 판정한다.

실패/실행파일 없음/timeout은 유한 예산 내 재시도할 수 있다. wrapper가 동일 키의 중복 실행을 견디고 foreground로 모든 자식의 종료를 책임져야 한다. 외부 부작용/원격 과금의 exactly-once나 분산 트랜잭션은 없다. 공급자 어댑터의 기본 재시도는 더 보수적인 never다.

timeout/취소는 그룹에 SIGTERM 뒤 0.3초 대기 후 SIGKILL이다. 정상 종료에도 그룹에 남은 자식을 정리한다. setsid/daemonize·원격 작업은 통제하지 못한다. start_new_session은 그룹 관리이지 보안 샌드박스가 아니다.

## 개인정보·권한·범위
일반 자식 환경은 PATH/LANG/LC_ALL/SYSTEMROOT/TMPDIR와 PYTHONDONTWRITEBYTECODE=1이다. API 키·일반 사용자 환경변수를 전달하거나 수집하지 않는다. raw argv/context/stdout/stderr/prompt/예외 메시지는 이벤트에서 제외한다. 이벤트는 고정 메타데이터·ID·결과·exit·hash만 보존한다. ID에 비밀을 넣지 않는다. quarantine은 원문 보존 목적이므로 운영자가 민감 내용 포함 가능성을 다루고 공개하지 않는다.

이 하네스는 현재 사용자의 subprocess 권한으로 실행하며 OS 파일/네트워크/과금 샌드박스를 제공하지 않는다. 사용자 승인과 호스트 정책을 대신하지 않는다. trusted manifest/작은 로컬 프로젝트/순차 작업에 맞춘 제품이며 실제 provider 추론·AI 성능·원격 CI·Linux 지원 확인은 수행한 증거가 없으면 NOT_RUN이다.
