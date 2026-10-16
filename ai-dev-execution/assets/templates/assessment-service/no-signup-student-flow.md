# No-Signup Student Flow

visibility: internal_only

## 권장 기본값

```text
반별 QR/코드 → 학년/반 자동 또는 선택 → 번호 선택 → 이름 선택 입력 → 진단 → 결과
```

## Flow States

| State | Required | Error |
|---|---|---|
| code_check | 코드 활성/만료 확인 | CODE_NOT_FOUND, CODE_EXPIRED |
| identify | 학년/반/번호 확인 | DUPLICATE_SUBMISSION |
| consent_notice | 최소수집 안내 | REQUIRED_CONFIRMATION |
| answer | 모든 문항 응답 | MISSING_ANSWER |
| submit | 서버 저장/채점 | SUBMIT_FAILED |
| result | 결과 표시 | RESULT_NOT_FOUND |

## Duplicate Policy

기본은 `admin_reset`: 같은 세션+학년+반+번호는 1회 제출. 실수 시 관리자 초기화.

## Student Copy

- 전화번호, 이메일, 주민등록번호, 주소는 수집하지 않습니다.
- 입력한 학년·반·번호는 응답 현황과 결과 확인을 위해서만 사용됩니다.
- 제출 후 수정이 필요하면 담당 선생님에게 문의하세요.
