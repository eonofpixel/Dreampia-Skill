# 로컬 실제 검증 기록

- 확인 시각: 2026-10-09T16:21:23Z (UTC; macOS 로컬 날짜는 10월 10일)
- 수정 범위: 이 scaffold 폴더만. 하네스/루트 패키지/manifest/버전 정책을 변경하거나 커밋·푸시하지 않음.
- 실행 프로젝트: `/tmp/dreampia-local-assessment-33x9s5/web` (저장소 밖 복사본).
- 환경: macOS Darwin 25.4.0, Node v25.9.0, npm 11.12.1. Next 16.4.0, React/React DOM 19.3.0, Playwright 1.64.0, TypeScript 7.0.2.
- 의존성: `/tmp/dreampia057-smoke4-RQxouk/web/node_modules/*/package.json`의 실제 버전 확인 → 이 버전으로 신규 설치 → 생성 lockfile 포함 → `npm ci --no-audit --no-fund` 성공. node_modules/.next는 scaffold에 포함하지 않음.

| 명령/검증 | 실제 관찰 | 판정 |
|---|---|---|
| `npm install --ignore-scripts --no-audit --no-fund` | 신규 격리 프로젝트에서 설치 성공 | PASS |
| `npm ci --no-audit --no-fund` | 포함한 lockfile로 실제 재설치, 종료 0 | PASS |
| `npm run test:unit` | 11 tests, 11 pass, 0 fail | PASS |
| `npm run build` | Compiled successfully, TypeScript 완료, 학생/관리자와 8개 동적 API/export 라우트 생성, 종료 0 | PASS |
| `DREAMPIA_UI_EVIDENCE=/tmp/dreampia-local-assessment-33x9s5/evidence npm run test:ui` | Chromium, mobile/tablet/desktop 각각 실제 전체 흐름; 3 passed (12.5s), 종료 0 | PASS |
| `git diff --check -- ai-dev-execution/assets/scaffolds/next-assessment-app` | 오류 없음 | PASS |

원문 최종 로그: `/tmp/dreampia-local-assessment-33x9s5/verification.log`.

## 확인된 행동
- 잘못된 코드 403 안내 → 유효 코드 시작 → 미응답 HTML 필수 검증 → 5점 응답 → 서버 가중/역문항 채점 → 실제 로컬 저장 → 100점 결과.
- 중복 제출 409, 누락/잘못된 응답 400. 키보드 Tab 입력 초점 및 라디오 방향키 선택.
- 관리자 인증 이전 submissions/audit/export 401, 잘못된 로그인 401, 유효 환경 비밀키 로그인.
- 제출 행/전체 평균 100/제출 수 1/반별 1건 확인, 페이지 새로고침 후 실제 저장 데이터 재조회.
- 실제 CSV 다운로드/내용 확인 → 제출 삭제 → 보존 기간 실행 → submit/login/read/export/delete/retention 감사 확인 → 교차 Origin 403 → 로그아웃 후 export 401.
- 단위 테스트는 invalid/empty/fractional/range/unsafe-weight/duplicate 답변, 역문항·가중치·정규화·경계, strict 질문/식별자 필드, 만료/미설정 코드, 미설정 관리자 키·HMAC 변조·만료, 6개 동시 작업/4개 **별도 프로세스** 중복 잠금, 재조회/삭제/보존/감사, 손상 파일 덮어쓰기 거부, CSV 수식 중화를 확인.

## 캡처 (합성 데이터만, 코드·비밀키 없음)
Viewport: mobile 390×844, tablet 820×1180, desktop 1366×768; fullPage 캡처 높이는 콘텐츠에 따라 달라집니다.

- `/tmp/dreampia-local-assessment-33x9s5/evidence/mobile-questions.png`
- `/tmp/dreampia-local-assessment-33x9s5/evidence/mobile-result.png`
- `/tmp/dreampia-local-assessment-33x9s5/evidence/mobile-admin.png`
- `/tmp/dreampia-local-assessment-33x9s5/evidence/tablet-questions.png`
- `/tmp/dreampia-local-assessment-33x9s5/evidence/tablet-result.png`
- `/tmp/dreampia-local-assessment-33x9s5/evidence/tablet-admin.png`
- `/tmp/dreampia-local-assessment-33x9s5/evidence/desktop-questions.png`
- `/tmp/dreampia-local-assessment-33x9s5/evidence/desktop-result.png`
- `/tmp/dreampia-local-assessment-33x9s5/evidence/desktop-admin.png`

자기 시각 검토: 모바일/데스크톱 문항, 태블릿 결과, 세 기기 관리자 캡처를 실제로 열어 한국어 줄바꿈·정렬·선택·통계·좁은 표를 확인했습니다. 모바일 표는 패널 내부 가로 스크롤이며 안내와 키보드 초점을 제공합니다. 문항/관리자 화면의 페이지 가로 overflow 없음은 실제 브라우저에서도 검사했습니다. 결과 캡처/세 기기 전 흐름은 자동화로 확인했습니다. 전체 WCAG/스크린리더/부하/다른 브라우저/실운영은 NOT_RUN이며 범위 밖입니다.

발견·수정한 문제: 최초 E2E에서 Next 내부 request.url(localhost)과 브라우저 Host(127.0.0.1)가 달라 정상 Origin을 거부했습니다. loopback Host 기반 검증과 회귀 단위 테스트로 수정 후 전 흐름을 재실행했습니다. Next route-announcer의 alert와 오류 alert가 충돌하던 테스트 선택자도 구분했습니다.

이 결과는 연결된 **LOCAL 개발 starter**의 검증이며 실제 학생 운영, 법적 적합성 또는 배포 완료를 뜻하지 않습니다. 보존은 수동 실행, CSV/백업은 별도 삭제, stale lock은 프로세스 종료 후 운영자 복구가 필요합니다. 상세 제한은 README를 따릅니다.
