# Dreampia-Skill 차세대 고도화 및 지속 검증 마스터 로드맵 (v0.8.0 ~ v1.0.0)

> 기준 버전: v0.7.0 (커밋 399854a)
> 운영 원칙: 무의존성(Zero-Dependency Python 3.9+ 표준 라이브러리 단독), SOLID 5원칙, Fail-Closed 보스 관문, 외부 코드 PR 미수용(자체 클린룸 구현)

---

## 1. 2026 글로벌 AI 에이전트 하네스 5대 트렌드 및 경쟁사 로드맵 분석

프론티어 LLM 모델의 기본 지능이 평준화되면서, 경쟁의 핵심 축은 모델 자체가 아니라 모델을 감싸는 에이전트 하네스(Agent Harness)와 검증 루프로 완전히 이동했습니다.

| 핵심 트렌드 축 | 경쟁 오픈소스 동향 (spec-kit, omc/omo, claude-flow, Aider, OpenHands, autoresearch) | Dreampia-Skill 현재 수준 (v0.7.0) | 차세대 추월 목표 |
| :--- | :--- | :--- | :--- |
| 1. SDD(명세 주도 개발) 및 추적성 | `spec-kit`은 `/specify -> /plan -> /tasks` 마크다운 체크리스트로 AI 탈선을 방지하나, 코드·테스트 실제 연결을 기계적으로 강제하지는 못함 | `sdd_engine.py`가 `REQ-* -> TASK-* -> TEST-*` 추적률과 명세 해시 드리프트(`STALE`)를 결정론적으로 차단 | 자연어 인터뷰에서 골든 입출력 벡터(`golden-io.json`)와 역방향 회귀 테스트 스켈레톤까지 자동 생성하는 양방향 SDD 컴파일러 |
| 2. 초압축 메모리 & 컨텍스트 엔지니어링 | 100만 토큰 시대에도 무작정 컨텍스트를 채우면 정확도가 급락하여, 핵심 규칙 30여 개만 선별·가지치기(Memory Pruning)하고 워크트리별로 격리하는 추세 | `compile_context_pack`으로 1,000토큰 미만 브리핑 패킷을 생성하고 `learn-rule`로 규칙을 누적함 | 중복·충돌 규칙 자동 병합(Rule Compaction), 실패 이력 기반 자동 오답 노트 추출, 워크트리 간 학습 규칙 무오염 동기화 |
| 3. Git Worktree 병렬 실행 및 원격 데몬 | `claude-flow`, `omc`, `OpenHands`는 Git Worktree 격리와 백그라운드 워커 데몬을 결합해 여러 서브에이전트가 동시에 구현·검증 후 리베이스 병합함 | `squad_worktree.py`와 `guild_camp.py`에 서명·검문소 프로토콜은 완성되어 있으나, 실제 원격 맥미니(`bot-01`)에서 큐를 폴링해 CLI를 자동 실행하는 라이브 워커 데몬이 없음 | 무의존성 표준 라이브러리 기반 라이브 워커 데몬(`camp-worker-run`) 및 충돌 사전 시뮬레이션 자동 리베이스 파이프라인 탑재 |
| 4. 자율 실험 루프 (`autoresearch` 패턴) | `karpathy/autoresearch` 계열은 수정 -> 벤치마크 측정 -> 개선 시 커밋(Keep), 퇴보 시 즉시 롤백(Discard)하는 무인 등반 루프를 표준화함 | `run_metric_climb`이 불변 파일 가드, 중복 해시 차단, 몬테카를로 유의성 판정 및 TSV 원장을 기록함 | `DISCARD` 또는 `CRASH` 판정 시 Git 워크트리를 직전 `KEEP` 상태로 자동 복원(`git checkout/reset`)하고 목표치 달성까지 무인 반복하는 완전 자율 클라이머 |
| 5. 실전 벤치마크 (`FeatureBench` / `SWE-bench`) | 경쟁 도구들은 자체 단위 테스트를 넘어 실제 결함 주입(Mutation Testing) 및 전후 성공률 비교 벤치마크 수치로 하네스 성능을 입증함 | 22개 테스트 모듈(213개 단위 테스트) 100% 통과 중이나, 하네스 적용 전후 AI 슬롭 차단율 및 결함 포착률을 정량 측정하는 벤치마크 하네스가 없음 | 고의적 결함·슬롭·오염 코드 50종을 주입해 Inquisitor와 Cleric의 적발률(Recall)과 오탐률(FPR 0%)을 상시 측정하는 자체 벤치마크 스위트 구축 |

