# 내부 개발 OS 인수 기준 및 오프라인 worker 실행

## 완료 범위와 주장 경계

이 문서는 **독립 workflow runner 작업자**의 실제 결과와 부모 통합 작업자의 남은 인수 항목을 구별한다. 전체 앱/제품/릴리스 완료 인증서가 아니다.

- 구현 파일: `harness/workflow_runner.py`
- 회귀 테스트: `harness/tests/test_workflow_runner.py`
- 진입점: 저장소 루트에서 `python3 -m harness.workflow_runner`
- 기존 `harness/cli.py`, 팀 CLI, 버전, manifest, 릴리스 파일은 이 작업자가 수정하지 않는다.
- planner/executor/reviewer/verifier는 실행 책임 **라벨**이다. 각 역할은 승인한 로컬 argv를 실제 subprocess로 실행한다. 모델 호출, AI 판단, 자동 코드 생성, 독립 LLM 검토를 가장하지 않는다.
- 기본 어댑터/모델/네트워크 호출은 없다. 명시적으로 계약에 등록하고 승인한 로컬 어댑터만 실행한다. 없는 어댑터는 실패 폐쇄한다.

## 프로젝트 JSON 계약

프로젝트 루트의 `workflow.json`이 유일한 계약 입력이다. 아래는 **설정 예시**이며 이미 실행된 제품 작업의 증거가 아니다. `/ABSOLUTE/PYTHON`을 실제 실행 가능 Python 절대 경로로 바꾸고 `workers/local_worker.py`를 직접 구현한다. 각 역할별 adapter를 분리해도 된다.

```json
{
  "version": 1,
  "source_files": ["workers/local_worker.py", "spec.md"],
  "adapters": {
    "local": {"argv": ["/ABSOLUTE/PYTHON", "workers/local_worker.py"]}
  },
  "tasks": [
    {"id":"plan", "role":"planner", "adapter":"local", "depends_on":[], "side_effect":false, "timeout":30, "max_attempts":2},
    {"id":"execute", "role":"executor", "adapter":"local", "depends_on":["plan"], "side_effect":true, "timeout":60, "max_attempts":1},
    {"id":"review", "role":"reviewer", "adapter":"local", "depends_on":["execute"], "side_effect":false, "timeout":30, "max_attempts":2},
    {"id":"verify", "role":"verifier", "adapter":"local", "depends_on":["review"], "side_effect":false, "timeout":60, "max_attempts":2}
  ]
}
```

계약 규칙:

- 위 필드가 모두 필수다. 알 수 없는 필드, 중복 JSON 키, task/adapter 식별자 오류는 거절한다.
- tasks는 위상 순서로 선언한다. dependencies는 앞에 선언된 task만 참조한다. 순환/자기 참조/없는 의존성을 거절한다. 선행 실패 시 후행은 `blocked`, 실행 횟수는 증가하지 않는다.
- 최대 128 tasks, 64 adapters, argv 64개/인자당 4,096자, 계약 1 MiB다.
- timeout은 task 시도당 0.01~300초, max_attempts는 최초 실행과 재개를 합친 총 1~5회다. read-only/idempotent 작업만 남은 횟수 내에서 재시도한다.
- `source_files`는 1~256개, 합계 16 MiB 이하의 **불변 입력**을 명시한다. argv에 직접 지정한 기존 로컬 입력 파일도 여기에 포함한다. 모듈의 간접 import, toolchain 라이브러리, 시스템 전체를 자동 수집하지 않는다.
- executable만 절대 경로다. 나머지 경로 인자는 프로젝트 내부 상대 경로를 쓴다. traversal, 절대 경로 인자, 심볼릭 링크 계약/소스/상태 경로를 거절한다. shell/주요 remote 실행 파일, 직접 URL, inline eval 인자도 거절한다. 임의 문자열 속 경로까지 해석하는 언어 파서는 아니다.
- 선언한 입력 소스를 변경하는 executor는 이 불변 계약에 맞지 않는다. 출력은 별도 파일에 쓰고, 소스 변경이 필요한 단계는 변경 후 새로운 검토된 계약/프로젝트 실행으로 분리한다. 중간 소스 변경은 전체 완료로 주장하지 않는다.

### 어댑터 stdin 및 실제 성공 의미

