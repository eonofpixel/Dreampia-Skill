# 별도 로컬 하네스 연동

공통 스킬은 이 폴더 안의 지침으로 유지한다. 통합 ZIP에는 형제 폴더 `harness/`의 실행 프로그램·테스트·한글 사용법·계약이 있다. 스킬 단독 ZIP에는 실행 하네스를 넣지 않는다. 하네스 없이도 스킬의 수동 절차를 적용할 수 있다.

하네스 MVP는 Python 3.9+ / POSIX 로컬 CLI다. `harness.json`에 요구 ID·작업·의존성·어댑터·필수 검증 명령을 정의한다. `run`, `status`, `trace`, `cancel`, `validate`를 제공한다. 실행 방법은 통합 패키지의 `harness/README.ko.md`, 계약은 `harness/ARCHITECTURE.ko.md`를 읽는다. 단독 스킬을 사용할 때 이 외부 경로가 존재한다고 가정하지 않는다.

| 항목 | 지침/사람의 판단 | MVP 프로그램의 강제 검사 |
|---|---|---|
| 명세 | 의미·범위·결정 근거·현재/변경분 통합 | manifest 요구 ID가 작업에 연결됨 |
| 작업 | 작업 분해·허용 범위·파일 소유 | 유일 ID·DAG·선행 작업 상태 |
| 검증 | 테스트가 실제 요구를 관찰하는지·Red 이유 | 명령 필수·종료 코드·시간 제한·실행 실패 |
| 완료 | 제품 인수·코드/시각 리뷰·승인 | 모든 작업에 현 소스 해시의 PASS 필요 |
| 재개 | 외부 부작용·실제 호스트 확인 | 원자적 저장·프로세스 잠금·누적 시도 제한 |
| 안전 | 권한·격리·비용·민감 데이터 판단 | 출력/argv/context를 이벤트에서 제외 |

검증 명령은 임의 프로그램이므로 `python3 -c pass` 같은 무의미한 명령의 의미를 프로그램이 알아낼 수 없다. trace는 구조적 링크만 검사한다. 해시 증거는 신뢰된 작업 공간의 재현 기준이며 위조 방지 서명이나 적대적 작업 격리가 아니다. 승인·실제 AI 코딩 품질·샌드박스는 하네스가 보장하지 않는다.

작은 실행 예제는 통합 ZIP의 `harness/examples/slots`에 있다. 순수 메모리 예약 규칙 4개 테스트와 2개 의존 작업으로 제한한다. 기존 `assets/examples/appointment-*`는 계속 가상 서비스 문서이며 NOT_RUN 상태를 유지한다. 로컬 예제 PASS를 실제 예약 서비스의 저장·인증·동시성 PASS로 옮기지 않는다.

## 하네스 0.2.0 연동 변경

소스 해시에서 루트 .harness/.git만 제외하고 중첩 같은 이름·모든 __pycache__·파일 권한·빈 디렉터리 구조를 포함한다. check.inputs는 중요한 상대 파일의 존재/경로 계약이며 전체 프로젝트 해시를 줄이지 않는다. 링크·경로 탈출·해시 읽는 동안의 변경을 거부하지만 원자적 트리 스냅샷은 아니다. 외부 입력/mtime/전역 도구·원격 상태를 자동 포함한다고 말하지 않는다.

state v1/v2를 검증해 읽고 v2로 쓴다. 손상 evidence나 알 수 없는 필드는 STATE_CORRUPT다. recover는 원문을 runtime quarantine에 보존하고 recovery_hold로 만든다. backup의 verified는 복원하지 않는다. reverify는 어댑터 없이 현재 실제 checks를 실행한다. authorize-replay는 정확한 작업과 부작용 인정이 있을 때만 새 유한 예산을 부여한다. manifest가 바뀌어도 hold 처리하므로 설정 변경만으로 외부 작업을 반복하지 않는다. 이 내부 상태를 문서의 approved/verified 승인 근거로 자동 변환하지 않는다.

Codex 선택 어댑터에는 무료 doctor와 명시적 run --allow-provider가 있다. 현재 설치 0.144.6의 help/version 및 가짜 CLI JSONL fixture만 검사했다. 실제 provider 추론/인증/비용/품질은 NOT_RUN이다. user/project 규칙·승인·샌드박스를 우회하는 플래그를 넣지 않는다. 기본 공급자 재시도는 never이며 transient만 명시적인 유한 예산에 허용한다.

