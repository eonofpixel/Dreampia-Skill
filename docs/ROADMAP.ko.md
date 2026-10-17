# Dreampia-Skill 차세대 고도화 및 지속 검증 마스터 로드맵 (v0.8.0 ~ v1.0.0)

> 기준 버전: v0.7.0 (2차 심층 트렌드 및 경쟁 오픈소스 아키텍처 조사 반영본)
> 운영 원칙: 무의존성(Zero-Dependency Python 3.9+ 표준 라이브러리 단독), SOLID 5원칙, Fail-Closed 보스 관문, 외부 코드 PR 미수용(자체 클린룸 구현)

---

## 1. 1·2차 심층 조사 종합: 2026 글로벌 에이전트 하네스 8대 핵심 기술 축

프론티어 LLM의 기본 코딩 지능이 상향 평준화되면서, 최신 오픈소스 생태계(`oh-my-claudecode / omc`, `oh-my-opencode / omo`, `claude-flow`, `GitHub spec-kit`, `Serena MCP`, `ast-grep MCP`, `VeriHarness`, `autoresearch`)는 아래 8가지 핵심 메커니즘에서 승부를 가르고 있습니다.

| 기술 축 | 경쟁 오픈소스 최전선 구현 방식 | Dreampia-Skill 현재 상태 (v0.7.0) | 냉정한 격차 및 추월 전략 |
| :--- | :--- | :--- | :--- |
| 1. 생애주기 훅 강제 개입 (`PreToolUse` / `PostToolUse` / `Stop`) | `omc`/`omo` 및 Claude Code 훅 생태계는 에이전트가 자발적으로 규칙을 지키길 기다리지 않고, 도구 실행 전(`PreToolUse`)에 위험 명령을 차단(exit 2 / `deny` / `defer`)하고, 파일 수정 직후(`PostToolUse`) 자동 린트를 돌리며, 턴 종료(`Stop`) 시 미완료 작업을 감지해 완료될 때까지 멈추지 못하게 강제함(Sisyphus 루프) | 현재 `setup --apply`는 `SKILL.md`, 슬래시 명령어, MCP 서버만 등록하며, 호스트의 네이티브 `hooks` 이벤트에는 아직 자동 연결되어 있지 않음 | 핵심 추월 포인트 1: `team_cli.py hook-dispatch`를 신설하여 `PreToolUse`(경계 밖 파일 쓰기·위험 쉘 차단), `PostToolUse`(증분 `audit-code`), `Stop`(`autopilot-gate` 미통과 시 종료 방어) 훅을 네이티브 지원 |
| 2. 뮤테이션 테스팅 & 경계값 퍼징 (Testing the AI's Tests) | AI가 `assert True`는 피하더라도 `assert result is not None`처럼 껍데기만 있는 약한 테스트를 짜는 자기기만(Self-Deception)을 막기 위해, 최신 하네스(`TT Harness`, `VeriHarness`)는 원본 코드의 연산자(`+`->`-`, `>`->`<`, `True`->`False`)를 살짝 변조(Mutant)했을 때 테스트가 실패하는지(Mutant Killed) 검사함 | 구문상 빈 테스트(`hollow-tdd-no-assertion`)와 `assert True`는 잡지만, 의미론적으로 약한 단언문(코드가 틀려도 통과하는 테스트)은 아직 통과됨 | 핵심 추월 포인트 2: 외부 패키지 없이 Python `ast.NodeTransformer`와 정규식 변조기로 핵심 비즈니스 로직에 변이(Mutant)를 주입해 AI가 짠 테스트의 실제 방어력(Mutation Score)을 검증하는 `mutation-check` 내장 |
| 3. 시맨틱 심볼 맵 & 구조적 탐색 (`Serena` / `ast-grep` 패턴) | `Serena MCP`와 `ast-grep MCP`는 에이전트가 2,000줄짜리 파일을 통째로 읽어 토큰을 낭비(Blind Context Stuffing)하지 않도록, 파일의 클래스·함수 시그니처·줄 번호 목차만 추출하거나 특정 심볼 본문만 슬라이싱해 토큰 소모를 75% 이상 절감함 | `blast-radius`용 공개 심볼 목록 추출기는 있으나, 에이전트에게 파일 내부 심볼 목차와 라인 범위(`start_line~end_line`)를 찝어주는 시맨틱 내비게이션 도구는 없음 | 핵심 추월 포인트 3: 내장 AST 및 다국어 중괄호 블록 파서를 활용해 파일 전체를 읽지 않고도 함수/클래스 시그니처와 줄 범위를 100토큰 내외로 요약하거나 특정 심볼 블록만 읽어오는 `symbol-map` 도구 추가 |
| 4. SDD(명세 주도 개발) 및 추적성 | `spec-kit`과 `BMAD-METHOD`는 `/specify -> /plan -> /tasks` 마크다운 절차를 제공하나, 명세와 실제 테스트 코드 사이의 해시 동기화나 커버리지를 기계적으로 차단하지 못함 | `sdd_engine.py`가 `REQ-* -> TASK-* -> TEST-*` 추적률과 명세 드리프트(`STALE`)를 결정론적으로 차단함 | 명세서에서 곧바로 골든 입출력(`golden-io.json`)과 언어별 실패 테스트(Red Phase) 스켈레톤을 자동 합성하는 양방향 SDD 컴파일러로 격차 확대 |
| 5. 초압축 메모리 가지치기 (Memory Pruning) | 100만 토큰 모델에서도 규칙을 무작정 나열하면 지침 망각이 발생해, 프로젝트 메모리를 핵심 32개 이내의 불변 규칙으로 자동 압축·정제하는 기법이 표준화됨 | `compile_context_pack`과 `learn-rule`을 보유 중이나, 규칙이 계속 쌓일 때 중복·충돌 정규식을 합치는 압축기가 없음 | 누적된 `project-rules.json`에서 중복·포함 관계의 규칙을 자동 병합하고 실패 빈도순으로 우선순위를 재정렬하는 `memory-compact` 탑재 |
| 6. Git Worktree 병렬 실행 및 원격 데몬 | `claude-flow`와 `OpenHands`는 Git Worktree 격리와 백그라운드 데몬을 결합해 여러 서브에이전트가 동시에 구현·검증 후 순차 리베이스 병합함 | `squad_worktree.py`와 `guild_camp.py`에 HMAC 서명 및 `BossGateMergeGuard` 검문소가 구현되어 있으나, 원격/로컬 큐를 폴링해 CLI를 자동 실행하는 라이브 워커 루프가 없음 | 무의존성 라이브 워커 폴링 데몬(`camp-worker-run`) 및 본진 병합 전 충돌 시뮬레이션(Dry-Run Merge) 가드 탑재 |
| 7. 자율 실험 루프 (`autoresearch` Keep/Discard) | `karpathy/autoresearch` 계열은 수정 -> 벤치마크 실행 -> 개선 시 커밋(`KEEP`), 퇴보·오류 시 즉시 워크트리 롤백(`DISCARD`)하는 무인 최적화 루프를 구동함 | `run_metric_climb`이 불변 파일 가드, 중복 해시 차단, 몬테카를로 유의성 판정 및 TSV 원장을 기록함 | `DISCARD` 또는 `CRASH` 판정 시 대상 파일을 직전 최고점(`KEEP`) 커밋 상태로 즉시 자동 복원(`--auto-rollback`)하는 무인 클라이밍 루프 완성 |
| 8. 정량적 벤치마크 스위트 (`FeatureBench` / Anti-Slop) | 경쟁 하네스들은 자체 단위 테스트를 넘어 실제 결함·슬롭 코퍼스를 주입했을 때의 적발률(Recall), 오탐률(FPR), 실행 지연 시간을 정량 리포트로 증명함 | 22개 모듈(213개 단위 테스트) 100% 통과 중이나, 다국어 슬롭 적발률과 오탐률 0%를 정량 산출하는 통합 벤치마크 명령이 없음 | 4개 언어(Python/TS/Rust/Go) 50종 적대적 슬롭·결함 코퍼스 기반 상시 벤치마크(`team_cli.py benchmark`) 구축 |

---

## 2. 단계별 검증·고도화 마스터 로드맵 (4단계 마일스톤)

### Phase 1 (v0.7.5): 자체 검증 벤치마크 스위트 + AST 뮤테이션 테스팅 (Verification & Anti-Deception)
AI가 짠 코드와 테스트의 진위 여부를 100% 검증하는 기반부터 완성합니다.
1. 적대적 슬롭·결함 벤치마크 (`harness/benchmark_suite.py` / `dreampia_benchmark`)
   - Python, TypeScript/React, Rust, Go 4개 언어의 가짜 TDD, 주석 위장 슬롭, 빈 `catch`, 클린룸 오염, SDD 누락 등 표준 결함 케이스와 정상 케이스를 실행하여 적발률(Recall 100%), 오탐률(False Positive Rate 0%), 스캔 시간(ms)을 `evidence/benchmark-report.json`으로 산출합니다.
2. 무의존성 뮤테이션 테스팅 게이트 (`mutation-check`)
   - AI가 작성한 테스트가 실제로 로직 변경(산술·비교·불리언 연산자 및 반환값 변이)을 잡아내는지 변이 생존율(Mutant Survival)을 측정하여, `assert result is not None` 같은 꼼수 테스트를 적발합니다.

### Phase 2 (v0.8.0): 네이티브 생애주기 훅(Lifecycle Hooks) & 시맨틱 심볼 맵 (Hook Guard & Serena Pattern)
`omc`/`omo` 및 `Serena MCP`의 최고 장점을 무의존성 표준 라이브러리로 흡수합니다.
1. 호스트 생애주기 훅 디스패처 (`hook-dispatch` 및 `setup --with-hooks`)
   - `PreToolUse`: `write_boundary.py` 및 위험 명령 필터를 실행 전에 즉시 적용하여 위반 시 차단 응답 반환.
   - `PostToolUse`: 파일 편집 직후 0.01초 증분 `audit-code --changed-only`를 자동 실행하여 AI 슬롭 유입 시 즉시 경고 주입.
   - `Stop`: 에이전트가 턴을 끝내려 할 때 미완료 SDD/TDD 항목이 남아 있으면 완료 전 종료를 방지(Continuation Enforcer).
2. 시맨틱 심볼 맵 및 부분 슬라이싱 (`symbol-map` / `dreampia_symbol_map`)
   - 대용량 파일 전체를 읽지 않고도 파일 내 클래스·함수 시그니처, 시작~종료 줄 번호(`L10-L45`), 호출 심볼 요약만 초압축 추출하여 컨텍스트 토큰 소모를 75% 이상 절감합니다.

### Phase 3 (v0.9.0): 길드 캠프 라이브 워커 데몬 & 자동 롤백형 Metric Climb (Live Execution Loop)
1. 길드 캠프 라이브 워커 폴링 데몬 (`camp-worker-run`)
   - 맥미니(`bot-01`) 또는 로컬 서브 슬롯에서 서명된 퀘스트 큐를 감시해 격리 워크트리 생성 -> CLI 실행 -> `verify_cmd` 검증 -> 결과 번들 서명 반환까지 무인 수행합니다.
2. 워크트리 Dry-Run 충돌 시뮬레이터 및 `metric-climb --auto-rollback`
   - 병렬 워크트리 합류 전 충돌 여부를 사전 시뮬레이션하고, 지표 등반 실패(`DISCARD`/`CRASH`) 시 대상 파일을 직전 `KEEP` 상태로 자동 복원합니다.

### Phase 4 (v1.0.0): 스마트 메모리 가지치기, 양방향 골든 I/O 합성 및 정적 관제 대시보드
1. 프로젝트 메모리 압축기 (`memory-compact`)
   - 누적된 학습 규칙(`project-rules.json`)의 중복·충돌 정규식을 정리하고 핵심 불변 규칙 32개 이내로 자동 가지치기합니다.
2. 양방향 SDD-골든 I/O 자동 합성 및 단일 HTML 관제 리포트 (`status --export-html`)
   - 기획 인터뷰에서 `approved-spec/golden-io.json`과 실패 테스트 스켈레톤을 자동 생성하고, 외부 패키지 없이 단일 HTML 파일로 전체 퀘스트·SDD·벤치마크 현황을 시각화합니다.
