# Dreampia-Skill 차세대 고도화 및 지속 검증 상세 엔지니어링 로드맵 (v0.7.5 ~ v1.0.0)

> 기준 베이스라인: v0.7.0 (파이썬 표준 라이브러리 단독 24개 코어 모듈, 22개 테스트 스위트 213개 단위 테스트, 30개 MCP 도구, 5대 호스트 어댑터)
> 아키텍처 헌장: 무의존성(Zero-Dependency Python 3.9+ stdlib only), 객체지향 SOLID 5원칙 강제, Fail-Closed 보스 관문, 외부 코드 PR 미수용(자체 클린룸 엔지니어링)

---

## 1. 로드맵 설계 원칙 및 아키텍처 불변 계약 (Invariants)

본 로드맵의 모든 신규 모듈과 기능은 아래 5가지 엔지니어링 불변 계약을 통과해야만 본진(`main`)에 병합될 수 있습니다.

1. 무의존성 순수 표준 라이브러리 유지 (Zero External Runtime Dependency)
   - `pip install`이나 `npm install`이 필요한 외부 패키지를 일절 도입하지 않으며, 오직 Python 3.9+ 표준 라이브러리(`ast`, `tokenize`, `re`, `hashlib`, `hmac`, `subprocess`, `sqlite3`, `json`, ` pathlib` 등)와 자체 구현한 다국어 렉서/파서만으로 동작해야 합니다.
2. SOLID 5원칙 기반 모듈 분리
   - 단일 책임 원칙(SRP): 파싱(Lexer/AST), 규칙 판정(Evaluator), 프로세스 격리 실행(Runner), 영속화(Ledger/Store), 입출력 어댑터(CLI/MCP/Hook)를 독립 클래스와 모듈로 분리합니다. (단일 함수 80줄 이하, 파라미터 5개 이하 엄수)
   - 개방-폐쇄 원칙(OCP): 새로운 언어(Python, TS/JS, Rust, Go 등)나 새로운 변이 연산자·감사 규칙을 추가할 때 기존 엔진 코드를 수정하지 않고 레지스트리 등록만으로 확장할 수 있어야 합니다.
   - 리스코프 치환 원칙(LSP): 모든 언어별 분석기(`LanguageAnalyzer`)와 변이 생성기(`Mutator`)는 동일한 추상 계약(입력 소스 -> 표준 데이터클래스 반환)을 100% 준수합니다.
   - 인터페이스 분리 원칙(ISP): 읽기 전용 분석 도구(`symbol-map`, `audit-code`)와 상태 변경 도구(`mutation-check --apply`, `hook-dispatch`)의 인터페이스를 엄격히 분리합니다.
   - 의존성 역전 원칙(DIP): 상위 오케스트레이터(`autopilot_engine.py`, `team_cli.py`)는 구체적인 호스트 환경이나 파일시스템 구현이 아닌 추상 프로토콜과 설정 객체에 의존합니다.
3. 레이턴시 예산 (Strict Performance Budget)
   - `PreToolUse` 생애주기 훅: 30ms 이내 응답 (에이전트 도구 호출 체감 지연 제로)
   - `PostToolUse` 단일 파일 증분 감사: 80ms 이내 응답
   - `symbol-map` 단일 파일(2,000줄 기준) 심볼 목차 추출: 40ms 이내 응답
   - 전체 단위 테스트 + 적대적 벤치마크 코퍼스(50종) 실행: 3,000ms 이내 완료
4. 원본 코드 무오염 보장 (Zero Workspace Contamination)
   - 뮤테이션 테스팅이나 병렬 워크트리 병합 시뮬레이션 중 예외, 타임아웃, 강제 종료(`SIGKILL`/`KeyboardInterrupt`)가 발생하더라도 사용자의 원본 작업 트리는 단 1바이트도 오염되지 않아야 합니다(임시 디렉터리 샌드박스 또는 인메모리 Git 객체 활용).
5. 결정론적 증적 남김 (Deterministic Evidence Ledger)
   - 모든 검증·벤치마크·뮤테이션·훅 차단 결과는 SHA-256 무결성 해시가 포함된 JSON 증적 파일(`evidence/*.json`)로 기록되어야 합니다.

---

## 2. v0.7.0 현재 베이스라인 진단 및 8대 기술 축 정밀 격차