---

## 2. 단계별 고도화 마스터 로드맵 (4단계 마일스톤)

### Phase 1 (v0.7.5): 자체 검증 벤치마크 하네스 및 뮤테이션 테스트 구축 (Verification First)
새 기능을 얹기 전에, 우리 스킬이 실제로 얼마나 정확하고 빠르게 작동하는지 수치로 증명하는 검증 체계를 먼저 확립합니다.
1. 적대적 슬롭·결함 벤치마크 (`harness/benchmark_suite.py`)
   - Python, TypeScript/React, Rust, Go 4개 언어에 대해 가짜 테스트(Hollow TDD), 주석 위장 슬롭, 타입 우회, 클린룸 오염, 요구사항 누락 등 50종의 표준 결함 코퍼스를 내장합니다.
   - `python -m harness.team_cli benchmark --project .` 실행 시 적발률(Recall 100% 목표), 오탐률(False Positive Rate 0% 목표), 파일당 평균 스캔 지연 시간(1ms 미만 목표)을 측정해 `evidence/benchmark-report.json`으로 출력합니다.
2. 선택적 네이티브 컴파일러 브리지 (`--with-toolchain`)
   - 평소에는 0.01초 내장 어휘·블록 스캐너로 동작하고, 최종 게이트에서 로컬에 설치된 `tsc --noEmit`, `cargo check`, `go vet`, `pyright` 진단 결과를 `AuditFinding`으로 흡수합니다.

### Phase 2 (v0.8.0): 길드 캠프 라이브 워커 데몬 및 병렬 워크트리 자동 합류 (Live Guild Camp)
컨트롤 플레인(서명·검문소)으로만 존재하던 `guild_camp.py`에 실제 실행 근육을 붙입니다.
1. 원격·로컬 워커 폴링 루프 (`camp-worker-run`)
   - 맥미니(`bot-01`) 또는 로컬 서브 슬롯에서 서명된 퀘스트 큐를 감시하다가, 퀘스트가 도착하면 격리 워크트리를 생성하고 지정된 에이전트 CLI(`claude`, `codex`, `gemini`)를 실행한 뒤 `verify_cmd` 통과 시 결과 번들을 자동 반환합니다.
2. 워크트리 충돌 사전 감지(Dry-Run Merge) 및 순차 리베이스 가드
   - `squad_worktree.py`에서 병렬 트랙(`Paladin`, `Bard`, `Archer`)이 작업을 마쳤을 때 `git merge-tree` 기반으로 파일·심볼 충돌 여부를 본진 병합 전에 미리 시뮬레이션합니다.

### Phase 3 (v0.9.0): 완전 자율 지표 등반(Autoresearch Loop) 및 스마트 메모리 압축 (Autonomous Climb & Memory)
1. 자동 롤백 연동형 Metric Climb (`metric-climb --auto-rollback`)
   - 실험 실패(`DISCARD`, `CRASH`, `COMPLEXITY_REJECTED`) 시 워커 워크트리의 대상 파일을 직전 최고점(`KEEP`) 상태로 자동 되돌려 에이전트가 오염된 코드 위에서 삽질하지 않도록 보장합니다.
2. 프로젝트 메모리 자동 가지치기 (`memory-compact`)
   - `.dreampia/memory/project-rules.json`에 쌓이는 학습 규칙 중 중복되거나 상충하는 정규식을 정리하고, 핵심 불변 규칙 32개 이내로 압축해 토큰 소모와 지침 드리프트를 최소화합니다.

### Phase 4 (v1.0.0): 양방향 SDD-골든 I/O 합성 및 로컬 관제 리포트 (Enterprise Autonomous OS)
1. SDD 명세에서 골든 입출력(`golden-io.json`) 및 TDD 스켈레톤 자동 합성
   - `interview-compile` 단계에서 요구사항 문장뿐만 아니라 경계값 입출력 벡터와 언어별 실패 테스트(Red Phase) 템플릿을 동시에 생성합니다.
2. 단일 HTML 정적 관제 리포트 생성 (`status --export-html`)
   - 별도 웹서버나 Node 패키지 없이도 현재 퀘스트 진행률, SDD 추적 행렬, 폭발 반경 그래프, 벤치마크 점수를 한눈에 볼 수 있는 로컬 정적 대시보드(`evidence/dashboard.html`)를 생성합니다.
