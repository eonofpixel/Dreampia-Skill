# Dreampia Internal Dev Cheatkey Pack

visibility: internal_only  
client_export_allowed: false  
redaction_required: true

이 폴더는 드림피아/이온오브픽셀 직원과 승인된 내부 에이전트만 사용하는 개발 치트키다. 고객 전달 패키지, 공개 저장소, 외부 제안서, 오픈소스 배포물에 그대로 포함하지 않는다.

## 목적

- 고객 자료를 빠르게 제품 요구와 개발 범위로 바꾼다.
- 웹서비스/관리자페이지/역량진단 프로젝트의 반복 설계를 표준화한다.
- AI 에이전트가 구현 전후에 같은 기준으로 검증·리뷰·인계하게 한다.
- 내부 판단 루브릭을 통해 MVP와 플랫폼, 개인정보, 관리자 기능, 배포 준비를 빠르게 결정한다.

## 1차 포함 및 자산 지도

- 빠른 시작: [QUICKSTART.md](QUICKSTART.md), [assessment-service 프리셋](project-presets/assessment-service.json), [OpenAI 호스트 메타데이터](../../agents/openai.yaml)
- `agents/` (매트릭스 스쿼드): [Oracle (planner)](agents/planner.md), [Architect (architect)](agents/architect.md), [Niobe (ux-designer)](agents/ux-designer.md), [Keymaker (analyst)](agents/analyst.md), [Neo (executor)](agents/executor.md), [Trinity (reviewer)](agents/reviewer.md), [Tank (verifier)](agents/verifier.md), [Seraph (privacy-guard)](agents/privacy-guard.md)
- `pipeline/`: [Morpheus 라우터](pipeline/agent-router.md), [레벨6 파이프라인](pipeline/level6-pipeline.md), [인계 계약 예시](pipeline/handoff-contract.example.json)
- `templates/assessment-service/`: [진단 PRD](../templates/assessment-service/assessment-prd.md), [비회원 학생 흐름](../templates/assessment-service/no-signup-student-flow.md), [관리자 대시보드](../templates/assessment-service/admin-dashboard-spec.md), [결과 문구 라이브러리](../templates/assessment-service/result-text-library.md), [Playwright UI 검증](../templates/assessment-service/ui-verification-playwright.md), [학생 제출 수직 슬라이스](../templates/assessment-service/vertical-slice-student-submit.md)
- `templates/admin-console/`: [감사 로그 패턴](../templates/admin-console/audit-log-pattern.md), [CRUD 목록·상세 패턴](../templates/admin-console/crud-list-detail-pattern.md)
- `templates/security-privacy/`: [미성년자 개인정보 체크리스트](../templates/security-privacy/minor-privacy-checklist.md), [고객 전달 마스킹·정제](../templates/security-privacy/client-safe-redaction.md)
- `prompts/internal/`: [원천자료 분석](../prompts/internal/intake-analysis.md), [역량진단 기획](../prompts/internal/assessment-service-planning.md), [리뷰·검증 게이트](../prompts/internal/review-and-verify-gate.md)
- `rubrics/`: [MVP vs 플랫폼](rubrics/mvp-vs-platform.md), [비로그인 접근 방식](rubrics/no-login-access-options.md), [개인정보 위험도](rubrics/privacy-risk-level.md)
- `checklists/`: [착수 전](checklists/before-dev-start.md), [완료 주장 전](checklists/before-claim-complete.md), [고객 전달 전](checklists/before-client-send.md)
- `scaffolds/`: [Next 역량진단 앱 README](../scaffolds/next-assessment-app/README.md), [앱 검증 가이드](../scaffolds/next-assessment-app/VERIFICATION.md)

## 외부 공개 금지

이 팩은 내부 방법론, 고객 응대 방식, 개발 검증 기준, 산출물 구조를 포함한다. 고객에게 전달할 때는 `client-safe-summary` 프롬프트로 정제하고, `internal_only` 파일을 제외한다.