worker는 stdin에서 JSON 한 객체를 받는다: `version`, `task_id`, `role`, `attempt`, `side_effect`, `source_fingerprint`, `dependencies`(선행 task 상태 맵). shell expansion이나 템플릿 치환은 하지 않는다. `cwd`는 프로젝트 루트다. 실제 worker가 task와 role을 읽어 해당 작업을 수행해야 한다.

exit 0은 그 **명령의 성공**일 뿐, 제품 정확성/AI 품질/보안 인증이 아니다. 역할별 검증 기준은 worker 구현과 제품 인수 테스트에서 정의해야 한다. stdout/stderr는 합계 64 KiB까지 기록한다. 초과는 `OUTPUT_LIMIT`, 시간 초과는 `TIMEOUT`, 실행 불능은 `SPAWN_ERROR`로 실패한다. 프로세스 그룹을 종료하여 같은 그룹의 자손도 정리한다.

## CLI 통합 사용법

```sh
# 저장소 루트에서 실행; PROJECT는 workflow.json이 있는 실제 프로젝트 경로
python3 -m harness.workflow_runner plan PROJECT
python3 -m harness.workflow_runner run PROJECT --approve-adapter local --approve-effect execute
python3 -m harness.workflow_runner status PROJECT
python3 -m harness.workflow_runner resume PROJECT --approve-adapter local
```

- `plan`: 계약 검증과 source fingerprint 출력만 한다. 실제 planner 명령 실행/계획 생성은 `run`에서 일어난다. checkpoint를 만들지 않는다.
- `run`: 새 workflow만 시작한다. 기존 checkpoint가 있으면 덮어쓰지 않고 `resume`을 요구한다.
- `status`: 현재 source와 checkpoint를 검증하고 durable 상태를 JSON으로 읽는다. 명령 자체가 정상 조회되면 exit 0이며 task 실패를 전체 성공으로 해석하지 않는다.
- `resume`: 기존 source fingerprint가 같은지 검사하고 성공 task는 건너뛴다. 실행할 read-only task의 adapter를 다시 승인해야 한다. 승인 정보는 다음 실행의 자동 승인으로 재사용되지 않는다.
- 반복 플래그로 adapter/task 여러 개를 명시한다. 부작용 task가 아직 시도되지 않았다면 재개에서도 해당 `--approve-effect TASK`가 필요하다.
- run/resume exit 0: 모든 task `passed`. exit 1: 실패/의존 차단/조정 필요. exit 2: 잘못된 계약/미승인/오래된 source/잠금 충돌/입출력 오류. SIGINT/SIGTERM은 exit 130과 기존 checkpoint 보존이다.

### 복구와 부작용 처리

`PROJECT/.workflow/state.json`이 체크포인트이자 증거 원장이다. 실행 **전** `running`과 증가한 시도 횟수를 fsync하고, 임시 파일의 원자적 교체 후 부모 디렉터리도 fsync한다. 명령 종료 뒤 argv/cwd/시각/timeout/exit/result/stdout/stderr/source fingerprint를 기록한다. 잠금은 프로세스 중복 실행을 거절하며 adapter에도 전달한다.

1. 먼저 `status`로 실제 checkpoint를 확인한다. source/runner/executable 변경이면 stale 오류를 반환한다. 기존 checkpoint를 임의 수정하여 PASS로 만들지 않는다.
2. 중단된 read-only 작업은 남은 총 시도 한도와 새 adapter 승인이 있을 때 재개한다. 중단 시도는 예산을 소비한다. 실행 중 죽은 시도는 시작 checkpoint만 있고 종료 증거가 없을 수 있다.
3. **한 번이라도 시도한 부작용 작업은 자동 retry/replay하지 않는다.** 실패·중단·timeout 후 `needs_reconciliation`으로 멈춘다. 같은 `--approve-effect`를 다시 주어도 재실행하지 않는다. 이미 성공한 부작용도 재개에서 건너뛴다.
4. 외부 실제 상태/출력을 사람이 대조하고 보상·수동 조정 여부를 결정한다. 원장을 보존하고 새 task/검토된 새 실행을 만들며, 이 runner는 외부 상태를 자동 조정하지 않는다.
5. 부모가 SIGKILL되면 adapter가 잠금을 유지할 수 있다. orphan 종료/실제 결과 대조 전에는 복구 실행을 진행하지 않는다. 별도 session으로 탈출한 자손/악의적 adapter까지 제어하는 OS sandbox는 아니다.

