# 선택적 Codex exec 계약 — 0.2.0

2026-10-07 [공식 비대화형 문서](https://developers.openai.com/codex/noninteractive)와 [CLI reference](https://developers.openai.com/codex/cli/reference), 로컬 codex-cli 0.144.6의 --version/--help를 확인했다. 어댑터는 이 버전의 JSONL 계약 fixture로 검증했다. 실제 provider 호출·모델 품질·계정/요금/인증은 NOT_RUN이다. 추가로 설치된 0.161.0의 --version/exec --help 필수 옵션을 확인하여 capability probe 허용 목록에 넣었다. live inference는 여전히 NOT_RUN이며, 다른 CLI 버전은 UNVERIFIED_VERSION으로 진단한다.

```json
{"kind":"codex","executable":"codex","prompt":"이번 작업의 허용 범위만 수행하라.","sandbox":"read-only","retry_policy":"never"}
```

executable은 명시한 로컬 바이너리 또는 PATH의 codex다. 임의 extra_args·profile·config override·인증 우회 옵션은 제공하지 않는다. 기존 로그인은 CLI가 자기 지원 방식으로 사용할 수 있으나 하네스는 자격증명을 읽거나 만들지 않는다. 키 환경변수도 전달하지 않는다. 실제 사용의 인증/비용 권한은 사용자가 별도로 갖추며 이 패키지는 공급자 설정을 수정하지 않는다.

명령은 `codex --ask-for-approval on-request exec --json --sandbox read-only --ephemeral --ignore-user-config -`이고 prompt는 stdin이다. workspace-write는 manifest의 명시적 선택으로만 허용한다. danger-full-access, --yolo, --dangerously-bypass*, --full-auto, ignore-rules, skip-git-repo-check를 넣지 않는다. on-request 승인이나 신뢰 규칙이 필요한 비대화형 흐름은 오류/시간 제한으로 종료할 수 있다. 이를 우회하지 않고 APPROVAL_REQUIRED 또는 실패로 보고한다. Git 프로젝트 요건도 CLI의 기본 검사에 맡긴다.

유일한 turn.completed 종료 이벤트와 프로세스 exit 0, 오류 이벤트 없음이 모두 있어야 어댑터 PASS다. turn.failed/error, exit 실패, JSON 손상/알 수 없는 event, 종료 누락/중복/종료 뒤 event는 실패다. 알려진 event 유형만 받아들이며 raw message/command/reasoning/thread ID/prompt/stderr는 영속 로그에 넣지 않는다. 증거는 result/category/exit_code/event 유형·수/stream SHA256/CLI 버전/protocol만 남긴다. raw stdout/stderr는 접근 제한된 임시 파일에서 검사 후 닫고 저장하지 않는다. 출력은 8 MiB를 넘으면 실패한다. 공급자 출력의 세부 의미/오류 분류는 문구 기반 보조 진단이며 미래 모든 오류를 정확히 분류한다고 보장하지 않는다.

AUTH_REQUIRED/APPROVAL_REQUIRED/NOT_INSTALLED/UNVERIFIED_VERSION/PROTOCOL_ERROR/INCOMPLETE_OUTPUT/CLI_ERROR 등은 프로그램의 고정 진단이다. 기본 retry_policy=never는 어댑터나 검증 실패 후 공급자를 다시 호출하지 않는다. 명시적 transient 정책만 NETWORK_ERROR/RATE_LIMIT에 대해 max_attempts 범위에서 재시도한다. 네트워크 오류도 원격 부작용/과금이 이미 발생했을 수 있다. 자동 무한 재시도·exactly-once·자동 승인 없음.

전체 adapter timeout에는 무료 probe 시간도 포함된다. 추론 프로세스는 foreground 그룹에 두고 취소/timeout에 SIGTERM→SIGKILL로 정리한다. 분리된 daemon/원격 작업은 통제하지 못한다. 하네스는 OS 샌드박스를 제공하지 않는다. --sandbox는 CLI의 모델 명령 정책 요청이며 실제 호스트의 격리 동작은 공급자 실행을 허용한 환경에서 별도 확인해야 한다.

실행 전에 run --allow-provider를 명시해야 한다. 미지정이면 blocked/attempts=0이다. 이 플래그는 사용 한도를 자동 관리하거나 사용자 승인·호스트 정책을 대신하지 않는다. 결정적 어댑터와 가짜 CLI는 유료 연결 없이 시험하며 provider 성공으로 보고하지 않는다.