| 기술 축 | 현재 보유 모듈 (v0.7.0) | 현재 구현 수준 | 핵심 한계점 및 기술 부채 | 목표 마일스톤 |
| :--- | :--- | :--- | :--- | :--- |
| 1. 다국어 정적 감사 및 슬롭 탐지 | `harness/autopilot_engine.py` | Python AST + TS/JS/Rust/Go 렉서(주석·문자열 마스킹, JSX 버튼 파서, 빈 `catch` 및 무단언 테스트 탐지) | 1) 자체 적발률(Recall)과 오탐률(FPR)을 정량 측정하는 적대적 코퍼스 벤치마크 부재<br>2) `expect(x).toBeDefined()` 같은 의미론적 약한 단언문(Tautological Assertion) 미탐지 | Phase 1 (v0.7.5) |
| 2. 테스트 진위 검증 (Testing the AI's Tests) | `harness/autopilot_engine.py` (`hollow-tdd-*`) | 구문상 단언문(`assert`/`expect`) 존재 여부만 정적 확인 | 프로덕션 로직이 틀려도 무조건 통과하는 가짜 테스트를 걸러낼 뮤테이션 테스팅(Mutation Testing) 엔진 부재 | Phase 1 (v0.7.5) |
| 3. 호스트 생애주기 훅 강제 개입 | `harness/write_boundary.py`, `harness/team_cli.py` | CLI 및 MCP 도구로만 제공됨 (에이전트가 호출을 건너뛰면 사후에나 적발 가능) | 호스트의 `PreToolUse`, `PostToolUse`, `Stop`, `UserPromptSubmit` 이벤트에 직접 바인딩되는 훅 디스패처와 자동 설치기 부재 | Phase 2 (v0.8.0) |
| 4. 시맨틱 코드 탐색 및 컨텍스트 절감 | `harness/autopilot_engine.py` (`compute_blast_radius`) | 파일 간 import 그래프 및 공개 심볼 이름 목록만 추출 | 대용량 파일의 클래스·함수 시그니처와 정확한 줄 번호(`L10-L45`)만 발췌하는 `Serena MCP` 스타일의 심볼 맵·슬라이서 부재 | Phase 2 (v0.8.0) |
| 5. 영향 반경(Blast Radius) 역추적 | `harness/autopilot_engine.py` | 1단계(1-Hop) 역참조 파일 목록만 산출 | 2단계 전이 역추적(2-Hop Transitive Callers) 및 수정 시 즉시 실행해야 할 타깃 테스트 파일 자동 매핑 부재 | Phase 2 (v0.8.0) |
| 6. 자율 루프 복원력 및 체크포인트 | `harness/autopilot_engine.py` (`run_metric_climb`) | 실험 결과(`KEEP`/`DISCARD`/`CRASH`) 판정 및 TSV 원장 기록 | `DISCARD`/`CRASH` 판정 시 또는 장기 루프 드리프트 시 직전 정상 상태(Golden Checkpoint)로 자동 복원하는 스냅샷 매니저 부재 | Phase 3 (v0.9.0) |
| 7. 병렬 워크트리 및 길드 캠프 워커 | `harness/guild_camp.py`, `harness/workflow_runner.py` | HMAC 서명 작업 패킷, `BossGateMergeGuard` 검문소 완비 | 큐를 상시 폴링해 실제 서브프로세스를 구동하는 라이브 워커 데몬(`camp-worker-run`)과 병합 전 Dry-Run 충돌 시뮬레이터 부재 | Phase 3 (v0.9.0) |
| 8. 학습 메모리 관리 및 SDD 자동 합성 | `harness/sdd_engine.py`, `harness/autopilot_engine.py` | `learn-rule`, `interview-compile`, `sdd-ledger` 보유 | 규칙 누적 시 중복·충돌 정규식을 합치는 압축기(`memory-compact`)와 명세에서 실패 테스트 스켈레톤을 생성하는 합성기 부재 | Phase 4 (v1.0.0) |

---

## 3. Phase 1 (v0.7.5) 상세 설계: 적대적 벤치마크 스위트 및 무의존성 뮤테이션 테스팅

목표: AI 에이전트가 작성한 코드와 테스트의 진위 여부를 정적·동적으로 100% 검증하고, 우리 하네스 자체의 적발률(Recall 100%)과 오탐률(FPR 0%)을 수치로 증명합니다.

### Epic 1-1: 다국어 적대적 슬롭·결함 벤치마크 스위트
- 명세 및 작업 ID: `SPEC-RD-101` / `TASK-RD-101`
- 신설 및 수정 파일:
  - 신설: `harness/benchmark_suite.py` (벤치마크 코퍼스 정의, 샌드박스 실행기, 정량 지표 계산기)
  - 신설: `harness/tests/test_benchmark_suite.py` (벤치마크 엔진 단위 및 통합 테스트)
  - 수정: `harness/team_cli.py` (`benchmark` 서브커맨드 추가)
  - 수정: `harness/mcp_server.py` (`dreampia_benchmark` MCP 도구 등록)
- 핵심 클래스 및 함수 설계 (SOLID 준수):
  - `BenchmarkCase` (dataclass): `case_id`, `language` (`python` | `typescript` | `tsx` | `rust` | `go`), `category` (`slop` | `hollow_tdd` | `ui_button` | `solid_srp` | `clean_code`), `source_files` (상대경로->코드 매핑), `expected_rule_ids` (적발되어야 할 규칙 ID 튜플; 정상 코드는 빈 튜플)
  - `CorpusRegistry`: 5개 언어에 걸친 50종 골든 테스트 케이스(적대적 결함 30종 + 오탐 방지용 정상 고급 코드 20종)를 관리하는 레지스트리
    - 결함 코퍼스 예시:
      1) Python: `except Exception: pass`, `assert True`, `assert res is not None` 단독 테스트, 85줄 과밀 함수, 하드코딩 시크릿
      2) TypeScript/TSX: `catch (e) { // ignore }`, `it("works", () => { render(<App />); })` 무단언 테스트, `onClick={(e) => { if (a > b) doSomething(); }}`에 `bg-transparent`가 누락된 실제 `<button>`
      3) Rust: `#[test] fn test_calc() { let _ = compute(10); }` 무단언 테스트, 빈 매치/에러 무시 블록
      4) Go: `func TestAdd(t *testing.T) { _ = Add(1, 2) }` 무단언 테스트
    - 오탐 방지(False Positive Guard) 코퍼스 예시:
      1) 블록 주석(`/* <button className="bg-red-500"> */`) 및 템플릿 리터럴 내부의 의사 코드
      2) `catch (err) { logger.error(err); throw err; }` 정상 에러 처리
      3) 커스텀 헬퍼(`assertValidResponse(res)`, `expectStatusOk(res)`)를 호출하는 정상 테스트
  - `BenchmarkRunner`: 임시 샌드박스에서 코퍼스를 실행하고 언어별·규칙별 True Positive(TP), False Positive(FP), True Negative(TN), False Negative(FN), Recall, Precision, FPR, 평균 스캔 소요 시간(ms)을 계산하여 `evidence/benchmark-report.json`에 저장
