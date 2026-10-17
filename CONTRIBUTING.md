# Dreampia-Skill 기여 및 운영 정책 (Contribution Policy)

> 요약: Dreampia-Skill은 소스코드를 투명하게 공개하지만, 외부의 코드 Pull Request(PR)는 병합(Merge)하지 않습니다. 버그 제보와 기능 아이디어는 GitHub Issues를 통해서만 받습니다.

---

## 1. 기본 원칙: Open-Source, Not Open-Contribution

Dreampia-Skill은 SQLite와 동일한 운영 철학(Open-Source, Not Open-Contribution)을 채택하고 있습니다.

- 저장소의 모든 소스코드는 공개되어 있으며 누구나 열람, 실행, 자체 감사에 활용할 수 있습니다.
- 그러나 외부 기여자가 작성한 코드 패치나 Pull Request(PR)는 어떠한 경우에도 메인 브랜치에 직접 병합하지 않습니다.
- 모든 코드는 메인테이너가 프로젝트의 SDD(명세 주도 개발) 및 클린룸 재구축 파이프라인을 통해 처음부터 직접 작성하고 검증합니다.

---

## 2. 외부 코드 PR을 받지 않는 이유

### 2.1 공급망 보안 및 에이전트 프롬프트 무결성 보호
Dreampia-Skill은 일반 라이브러리가 아니라 `/update` 명령을 통해 사용자의 로컬 AI 호스트(Antigravity, Claude Code, Codex, Gemini CLI, Cursor 등) 전역 경로와 MCP 서버에 직접 배포되는 자율 엔지니어링 하네스입니다. 외부 코드나 프롬프트 수정을 병합할 경우 발생할 수 있는 프롬프트 인젝션, 백도어 정규식, 권한 우회 등 공급망 오염 가능성을 0%로 차단하기 위해 외부 코드 유입을 허용하지 않습니다.

### 2.2 무의존성(Zero-Dependency) 및 아키텍처 순혈성 유지
본 프로젝트는 외부 패키지 의존성 0개(Python 3.9+ 표준 라이브러리 단독), SOLID 객체지향 5원칙, 결정론적 Fail-Closed 보스 관문(`autopilot-gate`)이라는 엄격한 설계 기준 위에서 동작합니다. 코드베이스 전체의 일관성과 무결성을 유지하기 위해 단일 아키텍처 통제 체계를 고수합니다.

### 2.3 단일 저작권(Single Ownership) 및 프로젝트 주권 유지
외부 코드를 단 한 줄이라도 직접 병합하면 저작권이 파편화됩니다. Dreampia-Skill은 100% 자체 작성 코드만을 유지하여 법적 소유권과 라이선스 주권을 온전히 보존합니다.

---

## 3. 버그 제보 및 아이디어 제안 방법 (GitHub Issues)

코드 PR은 받지 않지만, 사용 중 발견한 문제점이나 개선 아이디어는 GitHub Issues를 통해 언제든 환영합니다.

1. 버그 제보 (Bug Report)
   - 발생한 환경(OS, Python 버전, 사용 중인 AI IDE 호스트)
   - 문제를 재현할 수 있는 최소한의 입력 또는 실행 명령어
   - 기대한 결과와 실제 출력된 오류 메시지
2. 기능 및 규칙 제안 (Feature / Rule Idea)
   - 해결하려는 문제 상황과 필요한 이유
   - 기대하는 입출력 형태 또는 정적 감사 규칙 아이디어

주의사항: 이슈를 작성하실 때 외부인이 작성한 긴 코드 패치를 그대로 붙여넣기보다, 문제의 원인과 요구사항(명세) 위주로 설명해 주시는 것이 가장 빠르고 정확하게 반영됩니다. 채택된 제보나 아이디어는 메인테이너가 자체 클린룸 구현 및 단위 테스트 검증을 거쳐 반영합니다.

---

## 4. 외부 Pull Request 처리 방침

- 사전 안내를 보지 못하고 제출된 외부 Pull Request는 코드 검토나 병합 없이 자동으로 종료(Closed without merge)됩니다.
- 만약 제출된 PR이 중요한 버그를 지적하고 있다면, 해당 PR의 코드는 사용하지 않고 문제 정의만 이슈로 기록한 뒤 메인테이너가 독립적인 방식으로 새로 설계하여 해결합니다.

---

## 5. English Summary (Open-Source, Not Open-Contribution)

Dreampia-Skill follows the same philosophy as SQLite: the project is open-source, but not open-contribution.

1. No External Code PRs: We do not accept or merge external Pull Requests. Any submitted PR will be closed without merging.
2. Why:
   - Supply-Chain & Prompt Security: Dreampia-Skill synchronizes skills and STDIO MCP servers across global AI agent hosts (`~/.gemini`, `~/.claude`, `~/.codex`, `~/.cursor`). Rejecting external code patches guarantees zero third-party supply-chain or prompt-injection contamination.
   - Zero-Dependency & Architectural Purity: Every line of code is written in-house using only the Python 3.9+ standard library and verified against our deterministic Fail-Closed gates.
   - Single Copyright Ownership: Maintaining 100% original authorship keeps copyright and licensing unambiguous.
3. Bug Reports & Ideas Welcome via Issues: If you find a bug or have a feature idea, please open a GitHub Issue describing the behavior, reproduction steps, or specification rather than submitting a code patch.
