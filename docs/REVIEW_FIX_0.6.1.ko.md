# 0.6.1 독립 리뷰 후속 수정

0.6.0 부모 로컬 인수/푸시 이후 별도 독립 리뷰가 FAIL로 도착했다. 기존 0.6.0 완료 보고는 체크포인트 상태 검증 누락을 발견하지 못했다. 이 문서는 외부 리뷰 PASS 인증이 아니라 그 지적에 대한 부모의 재현·수정·재검증 기록이다.

## P1 checkpoint passed 증거 누락

실제 CLI 재현에서 evidence=[] 또는 result=FAIL/exit_code=7로 변경한 passed 상태를 resume이 exit 0으로 인정했다. 회귀 테스트 RED를 확인했다.

수정: evidence schema/types, 승인 argv, timeout, 실행 cwd, source_fingerprint, 타임스탬프, PASS와 exit0의 일관성 검사. passed는 모든 attempt 완료 증거와 마지막 PASS/exit0 및 의존 작업 passed를 요구한다. resume/status 모두 적용. running/중단·부작용 reconciliation은 완료 증거 누락이 가능하지만 passed로 인정하지 않는다. 상태 파일을 수정할 권한을 가진 공격자를 막는 서명 시스템은 아니다.

증거 없음/실패/nonzero exit/다른 argv/timeout/소스 지문/완료시각 누락/출력 형식/다른 cwd 9개 변형은 exit 2, 정상 체크포인트 재개는 exit 0으로 검증했다. 전용 workflow suite 15 tests PASS.

## P2 mock-store 정적 경로

리뷰 도중 이미 부모가 수정한 지적이다. 현재 app-static은 web/lib/store.ts를 검사한다. 새 생성 프로젝트와 전체 회귀에서 PASS를 확인한다.

## 비차단 권고: 구조 손상 저장 데이터

유효 JSON이지만 createdAt/감사 at이 잘못된 경우도 overwrite/retain을 거부하도록 최소 제출/감사 필드·타입·ISO 날짜를 검사한다. 실제 RED→GREEN 테스트에서 snapshot과 retention 모두 거부하고 원본 바이트를 보존한다.

## 재검증/반영

최종 실행 결과 및 Git SHA는 비공개 릴리스 폴더 /Users/bot-0/Dev/dreampia-releases/0.6.1/에 보존한다. 원격 CI/운영 배포/실학생/독립 provider 추론은 NOT_RUN이며 기존 로컬 범위를 유지한다. 이 수정은 독립 재리뷰가 PASS했다고 주장하지 않는다.
