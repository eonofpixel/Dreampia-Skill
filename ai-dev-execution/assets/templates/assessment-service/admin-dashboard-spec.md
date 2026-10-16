# Assessment Admin Dashboard Spec

visibility: internal_only

## Must Widgets

- 전체 대상/제출/완료율
- 학년별 완료율
- 반별 완료율
- 영역별 평균
- AI 윤리·보안 주의군 비율
- 최근 제출
- 중복/초기화 로그

## Must Actions

- 반별 코드/QR 생성
- 문항/결과문구 버전 확인
- 제출 초기화
- CSV 다운로드
- 진단 열기/닫기

## Export Rules

CSV 다운로드는 권한과 감사로그가 필요하다. 이름 정책이 none이면 이름 필드는 생성하지 않는다. masked면 마스킹값만 포함한다.
