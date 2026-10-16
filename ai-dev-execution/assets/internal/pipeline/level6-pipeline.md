# Dreampia Level-6 Pipeline

visibility: internal_only

## Target

자료 → 요구 → 문서 → scaffold → vertical slice → 검증 → 고객용 export → handoff까지 한 프로젝트 안에서 재개 가능하게 만든다.

## Commands

```bash
dreampia init --project <project> --apply
dreampia scaffold --project <project> --type assessment-service --apply
dreampia verify --project <project> --gate before-dev-start
dreampia export-client-summary --project <project> --out client
dreampia verify --project <project> --gate before-client-send
```

## Evidence Rule

PASS는 명령·시각·환경·관찰 결과가 남아야 한다. 실행하지 않은 항목은 NOT_RUN으로 적는다.
