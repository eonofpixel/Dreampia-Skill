# 거버넌스·클린룸·시각 검증 기준

드림피아 스킬(`ai-dev-execution` 및 `harness`)의 목표·위험도 기반 라우팅, 클린룸 격리, 시각 수용 검증 실행 통제 기준이다.

## 1. 목표·위험도 분류 및 프로파일 라우팅 (`route-plan`)

1. 사용자 목표(한글/영문)를 부작용 없이 결정론적으로 분류한다:
   - `change`: 기능 구현, 버그 수정, 리팩터링, 문서/코드 변경
   - `test`: 단위/통합/UI 테스트 및 검증 실행
   - `review`: 코드 리뷰, 감사, 변경점 검토
   - `explain`: 구조 설명, 요약, 분석
   - `operate`: 운영 배포, 릴리즈, 프로덕션 마이그레이션
   - `unsupported`: 프롬프트 인젝션, 검증 우회, 비밀 유출 시도 또는 모호한 입력
2. 위험도(`low` / `medium` / `high`)와 저장소 상태(`dirty` / `inspection-failed`)를 결합해 프로파일을 결정한다:
   - `quick`: 저위험 설명·리뷰·단일 테스트
   - `team`: 일반 변경 작업 (`planner`, `executor`, `reviewer`, `verifier` 및 소유 경로 경계)
   - `controlled`: 보안 민감·파괴적 변경·운영 작업 (`privacy-guard` 및 전체 검증 게이트 포함)
   - `cleanroom`: 역공학·외부 참조 격리 작업 (분석가·구현자·검증자 번들 분리)
3. **13대 프롬프트 단축어(Magic Shorthands)**를 통해 실행 모드·스쿼드·검증 게이트를 즉시 제어한다:
   - `sharpen` (`boost` / `고도화` / `구체화` / `생각`): 짧은 요청을 정밀 국문 엔지니어링 명세·엣지케이스·사전 인터뷰 질문 3선으로 심층 확장(`prompt-sharpen`)
   - `ulw` (`ultrawork` / `autopilot` / `풀가동`): `controlled` 프로파일 + 전 스쿼드 + `autopilot-gate` 원스톱 완주
   - `loop` (`until-pass` / `루프` / `완주`): 모든 SDD+TDD·코드감사·게이트가 `PASS`될 때까지 자가 수정 반복(`continuous_loop=True`)
   - `climb` (`hillclimb` / `성능등반` / `자율실험`): 불변 채점 파일 가드 + 중복 실험 해시 차단 + 몬테카를로 유의성 기반 자율 지표 등반(`metric-climb`)
   - `blast` (`폭발반경` / `영향도`): 변경 파일의 1-Hop/2-Hop 호출자 추적, 시스템 경계 교차 및 5단계 안전 증명 등급 산출(`blast-radius`)
   - `interrogate` (`심문` / `적대적리뷰`): `Architect`·`Trinity`·`Seraph` 다중 관점 적대적 코드 리뷰
   - `unslop` (`deslop` / `군더더기제거` / `슬롭제거`): 빈 예외 처리(`bare except: pass`), 가짜 단언문, 불필요한 슬롭 코드 정화
   - `btw` (`quick` / `eco` / `잠깐`): 파일 변경 없이 현재 문맥을 보존하며 `Oracle`이 즉답하는 `side-query` 모드
   - `sdd` (`plan` / `spec` / `명세`): `Oracle`+`Architect` 명세 설계 및 `sdd-check` 강제
   - `tdd` (`red-green` / `티디디`): `Neo`+`Trinity`+`Tank` 선행 테스트 및 가짜 단언문(`audit-code`) 차단
   - `re` (`cleanroom` / `역설계`): `Keymaker` 클린룸 3-Zone 격리 + `reconstruct-verify` + `golden-io`
   - `audit` (`trinity` / `sec` / `감사`): 파일 수정 없이 `Trinity`+`Seraph` 정밀 코드·보안 감사
   - `ui` (`niobe` / `화면`): `Niobe`+`Mouse`+`Neo`+`Tank` 시각 수용 검증(`visual-check` + `ui-evidence`)