- CLI 및 MCP 인터페이스:
  - CLI: `python -m harness.team_cli benchmark --project . [--language all|python|ts|rust|go] [--apply]`
  - MCP: `dreampia_benchmark(project_root, language, apply)`
- 완료 및 합격 기준 (Acceptance Criteria):
  - 적대적 결함 코퍼스 30종 적발률(Recall) = 100.0%
  - 정상 고급 코드 코퍼스 20종 오탐률(False Positive Rate) = 0.0%
  - 50종 전체 코퍼스 실행 시간 < 1,000ms

### Epic 1-2: 정적 약한 단언문(Weak / Tautological Assertion) 탐지 규칙 확장
- 명세 및 작업 ID: `SPEC-RD-102` / `TASK-RD-102`
- 수정 파일:
  - 수정: `harness/autopilot_engine.py` (`hollow-tdd-weak-assertion` 규칙 신설)
  - 수정: `harness/tests/test_autopilot_engine.py`
- 상세 탐지 메커니즘:
  - 테스트 함수 내에 구체적인 값/상태 비교 없이 아래의 약한 단언문만 단독으로 존재하는 경우 `hollow-tdd-weak-assertion` (`blocking: True`)으로 즉시 적발합니다.
    - Python: `assert x is not None`, `assert isinstance(x, ...)`만 있고 실제 값/속성 검증이 없는 테스트
    - TS/JS: `expect(x).toBeDefined()`, `expect(x).not.toBeNull()`, `expect(typeof x).toBe(...)`만 단독으로 존재하는 테스트
    - Go: `if res == nil { t.Fatal() }`만 있고 필드/결과값 비교가 없는 테스트

