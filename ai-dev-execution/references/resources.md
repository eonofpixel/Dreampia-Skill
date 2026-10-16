# 문서·프롬프트·예제 지도

모든 경로는 이 파일 기준이다. 현재 단계에 필요한 파일만 읽고 프로젝트별 사본으로 사용한다. 스킬 원본을 진행 기록으로 수정하지 않는다. 실제 프로젝트에 같은 역할의 문서가 있으면 재사용한다.

## 문서 역할과 다음 소비자

| 원본 | 기준 정보 | 다음 소비자 |
| --- | --- | --- |
| [00 브리프](../assets/templates/00-project-brief.md) | 목적·실행 환경·권한·범위·실제 문서 지도 | 모든 참여자 |
| [01 PRD](../assets/templates/01-prd.md) | 문제·성과·범위·인수 조건 | UX·설계·인수 검토 |
| [02 IA·UX](../assets/templates/02-ia-ux.md) | 사용자 흐름·화면 상태·접근성 | 구현·UI/E2E 검사 |
| [03 TRD·아키텍처](../assets/templates/03-trd-architecture.md) | 환경·구성·비기능 요구·실험 | 상세 설계·운영 |
| [04 상세 설계](../assets/templates/04-solution-design.md) | 기능 처리·상태·불변식 | 구현 작업 |
| [05 계약·데이터](../assets/templates/05-contracts-data.md) | API·이벤트·스키마·권한·호환성 | 클라이언트·서버·검사 |
| [06 테스트 계획](../assets/templates/06-test-plan.md) | 기대 결과·검증 방법·AI 평가 | 구현·독립 인수 검토 |
| [07 백로그](../assets/templates/07-backlog.md) | 작업·DAG·소유 파일·DoR/DoD | 실행·병렬 통합 |
| [08 출시·운영 런북](../assets/templates/08-release-runbook.md) | staging·배포·마이그레이션·복구·관측 | 릴리스·운영 |
| [09 결정·위험·변경](../assets/templates/09-decision-log.md) | ADR·위험·변경 영향·폐기 근거 | 모든 변경 작업 |
| [10 진행·증거·인계](../assets/templates/10-progress-handoff.md) | 실제 결과·현재 상태·재개 조건 | 현재·다음 AI와 검토자 |

소형 3~4개, 표준 7~10개 또는 복합 모듈의 통합 기준은 [SKILL.md](../SKILL.md)와 [워크플로](workflow.md)에 있다. 합쳐도 기준 정보의 책임을 유지한다. 템플릿의 `{{변수}}`와 안내 문구는 실제 값 또는 명시적 미확인·미적용 이유로 바꾼다. 복사·통합·이동 시 상대 링크와 프롬프트의 문서 경로도 함께 갱신한다.

## 필요할 때 복사하는 프롬프트

아래는 사람이 채워 AI에 전달하는 요청 원본이다. 스킬을 쓸 때 모두 읽거나 실행할 필요는 없다. 현재 사용자의 명시적 요청과 실제 프로젝트 문서가 우선하며 프롬프트에 빈 변수가 있다고 기존 승인이 사라지는 것은 아니다.

- [새 프로젝트 시작](../assets/prompts/start-project.md): 탐색·질문·범위·초기 산출물
- [다음 기능·마일스톤 구현](../assets/prompts/implement-next-slice.md): 준비된 수직 기능을 승인 범위의 DoD까지 실행
- [검토와 검증](../assets/prompts/review-and-verify.md): 인수 조건과 실제 증거를 비교; 수정은 명시된 범위만
- [프로젝트 재개](../assets/prompts/resume-project.md): 이전 기록과 현재 환경을 대조하고 이어가기
- [요구 변경](../assets/prompts/change-request.md): 영향 분석·결정·문서/테스트 정합화
- [프로젝트 지침 템플릿](../assets/AGENTS.template.md): 기존 프로젝트 지침에 필요하고 승인된 내용만 병합; 자동 활성화 파일 아님

## 연결 형식을 보고 싶을 때

[예제 읽기](../assets/examples/README.md) → [예약 명세](../assets/examples/appointment-spec.md) → [작업·테스트](../assets/examples/appointment-tasks-tests.md) → [증거·인계](../assets/examples/appointment-evidence.md).

이 네 파일은 가상 예약 기능의 문서 예제다. 실제 사용자·서비스·구현·실행·배포 증거가 없으며 앱 검사 결과는 모두 `NOT_RUN`이다. 예제의 요구·데이터·수치·기술 선택을 새 프로젝트의 기본 사실로 복사하지 않는다.

## 검증과 상세 기준

- [워크플로](workflow.md): 조건별 절차와 단계 연결 기준
- [품질 게이트](quality-gates.md): G0~G5 입력·출력·중단·복구
- [체크리스트](checklist.md): 프로젝트별 판정·근거를 채우는 원본

## 이번 작업에 맞춰 선택하는 확장 자료
- [간편 프로젝트](../assets/templates/compact-project.md): 낮은 위험의 한 흐름을 한 파일로 시작
- [변경분](../assets/templates/change-delta.md): 현재 명세와 변경 이력의 책임 분리
- [구현/시각 리뷰와 평가](review-and-evaluation.md): 실제 검토·독립 A/B 시나리오
- [하네스 경계](harness-integration.md): 지침과 프로그램 강제 검사, 실행 예제 위치
- [비교 시나리오](../assets/evals/scenarios.json): 평가용 입력; 모델 비교 실행은 NOT_RUN