```bash
python -m harness.team_cli route-plan --project /path/to/project --goal "ulw loop 학생 제출 API 인증 검증 로직 수정"
```

## 2. 결정론적 PNG 구조 및 시각 수용 검증 (`visual-check`)

1. 단순 8바이트 PNG 헤더 검사를 넘어 `IHDR`, `IDAT`, `IEND` 청크 구조, CRC32, 해상도 상한, zlib 압축 해제 및 스캔라인 필터(`None`, `Sub`, `Up`, `Average`, `Paeth`)까지 검증한다.
2. 베이스라인 PNG와 후보 PNG의 픽셀 단위 비교(`compare_visuals`) 및 매니페스트 기반 일괄 시각 수용 검증(`verify_visual_acceptance`)을 지원한다.

```bash
python -m harness.team_cli visual-check --project /path/to/project --baseline evidence/base.png --candidate evidence/cand.png --max-diff-ratio 0.01
```

## 3. 소유 경로 쓰기 경계(`write_boundary`) 및 클린룸 번들 격리

1. 실행 전후 파일시스템 스냅샷(`capture_inventory`)을 비교해 선언된 `owned_paths` 외부 파일 변경, 심볼릭 링크/하드링크 생성, 특수 파일 생성, 제어 메타데이터(`.git`, `.dreampia-install`, `.harness`, `.workflow`) 변조를 차단한다.
2. 클린룸(`cleanroom`) 프로파일에서는 오염 영역(`contaminated-zone`)을 분석가(`analyst`) 번들에만 허용하고, 구현자(`implementer`/`executor`) 및 검증자(`verifier`) 번들에는 승인된 명세(`approved-spec`)만 전달한다.
3. 지침 드리프트 점검(`instruction-check`)으로 `AGENTS.md`, `CLAUDE.md`, `.dreampia/WORK_CONTRACT.ko.md` 간 불일치와 심볼릭 링크 탈출을 비파괴적으로 확인한다.

```bash
python -m harness.team_cli instruction-check --project /path/to/project
```

## 4. 2-Tier 클린룸 역설계 및 복원 원장 (`reconstruct-*`)

1. **Tier 1 (기본 내장 무의존성 엔진)**: 외부 프로그램 설치 없이 순수 Python 표준 라이브러리(`harness/reconstruct_engine.py`)만으로 PE(EXE/DLL), ELF(32/64), Mach-O(Universal 포함), WASM, Electron ASAR, ZIP/APK 및 소스 디렉터리의 공개 표면(심볼, API 라우트, IPC 채널)을 0.1초 내에 정적 분석한다.
2. **Tier 2 (선택적 외부 리버싱 부스터 — `reconstruct-doctor`)**: 호스트에 `llvm-objdump`/`objdump`, `nm`, `rizin`, `jadx`(Android DEX), `wasm2wat`(WABT), `ghidra`(`analyzeHeadless`), `adb`가 설치되어 있으면 비파괴·읽기전용으로 심층 심볼을 자동 병합(`tier2_enrichment`)하고, 미설치 시 현재 OS(`winget`/`brew`/`apt`)에 맞는 선택 설치 명령어를 안내한다(무승인 `sudo` 및 MCP 원격 설치는 차단).
3. 클린룸 복원 3단계 워크플로:
   - **진단 및 표면 분석 (`reconstruct-doctor` / `reconstruct-inspect`)**: Tier 1+2 엔진 상태 확인 후 `contaminated-zone/` 내 바이너리·번들·소스의 구조와 공개 계약을 추출한다.
   - **의무 원장 생성 (`reconstruct-ledger`)**: 추출된 모든 계약을 의무 항목(`obl_001`, ...)으로 등록하고 `evidence/reconstruction-ledger.json`에 서명 기록한다.
   - **무오염 복원 검증 (`reconstruct-verify` / `reconstruct-compare`)**: 모든 의무 항목이 `approved-spec/`에 명세되고 `implementation/`에 100% 구현되었는지, 그리고 `contaminated-zone/`의 파일 해시가 직접 복사되지 않았는지(`verify_cleanroom_separation`) Fail-Closed 방식으로 검증한다.

