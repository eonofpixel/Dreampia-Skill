# Vertical Slice — Student Submit Flow

visibility: internal_only

## Goal

학생이 회원가입 없이 진단 코드로 접속해 식별 정보를 입력하고, 문항 응답을 제출한 뒤 결과를 확인한다.

## Owned Paths

- app/
- data/
- tests/ui/
- evidence/student-submit-flow/

## Tasks

1. code_check: 진단/반 코드 유효성 확인
2. identify: 학년·반·번호 입력 및 중복 제출 처리
3. answer: 5점 척도 문항 응답
4. submit: 서버 저장/채점 경계 정의
5. result: 영역별 점수/레벨/추천활동 표시
6. admin_reflect: 관리자 완료율 반영
7. verify: tablet/desktop/mobile viewport smoke

## Evidence

- build/test command output
- screenshot paths
- PASS/FAIL/NOT_RUN table
