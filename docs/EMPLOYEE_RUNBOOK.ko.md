# 직원용 내부 개발 OS runbook

## 범위

비공개 내부 개발 도구다. generated assessment starter는 synthetic data 기반 로컬 검증용이며 학교 운영 승인/배포 인증이 아니다. 영속 adapter는 단일 로컬 인스턴스 범위에서 검증하고 분산 운영 DB는 별도 설계한다.

## 설치·갱신

- 설치된 POSIX Python >=3.9와 Node(Next가 지원하는 버전)를 사용한다.
- repo의 공식 명령과 승인된 설치 경로를 확인한다. 개인 계정 인증 파일을 복사하지 않는다.
- `python3 harness/team_cli.py init --project ABS_PROJECT`로 preview 후 `--apply` 실행한다.
- `update`는 관리 대상 기존 변경 충돌을 보존한다. 충돌을 강제 삭제하지 않는다.
- `doctor --project ABS_PROJECT`로 설치 무결성을 확인한다.

## 앱 생성·검증

- `scaffold --project ABS_PROJECT --apply`
- `scaffold-app --project ABS_PROJECT --apply`
- generated `web/`에서 `npm ci --ignore-scripts --no-audit --no-fund`
- `npm run build`, `npm run test:unit`
- Playwright Chromium이 없다면 `npx playwright install chromium` (네트워크 다운로드).
- `app-check --project ABS_PROJECT --apply`, `ui-check --project ABS_PROJECT --apply`
- `verify --project ABS_PROJECT --gate before-claim-complete`

진단 접근 코드/관리자 비밀값은 generated README가 정하는 환경변수로 설정하며 문서·git·화면 evidence에 실비밀을 기록하지 않는다. demo test 전용 값과 실운영 비밀을 구분한다.

## 완료 판정

FAIL/NOT_RUN은 완료가 아니다. evidence JSON의 각 check 성공과 현재 source fingerprint 일치 여부, 새 실행 screenshots를 확인한다. 눈으로 Korean layout을 확인하고 제출→결과→관리자 재조회→CSV 데이터 일치를 별도로 검증한다. 로그 존재만으로 성공을 주장하지 않는다.

## 역할 실행·복구

`python3 -m harness.workflow_runner --help`의 실제 계약을 따른다. 승인된 로컬 subprocess adapter만 실행한다. 역할 이름은 LLM inference가 아니다. 유료 inference/계정/외부 send adapter는 별도 승인한다. status와 checkpoint를 보고 명시 resume하며 side-effect 작업을 자동 replay하지 않는다.

## 고객 전달

명시 `client_export_allowed: true`의 승인 문서만 export한다. 내부 prompts/rubrics/원장/비밀값/개인정보/원시 로그를 전달하지 않는다. package 내용과 secret 검사 결과를 확인하고 사용자 승인 없이 외부 송신하지 않는다.

## 학교 production 전 미확정 항목

최종 문항/채점과 결과문구 승인, 수집 필드·법적 근거·보관/삭제 기간, 실제 기관 관리자/권한, HTTPS/session/CSRF/rate limiting, 운영 DB/backup/복구, 실제 대상 기기 및 동시 사용 테스트, 학교 pilot와 배포 승인. 이 항목은 local 도구 구현으로 대신 확정할 수 없다.