fingerprint는 정규화 계약, 선언 입력 파일, runner 소스, adapter executable 경로/바이트를 포함한다. 실행 전후 검사와 재개/조회에서 검증한다. 선언되지 않은 출력물 전체 무결성, 외부 환경의 완전한 재현성을 뜻하지 않는다.

## 실제 검증 원장: 이 작업자의 확인 범위

- 사용한 `python3 --version`: **Python 3.9.6**. 호스트 설명의 Python 버전과 달리 실제 쉘 명령이 선택한 실행기다. 다른 Python 버전 호환은 별도 확인한다.
- RED: 신규 모듈이 없을 때 happy-path 테스트 1개가 실제 FAIL. 그 후 계약/승인/timeout/재개 안전 기능에 대한 테스트가 실제 실패했다.
- 추가 RED: 실행 중 계약 변경을 탐지하지 못한 테스트와 exhausted interrupted attempt가 `running`으로 남던 테스트가 각각 실제 FAIL. 수정 후 GREEN으로 검증했다.
- 전용 테스트 명령: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest harness.tests.test_workflow_runner -v`.
- 전용 검증 범위: 실제 subprocess 및 checkpoint, 네 역할 의존 순서, 선행 실패 차단, read-only 실패→성공 재시도, 실제 SIGTERM 후 재개, 성공 task 비재실행, 총 시도 상한, timeout 자손 종료, 출력 한도, 부작용 승인/재실행 금지, 미등록·미승인 adapter, 잘못된 JSON 계약/경로/심볼릭 링크, 계약 변경/stale 탐지, 동시 실행 잠금.
- 전용 테스트 최종 결과: **`Ran 14 tests in 3.329s` / `OK` / exit 0**. 아래 미완 항목을 전용 테스트 PASS로 대체하지 않는다.
- 전체 `PYTHONDONTWRITEBYTECODE=1 python3 harness/local_ci.py`도 실제 실행했으나 **exit 1 / STALE**였다. 해당 실행의 전체 unittest 결과는 `Ran 143 tests in 39.705s`, `FAILED (failures=1, errors=22)`였다. 병렬 수정 중 source_before/source_after가 달랐고, scaffold 변경과 아직 갱신되지 않은 bundle manifest 사이의 `bundle hash mismatch: assets/scaffolds/next-assessment-app/app/admin/export/route.ts` 오류가 관찰됐다. 이 작업자는 manifest를 수정하지 않는다. 모든 부모 통합/manifest 동기화가 끝난 고정 source에서 재실행해야 한다.
- `python3 -m harness.workflow_runner --help` 실제 출력 확인. 원격 CI/모델 inference/배포는 **NOT_RUN**이다.

## 보안 경계

**승인된 로컬 프로그램은 신뢰하는 코드다. 이 runner는 sandbox가 아니다.** executable 이름/argv 검사와 제한 환경변수는 실수 방지이며 악의적 Python/Node 코드의 네트워크, 외부 파일 쓰기, subprocess, 동적 import를 봉쇄하지 않는다. 어댑터가 `side_effect:false` 선언을 실제로 지키는지도 자동 증명하지 않는다. 민감한 프로젝트는 별도 OS sandbox/네트워크 차단/최소 권한 계정을 써야 한다.

기본 환경에 provider 키, 사용자 shell 환경, PYTHONPATH를 전달하지 않는다. 하지만 명령이 OS 자원이나 사용자 파일을 직접 읽는 것은 막지 못한다. stdout/stderr 역시 자동 비밀 redaction을 하지 않는다. 고객 export에 `.workflow`/내부 원장을 포함하지 않고 별도 허용목록·비밀 검사를 적용해야 한다. 상태 파일 0600/상태 폴더 신규 생성 0700은 접근 제한 보조 수단이지 암호화나 변조 방지 서명은 아니다.

## 남은 전체 인수 체크리스트 — 부모 통합 책임

`[x]`는 이 작업자가 실제 검증한 범위다. `[ ]`는 다른 작업자가 구현했더라도 **이 작업자 관점에서 통합 확인 대기**다. 미실행을 PASS로 전환하지 않는다.

### 오케스트레이션 / 복구

- [x] 네 역할을 실제 승인된 로컬 argv로 실행; missing adapter fail-closed.
- [x] DAG 순서/의존 차단, bounded timeout/retries/output, durable checkpoint, 재개, source fingerprint.
- [x] 부작용 명시 승인, 시도된 부작용 자동 replay 금지, 실제 중단 복구/잠금 검증.
- [ ] 부모 CLI/설치 패키지에 module 포함 및 도움말/운영 문서 연결. 기존 CLI를 이 작업자는 수정하지 않음.
- [ ] 실제 팀용 planner/executor/reviewer/verifier **서로 다른 adapter 구현**과 각 역할의 산출물·검증 기준 확인. 테스트의 role 출력은 AI 검토 품질 증명이 아님.
- [ ] 부작용 조정 절차·운영 책임자·보상 실행 승인 기록, 실제 운영 리허설.

### 검증 / 증거 최신성

- [ ] 부모의 verification 명령이 요구사항/명세/소스/증거를 연결하고 테스트 실패·미실행·stale를 구별.
- [ ] 병렬 변경 종료 및 manifest 동기화 뒤 local_ci 전체 PASS와 source_current=true.
- [ ] 실제 설치된 팀 패키지에서 검증 실행, 동일 버전/동일 소스 증거를 확인.
- [ ] 단순 성공 문자열, 빈 evidence, 과거 PASS 복사, source 변경 후 완료 주장을 차단.
- [ ] 실제 모델/호스트 연결 필요 시 별도 승인으로 테스트; 유료 inference·원격 결과는 미실행 상태 유지.

### 앱 / 데이터 / UX

- [ ] fresh scaffold 설치 → dependency 설치 → lint/typecheck/unit/build → 서버 readiness → Playwright 실제 실행.
- [ ] 사용자 제출 → 저장 → 재조회 → 관리자 조회/내보내기까지 실제 API·저장소 연결 확인.
- [ ] 질문/점수 범위, 누락/중복/잘못된 입력, 오류·빈 상태, retry/idempotency, persistence/restart 테스트.
- [ ] 주요 화면 실제 시각/조작 확인, 접근성/모바일 뷰, 증거 위치 기록. 목업이나 CLI PASS로 대체 금지.

### 보안 / 개인정보

- [ ] 관리자 인증/권한, 세션/만료/CSRF/origin/rate limit 정책과 실제 우회 테스트.
- [ ] 비밀·원시 개인정보를 client bundle/log/CSV/package/export에 포함하지 않는 검증.
- [ ] 미성년자/평가 데이터 최소 수집, 보유/삭제/접근 범위, 동의/권리 처리 확인.
- [ ] 신뢰 경계와 sandbox 필요 여부, adapter 라이선스/고정 revision/권한 승인 검토.
- [ ] 심볼릭 링크/경로 탈출/충돌 파일/손상 state/종속성 보안 회귀, 외부 공유 전 비밀 스캔.

### 고객 export / 재현성 / 릴리스

- [ ] client-safe allowlist export: 내부 agent/정책/원장/키/설치 백업/개인정보 제외, CSV formula injection 및 인코딩 확인.
- [ ] artifact checksum/manifest/version 일치, 반복 export 결과 일치, 실제 zip/package 내부 재검증.
- [ ] 새 임시 프로젝트와 격리 npm smoke에서 설치/doctor/업데이트/롤백/사용자 파일 보존 확인.
- [ ] clean install toolchain/lockfile/runtime 버전, 실행 명령, 재현 가능한 데이터/증거를 기록.
- [ ] 정적 패키지 목록에 신규 runner 포함, smoke/전체 테스트 후 최신 source 해시 확인.
- [ ] 부모가 릴리스 승인을 받은 경우에만 version/manifest/release 반영. commit/push/publish/배포는 별도 사용자 지시.

전체 완료 조건은 필수 체크가 실제 PASS이며 모든 FAIL/STALE/NOT_RUN이 해소되거나 사용자 승인으로 명시 제외된 상태다. 이 문서 자체의 존재나 전용 worker 테스트 성공은 제품 완료를 뜻하지 않는다.
