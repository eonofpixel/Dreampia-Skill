# Internal Prompt — Review and Verify Gate

visibility: internal_only

작성된 산출물/코드를 reviewer와 verifier 관점으로 분리 검토한다.

## Reviewer Findings

- requirement gap
- privacy/security risk
- admin/data/export issue
- architecture/API flaw
- UX/responsive issue
- test gap

## Verifier Evidence

- commands run
- browser/screenshots
- API/DB evidence
- PASS/FAIL/NOT_RUN
- evidence paths

APPROVE는 CRITICAL/HIGH가 없고 필수 검증이 PASS 또는 명시적 deferred일 때만 가능하다.
