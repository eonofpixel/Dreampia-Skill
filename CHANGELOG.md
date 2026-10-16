# 0.6.2

- 접두사 없는 표준 운영 슬래시·CLI 명령어 체계(/version, /status, /doctor, /config, /update, /uninstall, /release, /clean) 및 29종 MCP 서버 도구 일원화

# 0.6.1

- 비관리 `.dreampia/` 사용자 데이터 폴더 충돌 감지 및 `.dreampia-skill/` 상태 디렉터리 자동 격리.
- 글로벌 설치(`setup --apply`) 시 기존 비관리 스킬 자동 백업(`.pre-dreampia.bak`) 및 `uninstall-global` 원상복구 명령어 추가.
- `bin/dreampia.cjs` Windows/POSIX Python 실행기(`python3`, `python`, `py -3`) 자동 탐지 및 Python 3.9+ 호환성 일원화.
- 보안 강화: `reconstruct-doctor` 미검증 제3자 패키지 제거·무승인 `sudo` 및 MCP 원격 설치 차단, `golden-io` AST 정적 안전 검증, `metric-climb` 기본 미리보기(`PREVIEW`) 전환, `squad-worktree` 강제 브랜치 덮어쓰기 제거 및 Windows junction 안전 해제, MCP 프로젝트 루트 경계 잠금.
- 프로젝트별 UI 규칙 강제 여부 선택(`enforce_ui_rules: false`, `--no-ui-rules`), `audit-code --apply` 시 `evidence/code-audit.json` 기록, `sdd-check`의 `SPEC-*`·`T*` ID 및 테스트 파일 직접 참조 인식 지원.

# 0.6.0

- 국문 프롬프트 고도화 브리핑(`expand-prompt`), 소크라테스식 사전 인터뷰 컴파일러(`interview-compile`), 상태 기반 다음 추천 작업 가이드(`next-actions`), 프로젝트 자가 학습 규칙(`learn-rule`), 폭발 반경 분석(`blast-radius`), 자율 지표 등반(`metric-climb`), 2-Tier 클린룸 역설계(`reconstruct-*`), 22종 STDIO MCP 서버(`harness/mcp_server.py`) 통합.

# 0.5.2

필수 스킬 참조 누락 설치를 실제 Red→Green으로 차단. 이름/버전/출처/path/hash/required 번들 manifest strict 검사, 기존설치manifest/롤백 유지. 선택컨텍스트/모델/자동CI 정책 유지.

# 0.5.1

공식 검사 명령 선택·검증 stale·게시 대상 바이트 일치 참조. local_ci timeout 예외 종료를 기존 그룹 취소 코드와 상태 요약으로 수정. 전후 소스 연결 추가. 자동 원격CI는 계속 비활성.

# 0.5.0 — 플랫폼별 디자인 스킬 고도화

- 공통디자인은 브랜드/실제한국어·긴데이터/역할별토큰과 상태연결을 보강. 웹·desktop·mobile·검증 4개 선택 reference를 직접 작성. 고정미학/툴/문서생성/API 의존성 미도입.
- 플랫폼별입력/접근성/반응형·창/OS lifecycle/모바일키보드·safe area/터치단위 구별. 실제검증 증거와효과·NOT_RUN 구별.
- backend/CLI-only 제외, 기존game-ai설치본/평가baseline 보존. 패키지참조포함·실제이전버전upgrade/rollback 및전체회귀검증.

# 0.4.0 — 선택적 제품 디자인

- 사용자용 UI 범위의 제품 표면·흐름·브랜드/토큰·레이아웃·구현·실제 시각/조작/연결 검증 계약 추가. CLI/backend-only 제외.
- 핵심 SKILL을 짧은 라우터로 축약하고 기존 상세 실행 정책은 reference에 보존.
- 목업·내부 런타임 PoC·연결된 UI·제품 완료 수준 구별; 전달된 game-ai 사용 실패 기록.
- npm 명시 파일 목록 및 설치/업데이트/롤백의 디자인 참조 전달 검증. 하네스 실행 코드의 버전 상수 외 동작 변경 없음.
- 과거 검증 보존; 이번 실행 결과는 evidence/v0.4와 최종 패키지 외부 영수증으로 구분.

# 0.3.1 — 최종 ZIP 전체 검증 후속 수정

- 기존 최종 0.3.0 ZIP에서 승인/인증/정상 fake provider 세 시험의 2초 예산 초과 TIMEOUT을 확인했다. 성공으로 덮지 않고 로그를 보존했다.
- 정상 프로토콜/오류 분류 fixture의 기본 작업 예산만 10초로 보강했다. 실제 timeout 시험의 0.2초와 실행 하네스/어댑터 timeout 계약은 변경하지 않았다.
- 고아 잠금 시험의 sleep(1) 타이밍 가정을 명시적 release 신호로 교체하여 잠금 유지/해제를 실제 contender 완료에 동기화했다.
- 최종 ZIP 그 자체를 새 디렉터리에 추출하여 전체 CI를 실행하고 별도 해시·명령·결과 영수증으로 연결한다. npm tgz는 별도 산출물이다.

# 0.3.0 — 2026-10-08

- v0.2 입력 ZIP/영수증/버전/파일 바이트를 검증하여 수정재사용.
- 감사 세 결함 실제 Red→Green: probe 자식 그룹 종료, 평가 유한 예산, manifest 오타 fail-closed.
- 엄격 JSON/입력/숫자 범위·소유권 선언·모델 medium 고정 보강.
- 프로젝트 설치 미리보기/명시 apply/doctor/갱신/충돌 보존/중단 journal/단계 rollback/관리파일 제거.
- private npm thin wrapper, 자동 hook 없는 offline packaging.
- 선별 출처·비공개 이용 범위·한글 팀 정책·아키텍처·검증 기록.
- 독립 검토의 중단 rollback·소유권 검증·큰 정수 오류 처리 결함 수정 및 재검증.

과거 이력(아래)은 해당 버전 당시 결과이며 v0.3 검증을 대체하지 않는다.

# 변경 기록

## 0.2.0 — 2026-10-07
- 루트 .harness/.git 런타임만 해시 제외. 중첩 같은 이름과 모든 __pycache__ 입력은 포함. 검사 Python bytecode 생성을 비활성화하고 파일 해시 중 변경을 확인한다.
- 선택 check.inputs 경로 계약과 심볼릭 링크/탈출 거부. 증거의 소스 범위는 전체 프로젝트이며 외부 입력은 자동 포함되지 않는다.
- 상태/evidence 스키마, 구조화된 오류, 이전 상태 백업, 격리 복구·검사만 재검증·특정 작업의 명시적 부작용 재실행.
- 선택적 Codex exec JSONL 어댑터, 무료 doctor, 공급자 실행 opt-in, 기본 공급자 재시도 없음, 출력 최소화.
- 제품 버전/패키지 메타데이터/무의존 zipapp 빌드, 로컬 CI·미실행 원격 CI 설정, 지원 매트릭스·배포 라이선스 미선정 기록.
- 고정 baseline/holdout 평가 준비·수동 증거 검증·집계 runner. 실제 모델 A/B 비교 NOT_RUN.

## 0.1.0 — 초기 MVP
- 요구/작업/check 연결, DAG, 원자 저장, 잠금, 취소·재개, 제한 시도, 명령/해시 증거.
- 개선 스킬·작은 예약 예제·33개 하네스 회귀 검사.
