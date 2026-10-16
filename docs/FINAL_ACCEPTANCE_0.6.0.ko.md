# Dreampia 0.6.0 최종 로컬 인수 보고

**이후 정정:** 독립 리뷰에서 checkpoint passed 증거 검증 누락이 발견됐다. 0.6.0을 최종 권장본으로 취급하지 않는다. [0.6.1 후속 수정·재검증 기록](REVIEW_FIX_0.6.1.ko.md)을 따른다.

## 판정 범위

내부·로컬 개발 도구 마일스톤이며 운영 배포/실학교 서비스 완료/독립 LLM 자동 개발 인증이 아니다. GitHub 저장소는 PRIVATE다. 합성 데이터만 사용했다.

## 부모가 직접 실행·확인한 검증

- 새 프로젝트: `/Users/bot-0/Dev/dreampia-acceptance-0.6.0` (CLI init/scaffold/scaffold-app)
- 포함 lockfile로 npm ci 성공
- app-check: Next build 및 실제 unit 11 pass/0 fail, source unchanged PASS
- ui-check: mobile/tablet/desktop 전체 E2E 3 passed; screenshots 9개, ui-evidence gate PASS
- before-claim-complete gate PASS (현재 app/UI evidence 및 healthy install)
- 시각 직접 검토: 모바일 관리자, 데스크톱 문항, 태블릿 결과. 한글/선택 상태/통계/결과 읽기 가능, 모바일 표 내부 가로 스크롤 안내 포함
- 실제 workflow CLI: planner/executor/reviewer/verifier 승인 로컬 명령 모두 passed; executor는 생성 앱 real unit tests 실행. 모델 호출은 없음
- 고객 export: 명시 승인 synthetic summary만 포함. 실제 ZIP members는 client/CLIENT_SAFE_SUMMARY.md, docs/CLIENT_APPROVED_LOCAL_SUMMARY.md 2개; before-client-send PASS
- local_ci: 147개 tests OK + 별도 slots 예제 4개 OK; source_current true, PASS
- npm 실제 pack/격리 offline install/CLI smoke PASS
- 내부 source ZIP: CRC/source bytes PASS, 별도 archive verifier 7 commands all_pass true
- 제일여상 skill update: 0.6.0, doctor healthy true. 해당 서비스 web 앱을 기존 원문/문항 대신 덮어쓰지 않음
- Hermes skill: 사전 백업 후 source bytes equality 확인

## 실패와 해결

1. 숨김 scaffold .gitignore가 bundle path 보안 규칙에 거절됨 → gitignore.template로 저장하고 생성 시 web/.gitignore로 매핑; 회귀 테스트 PASS.
2. app-static gate가 삭제된 mock-store.ts 요구 → 실제 store.ts 요구로 수정; 기존 회귀 PASS.
3. Next 최초 build가 tsconfig include를 변경해 source unchanged FAIL → scaffold에 .next/dev/types include를 사전 정의; 재빌드에서 현재 소스 증거 PASS.
4. package/verification 명령은 실제 인자 계약에 맞춰 실행. 잘못된 호출/짧은 timeout 결과를 성공으로 복사하지 않음.

## 실제 증거

- 앱: acceptance 프로젝트 evidence/app-check.json, evidence/ui-check.json
- 화면: evidence/ui/aa2a4a18487d491fbbb99a61aa05260b/*.png (9개)
- workflow: acceptance 프로젝트 .workflow/state.json
- CI: /tmp/dreampia060-ci.log
- 설치 smoke: /tmp/d060-npm-smoke.json
- source ZIP 확인: /tmp/d060-release.json, /tmp/d060-archive-verify.json
- 고객 전달 gate: /tmp/d060-client-gate.json

## 의도적으로 미실행/운영 전 조건

실학생 정보·학교 확정 문항/채점·공개 배포·유료 provider inference·분산 DB·250명 부하·재해복구·다른 브라우저/완전 WCAG는 NOT_RUN이다. 파일 adapter는 단일 보호된 로컬 개발 환경 범위, retention은 수동이며 stale lock 복구/CSV 사본 삭제는 운영자 책임이다. approved argv adapter는 신뢰 코드이고 OS/network sandbox가 아니다. export secret scan은 패턴 기반으로 사람의 개인정보/기밀 검토를 대체하지 않는다.

독립 리뷰 결과와 최종 Git SHA는 아래 별도 종료 기록으로 남긴다.
