# Codex 호스트 어댑터

공통 스킬은 모델 및 도구에 독립적인 작업 흐름을 정의한다. Python `harness/codex_adapter.py`는 선택적인 Codex CLI JSONL 계약만 처리한다. 팀 정책의 모델 `gpt-6.1-sol`, reasoning `medium`을 argv에 고정하고 다른 모델·reasoning 요청은 거부한다. CLI의 실제 모델 식별자 수용 및 inference는 이번 버전에서 NOT_RUN이다. 허용 capability probe 버전은 0.144.6과 0.161.0이다. 0.161.0은 실제 --version/exec --help의 필수 옵션만 확인했으며 live inference는 NOT_RUN이다. 그 외 버전은 UNVERIFIED_VERSION으로 차단한다. help probe READY를 모델 호출/품질 인증으로 주장하지 않는다.

원시 provider 출력 및 인증환경을 보관하지 않는다. 계정 로그인·키 설정·승인·OS sandbox는 호스트의 책임이다. `doctor` 기본은 Python·설치 파일·프로젝트 설정을 확인하며 provider를 실행하거나 로그인하지 않는다. `dreampia harness doctor PROJECT --executable PATH`는 명시적으로 CLI help/version만 조회한다.