### Epic 1-3: 무의존성 AST·렉서 기반 뮤테이션 테스팅 엔진 (Testing the AI's Tests)
- 명세 및 작업 ID: `SPEC-RD-103` / `TASK-RD-103`
- 신설 및 수정 파일:
  - 신설: `harness/mutation_engine.py` (변이 생성기, 격리 샌드박스 테스트 실행기, 생존 변이 리포터)
  - 신설: `harness/tests/test_mutation_engine.py`
  - 수정: `harness/autopilot_engine.py` (`strict` 티어에서 `autopilot-gate` 실행 시 선택적 뮤테이션 게이트 연동)
  - 수정: `harness/team_cli.py` (`mutation-check` 서브커맨드 추가)
  - 수정: `harness/mcp_server.py` (`dreampia_mutation_check` MCP 도구 추가)
- 핵심 클래스 및 5대 변이 연산자(Mutators) 설계:
  - `MutationSite` (dataclass): `mutant_id`, `file_path`, `line`, `operator_type`, `original_snippet`, `mutated_snippet`
  - 지원 변이 연산자 5종:
    1) `AOR` (산술 연산자 변이): `+` <-> `-`, `*` <-> `/` (문자열 결합 제외, 수식 컨텍스트 한정)
    2) `ROR` (비교 연산자 변이): `>` <-> `<=`, `<` <-> `>=`, `==` <-> `!=`, `===` <-> `!==`
    3) `LCR` (논리/불리언 리터럴 변이): `True` <-> `False`, `true` <-> `false`, `and` <-> `or`, `&&` <-> `||`
    4) `RVR` (반환값 변이): 함수의 핵심 `return expr`을 `return None` / `return null` 또는 빈 값으로 변이
    5) `SBR` (조건 분기 반전): `if cond:` -> `if not (cond):`
  - 무오염 샌드박스 실행 아키텍처 (`SandboxMutationRunner`):
    - 원본 작업 디렉터리의 파일을 절대 직접 수정하지 않습니다.
    - `tempfile.TemporaryDirectory`에 대상 파일(또는 경량 프로젝트 스냅샷)을 복사한 뒤 변이본을 주입하여 지정된 타깃 테스트 명령(`pytest`, `unittest`, `vitest`, `cargo test`, `go test`)을 짧은 타임아웃(기본 5초)으로 실행합니다.
    - 판정 규칙:
      - 테스트가 실패(exit code != 0)하면 `KILLED` (정상: AI가 짠 테스트가 코드 변조를 정확히 잡아냄)
      - 테스트가 여전히 통과(exit code == 0)하면 `SURVIVED` (경고/차단: 코드가 망가졌는데도 통과하는 가짜 테스트 구간 적발, 정확한 파일·줄 번호·생존 변이 스니펫 반환)
      - 타임아웃 발생 시 `TIMEOUT` (무한 루프 유발 변이로 간주하여 유효 방어로 처리)
- CLI 및 MCP 인터페이스:
  - CLI: `python -m harness.team_cli mutation-check --project . --targets <file1,file2> --test-cmd "<cmd>" [--max-mutants 15] [--min-score 0.8] [--apply]`
  - MCP: `dreampia_mutation_check(project_root, target_files, test_command, max_mutants, min_score, apply)`
- 완료 및 합격 기준:
  - 변이 주입 후 강제 예외 발생 시에도 원본 워크스페이스 파일 해시 불변(100% 무오염)
  - 가짜 테스트(`assert calc(2, 2) is not None`)에 대해 `Mutation Score = 0.0` 및 `SURVIVED` 변이 위치 정확히 리포트

---

## 4. Phase 2 (v0.8.0) 상세 설계: 네이티브 생애주기 훅(Lifecycle Hooks) 및 시맨틱 심볼 맵

목표: 에이전트가 지침을 잊거나 도구를 자발적으로 호출하지 않아도 호스트 이벤트 루프 수준에서 규칙을 물리적으로 강제하고, 파일 탐색 시 컨텍스트 토큰 소모를 75% 이상 절감합니다.

