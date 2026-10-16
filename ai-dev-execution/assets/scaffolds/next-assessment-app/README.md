# Local assessment starter — 연결된 로컬 개발용

## 범위와 화면
- `/`: 코드 + 학년(1–12)·반(1–50)·번호(1–60) → 서버 코드 확인 → 설정 기반 5점 4문항 → 서버 채점·영구 저장 → 전체/영역 결과.
- `/admin`: 환경 비밀키 인증 → 실제 제출/응답 상세·반별 수·평균 → CSV → 제출 삭제/재응답 허용 → 보존 기간 적용·감사 로그.
- 모바일 390px, 태블릿 820px, 데스크톱 1366px. 한국어, 표준 폼/레이블, 초점 표시, 응답 상태와 오류 안내. 밝은 바탕/파란 강조의 동일한 학생·관리자 UI. 자동화 검사는 전체 접근성 인증이 아닙니다.

## 실행 (Node >=22.18, npm)
이 폴더를 프로젝트 작업 디렉터리에 복사한 다음 실행하세요. npm 의존성은 검증 설치의 실제 버전으로 고정되어 있으며 `package-lock.json`을 포함합니다.

```sh
npm ci
# 무작위 값은 터미널에 출력하지 않고 현재 프로세스 환경에만 설정합니다.
export ASSESSMENT_ADMIN_SECRET="$(node -e 'process.stdout.write(require("crypto").randomBytes(32).toString("hex"))')"
export ASSESSMENT_ACCESS_CODE="$(node -e 'process.stdout.write(require("crypto").randomBytes(12).toString("hex"))')"
export ASSESSMENT_EXPIRES_AT="$(node -e 'process.stdout.write(new Date(Date.now()+86400000).toISOString())')"
# public/ 밖의 로컬 전용 경로. 권한이 제한된 디스크를 사용하세요.
export ASSESSMENT_DATA_DIR="$PWD/.local-data"
npm run build
npm run start -- --port 3000
```

`http://127.0.0.1:3000`에서 사용합니다. 생성된 코드/비밀키를 로컬 비밀 관리 경로로 전달하세요. README의 기본 비밀값은 없으며 키/코드/만료 시각 미설정 시 서버는 **fail closed** 합니다. 비밀키는 최소 32자, 코드는 최소 8자이며 만료 시각은 필수 ISO 날짜입니다. 설정은 런타임 환경 변수이며 `NEXT_PUBLIC_`을 사용하지 않습니다. 환경 변수를 바꿨으면 프로세스를 다시 시작합니다. 개발 모드는 `npm run dev`입니다. start/dev는 기본 loopback 바인딩이며 외부로 노출하지 마세요.

## 계약 및 정책
- 질문 원본 `data/questions.sample.json`: 세션/채점 버전, 질문 ID, 문구, 영역, 역문항, 가중치. 서버가 설정에서 reverse/weight를 가져오며 클라이언트 점수·임의 항목은 거부합니다. 질문 ID는 유일, scale=5, weight는 유한 양수여야 합니다. 수정한 질문 은행은 테스트 후 **새 sessionId/scoringVersion**으로 배포하세요.
- 점수: 역문항 `6-value`, 가중 평균, `round((avg-1)/4*100)`. 각 영역과 전체. level 경계는 21/41/61/81점이며 결과 문구는 성장 안내이지 확정 평가가 아닙니다.
- `POST /api/access {code}`, `POST /api/submit {code,grade,classNumber,studentNumber,answers:{Q001:1..5,...}}`. 코드 만료, 정확한 질문 집합, 정수·범위, 허용 필드만 검증. 응답은 결과만 반환하며 학생 전체 목록 API는 없습니다.
- 같은 sessionId+학년+반+번호는 **409로 차단**합니다. 관리자가 기존 제출을 삭제해야 다시 제출할 수 있습니다. 동시 중복도 파일 잠금 안에서 검사합니다. 이름/이메일/전화/계정은 수집하지 않습니다. 입력한 번호가 본인인지 증명하지 않는 접근 모델입니다.
- `POST /api/admin/login {secret}`: HMAC 서명 1시간 HttpOnly/SameSite=Strict 쿠키, HTTPS 시 Secure. `GET /api/admin/submissions`, `GET /api/admin/audit`, `GET /admin/export`, `DELETE /api/admin/submissions {id}`, `POST /api/admin/retention {days:1..365}`, `POST /api/admin/logout {}`는 인증 필요. 인증 없으면 401, 교차 Origin 쓰기는 403. 모든 쓰기는 같은 Origin이 필요합니다. 개인별 계정/RBAC/MFA는 없습니다.
- 응답/CSV는 no-store. CSV는 UTF-8 BOM/RFC 인용·따옴표 이스케이프, 위험한 `= + - @`/선행 공백·제어문자 수식을 작은따옴표로 중화합니다. 실제 저장 데이터만 내보냅니다. CSV를 받는 앱에서 다시 변환하면 보호가 없어질 수 있습니다.

