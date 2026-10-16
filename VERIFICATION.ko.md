# 0.5.2 검증 범위

실제 누락참조 Red→Green, 변조/오타/누락/unlisted/버전/optional 검증과 전체회귀/재추출/npm 결과는 evidence/v0.5.2 및 최종archive해시 외부영수증 참조. 새로운runtime/자동재개/provider추가 없음. 실제AI·소비UI·모델비용효과·원격CI NOT_RUN.

# 0.5.1 검증 범위

실제 timeout Red→Green, 다섯 로컬CI 회귀 및 전체 회귀/격리 npm/최종 재추출 결과는 evidence/v0.5.1과 최종 ZIP 해시 외부 영수증 참조. 소비 프로젝트 사례 계획/실제 실행/NOT_RUN을 구별한다. 실제 AI/효과A/B/소비UI/원격CI는 NOT_RUN. 이전0.5.0은 a30b59f private 업로드 완료, 실제Actions목록[]였다. 이 버전도 push/PR 자동트리거 없음.

# 0.5.0 검증 범위

현재 결과는 evidence/v0.5 및 최종 ZIP 해시에 연결한 외부 영수증으로 기록한다. 과거 결과를 최신 결과로 대체하지 않는다.

- 수정 전 소스 전체 CI: macOS Python3.9.6 / 3.11.15 각각 하네스95 + 예약 예제4 PASS. 최신 수정 후 최종 ZIP 재추출 전체 CI는 별도 최종 영수증에서 확인한다.
- 수정 후 디자인 전달 회귀2개 PASS. 실제0.4.0→0.5.0 설치/업데이트/정확한 이전 manifest 롤백/신규 참조 제거/충돌·사용자 파일 보존 PASS.
- 격리 offline npm smoke PASS. 최종 tarball을 다시 포장해 설치와 ZIP 소스 바이트 일치를 외부 영수증에 기록한다.
- 독립 웹/macOS/모바일/CSV CLI 사례 검토의 P2 계약 충돌 수정.
- 실제 소비 UI 구현/스크린샷/조작/호스트 실사용·실제AI·효과A/B는 NOT_RUN. 스킬 문서 사례 검토와 실제 제품 품질을 혼동하지 않는다.
- evals baseline 바이트 보존. game-ai 설치본 변경 없음.

사용자 승인으로 이번 버전 검증 소스의 비공개 GitHub commit/push를 수행한다. 이전 버전의 미수행 기록은 역사 자료다. 원격 CI 설정의 npm 고정 파일명을0.5.0으로 수정했다. 실제 원격 실행 상태와 검증 commit SHA는 최종 외부 영수증에서 구별해 기록한다. 비밀/배포 ZIP·tgz/임시 원시 로그는 Git stage에서 제외한다.

# 0.4.0 디자인 계약 검증

현재 버전 결과는 최종 ZIP 해시에 연결된 외부 영수증으로 기록한다. 설치/패키지 검증과 독립 문서 사례 검토는 UI를 실제 구현·조작한 효과 A/B가 아니다. 실제 소비 프로젝트 UI 구현·스크린샷/조작 검증은 이번 스킬 수정 범위 밖이므로 NOT_RUN이다. game-ai 설치본은 변경하지 않는다.

## 이번 버전 실제 소스 검증

- macOS Python3.9.6 / Python3.11.15: 전체 CI 각각 하네스95 + 예제4 PASS.
- 새 배포/참조 생명주기 회귀2개 포함; 일반 설치/충돌/갱신/롤백/제거 전체 회귀 유지.
- actual-upgrade.json: 이전 최종 ZIP의 실제0.3.1 installer→현재0.4.0 update, 정확한 manifest/파일 rollback, 새 참조 제거, 충돌·사용자 파일·비밀 보존 PASS. 격리tmp에서만 실행.
- npm-smoke.json: 격리offline npm 설치/재설치/프로젝트 흐름 PASS. npm-pack.json에 파일 목록, private:true/hooks/dependency 없음. tgz는 통합ZIP 밖의 별도 산출물.
- skill frontmatter validator PASS(기존yaml 있는 Python3.14), 링크 검증223 PASS. 링크·파일 검사는 디자인 효과 증거가 아니다.
- 독립 UI/CLI-only 문서 사례 검토의 P2 계약 충돌 수정 및 해당절 재검토 완료.
- 실제UI 구현/스크린샷/조작/효과A/B/ChatGPT·Claude·DeepSeek 각 소비호스트 실사용, 실제AI/Linux/remoteCI는 NOT_RUN. 현재 작업은 스킬계약·전달 검증이며 게임프로젝트 제품UI완료를 주장하지 않는다.

최종ZIP 재추출 전체검증은 ZIP을 만든 뒤 실행하여 해시·명령·결과를 별도final-full-ci.json에 기록한다. 해당 실제 결과는 소스 검증과 구별한다.

