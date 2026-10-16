# 지원 범위 (v0.6.1)

`0.6.1`은 사용자·사내 개발자용 크로스플랫폼 로컬 통합 버전이다. **Windows 10/11 (Win32 Job Objects / `msvcrt`), macOS (Apple Silicon / Intel), Linux** 및 **Python 3.9 이상**에서 외부 패키지 의존성 없이 순수 표준 라이브러리만으로 동작한다.

Node wrapper(`dreampia`)는 Node.js 18 이상과 Python 3.9 이상을 요구한다. 기본 설정에서는 원격 CI, 유료 공급자 추론(`provider_enabled`), 외부 네트워크 호출을 자동 실행하지 않으며, 모든 정적 분석·SDD+TDD 추적·Trinity 코드 감사·클린룸 복원 검증·시각 수용 검증은 로컬 오프라인에서 결정론적으로 수행된다.

업데이트는 팀이 승인한 고정된 Git ref, ZIP 또는 로컬 npm tarball로만 수동 수행한다. 자동 업데이트·전역 설정 임의 변경·모델 자동 상향은 없다. 파일 충돌은 보존하며 `doctor`, 미리보기와 명시적 `rollback`으로 진단·복구한다. 롤백 기록은 직전 트랜잭션을 안전하게 복원한다. 지원 문제를 공유할 때 `.env`, quarantine, 원시 provider 출력, 비밀 키를 포함하지 않는다.

최종 검증 범위와 결과는 [VERIFICATION.ko.md](VERIFICATION.ko.md) 및 [ARCHITECTURE.ko.md](ARCHITECTURE.ko.md)를 참조한다.
