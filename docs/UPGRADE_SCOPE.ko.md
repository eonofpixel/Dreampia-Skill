# 내부 개발 OS 고도화 범위와 완료 기준

이 문서는 출시 인증이 아니다. 실제 상태는 실행 증거와 acceptance 보고서로 판정한다. 저장소는 비공개이며 외부 배포·registry publish·실학생 데이터 처리는 이번 범위에서 제외한다.

## 전체 잔여 작업 목록

- 검증: FAIL/NOT_RUN fail-closed, CLI 실패 exit code, evidence JSON 상태와 개별 check 확인, 소스 fingerprint, 실행별 UI evidence, 오래된 증거 무효화, placeholder 검사 거부.
- 테스트: 실제 scoring 정상/역문항/가중치/오류 tests, API validation tests, submit/result/save/reload/admin/export E2E, unauthorized access, duplicate rejection, CSV injection regression.
- 앱: 설정 기반 questions, class access, 학생 no-signup 흐름, 1~5점 응답, 결과 표시, local persistence, admin 조회와 통계/CSV, audit/deletion/retention 경로.
- 보안: 관리자 인증 실패 시 차단, 비밀값 환경변수 입력, 서버 검증, 최소수집, 중복 제출 제어, 관리 기능 권한, CSV formula defense. 공개 운영 전 추가 rate limit/HTTPS/session/CSRF/기관별 정책 검토 필요.
- orchestration: 명시적 contract와 역할, 실제 local adapter 호출, 의존성, bounded timeout/retry, status/evidence, 미설정 adapter NOT_RUN/FAIL.
- 복구: durable checkpoint, 명시 resume, 변경된 소스와 증거 구분, side-effect approval와 자동 replay 금지.
- 전달 보호: 명시 client_export_allowed 허용 목록, internal path 차단, secrets 검사, ZIP 중첩 제외, 고객 요약에 내부 파일명 노출 금지.
- 재현성: pinned deps와 lockfile, npm ci, 지원 환경, preview/apply/conflict preservation, 설치/업데이트/검증 안내.
- 실전 검증: fresh generated project, actual npm ci/build/unit/browser, submit 저장→조회→CSV 확인, 직접 screenshot 검수, 인계.
- 문서: 완료와 미실행/운영승인 필요 구분, 직원용 runbook, source/license/provenance 보존.

## 두 종류의 완료

1. 내부 도구 milestone: 테스트된 local 실행과 안전한 전달/복구 도구. 이 범위의 acceptance가 통과하면 내부 milestone 완료.
2. 학교용 production 서비스: 최종 문항/채점 승인, 개인정보 정책·보관 기간, 관리자 운영 권한, 배포 환경·domain·DB·backup, 보안/load tests, 학교 pilot. 내부 milestone만으로 이 범위를 완료했다고 주장하지 않는다.

## 승인 경계

사용자 요청은 로컬 개발·검증을 승인했다. 외부 배포/실제 계정·키 설정/실학생 데이터 사용/유료 모델 inference/외부 발송은 자동 실행하지 않는다. git commit/push는 현재 명시 지시 없으면 하지 않는다.