# 0.3.1 최종 패키지 검증 후속 기록

이전 0.3.0 최종 ZIP SHA256 aed4b82b5296ae22c9bcf85eb384ac6d197abc3f4ea77261f00e78fe4ce98d5f의 전체 재추출 CI는 실제 FAIL이었다. 실패한 시험은 test_approval_error_is_not_success, test_auth_failure_no_automatic_retry, test_fake_provider_contract_integration 3개다. 기대 승인/인증/성공 결과 대신 TIMEOUT이 반환됐다. 이를 단순 외부 90초 timeout과 혼동하지 않는다.

별도 측정에서 세 fixture의 정상 실행은 0.66~1.24초(최초 version probe 0.43~0.84초)였고 오류 분류는 정확했다. 실행 시간이 변하는 환경에서 정상 fixture의 전체 2초 예산이 불안정한 검증 설계였다. 예산 초과를 TIMEOUT으로 처리한 제품 실행 계약은 유지한다. 정상 fixture 기본 예산만 10초로 보강하고 실제 timeout/cancel 회귀의 한도는 유지했다. 이 자료만으로 OS 지연의 정확한 원인을 인증하지 않는다.

첫 0.3.1 후보 ZIP 전체 CI에서는 Codex 세 시험이 통과했으나 test_orphan_holds_lock_after_runner_kill이 FAIL이었다. 1초 sleep 동안 새 CLI가 시작된다고 가정한 시험이었으므로 명시적 release gate로 자식 생존을 contender 완료에 동기화했다. 실제 lock 유지와 해제 assertion은 유지하고 runtime 코드는 변경하지 않았다. 해당 후보 실패 로그도 보존했다.

두 번째 0.3.1 후보 ZIP에서는 provider cancel 시험의 CLI 종료 코드가 예상 1 대신 2로 한 번 실패했다. 그 시험은 stdout/stderr를 버렸으므로 원인을 확정할 진단이 없었다. 진단 출력을 보존하도록 보강한 뒤 해당 취소 시험 12회와 Codex 전체 13개를 재실행했으며 모두 PASS였다. 오류 원인을 단정하지 않고 후보 실패 기록과 재현 시도를 보존한다.

최종 0.3.1 ZIP을 그대로 다시 추출한 전체 CI 결과 및 ZIP 해시는 배포 폴더 post-delivery-verification/final-031-full-ci.json과 FINAL-RESULT.json에 기록한다. 문서 작성 후 실제 ZIP을 검증하므로 결과 영수증은 ZIP 외부에 둔다. 실패 로그·측정 자료도 보존한다. npm tarball은 통합 ZIP 내부에 넣지 않고 별도 파일로 제공한다.

아래는 0.3.0 시점의 역사 기록이며 0.3.1 최종 결과를 대체하지 않는다.

# 0.3.0 실제 검증 — 2026-10-08 UTC

대상은 사용자·사내 개발자용 비공개 스킬+CLI 첫 팀 통합이다. 과거 v0.1/v0.2 보고서는 역사 자료이며 아래 현재 실행 결과로 대체하지 않는다.

## 입력과 회귀

기존 로컬 원본을 실제 읽고 VERSION=0.2.0, 검증 보고·추가 감사를 확인했다. 기존 스킬 ZIP(32파일) 및 통합 ZIP(106파일)은 CRC PASS이며 영수증 SHA256 및 deliverables와 모든 포함 파일 바이트가 일치했다.

감사 세 결함은 수정 전 실제 행동 FAIL 3개로 재현했다. `red-audit.txt` → `green-audit.txt`에서 평가 Infinity 거부, max_attempt 오타로 부작용 수행 전 거부, probe timeout 후 SIGTERM 무시 자식까지 종료를 확인했다. 최초 probe fixture가 자식 시작을 확인하지 않아 false green 가능성이 있었고, 최종 Red는 시작 확인을 추가한 정확한 시험이다. 재추출 중 한 번은 자식이 1초 내 시작하지 않아 assertion이 실패했다. 최종 시험은 3초 시작 예산·PID 시작 확인·probe 반환 후 gate 해제로 생존 부작용을 관찰한다. 이전 실패 로그를 성공으로 덮어 주장하지 않는다.

독립 검토에서 롤백 중간 실패 후 복구 차단, 초기 소유권 검사 누락, 매우 큰 정수 traceback을 찾아 수정했다. 최종 입력 검토의 루트/예약파일 하위 경로 및 macOS 대소문자·Unicode 파일명 충돌도 입력 생성 전에 거부하도록 최소 수정했다. 롤백 회귀는 수정 전 ERROR 1(행동 중 Conflict 예외), 수정 후 팀 시험 13 PASS이다. 이를 최초 감사의 행동 FAIL과 혼동하지 않는다. 독립 검토자가 수정 결과를 별도로 재현했다. 근거: independent-review.ko.md, red/green-rollback-review.txt 및 strict 테스트.