## 로컬 내구성·삭제·감사 경로
- `${ASSESSMENT_DATA_DIR}/store.json`: version=1, submissions, audit. 처음엔 빈 저장소이며 예시 제출이 없습니다. 파일 mode 0600, 새 데이터 디렉터리/잠금 mode 0700.
- `${ASSESSMENT_DATA_DIR}/write.lock/`: 원자적 mkdir 잠금, 재시도 후 5초에 fail closed. 쓰기/읽기/중복 확인/감사는 모두 같은 잠금 안에서 수행합니다. 임시 파일 fsync → atomic rename → 디렉터리 fsync. 실패/손상 데이터는 덮어쓰지 않습니다.
- 프로세스가 강제 종료되어 잠금이 남으면 앱을 모두 멈추고 데이터 파일을 백업/검사한 뒤 `write.lock/`만 수동 삭제하세요. 자동 stale-lock 회수는 하지 않습니다. 파일이 작고 로컬 파일시스템일 때만 적합합니다. NFS/공유 디스크/다중 호스트/서버리스는 지원하지 않습니다.
- 제출 삭제/보존 기간 적용은 원문 응답·학년/반/번호·결과를 원자적으로 제거합니다. 보존은 **관리자 수동 실행**, 자동 cron 없음. 감사 메타데이터(submit/login/read/export/delete/retention/logout/audit_read)에는 무작위 제출 ID, 시각, 건수만 남습니다. 감사는 다음 저장소 접근 시 90일 초과 기록을 정리합니다. 코드/비밀키/응답/학년·반·번호는 감사에 남기지 않습니다. 감사는 로컬 파일 관리자에 의해 수정될 수 있어 변조 방지 로그가 아닙니다.
- 다운로드 CSV는 저장소 삭제와 별개입니다. 브라우저 다운로드/스크린샷/백업은 사용자가 보존 정책에 맞게 직접 삭제해야 합니다. 원자적 파일 교체는 디스크 포렌식 보안 삭제가 아닙니다. 디스크 암호화·OS 계정 권한은 운영자 책임입니다.

## 실제 검증
```sh
npm run test:unit
npm run build
DREAMPIA_UI_EVIDENCE=/absolute/path/to/evidence npm run test:ui
```
UI 테스트는 Playwright Chromium이 필요합니다(`npx playwright install chromium`). `DREAMPIA_UI_PORT` 기본 31947, 127.0.0.1 격리 서버이며 기존 서버 재사용을 **금지**합니다. 합성 비밀키/코드와 임시 데이터 디렉터리는 매 테스트 실행에서 생성합니다. 3 viewport에서 학생 제출 → 결과 → 관리자 조회·새로고침·CSV → 삭제·보존·감사·로그아웃 및 비인증/오류/중복/Origin 거부를 확인합니다. questions/result/admin PNG를 `DREAMPIA_UI_EVIDENCE` 아래 저장합니다. 사용한 임시 데이터 디렉터리는 테스트 종료 후 필요 없으면 직접 삭제하세요.

## LOCAL ONLY — 명시적 제한
실제 학생 개인정보·학교 운영·외부 공개 배포에 사용하지 마세요. TLS 서비스/다중 사용자 인증/권한 분리/개별 초대 코드/견고한 distributed rate limit/암호화 DB/백업 복구 정책/자동 보존/동의·법률 검토/부하·접근성 감사가 없습니다. 요청 제한은 단일 프로세스 메모리의 전역 경량 제한이며 재시작 시 초기화됩니다. 실패 인증은 보안 이벤트 저장/알림으로 제공하지 않습니다. 코드 공유자가 다른 번호를 제출할 수 있습니다. 질문/영역 설정 변경 시 과거 데이터 마이그레이션은 제공하지 않습니다. 운영 준비 완료/법적 적합성/실제 배포를 의미하지 않습니다.