```bash
python -m harness.team_cli reconstruct-doctor
python -m harness.team_cli reconstruct-inspect --project /path/to/project --target contaminated-zone
python -m harness.team_cli reconstruct-ledger --project /path/to/project --source contaminated-zone --apply
python -m harness.team_cli reconstruct-verify --project /path/to/project --candidate implementation
python -m harness.team_cli reconstruct-compare --project /path/to/project --source contaminated-zone --candidate implementation
```

## 5. 유니버설 멀티 에이전트 라우터 및 MCP 서버 (`router-*` / `mcp-serve`)

1. 11종 에이전트 호스트(`codex`, `claude`, `gemini`, `opencode`, `dsh`, `qwen`, `aider`, `goose`, `hermes`, `pi`, `local`)에 대한 자동 탐색(`router-discover`), 스킬/플러그인 일괄 배치(`router-materialize`), 실시간 비대화형 CLI 실행 어댑터(`router-dispatch`), 그리고 STDIO JSON-RPC 2.0 MCP 서버(`mcp-serve`, 30종 도구)를 기본 제공한다.

```bash
python -m harness.team_cli discover --project /path/to/project --bootstrap-sdd --apply
python -m harness.team_cli router-discover --project /path/to/project
python -m harness.team_cli router-materialize --project /path/to/project --harness all --apply
python -m harness.team_cli mcp-serve --project /path/to/project
```

## 6. SDD+TDD 추적, 코드 감사, Golden I/O 및 오토파일럿 통합 게이트

1. **SDD+TDD 계층 추적 (`sdd-ledger` / `sdd-check`)**: `PRD-R* / REQ-* / SPEC-* → API-* / UX-S* → TASK-* / T* → TEST-*` 4단계 계층 BFS 추적(테스트 파일 내 `T1207`/`TASK-*` 직접 인용 및 브라운필드 `brownfield-baseline.md` 포함), 고아 요구사항 차단, 명세 해시(`spec_sha256`) 기반 Spec Drift(`STALE`) 감지.
2. **Trinity AST 코드·가짜 TDD 감사 (`audit-code`)**: 가짜 단언문(`assert True`, `expect(true).toBe(true)`, `assert!(true)`, 무단언 테스트), `any` 타입 사용, 반환 타입 누락, 선택적 UI 규칙(`--no-ui-rules` 또는 `enforce_ui_rules: false`로 해제 가능), Git 변경분 증분 감사(`--changed-only`)를 정적 차단하고 `--apply` 시 `evidence/code-audit.json`을 저장.
3. **장기 실행 문맥 압축 (`context-pack`)**: 활성 요구사항, 미완료 작업, `ADR-*`/`RISK-*` 불변 조건을 `evidence/context-pack.json`으로 컴파일하여 세션 문맥 망각(Context Rot) 방지.
4. **클린룸 블랙박스 동치성 (`golden-io`)**: `approved-spec/golden-io.json` 입출력 벡터와 `implementation/` 모듈의 실행 결과를 AST 정적 안전 검증 후 대조 검증.
5. **단일 자율 완주 게이트 (`autopilot-gate`)**: 작업 규모별 3단 탄력 티어(`nano` / `standard` / `full`) 및 증분 감사(`--changed-only`)를 지원하며, 지침 드리프트, SDD+TDD 추적성, Trinity 코드 감사, 클린룸 커버리지, Golden I/O, 시각 수용 검증을 원자적으로 실행하고 `evidence/autopilot-verdict.json`을 발급.

```bash
python -m harness.team_cli sdd-ledger --project /path/to/project --apply
python -m harness.team_cli audit-code --project /path/to/project --apply
python -m harness.team_cli context-pack --project /path/to/project --apply
python -m harness.team_cli golden-io --project /path/to/project
python -m harness.team_cli autopilot-gate --project /path/to/project --apply
```