### Epic 2-1: 호스트 생애주기 훅 디스패처 및 자동 설치기
- 명세 및 작업 ID: `SPEC-RD-201` / `TASK-RD-201`
- 신설 및 수정 파일:
  - 신설: `harness/hook_dispatcher.py` (호스트 이벤트 페이로드 파서, 이벤트별 정책 실행기, 호스트 설정 병합기)
  - 신설: `harness/tests/test_hook_dispatcher.py`
  - 수정: `harness/team_cli.py` (`hook-dispatch`, `setup --with-hooks`, `uninstall --hooks` 추가)
- 4대 생애주기 이벤트 상세 처리 규격:
  1. `PreToolUse` (도구 실행 전 사전 검문소 — 목표 응답 시간 < 30ms)
     - 입력: stdin 또는 인자로 전달된 도구 이름(`Write`, `Edit`, `MultiEdit`, `Bash`, `run_command` 등) 및 도구 인자 JSON
     - 검증 로직:
       - 파일 쓰기 계열 도구: `write_boundary.py`를 즉시 호출하여 허용된 워크스페이스/스쿼드 경계 밖 수정이거나 보호 대상 파일(`bundle-manifest.json`, `.git/config`, 불변 벤치마크 파일) 수정 시도 시 즉시 차단(`decision: "block"` / `permissionDecision: "deny"`, exit code 2) 및 한국어 사유 반환
       - 셸 실행 계열 도구: 파괴적 명령 패턴(`rm -rf /`, 승인되지 않은 `git push --force`, `git reset --hard`) 감지 시 즉시 차단 또는 사용자 확인 유예(`defer`) 반환
  2. `PostToolUse` (도구 실행 직후 증분 감사 — 목표 응답 시간 < 80ms)
     - 입력: 방금 수정된 파일 경로(`file_path` / `TargetFile`)
     - 검증 로직:
       - 수정된 단일 파일에 대해서만 인메모리 증분 `audit_code(changed_files=[target_file])`를 즉시 실행합니다.
       - 위반 사항(`hollow-tdd-*`, `slop-*`, `ui-button-*`, `solid-*`) 발견 시 호스트가 에이전트의 다음 턴에 즉시 주입할 수 있도록 `additionalContext` 필드에 구체적인 줄 번호와 수정 지침을 담아 반환합니다.
  3. `Stop` (턴 종료 시 미완료 작업 강제 루프 — Sisyphus Continuation Enforcer, 목표 응답 시간 < 120ms)
     - 입력: 에이전트 종료 시도 이벤트(`stop_hook_active` 플래그 확인으로 무한 루프 방지)
     - 검증 로직:
       - 현재 프로젝트에 활성 퀘스트나 변경된 파일이 있을 때 경량 증분 게이트를 점검합니다.
       - 차단 등급(`blocking: True`) 결함이 남아 있거나 SDD 추적성 미달 항목이 존재하면 종료를 거부(`decision: "block"`, `reason: "미해결 차단 결함 N건이 남아 있습니다..."`)하여 에이전트가 스스로 결함을 고치고 종료하도록 강제합니다. (단, 연속 3회 차단 시 안전 탈출 허용)
  4. `UserPromptSubmit` (프롬프트 제출 시 핵심 메모리 자동 주입)
     - 입력: 사용자의 원본 프롬프트
     - 동작: 프로젝트의 `project-rules.json` 상위 규칙과 활성 퀘스트 브리핑 요약을 컨텍스트로 자동 첨부합니다.
- 호스트 설정 자동 설치 (`setup --with-hooks --apply`):
  - Claude Code (`~/.claude/settings.json` 또는 `.claude/settings.json`) 등 훅 지원 호스트의 기존 `hooks` 배열을 보존하면서 Dreampia `hook-dispatch` 엔트리를 멱등성 있게(Idempotent) 병합하고, `uninstall` 시 깔끔하게 제거합니다.

### Epic 2-2: 무의존성 다국어 시맨틱 심볼 맵 및 슬라이서 (`Serena MCP` / `ast-grep` 패턴)
- 명세 및 작업 ID: `SPEC-RD-202` / `TASK-RD-202`
- 신설 및 수정 파일:
  - 신설: `harness/symbol_indexer.py` (다국어 심볼 목차 추출기 및 심볼 단위 코드 슬라이서)
  - 신설: `harness/tests/test_symbol_indexer.py`
  - 수정: `harness/team_cli.py` (`symbol-map`, `symbol-slice` 서브커맨드 추가)
  - 수정: `harness/mcp_server.py` (`dreampia_symbol_map`, `dreampia_symbol_slice` MCP 도구 등록)