통합 ZIP의 evals/suite.json과 suite.lock.json은 E1/E2 baseline, E3/E4 holdout의 초기 파일·요청·rubric을 고정한다. harness/eval_runner.py prepare는 두 arm의 폴더와 NOT_RUN 템플릿을 만들고 aggregate는 원시 증거 파일/해시와 controls를 검사해 집계한다. API 호출·자동 품질 판단은 하지 않는다. 모든 실제 비교가 미실행이면 effect_score=null이다. 단독 스킬에는 공통 지침/시나리오를 유지하고 이 외부 소프트웨어가 존재한다고 가정하지 않는다.

## 하네스 0.5.2 팀 통합

manifest·task·adapter·check 미지 키, 중복 JSON 키, 비유한 토큰을 거부한다. 정수/실수/boolean을 구분하고 실행 예산·평가 예산 범위를 검사한다. 선택 owner/owns 선언은 반드시 함께 지정하며 작업 간 겹치는 경로를 거부한다. 실제 파일 쓰기 격리는 제공하지 않는다.

`dreampia init/doctor/update/uninstall/rollback --project PROJECT`는 프로젝트 범위만 다룬다. 기본은 미리보기, 쓰기는 --apply다. 설치 manifest의 버전·SHA256과 관리파일 원본을 기준으로 충돌을 보존한다. 변경과 rollback 모두 write-ahead journal로 중단을 기록하며 미완료 작업은 명시 rollback으로만 되돌린다. 전역 설정과 기존 AGENTS.md는 덮어쓰지 않는다.

Codex help/version probe도 별도 POSIX 프로세스 그룹에서 실행하고 취소·timeout·출력 상한을 감시한다. 부모가 먼저 종료해도 그룹의 남은 자식을 종료한다. setsid로 탈출한 프로세스는 계약 밖이다. 실제 AI inference와 CLI 모델 식별자 수용은 NOT_RUN이다.

## 드림피아 유니버설 하네스 라우터

`harness/universal_router.py` 및 `dreampia router-*` 명령은 드림피아 라우터 프로토콜(`DRP`)과 로컬 HTTP 엔드포인트를 통해 어떤 에이전트 하네스 환경에서도 라우터 형태로 동작한다:

1. **다중 하네스 탐색 (`router-discover`)**: `codex`, `claude`, `gemini`(Antigravity), `opencode`, `dsh`(DeepSeek CLI), `hermes`, `pi`, `goose`, `qwen`, `aider`, `local` 백엔드의 로컬 실행 가능 여부(`available`)와 스킬 로더 경로를 결정론적으로 탐색한다.
2. **하네스별 스킬·MCP·플러그인 배치 (`router-materialize`)**: 각 하네스 로더가 실제로 읽는 고유 경로(`.agents/skills`, `.claude/skills`, `.gemini/skills`, `.harness/skills` 등)와 백엔드별 MCP 설정(`.mcp.json`, `.harness/codex-mcp.toml`, `.gemini/settings.json` 등)을 미리보기 후 `--apply`로 안전하게 배치한다.
3. **표준 플러그인 내보내기 (`router-export-plugin`)**: `ai-dev-execution` 번들을 플러그인 매니페스트(`plugin.json` + `mcp.json` + `skills/ai-dev-execution/`) 규격으로 내보내며, 자격 증명(`auth`/`headers`)은 자동 제외하고 `skipped`에 기록한다.
4. **세션 연속성·모델 대체 추적·비밀 마스킹 라우팅 (`router-dispatch` 및 `/v1/responses`)**: 작업 목표/위험도 분류(`route_planner`)와 결합해 하네스를 선택하고, `previous_response_id` 세션 체이닝(`dp_sess_`, `dp_exec_`), `harness_mismatch`(409) 차단, `metadata.ignored_fields`(`tools`, `include`), `metadata.model_fallback` 기록, 비밀 마스킹(`redact_secrets`), 산출물 컨테이너(`dp_box_`, `dp_art_`) 추적을 수행한다.

