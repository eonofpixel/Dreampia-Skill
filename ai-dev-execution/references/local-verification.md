# 완료 전 로컬 검증

스킬은 검사 선택과 해석을 안내한다. 결정적 스크립트/하네스는 명령 실행·종료·시간제한·상태·증거를 처리한다. 지침만으로 우회 불가 보안 게이트를 만들었다고 주장하지 않는다.

## 공식 명령부터 확인
요청한 저장소의 AGENTS/README/CONTRIBUTING, package.json scripts, pyproject/Makefile 및 기존 CI 설정을 읽어 실제 공식 명령·작업 디렉터리·지원 버전·기존 설치 상태를 확인한다. 명령을 추측하거나 다른 사용자 프로젝트를 탐색하지 않는다. scripts 이름만 보지 말고 실행 내용·외부 서비스/키/배포/자동 설치 부작용을 확인한다. 기존 Git diff를 보존한다.

변경 행동과 위험에 맞게 lint/typecheck/test/build/필요한 E2E를 선택한다. 없는 도구는 설치 강제가 아니라 NOT_RUN과 이유/해제 조건으로 남긴다. lint PASS를 build PASS로, 단위 시험을 실제 UI/E2E PASS로 확대하지 않는다. 문서/정적 변경에 불필요한 서버·E2E를 만들지 않는다. 실제 결함은 수정 전 행동 Red와 수정 후 Green을 기록한다.

## 실행과 결과
각 검사에 정확한 argv/cwd, 환경·버전·시각, 기대/관찰 결과, 종료 코드·시간제한, PASS/FAIL/NOT_RUN 및 증거 위치를 연결한다. 시간초과·취소·출력상한은 PASS가 아니다. 실패와 권한/환경 제약을 구별한다. 남은 검사를 실행하지 않았다면 NOT_RUN이다. 긴 출력은 필요한 경우 외부 증거로 분리하고 비밀·개인 원문을 자동 저장하지 않는다.

선택 하네스는 기존 checks·source_hash·status/reverify를 사용한다. 검증 중 소스 변경은 거부하고 이후 변경은 stale이다. 새 증거 원장/실행 엔진을 중복 생성하지 않는다. 하네스를 사용하지 않으면 기존 프로젝트 기록에 검증 대상 파일·설정·검사 정의의 해시와 증거를 연결한다. 해시 대상/제외 범위를 명시하며 외부 API·설치 상태까지 인증한다고 주장하지 않는다.

## 게시 직전 대상 대조
최종 수정 뒤 영향받은 검사를 다시 실행한다. 이후 바뀐 파일/검사/환경에 종속된 결과는 stale 또는 NOT_RUN으로 돌린다. 검증한 파일 해시를 stage 또는 배포 아카이브의 실제 바이트와 대조하고, commit 후 HEAD와 게시할 commit SHA를 확인한다. 승인된 게시 전에 기존 사용자 변경·비밀·빌드/원시 로그 제외와 공개 범위를 확인한다. 다른 commit을 검증한 결과를 복사하지 않는다. 로컬 검증 후 push가 기본이며 GitHub Actions의 push/PR 자동 실행은 켜지 않는다. 수동 원격 실행은 별도 요청이 있어야 한다.

## 이 저장소의 공식 경로
`PYTHONDONTWRITEBYTECODE=1 python3 harness/local_ci.py`는 결정적 하네스 시험·참조 검사·예약 예제·zipapp·offline 평가 준비만 실행한다. 기존 설치된 지원 Python을 사용한다. `npm pack --ignore-scripts` 후 `python3 harness/npm_smoke.py TAR`는 격리 offline 설치를 검증하며 Python 의존성은 남는다. 최종 배포 ZIP의 재추출 검증과 npm 파일 바이트 대조는 별도로 수행한다.

local_ci는 기존 POSIX process.capture의 그룹 종료를 재사용하고 TIMEOUT/CANCELLED/OUTPUT_LIMIT 뒤 남은 검사를 NOT_RUN으로 기록한다. source_before/source_after는 이 도구의 명시 소스 루트 중 evidence를 제외한 파일 바이트의 연결이며 atomic snapshot/서명/적대적 변경 방어가 아니다. 실제 AI·제품 UI·다른 OS·원격 CI는 실행하지 않았다면 NOT_RUN이다.