- 핵심 클래스 및 동작 규격:
  - `SymbolNode` (dataclass): `name`, `kind` (`class` | `interface` | `struct` | `function` | `method` | `const`), `signature`, `start_line`, `end_line`, `line_count`, `parent_symbol`, `docstring_summary`, `calls` (내부에서 호출하는 주요 식별자 최대 10개)
  - 언어별 파싱 엔진:
    - Python: `ast.parse`를 사용해 클래스, 메서드, 비동기 함수, 데코레이터, 타입 어노테이션이 포함된 정확한 시그니처와 `lineno ~ end_lineno` 추출
    - TypeScript / JavaScript / TSX / Rust / Go: `autopilot_engine.py`의 `_mask_c_comments_and_strings`와 `_find_matching_delimiter`를 재사용하여 주석·문자열에 현혹되지 않고 `export class`, `interface`, `function`, `const fn = (...) =>`, `pub fn`, `impl`, `func (r *Recv) Name`의 정확한 시작 줄과 닫는 중괄호(`}`) 종료 줄을 100% 결정론적으로 추출
  - 제공 기능 2종:
    1) `symbol-map`: 파일(또는 디렉터리)의 전체 본문을 생략하고 계층적 심볼 목차(`L15-L82: def audit_code(...) -> Dict[str, Any]`)만 반환하여 2,000줄 파일도 150토큰 이내로 파악 가능
    2) `symbol-slice`: 파일 경로와 심볼 이름(예: `autopilot_engine.py::audit_code` 또는 `MyClass.myMethod`)을 지정하면 해당 심볼의 정의 구간(`start_line ~ end_line`)만 줄 번호와 함께 정확히 잘라서 반환
- 완료 및 합격 기준:
  - 2,000줄 규모의 Python 및 TypeScript 파일에서 `symbol-map` 출력 텍스트 크기가 원본 파일 대비 80% 이상 감소(토큰 75% 이상 절감)
  - `symbol-slice` 호출 시 요청한 함수/메서드의 시작 줄부터 닫는 줄까지 누락 없이 정확히 추출

### Epic 2-3: `blast-radius` 2단계 전이 역추적(2-Hop Transitive Call Graph) 및 타깃 테스트 추천
- 명세 및 작업 ID: `SPEC-RD-203` / `TASK-RD-203`
- 수정 파일:
  - 수정: `harness/autopilot_engine.py` (`compute_blast_radius` 고도화)
  - 수정: `harness/tests/test_autopilot_engine.py`
- 상세 설계:
  - 기존 1단계(`direct_dependents`) 역참조에 더해, 1단계 파일을 다시 import/호출하는 2단계(`transitive_dependents`) 파일 목록과, 영향권 내에 위치한 테스트 파일(`affected_test_files`) 및 즉시 실행 가능한 검증 명령(`recommended_test_commands`)을 자동 생성하여 에이전트가 전체 테스트 대신 타깃 테스트를 1초 만에 먼저 돌려볼 수 있게 합니다.

---

## 5. Phase 3 (v0.9.0) 상세 설계: 자율 루프 체크포인트 롤백, 병합 시뮬레이터 및 라이브 워커 데몬

목표: 장기 자율 루프(`continuous-loop`, `metric-climb`)와 멀티 에이전트 병렬 작업 중 실패나 충돌이 발생해도 작업 유실 없이 직전 최고 상태로 복구되는 회복 탄력성(Resilience)을 완성합니다.

### Epic 3-1: 자율 루프 Golden Checkpoint 스냅샷 매니저 및 자동 롤백
- 명세 및 작업 ID: `SPEC-RD-301` / `TASK-RD-301`
- 신설 및 수정 파일:
  - 신설: `harness/checkpoint_manager.py` (안전 스냅샷 생성, 목록 조회, 무손실 롤백, 오래된 스냅샷 정리)
  - 신설: `harness/tests/test_checkpoint_manager.py`
  - 수정: `harness/autopilot_engine.py` (`run_autopilot_gate --continuous-loop` 및 `run_metric_climb --auto-rollback` 연동)
  - 수정: `harness/team_cli.py` (`checkpoint` 서브커맨드 추가)
