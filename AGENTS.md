# 팀 개발 지침

대상은 공통 스킬(`ai-dev-execution`)과 무의존성 Python 3.9+ 크로스플랫폼(Windows/macOS/Linux) 하네스다. 기존 사용자 변경과 비관리 `.dreampia/` 데이터 폴더를 먼저 확인하고 보존한다. 공통 스킬, 하네스, 호스트 어댑터, 팀 정책, 프로젝트 설정을 분리한다.

요청 모델 gpt-6.1-sol과 reasoning medium을 유지하고 자동 상향하지 않는다. 기본 단일 실행자이며 독립 작업 병렬/독립 검토는 사용자가 허용한 범위에서만 사용한다. 수정한 행동과 영향을 받은 검증을 먼저 확인하고 완료 전 실제 결과를 기록한다.

Apache-2.0 라이선스(`LICENSE`) 및 클린룸 3-영역 오염 분리 경계(`NOTICE`)를 준수한다. 계정/키/SSH/전역 설정/remote/push/registry 게시/배포/유료 inference는 별도 사용자 지시 없이는 하지 않는다. 커밋은 요청되었을 때만 한다.

검증은 `PYTHONDONTWRITEBYTECODE=1 python -m harness.local_ci`와 팀 설치/격리 npm smoke다. PASS와 NOT_RUN, CI 설정과 실제 원격 실행을 구별한다.
