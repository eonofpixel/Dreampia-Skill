# v0.6.2 구조와 신뢰 경계

| 계층 | 파일 | 책임 |
|---|---|---|
| 공통 스킬 | `ai-dev-execution/` | 목표·SDD 명세·TDD·매트릭스 10인 스쿼드 역할(`Mouse` 포함)·검토·완료 보고 정책 |
| 팀 정책 | `team/policy.json`, `WORK_CONTRACT.ko.md` | 단일 실행자·`gpt-6.1-sol`/`medium`·모델 자동 상향 없음·최대 2회 검토 |
| 프로젝트 설정 | 설치된 `.dreampia/project.json` | 호스트 선택·원시 출력 폐기·provider 정보; 미지 키 거부, 비관리 데이터 폴더 충돌 시 `.dreampia-skill/` 격리 |
| 목표·라우트 지휘 | `harness/route_planner.py` | **Morpheus(모피어스)** 한글/영문 목표·위험도 분류, 프로파일·매트릭스 스쿼드 편성, 13종 매직 단축어 |
| SDD+TDD 추적 엔진 | `harness/sdd_engine.py` | 마크다운 다줄 섹션 `PRD-R*/SPEC-* → API/UX → TASK-*/T* → TEST-*` 계층 BFS 추적, 고아 명세·Spec Drift(`STALE`) 차단 |
| 역설계·클린룸 엔진 | `harness/reconstruct_engine.py` | **Keymaker(키메이커)** PE/ELF/Mach-O/WASM/ASAR/APK 정적 해부 및 복원 의무 원장 100% 커버리지 검증 |
| 쓰기·오염 경계 | `harness/write_boundary.py`, `handoff_contract.py` | **Seraph(세라프)** & **Tank(탱크)** 소유 경로(`owned_paths`), 3-Zone 클린룸 분리, SHA-256 인계 검증 |
| 시각 수용 검증 | `harness/visual_acceptance.py` | **Niobe(니오베)** & **Tank(탱크)** 8-bit RGBA PNG 디코딩, 뷰포트 예산, 픽셀 차이율 대조 |
| 자율 완주·감사 엔진 | `harness/autopilot_engine.py` | **Trinity(트리니티)** AST 코드·가짜 TDD 감사, 컨텍스트 압축 패킷, Golden I/O 동치성, **Morpheus & Tank** 통합 오토파일럿 게이트 |
| 유니버설 라우터 | `harness/universal_router.py` | 11종 에이전트 CLI 어댑터 디스패치, 스킬/플러그인 배포, 루프백 HTTP 게이트웨이 |
| STDIO MCP 서버 | `harness/mcp_server.py` | Zero-Dependency JSON-RPC 2.0 MCP 도구(`dreampia_expand_prompt`, `dreampia_route_plan`, `dreampia_sdd_check`, `dreampia_audit_code`, `dreampia_autopilot_gate` 등 22종) 제공 |
| 실행 하네스 | `harness/core.py`, `process.py`, `schema.py` | 의존성·한정 실행·크로스플랫폼(Windows Job Object / POSIX 프로세스 그룹)·원자 상태·현재 소스 증거 |
| 팀 설치·CLI | `harness/team_cli.py` | 미리보기·`--apply`·글로벌 백업/제거(`uninstall-global`)·4종 도메인 스캐폴드·게이트 검증·트랜잭션 journal·단계 rollback |
| thin npm | `bin/dreampia.cjs` | 크로스플랫폼 Python(`python3`/`python`/`py -3`) 자동 탐지 및 CLI 전달 |

목표 문서는 사람이 작성하고 실행 상태·이벤트 원장은 코드가 기록한다. 의미상 목표 충족·검토 품질·실제 화면 심미성은 프로그램이 자동 인증하지 않는다. `sdd_engine.py`, `reconstruct_engine.py`, `autopilot_engine.py`는 요구 ID-작업-테스트 연결, 명세 해시(`spec_sha256`) 드리프트, 가짜 TDD(`assert True`·빈 테스트)·`any` 타입·반환 타입 누락·선택적 UI 규칙 정적 감사, Golden I/O 블랙박스 동치성, 클린룸 의무 원장 커버리지, 3-Zone 오염 격리를 기계적으로 강제한다.

manifest와 실행 상태의 엄격한 구조, JSON 중복 키·NaN/Infinity 거부, 유한 예산(작업 timeout 0초 초과~3600초, max_attempts 정수 1~10, eval time budget 0초 초과~3600초), fresh PASS 증거·명령 해시, lock·recovery hold는 코드로 검사한다. 부모가 종료하더라도 POSIX 프로세스 그룹 및 Windows Job Object/taskkill로 자식 트리를 정리한다.

호스트 OS sandbox·키·로그인·권한 승인은 호스트가 담당한다. `--apply`는 프로젝트 설치 변경, `--allow-provider`는 공급자 실행, `--accept-side-effects`는 명시 replay 계약이다.

프로젝트 installer는 전체 사용자 프로젝트를 스캔하지 않고 지정된 관리 경로만 읽는다. 임의 파일이나 `.env`를 백업/배포하지 않는다. symlink를 거부하고 hash 충돌을 보존한다.

## 선택적 제품 디자인 및 매트릭스 스쿼드 거버넌스 (0.6.2)

공통 SKILL은 작업 범위 판단과 실행 원칙의 짧은 진입점이다. `product-design` 및 웹·데스크톱·모바일·시각검증 4개 reference는 사용자용 UI가 범위인 때만 선택 로드한다. 매트릭스 10인 스쿼드(`Morpheus`, `Oracle`, `Architect`, `Niobe`, `Keymaker`, `Neo`, `Trinity`, `Tank`, `Seraph`, `Mouse`)는 역할 분리와 인계 계약(`handoff_contract.py`), SDD 추적(`sdd_engine.py`), 클린룸 역설계(`reconstruct_engine.py`) 전 과정에서 일관된 코드네임과 책임 경계로 작동한다.