## 현재 실제 실행

- `PYTHONDONTWRITEBYTECODE=1 python3 harness/local_ci.py`: Python 3.9.6, 하네스 **93 PASS**, 예약 예제 **4 PASS**, 종료 0, all_pass=true.
- 같은 명령의 `python3.11`: Python 3.11.15, **93+4 PASS**, 종료 0, all_pass=true.
- 공통 스킬 frontmatter/로컬 링크 검사, fresh example run/trace, 0.3.0 zipapp build/version, locked suite prepare/aggregate PASS. 실제 평가 완료 쌍 0이며 effect_score=null.
- Node v22.22.3 / npm 10.9.8: `npm pack --ignore-scripts` PASS. private=true·버전 고정·dependency/자동 hooks 없음·.env/.git/.harness/원시 증거 제외를 확인했다.
- `python3 harness/npm_smoke.py TAR`: offline 격리 임시 prefix install, wrapper version, preview 무변경, init, doctor, 재설치, update, 충돌 보존, uninstall, rollback, 하네스 validate/run/trace PASS. 전역 설치·registry 접근 없음. 원래 AGENTS.md 및 fake .env 보존, 비밀이 metadata에 복사되지 않음 PASS.
- 팀 설치 단위 시험: 실제 내용 변경 update/rollback, managed-only 제거·사용자 파일 보존, 미완료 설치 및 미완료 rollback journal 복구, 설정 오타·bool/숫자·symlink/manifest 경로 변조·수정 충돌 거부 PASS.
- 전체 strict 시험: manifest 모든 레벨 오타·중복 JSON 키·비유한/범위/거대정수·파일 소유권 겹침·모델 상향/다른 reasoning 거부, locked evaluation 경로/미지 키 거부, probe 취소 자식 종료 PASS.

실행 로그는 evidence/v0.3/local-ci-py39.txt, local-ci-py311.txt, npm-pack.json, npm-smoke-final.json에 있다. 독립 검토는 84개+추가 strict 8개 시점이며 최종 전체 수는 위 현재 93개다.

## 패키지·저장소 결과

배포 ZIP CRC 및 재추출 smoke(version/설치/doctor/예약 예제4/trace/zipapp/제거)는 PASS이며 재추출 코드가 위 전체 검증 소스와 SHA256 일치한다. 재추출 전체 CI의 별도 시도는 fixture 시작 지연 실패 및 외부 90초 timeout으로 NOT_PASS이며 소스 전체 93+4 PASS와 구별한다. 근거: reextract.json, reextract-ci-first-failure.txt, reextract-full-ci-timeout.json. npm 및 소스 ZIP의 가짜 .env.local/개인키 파일 제외는 package-secret-exclusion.json에 PASS다. 대상 저장소 반영은 최종 결과 파일로 기록한다. source-sha256.json은 현재 코드·설정·문서의 해시다. Git identity를 보존하고 commit/stage/push/remote 생성은 하지 않는다. `git diff --no-index`는 v0.2 대비 변경 근거이며 빈 저장소의 untracked 내용을 커밋한 것으로 주장하지 않는다.

## NOT_RUN과 한계

실제 AI inference·모델 식별자 수용·로그인/유료 호출·AI 효과 A/B·다른 호스트 자동 발견·Linux/Windows·remote CI·wheel/pip 설치는 **NOT_RUN**. GitHub Actions 설정을 작성했지만 실행하지 않았다. 공개 게시·배포·팀 초대·전역 설치·키/SSH 설정은 범위 밖이다. 공개 배포 라이선스는 미선정이며 자체 코드를 MIT로 부여하지 않았다.

프롬프트 정책인 TDD/구현·검토 분리/검토 품질/파일 소유권 실제 접근을 코드가 인증하지 않는다. 엔진은 순차 실행한다. source_hash는 atomic snapshot/attestation이 아니며 외부 입력 자동 추적·OS sandbox·remote exactly-once·daemon/setsid 탈출 종료를 보장하지 않는다. 신뢰된 협조적 로컬 프로젝트를 대상으로 하며 적대적 동시 파일시스템 race를 인증하지 않는다. 민감 원문 quarantine은 배포하지 않는다.

GitHub 비용 정책(0.5.0): 로컬 `PYTHONDONTWRITEBYTECODE=1 python3 harness/local_ci.py` 및 격리 npm smoke를 실행한 뒤 업로드한다. `.github/workflows/local-ci.yml`은 `workflow_dispatch` 수동 실행만 허용하며 push/PR 자동 트리거는 없다. 이 작업에서는 원격 workflow를 실행하지 않는다. 계정/결제 설정은 변경하지 않는다.