- 핵심 메커니즘:
  - Git 저장소 환경을 오염시키지 않도록 `.dreampia-skill/checkpoints/<checkpoint_id>/` 아래에 변경 대상 파일들의 원본 바이트 백업과 SHA-256 매니페스트(`checkpoint-manifest.json`), 당시 통과한 테스트/지표 점수를 원자적으로 기록합니다.
  - `run_metric_climb`에서 `--auto-rollback` 활성화 시:
    - 판정이 `KEEP`이면 현재 상태를 새로운 Golden Checkpoint로 갱신합니다.
    - 판정이 `DISCARD` 또는 `CRASH`이면 수정했던 대상 파일들을 직전 Golden Checkpoint 바이트로 즉시 자동 복원하고 롤백 증적을 남깁니다.

### Epic 3-2: 병렬 워크트리 Dry-Run 병합 충돌 시뮬레이터 및 적대적 Diff 리뷰어
- 명세 및 작업 ID: `SPEC-RD-302` / `TASK-RD-302`
- 수정 파일:
  - 수정: `harness/workflow_runner.py` (`simulate_worktree_merge` 추가)
  - 수정: `harness/guild_camp.py` (`BossGateMergeGuard`에 사전 충돌 시뮬레이션 단계 통합)
  - 수정: `harness/team_cli.py` (`squad-merge-check` 서브커맨드 추가)
- 핵심 메커니즘:
  - 여러 서브에이전트 워크트리(`slot-1`, `slot-2`)를 본진에 병합하기 전, 실제 브랜치를 건드리지 않고 두 워크트리 간의 수정 파일 교집합, 라인 범위 겹침, 공개 심볼 시그니처 변경 충돌 여부를 정적으로 시뮬레이션하여 충돌 리포트를 생성합니다.

### Epic 3-3: 길드 캠프 라이브 워커 폴링 데몬 (`camp-worker-run`)
- 명세 및 작업 ID: `SPEC-RD-303` / `TASK-RD-303`
- 수정 파일:
  - 수정: `harness/guild_camp.py` (`CampWorkerDaemon` 클래스 신설)
  - 수정: `harness/team_cli.py` (`camp-worker-run` 서브커맨드 추가)
  - 수정: `harness/tests/test_guild_camp.py`
- 핵심 메커니즘:
  - 워커 노드(로컬 서브 슬롯 또는 맥미니 `bot-01`)에서 큐 디렉터리를 폴링하다가 `HMAC-SHA256` 서명이 유효한 작업 패킷을 발견하면:
    1) 격리 워크트리 체크아웃
    2) 지정된 검증/빌드/테스트 명령 실행 및 타임아웃 감시
    3) 산출물 및 로그 수집 후 워커 서명이 포함된 결과 패킷 기록
    4) `--max-jobs N` 또는 `--once` 옵션으로 안전한 종료 보장 (무한 좀비 프로세스 방지)

---

## 6. Phase 4 (v1.0.0) 상세 설계: 스마트 메모리 압축기, 양방향 골든 I/O 합성 및 HTML 관제 대시보드

목표: 장기 운영 시 누적되는 프로젝트 학습 규칙의 품질을 유지하고, 기획 명세에서 테스트 코드로의 전환을 자동화하며, 전체 하네스 상태를 한눈에 볼 수 있는 v1.0 완전체 패키지를 달성합니다.

### Epic 4-1: 프로젝트 학습 메모리 자동 압축 및 충돌 해결기 (`memory-compact`)
- 명세 및 작업 ID: `SPEC-RD-401` / `TASK-RD-401`
- 신설 및 수정 파일:
  - 신설: `harness/memory_compactor.py`
  - 신설: `harness/tests/test_memory_compactor.py`
  - 수정: `harness/team_cli.py` (`memory-compact` 서브커맨드 추가)
  - 수정: `harness/mcp_server.py` (`dreampia_memory_compact` MCP 도구 등록)
- 핵심 메커니즘:
  - `.dreampia-skill/memory/project-rules.json`에 규칙이 누적될 때:
    1) 동일한 정규식이나 부분집합 관계에 있는 중복 규칙을 하나로 병합
    2) 상충하는 `blocking` 설정이나 모호한 패턴 감지 및 정리
    3) 심각도(`blocking` 우선)와 최근 적발 빈도를 기준으로 정렬하여 상위 32개 이내의 핵심 활성 규칙(Active Core Rules)과 아카이브 규칙(Archived Rules)으로 분리해 에이전트의 지침 망각(Instruction Drift)을 원천 방지합니다.

