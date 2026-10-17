<div align="center">

<img src="docs/assets/dreampia-hero-banner.svg" alt="Dreampia-Skill Hero Banner" width="100%" />

<br/>

**[🇺🇸 English](README.md)** | **[🇰🇷 한국어](README.ko.md)** | **[🇯🇵 日本語](README.ja.md)** | **[🇨🇳 简体中文](README.zh-CN.md)**

<br/>

[![Version](https://img.shields.io/badge/version-1.1.0-0ea5e9?style=for-the-badge)](package.json)
[![License](https://img.shields.io/badge/License-Apache_2.0-8b5cf6?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-10b981?style=for-the-badge&logo=python&logoColor=white)](pyproject.toml)
[![MCP Tools](https://img.shields.io/badge/MCP_Tools-23_Ready-f59e0b?style=for-the-badge)](harness/mcp_server.py)
[![Zero Warnings](https://img.shields.io/badge/Self_Audit-70_Files_0_Warnings-22c55e?style=for-the-badge)](harness/autopilot_engine.py)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero_(Stdlib_Only)-ec4899?style=for-the-badge)](pyproject.toml)

**국문 프롬프트 고도화 브리핑(3줄 핵심 요약 + 소크라테스식 사전 질문 + 다음 추천 작업), SDD + TDD 실행, 2-Tier 클린룸 역공학(내장 파서 + 외부 리버싱 부스터), 자율 지표 등반(Metric-Climb), 폭발 반경(Blast-Radius) 분석, 통합 오토파일럿을 하나로 묶은 6대 호스트 에이전트 하네스**

</div>

---

## ✨ 왜 Dreampia-Skill 인가요?

기존 AI 코딩 도구들은 사용자의 짧은 요청을 얕게 해석해 엣지케이스를 놓치거나, 테스트를 생략하고, 채점 파일을 임의로 수정(Reward Hacking)하거나, 무거운 외부 의존성 설치 실패로 멈추기 쉽습니다. **Dreampia-Skill**은 Dreampia가 100% 독자적인 클린룸 아키텍처(**Apache-2.0**)로 설계한 **무의존성(Python 3.9+ 표준 라이브러리 전용)** 하네스로, **Antigravity, Claude Code, Cursor, Codex, OpenCode, Gemini CLI**에 단 한 줄로 설치됩니다:

1. **🧠 국문 프롬프트 고도화 & 소크라테스식 사전 인터뷰 (`expand-prompt` / `sharpen`)**: 주인공 영웅(**Hero**, 사용자)의 한 줄 한글 퀘스트 요청을 곧바로 코딩하지 않고, **한 번 더 생각한 국문 엔지니어링 프롬프트**(SOLID 5원칙·타입 안전성·선택적 UI 규칙·방어할 엣지케이스 자동 주입)와 **Sage(대현자)의 도메인별 핵심 질문 3선**, **다음 추천 퀘스트 작업 가이드**를 채팅창 상단에 먼저 브리핑합니다.
2. **🔬 2-Tier 클린룸 역공학 & 외부 리버싱 도구 진단/설치 플래너 (`reconstruct-doctor`)**:
   - **Tier 1 (내장 무의존성 엔진)**: 외부 프로그램 설치 없이도 `PE/ELF/Mach-O/WASM/ASAR/APK/ZIP/Source`의 바이너리 헤더와 공개 심볼·API 표면을 즉시 추출하고 3-영역 무오염 격리(`contaminated-zone` / `approved-spec` / `implementation`) 및 의무 원장(`Obligation Ledger`) 100% 커버리지를 강제합니다.
   - **Tier 2 (선택적 외부 부스터 & 설치 플래너)**: 호스트 OS의 패키지 매니저(`winget`, `scoop`, `choco`, `brew`, `apt-get`)를 자동 감지하여 `rizin`, `jadx`, `ghidra`, `wasm2wat`, `objdump`, `nm`, `adb`를 선택 설치 계획(`--install-tool <id|all> [--apply]`, 무승인 `sudo` 및 MCP 원격 설치는 안전 차단)으로 안내하고 심층 심볼을 자동 병합합니다.
3. **⚔️ 판타지 RPG 주인공 영웅(Hero) & 길드 파티 스쿼드 + 13종 매직 단축어**: 주인공 영웅(`Hero`)이 발주한 프로젝트를 퀘스트 등급(`C/B/A/S`)으로 분류하고, `GuildMaster`(길드장) 지휘 아래 `Sage`(대현자), `Archmage`(대마법사), `Bard`(음유시인), `Paladin`(성기사), `Inquisitor`(심판관), `Cleric`(치유사), `Guardian`(수호기사), `Alchemist`(연금술사), `Archer`(궁수)가 역할과 쓰기 경계를 분리해 협업하며, `ulw`, `loop`, `climb`, `blast`, `sharpen`(`구체화`), `re` 등 13종 단축어로 즉시 가동됩니다.
4. **🛡️ 비관리 `.dreampia/` 데이터 폴더 충돌 방지 & 안전한 글로벌 백업/복원**: 프로젝트에 이미 애플리케이션 데이터용 `.dreampia/` 폴더가 있으면 스킬 상태(메모리·워크트리)를 `.dreampia-skill/`로 자동 격리하고 `init` 덮어쓰기를 차단합니다. 또한 `setup --apply` 시 기존 비관리 글로벌 스킬을 `.pre-dreampia.bak`으로 자동 백업하며 `uninstall-global --apply`로 언제든 원상복구할 수 있습니다.

---

## ⚡ 10초 원클릭 설치 가이드 (Windows & macOS 완벽 지원)

파이썬 가상환경(`venv`)이나 `pip install` 설정이 전혀 필요 없습니다(`bin/dreampia.cjs`가 Windows의 `python`/`py -3`와 macOS/Linux의 `python3`를 자동 탐지합니다).

### 방법 1. `npx` 원클릭 글로벌 설치 & 제거
터미널(Windows PowerShell 또는 macOS/Linux)에서 아래 한 줄만 실행하면 글로벌 스킬 경로(Antigravity, Claude Code, Cursor, Gemini, Agents)와 Antigravity 글로벌 MCP(`mcp_config.json`)가 등록됩니다(기존 동명 비관리 스킬은 자동 백업):

```bash
# 글로벌 설치
npx github:eonofpixel/Dreampia-Skill setup --apply

# 글로벌 설치 제거 및 백업 원상복구 (미리보기 후 --apply)
python -m harness.team_cli uninstall-global --apply
```

### 방법 2. AI에게 복붙 한 줄로 설치 시키기
사용 중인 AI 채팅창(Antigravity, Claude Code, Cursor, Codex, OpenCode 등)에 아래 문장을 그대로 붙여넣으세요:

> ```text
> https://github.com/eonofpixel/Dreampia-Skill 레포를 클론하고 python -m harness.team_cli setup --apply 실행해서 글로벌 스킬이랑 MCP까지 한 번에 설치해줘.
> ```

### 방법 3. 호스트별 네이티브 플러그인 & 수동 설치

| 사용 환경 | 원클릭 명령어 |
| :--- | :--- |
| **Claude Code** | `/plugin marketplace add eonofpixel/Dreampia-Skill` &#8594; `/plugin install dreampia-skill` |
| **Cursor** | `/add-plugin https://github.com/eonofpixel/Dreampia-Skill` (`.cursor-plugin/plugin.json` 지원) |
| **Gemini CLI** | `gemini extensions install https://github.com/eonofpixel/Dreampia-Skill` |
| **Git Clone (Windows / macOS)** | `git clone https://github.com/eonofpixel/Dreampia-Skill.git && cd Dreampia-Skill && python -m harness.team_cli setup --apply` |

---

## 🧠 국문 프롬프트 고도화 & 소크라테스식 인터뷰 브리핑 (`expand-prompt`)

짧게 `"구체화 결제 버튼 만들어줘"`라고만 입력해도, 에이전트가 작업 착수 전 아래와 같은 **심플한 국문 퀘스트 작전 브리핑**을 채팅창 상단에 먼저 출력합니다:

```text
[Dreampia 국문 프롬프트 고도화 & 퀘스트 작전 브리핑]
- 한 번 더 생각한 고도화 프롬프트: [결제 버튼] 작업 시 기본 동작뿐 아니라 입력값 검증·예외 방어·상태 일관성까지 함께 챙깁니다. 버튼 기본 스타일(bg-transparent + hover/focus)과 lucide-react 아이콘 규격을 준수하고 중복 클릭·로딩·오류 상태를 매끄럽게 처리하며, SOLID 5원칙과 타입 안전성(any 금지·반환 타입 명시), 친절한 한글 안내 문구, 실제 테스트 검증까지 한 번에 적용합니다.
- 자동 챙김 항목: SOLID/타입 안전성, 보안/권한 차단, UI 규격(투명 버튼/lucide 아이콘/연타 방지), 예외/경계값 방어, 실제 테스트 검증
- 담당 길드 파티: Hero(주인공 영웅) -> GuildMaster(길드장) -> Sage(대현자) -> Paladin(성기사) -> Inquisitor(심판관) -> Cleric(치유사) -> Guardian(수호기사) -> Archmage(대마법사)
- Sage(대현자) 사전 인터뷰 핵심 질문:
  1. 주로 사용할 화면 크기(뷰포트: PC/모바일)와 버튼 중복 클릭·로딩 중 화면 처리는 어떻게 할까요?
  2. 입력이 잘못되었거나 완료되었을 때 알림(인라인 문구·토스트·팝업)을 어떻게 보여줄까요?
  3. 꼭 맞춰야 하는 기준 디자인이나 기존 화면 컴포넌트 스타일이 있나요?
- 다음 추천 작업 (Next Actions):
  1. 질문 답변으로 기획서·할일 목록 자동 생성 -> 입력 예시: "sdd 위 질문 답변 반영해서 기획서랑 할일 목록 만들어줘"
  2. 방금 작성한 코드 품질·규칙 자동 점검 -> 입력 예시: "audit 방금 짠 코드 규칙 위반 없는지 점검해줘"
  3. 연결된 다른 파일 영향도 확인 -> 입력 예시: "blast 수정한 파일과 연결된 곳에 영향 없는지 봐줘"
```

터미널에서 직접 실행해 보기:
```bash
python -m harness.team_cli expand-prompt --project . --goal "구체화 결제 버튼 만들어줘"
```

---

## ⚔️ 판타지 RPG 주인공 영웅(Hero), 퀘스트 등급 & 길드 파티 아키텍처

<div align="center">
  <img src="docs/assets/guild-party-architecture.svg" alt="Dreampia Guild Party Architecture" width="100%" />
</div>

### 1. 주인공 영웅(`Hero`) & 10대 길드 클래스 편성표

| 클래스 콜사인 | 한글 명칭 | 역할 (Role) | 핵심 담당 업무 및 소유 경계 |
| :--- | :--- | :--- | :--- |
| **`Hero` (사용자)** | 주인공 영웅 | `protagonist` | 퀘스트 발주자 및 원정 총사령관 — 최종 의사결정 및 병합(Merge) 승인 |
| **`GuildMaster`** | 길드마스터 (길드장) | `commander` | 총괄 라우터 및 퀘스트 지휘관 — 퀘스트 등급(`C/B/A/S`) 판정, 파티 편성 및 실행 모드 라우팅 |
| **`Sage`** | 세이지 (대현자) | `planner` | 제품 기획 및 퀘스트 저널(SDD)·백로그 설계자 — 소크라테스식 사전 인터뷰 질문 3선 및 `PRD/REQ` 수립 |
| **`Archmage`** | 아크메이지 (대마법사) | `architect` | 시스템·데이터·신뢰 결계 설계자 — 모듈 분리, API 계약, 1-Hop/2-Hop 폭발 반경(`blast-radius`) 산출 |
| **`Paladin`** | 팔라딘 (성기사) | `executor` | TDD 기반 주력 코드 구현자 — Red-Green-Refactor 사이클 및 SOLID 코드 작성 (`src/`, `harness/`) |
| **`Knight`** | 나이트 (기사) | `implementer` | 클린룸 독립 재구현 및 대규모 퀘스트 병렬 제2구현자 (`implementation/`) |
| **`Archer`** | 아처 (궁수) | `design-critic` | 프론트엔드·UI 컴포넌트 정밀 구현 및 시각 위계·`bg-transparent` 버튼·`lucide-react` 아이콘 감식 (`app/`, `components/`) |
| **`Bard`** | 바드 (음유시인) | `ux-designer` | 사용자 여정(UX Flow)·다국어 문구·반응형 뷰포트 예산 및 시각 수용(`visual-check`) 설계 (`docs/02_IA_UX.md`) |
| **`Alchemist`** | 알케미스트 (연금술사) | `analyst` | 클린룸 역공학(`re`) 명세 추출 및 재구축 의무 원장(`Obligation Ledger`) 연성 (`contaminated-zone/` &#8594; `approved-spec/`) |
| **`Inquisitor`** | 인퀴지터 (심판관) | `reviewer` | SOLID 원칙·설계 정합성·결함 수석 심판관 — 정적 AST 코드 감사(`audit-code`) 및 적대적 테스트 검증 (`tests/`) |
| **`Cleric`** | 클레릭 (치유사) | `verifier` | 실행 증거·시각 픽셀·원장 커버리지 검증 및 자가 치유(`loop`) 오퍼레이터 — 최종 보스 관문(`autopilot-gate`) 판정 |
| **`Guardian`** | 가디언 (수호기사) | `privacy-guard` | 개인정보(PII)·비밀키·클린룸 3-영역 무오염 결계 및 지침 드리프트 수호자 |

### 2. 퀘스트 등급 (`QUEST_RANKS`: C / B / A / S)

| 퀘스트 등급 | 프로파일 (`profile`) | 엄격도 (`rigor_tier`) | 출정 길드 파티 구성 및 적용 대상 |
| :---: | :---: | :---: | :--- |
| **`C급` 단기 토벌** | `quick` | `nano` | `Paladin` &#8594; `Cleric` (2인 속전속결) — 단일 파일 수정, 오타·경미한 버그 패치 |
| **`B급` 정규 파티 원정** | `team` | `standard` | `Sage` &#8594; `Paladin` &#8594; `Inquisitor` &#8594; `Cleric` (4인 정규 파티) — 일반 기능 개발, API·모듈 추가 |
| **`A급` 정예 공성전** | `controlled` | `full` | `Sage` &#8594; `Archmage` &#8594; `Paladin` &#8594; `Inquisitor` &#8594; `Cleric` &#8594; `Guardian` (+UI 시 `Bard`/`Archer`) — 결제·인증·DB·대규모 리팩토링 |
| **`S급` 고대 유물 복원** | `cleanroom` | `full` | `Sage` &#8594; `Alchemist` &#8594; `Paladin`/`Knight` &#8594; `Inquisitor` &#8594; `Cleric` &#8594; `Guardian` — 바이너리·번들 역공학 및 무오염 클린룸 재구축 |

### 3. 1컴 다중 파티원(Multi-Agent Worktree) 배치 & 1~10호기 원정 캠프 (`camp-01` ~ `camp-10`)

컴퓨터 1대에 에이전트 1명만 둘 필요 없이, **PC 1대(윈도우 PC 또는 맥미니 1대) 안에 Git Worktree 격리 공간(`.dreampia/worktrees/*`)을 통해 4~6명의 길드 파티원을 동시에 배치**할 수 있습니다. 여러 대의 기기(`1~10호기`)를 운영할 때는 각 기기를 길드 파티가 주둔하는 **원정 캠프(배럭)**로 활용합니다:

- **본성 (`GuildHall` / 드림피아 AI 브라우저 & 모바일 리모트 앱)**: 주인공 영웅(`Hero`)이 데스크톱 AI 브라우저 채팅창이나 모바일 리모트 앱에서 퀘스트를 발주하고 보스 관문(`autopilot-gate`) 통과 시 병합(Merge)을 승인합니다.
- **단일 PC 다중 파티원 모드 (기본)**: 1대의 PC 내부에서 `Paladin`(`dreampia/squad-paladin`), `Archer`(`dreampia/squad-archer`), `Inquisitor`(`dreampia/squad-inquisitor`)가 서로 다른 워크트리와 소유 경로(`owned_paths`)를 잡고 충돌 없이 동시 작업합니다.
- **다중 호기(`camp-01` ~ `camp-10` / `bot-01` ~ `bot-10`) 확장 모드**:
  - **방식 A (퀘스트별 전담 원정대)**: `1호기(camp-01)`는 프로젝트 A 풀파티(5인), `2호기(camp-02)`는 프로젝트 B 풀파티(5인), `3호기(camp-03)`는 S급 역공학 파티(4인)처럼 호기마다 독립 풀파티를 배치합니다.
  - **방식 B (부하별 특화 캠프)**: 가벼운 기획·설계·코드 구현 클래스(`Sage`, `Archmage`, `Paladin`×2, `Archer`×2)는 1호기에 다중 합숙시키고, 무거운 브라우저 E2E·WASM 빌드(`Cleric`, `Inquisitor`)나 바이너리 리버싱(`Alchemist`)은 2~3호기에 전담 배치합니다.

---

## 🚀 13종 매직 프롬프트 단축어

프롬프트 앞이나 중간에 짧은 단축어를 넣으면 최적의 멀티 에이전트 길드 파티 파이프라인이 즉시 활성화됩니다:

| 영문 단축어 | 한글 단축어 | 활성화되는 파이프라인 및 동작 | 프롬프트 사용 예시 |
| :---: | :---: | :--- | :--- |
| **`sharpen`** / `boost` | `고도화`, `구체화`, `생각` | **국문 프롬프트 심층 고도화 + Sage 사전 인터뷰 질문 3선**<br/>모호한 요청을 정밀 엔지니어링 명세·엣지케이스·역질문으로 확장 | `"구체화 결제 버튼 만들어줘"` |
| **`ulw`** / `ultrawork` | `풀가동`, `오토파일럿` | **전 길드 파티 풀가동 + 통합 오토파일럿 게이트**<br/>A급 정예 공성전(`controlled`) 프로파일 + 전 단계 검증 원스톱 실행 | `"ulw 결제 모듈 리팩토링하고 웹훅 재시도 추가해줘"` |
| **`loop`** / `until-pass` | `루프`, `완주`, `끝까지` | **자율 복구 Pass/Fail 완주 루프**<br/>테스트와 코드 감사가 100% 통과할 때까지 자동 자가 수정 | `"loop 인증 미들웨어 깨진 테스트 끝까지 고쳐줘"` |
| **`climb`** / `hillclimb` | `성능등반`, `자율실험` | **자율 지표 등반 엔진 (`metric-climb`)**<br/>불변 채점 파일 가드 + SHA-256 중복 실험 차단 + 몬테카를로 유의성 | `"climb 파서 응답 지연시간 5ms 이하로 성능등반해줘"` |
| **`re`** / `cleanroom` | `역설계`, `클린룸` | **2-Tier 클린룸 역공학 & 재구축 원장 검증**<br/>내장/외부 파서 분석 &#8594; 3-영역 격리 &#8594; 의무 원장·골든 I/O 100% 검증 | `"re 레거시 바이너리 분석해서 클린룸 재구현해"` |
| **`blast`** | `폭발반경`, `영향도` | **폭발 반경(Blast Radius) & 5단계 안전 증명**<br/>1-Hop/2-Hop 호출자 추적, 시스템 경계 교차 및 안전 증명 등급 산출 | `"blast route_planner.py 수정 시 폭발반경 체크해줘"` |
| **`interrogate`** | `심문`, `적대적리뷰` | **다중 관점 적대적 코드 심문**<br/>Archmage·Inquisitor·Guardian이 동시에 변경사항의 취약점을 타격 | `"interrogate 이번 PR 변경점 적대적리뷰 해줘"` |
| **`unslop`** / `deslop` | `군더더기제거`, `슬롭제거` | **AI 슬롭(Slop) 코드·주석 정밀 세척**<br/>예외를 삼키는 `bare except: pass`, 가짜 단언문, 불필요한 주석 제거 | `"unslop 새로 짠 서비스 레이어 군더더기제거 해줘"` |
| **`btw`** | `잠깐`, `빠르게` | **컨텍스트 오염 없는 사이드 질문**<br/>파일 수정 없이 현재 문맥을 보존하며 `Sage`가 즉시 답변 | `"btw 지금 프로젝트에서 라우터 설정 파일 어디 있어?"` |
| **`sdd`** | `명세`, `설계` | **명세 주도 개발 (`sdd-ledger` / `sdd-check`)**<br/>`PRD-R*` &#8594; `TASK-*` &#8594; `TEST-*` 양방향 추적성 원장 검증 | `"sdd 멀티테넌트 구독 결제 API 명세부터 설계해줘"` |
| **`tdd`** | `티디디` | **테스트 주도 개발**<br/>실패하는 실제 단언문 테스트 먼저 작성 &#8594; 최소 구현 &#8594; 리팩토링 | `"tdd 레이트 리미터 미들웨어 구현해줘"` |
| **`audit`** | `감사`, `보안점검` | **Inquisitor 정적 AST 코드 감사 (`audit-code`)**<br/>SOLID, `any` 금지, 반환 타입 명시, 슬롭 차단, 버튼/아이콘 규칙 검사 | `"audit 현재 프로젝트 SOLID랑 UI 규칙 위반 점검해"` |
| **`ui`** | `화면`, `디자인` | **UI/UX 구현 & 시각 수용 검증 (`visual-check`)**<br/>`bg-transparent` 버튼·`lucide-react` 아이콘 강제 및 PNG 픽셀/뷰포트 검증 | `"ui 다크모드 실시간 매출 대시보드 화면 만들어줘"` |

---

## 🔬 2-Tier 클린룸 역공학 & 외부 리버싱 부스터 (`reconstruct-doctor`)

Dreampia-Skill은 외부 도구가 없어도 즉시 작동하는 **Tier 1 내장 엔진**과, 호스트에 설치된 전문 리버싱 도구를 자동 병합하는 **Tier 2 외부 부스터**를 결합했습니다.

```bash
# 1. 현재 OS 패키지 매니저(winget/scoop/brew/apt) 및 Tier 1 & Tier 2 도구 가용 상태 진단
python -m harness.team_cli reconstruct-doctor

# 2. 미설치된 Tier 2 외부 도구(예: rizin, jadx, ghidra, wasm2wat, objdump, nm, adb, all) 설치 계획 미리보기
python -m harness.team_cli reconstruct-doctor --install-tool rizin,jadx

# 3. 로컬 CLI에서 선택 설치 실행 (--apply 명시 시에만 실행, sudo 및 MCP 원격 호출은 안전 차단)
python -m harness.team_cli reconstruct-doctor --install-tool rizin,jadx --apply
```

---

## 🛡️ 주요 검증 파이프라인 CLI 명령어 (자체 도그푸딩 지원)

`Dreampia-Skill` 저장소 자체(`--project .`)를 포함해 모든 프로젝트에서 즉시 실행할 수 있습니다:

```bash
# 1. 국문 프롬프트 고도화 & 소크라테스식 사전 인터뷰 질문 생성
python -m harness.team_cli expand-prompt --project . --goal "구체화 결제 버튼 만들어줘"

# 2. Inquisitor 정적 AST 코드 감사 (--apply 시 evidence/code-audit.json 저장, --no-ui-rules로 자체 디자인 시스템 프로젝트 UI 규칙 검사 생략 가능)
python -m harness.team_cli audit-code --project . --apply

# 3. Archmage & Cleric 1-Hop/2-Hop 폭발 반경(Blast Radius) 및 5단계 안전 증명 분석
python -m harness.team_cli blast-radius --project . --target harness/route_planner.py

# 4. 장기 세션 문맥 망각(Context Rot) 방지용 초압축 컨텍스트 팩 생성
python -m harness.team_cli context-pack --project . --goal "역공학 엔진 고도화"

# 5. 통합 오토파일럿 게이트 (지침 동기화 + SDD/TDD 추적 + 코드 감사 + 클린룸/시각 검증 원샷 판정)
python -m harness.team_cli autopilot-gate --project . --allow-doc-only

# 6. 프로젝트 자가 학습 메모리 등록 (이후 audit-code 및 expand-prompt에 영구 자동 반영)
python -m harness.team_cli learn-rule --project . --rule "결제 금액 계산 시 float 금지" --forbidden-regex "\bfloat\s*\(" --apply

# 7. Sage 인터뷰 답변 ➔ SDD 3종 명세서(PRD/BACKLOG/TEST_PLAN) 및 추적 원장 원샷 생성
python -m harness.team_cli interview-compile --project . --goal "결제 버튼 만들어줘" --answers "1440px,모달 알림,0.01" --apply

# 8. 역공학 클린룸 한글 명세서(00_CLEANROOM_SPEC.md) + Golden I/O 벡터 초안 자동 합성
python -m harness.team_cli reconstruct-spec --project . --source contaminated-zone --apply

# 9. Git Worktree 기반 무충돌 병렬 길드 파티(Paladin/Archer/Inquisitor) 격리 작업 공간 편성 (--mode 또는 --action 사용 가능)
python -m harness.team_cli squad-worktree --project . --mode plan --goal "대규모 결제 리팩토링"

# 10. 프로젝트 상태(SDD/클린룸/감사/학습규칙) 기반 다음 추천 작업 1~3순위 가이드
python -m harness.team_cli next-actions --project . --goal "결제 버튼 만들어줘"

# 11. 1~10호기(bot-01~bot-10) 원정 야영지 다중 파티 배치, 6자리 페어링 코드 발급, HMAC-SHA256 서명 퀘스트 발주·검증 및 보스 병합 보호
python -m harness.team_cli guild-camp --project . --mode status
python -m harness.team_cli guild-camp --project . --mode pair --slot bot-01 --party "Paladin,Archer,Inquisitor,Cleric" --apply
python -m harness.team_cli guild-camp --project . --mode dispatch --slot bot-01 --goal "결제 모듈 TDD 리팩토링" --apply
python -m harness.team_cli guild-camp --project . --mode merge-guard --slot bot-01 --hero-approve
```

---

## ⚡ 표준 운영 슬래시 & CLI 명령어 (접두사 없는 1:1 대응)

별도의 접두사 없이 채팅창 슬래시 명령어(`/명령어`)와 터미널 CLI(`npx dreampia <명령어>` 또는 `python -m harness.team_cli <명령어>`)에서 동일한 이름으로 실행할 수 있습니다:

| 슬래시 명령어 (`commands/*.md`) | CLI 명령어 (`npx dreampia ...`) | MCP 도구 | 핵심 동작 |
| :--- | :--- | :--- | :--- |
| `/version` | `version --check-remote` | - | 로컬 버전, Git 커밋/브랜치 및 원격(`origin/main`) 최신 일치 여부 조회 |
| `/status` | `status --project .` | `dreampia_status` | 상태 폴더(`.dreampia` 또는 `.dreampia-skill`), UI 규칙 강제 여부, SDD 정규식, 학습 규칙 수, 글로벌 5개 호스트 동기화 대시보드 |
| `/doctor` | `doctor --project . --global --check-remote` | `dreampia_doctor` | Python 런타임, 번들 SHA-256 매니페스트, 비관리 `.dreampia/` 데이터 충돌, 글로벌 5개 호스트 및 MCP 등록 통합 진단 |
| `/config` | `config --project . --ui-rules off --apply` | `dreampia_config` | 프로젝트별 UI 규칙 강제 여부(`on`/`off`), 상태 폴더, SDD 작업 ID 정규식(`--task-pattern`) 조회 및 변경 |
| `/update` | `update --global --apply` (`self-update --apply`) | `dreampia_self_update` | 저장소 `git pull --ff-only`, 번들 매니페스트 갱신 및 글로벌 5개 호스트 스킬 재배포 원샷 실행 |
| `/uninstall` | `uninstall --global --apply` (`uninstall-global --apply`) | - | 글로벌 5개 호스트(백업 `.pre-dreampia.bak` 자동 복원) 또는 프로젝트 설치본 안전 제거 |
| `/release` | `release --to <X.Y.Z> --apply` (`bump-version`) | `dreampia_release` | 저장소 내 모든 버전 상수·문서·번들 매니페스트(`bundle-manifest.json`)·`CHANGELOG.md` 일괄 버전 릴리즈 |
| `/clean` | `clean --project . --apply` | `dreampia_clean` | 임시 병렬 길드 파티 워크트리, 중단된 트랜잭션 저널 및 임시 증거 캐시 안전 정리 |

---

## 🔌 30종 네이티브 MCP 서버 도구 (`harness/mcp_server.py`)

`setup --apply` 실행 시 IDE 및 에이전트에서 즉시 호출할 수 있는 **30개 표준 MCP 도구**가 등록됩니다:

| 분류 | MCP 도구 이름 | 설명 |
| :--- | :--- | :--- |
| **표준 운영 & 라이프사이클** | `dreampia_status` | 프로젝트 상태 폴더, UI 규칙 강제 여부, SDD 정규식, 학습 규칙, 글로벌 5개 호스트 동기화 대시보드 조회 |
| | `dreampia_doctor` | Python 런타임, 번들 SHA-256 매니페스트, 비관리 `.dreampia/` 충돌, 글로벌 호스트 및 원격 버전 통합 진단 |
| | `dreampia_config` | 프로젝트별 UI 규칙 강제 여부(`on`/`off`), 상태 폴더(`.dreampia-skill`), SDD ID 정규식 조회 및 설정 |
| | `dreampia_self_update` | 저장소 `git pull` 최신화, 번들 매니페스트 갱신 및 5개 글로벌 호스트 스킬 폴더 일괄 재동기화 |
| | `dreampia_clean` | 병렬 길드 파티 임시 워크트리, 중단된 트랜잭션 저널 및 임시 증거 캐시 안전 정리 |
| | `dreampia_release` | 저장소 내 모든 버전 상수·문서·번들 매니페스트·`CHANGELOG.md` 일괄 시맨틱 버전 릴리즈 |
| | `dreampia_discover` | 브라운필드/폴리글랏/모노레포 스택 프로필(`project-profile.json`) 탐색 및 SDD 베이스라인 자동 부트스트랩 |
| **프롬프트 고도화 & 라우팅** | `dreampia_expand_prompt` | 짧은 입력을 국문 엔지니어링 프롬프트, 제약조건(자가 학습 규칙 포함), 엣지케이스, 소크라테스식 역질문 3선 및 다음 추천 작업(`echo_markdown_ko`)으로 확장 |
| | `dreampia_next_actions` | 현재 프로젝트 상태(Git, SDD 명세/원장, 클린룸, 코드 감사, 학습 규칙)와 목표를 분석해 우선순위별 다음 추천 작업(1~3순위), 단축어 프롬프트, CLI 명령어 안내 |
| | `dreampia_interview_compile` | 목표(`goal`)와 사전 인터뷰 답변(`answers`)을 결합해 `PRD-R*`, `TASK-*`, `TEST-*` 명세서와 SDD 원장을 자동 생성 |
| | `dreampia_route_plan` | 자연어 목표와 13종 매직 단축어를 분석해 최적 퀘스트 등급·길드 파티 요원·필수 게이트 산출 |
| | `dreampia_router_discover` | 현재 시스템에서 사용 가능한 멀티 에이전트 하네스 노드 및 스킬 설치 상태 탐색 |
| | `dreampia_squad_worktree` | `Paladin`·`Archer`·`Inquisitor` 병렬 길드 파티를 위한 Git Worktree 격리 작업 공간 계획(`plan`)·생성(`create`)·정리(`cleanup`) |
| | `dreampia_guild_camp` | 1~10호기(`bot-01`~`bot-10`) 원정 야영지 다중 파티 배치(`configure`), 인바운드 포트 0개 6자리 페어링(`pair`), HMAC-SHA256 서명 퀘스트 발주(`dispatch`)/검증(`verify`), 시크릿·파괴적 명령 차단 및 보스 병합 보호(`merge-guard`) |
| **2-Tier 클린룸 역공학** | `dreampia_reconstruct_doctor` | Tier 1 내장 엔진 및 Tier 2 외부 리버싱 도구(`rizin`, `jadx`, `ghidra`, `wasm2wat`, `objdump`, `nm`, `adb`) 상태 진단 및 설치 계획 안내 |
| | `dreampia_reconstruct_inspect` | `PE/ELF/Mach-O/WASM/ASAR/APK/ZIP/Source` 아티팩트 구조 및 Tier 1 + Tier 2 심층 심볼 정적 분석 |
| | `dreampia_reconstruct_spec` | 아티팩트 분석과 의무 원장을 결합해 한글 클린룸 명세서(`00_CLEANROOM_SPEC.md`) 및 `golden-io.json` 초안 자동 합성 |
| | `dreampia_reconstruct_ledger` | 참조 영역(`contaminated-zone`)에서 재구축 의무 원장(`Obligation Ledger`) 도출 및 저장 |
| | `dreampia_reconstruct_verify` | 재구축 의무 원장 대비 구현체(`implementation`) 100% 커버리지 및 3-영역 무오염 격리 검증 |
| | `dreampia_reconstruct_compare` | 원본과 재구축 대상 간의 공개 심볼·라우트·IPC 표면 일치율(`Parity Ratio`) 비교 |
| | `dreampia_golden_io` | `approved-spec/golden-io.json` 입출력 벡터 기반 블랙박스 동치성 검증 |
| **오토파일럿 & 정적 감사** | `dreampia_autopilot_gate` | 지침 동기화, SDD+TDD, 코드 감사, 클린룸/Golden I/O/시각 수용 통합 판정서 발급 |
| | `dreampia_audit_code` | Inquisitor 정적 AST 감사 (가짜 테스트, `any` 금지, 반환 타입 명시, 슬롭 차단, 버튼 `bg-transparent`, `lucide-react` 아이콘, 자가 학습 정규식) |
| | `dreampia_learn_rule` | 프로젝트 고유 교훈·금지 정규식(`forbidden_regex`)을 `.dreampia/memory/project-rules.json`에 영구 학습 |
| | `dreampia_blast_radius` | 변경 파일의 1-Hop/2-Hop 호출 의존성, 시스템 경계 교차 여부 및 5단계 안전 증명 등급 산출 |
| | `dreampia_metric_climb` | 불변 평가 파일 가드, 중복 해시 차단, 몬테카를로 유의성 기반 자율 지표 등반 엔진 |
| | `dreampia_context_pack` | 장기 세션 문맥 보존용 초압축 아키텍처·미완료 작업 브리핑 패킷 컴파일 |
| **SDD & 시각·품질 게이트** | `dreampia_sdd_ledger` | `PRD-R*`, `REQ-*`, `TASK-*`, `TEST-*` 양방향 추적 원장(`evidence/sdd-ledger.json`) 생성 |
| | `dreampia_sdd_check` | 고아 요구사항, 명세 드리프트(`STALE`), 실제 TDD 테스트 코드 존재 여부 Fail-Closed 검증 |
| | `dreampia_visual_check` | UI 시각 수용 매니페스트 및 PNG 스크린샷 해상도·뷰포트 예산·픽셀 차이율 검증 |
| | `dreampia_verify_gate` | 단계별 품질 게이트(`before-dev-start`, `before-claim-complete`, `before-client-send`, `app-static`, `ui-evidence`) 검증 |

---

## 📜 라이선스 (Apache License 2.0)

본 프로젝트는 **[Apache License 2.0](LICENSE)** 하에 배포됩니다.
- 명시적인 특허권 허여(제3조) 및 재배포 시 원저작자 출처 보존 의무(제4조)가 포함됩니다.
- 클린룸 역공학 파이프라인(`re` / `reconstruct-*` / `golden-io`)은 지적재산권 보호를 위해 3-영역 오염 분리 경계와 관찰 가능한 블랙박스 입출력 명세만을 기반으로 동작합니다. 자세한 내용은 [NOTICE](NOTICE)를 참고하세요.