### Epic 4-2: 양방향 SDD-골든 I/O 및 Red-Phase 실패 테스트 스켈레톤 자동 합성기 (`sdd-synthesize`)
- 명세 및 작업 ID: `SPEC-RD-402` / `TASK-RD-402`
- 수정 파일:
  - 수정: `harness/sdd_engine.py` (`synthesize_red_tests` 및 골든 I/O 추출기 추가)
  - 수정: `harness/team_cli.py` (`sdd-synthesize` 서브커맨드 추가)
  - 수정: `harness/mcp_server.py` (`dreampia_sdd_synthesize` MCP 도구 등록)
- 핵심 메커니즘:
  - 승인된 SDD 명세(`REQ-*`, `TASK-*`)와 입출력 계약이 주어지면, 언어별(Python `unittest`/`pytest`, TypeScript `vitest`/`jest`, Rust `#[test]`, Go `testing`)로 실제 단언문(`assertEqual`, `expect(...).toEqual(...)`)이 포함된 Red-Phase 테스트 스켈레톤 파일을 생성하고 `sdd-ledger.json`에 즉시 매핑합니다.

### Epic 4-3: 무의존성 단일 파일 HTML 관제 리포트 (`status --export-html`)
- 명세 및 작업 ID: `SPEC-RD-403` / `TASK-RD-403`
- 수정 파일:
  - 수정: `harness/team_cli.py` (`status --export-html` 옵션 및 자체 완결형 HTML 렌더러 추가)
- 핵심 메커니즘:
  - 외부 네트워크나 CDN 없이 순수 인라인 CSS/SVG만으로 렌더링되는 `evidence/dreampia-dashboard.html`을 생성하여 SDD 추적성(100%), Inquisitor 감사 결과, 뮤테이션 테스팅 점수, 적대적 벤치마크 적발률, 길드 캠프 워커 상태를 한 화면에서 시각적으로 브리핑합니다.

---

## 7. 마일스톤 실행 순서표 (Critical Path) 및 버전별 출시 게이트 (Release Gate KPI)

| 순서 | 버전 | 핵심 에픽 (Epic ID) | 주요 신설/확장 모듈 | 출시 승인 정량 게이트 (Release Gate KPI) |
| :--- | :--- | :--- | :--- | :--- |
| Step 1 | v0.7.5 | `SPEC-RD-101` 적대적 벤치마크 스위트<br>`SPEC-RD-102` 약한 단언문 정적 탐지<br>`SPEC-RD-103` 무의존성 뮤테이션 테스팅 | `harness/benchmark_suite.py`<br>`harness/mutation_engine.py` | 1) 50종 코퍼스 Recall 100%, FPR 0.0%<br>2) 가짜 테스트 변이 적발률 100%<br>3) 원본 파일 오염 0건 |
| Step 2 | v0.8.0 | `SPEC-RD-201` 생애주기 훅 디스패처<br>`SPEC-RD-202` 시맨틱 심볼 맵/슬라이서<br>`SPEC-RD-203` 2-Hop 영향 반경 역추적 | `harness/hook_dispatcher.py`<br>`harness/symbol_indexer.py` | 1) `PreToolUse` 응답 < 30ms, `PostToolUse` < 80ms<br>2) 2,000줄 파일 심볼 맵 토큰 75%+ 절감<br>3) 5대 호스트 동기화 무결성 통과 |
| Step 3 | v0.9.0 | `SPEC-RD-301` Golden Checkpoint 롤백<br>`SPEC-RD-302` 워크트리 병합 시뮬레이터<br>`SPEC-RD-303` 길드 캠프 라이브 워커 | `harness/checkpoint_manager.py`<br>`harness/guild_camp.py` 확장 | 1) `DISCARD`/`CRASH` 시 100% 바이트 일치 복원<br>2) 병합 충돌 사전 감지율 100%<br>3) 라이브 워커 데몬 서명 검증 통과 |
| Step 4 | v1.0.0 | `SPEC-RD-401` 스마트 메모리 압축기<br>`SPEC-RD-402` 양방향 SDD 테스트 합성<br>`SPEC-RD-403` 단일 HTML 관제 대시보드 | `harness/memory_compactor.py`<br>`harness/sdd_engine.py` 확장 | 1) 중복 규칙 병합 및 32개 핵심 규칙 유지<br>2) 4개 언어 Red 테스트 자동 합성 통과<br>3) 전체 테스트 스위트 300개+ 100% 통과 |
