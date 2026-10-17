# 0.7.0 내부 로컬 개발 OS

0.7.0은 passed 체크포인트를 완료된 성공 증거·argv·timeout·실행 프로젝트·source fingerprint와 대조하며 모순된 상태를 resume/status에서 거부한다. 로컬 저장소도 유효 JSON의 구조/날짜 손상에 대해 원본 보존·삭제 거부 방식으로 처리한다.

## 검증·완료 경계

0.5.7의 placeholder unit script와 NOT_RUN/파일존재 기반 검증을 교체했다. app-check와 ui-check는 실제 실행 성공, 현재 웹 소스 fingerprint, 생성 시각, 필수 checks를 검사한다. UI evidence는 실행별 폴더와 PNG 해시를 기록한다. 기본 24시간 신선도 안에서도 소스가 변경되면 재실행한다. 증거는 서명 인증서가 아니며 전체 제품·법적·운영 보안을 인증하지 않는다.

## CLI

```sh
dreampia scaffold-app --project PROJECT --apply
# 생성된 web에서 npm ci --ignore-scripts --no-audit --no-fund
# Chromium이 없으면 명시적으로 npx playwright install chromium 실행
dreampia app-check --project PROJECT --apply
dreampia ui-check --project PROJECT --apply
dreampia verify --project PROJECT --gate ui-evidence
dreampia workflow plan WORKFLOW_PROJECT
dreampia workflow run WORKFLOW_PROJECT --approve-adapter local --approve-effect execute
dreampia workflow status WORKFLOW_PROJECT
dreampia workflow resume WORKFLOW_PROJECT --approve-adapter local
```

workflow.json의 역할은 승인된 로컬 argv 실행 라벨이다. 실제 독립 AI 판단·자동 코드생성을 가장하지 않는다. 실행할 adapter·부작용을 매번 명시 승인한다. 한 번 시도한 부작용은 자동 replay하지 않는다. adapter는 신뢰 코드이며 OS/network sandbox가 아니다. 불변 입력 변경은 stale로 차단하고 새로운 검토 계약으로 분리한다.

## 로컬 앱

회원가입/이름 수집 없이 코드·학년·반·번호로 진입한다. 샘플 문항은 실제 학교 확정 문항이 아니다. 서버 채점·파일 잠금/atomic rename 영속 저장·관리자 서명 쿠키·조회/CSV/삭제/보존/감사 연결이 있다. ASSESSMENT_ADMIN_SECRET과 ASSESSMENT_ACCESS_CODE 없이는 fail closed다. 로컬 loopback 보호된 컴퓨터/합성 데이터만 사용한다. 보존은 수동, CSV 사본 삭제와 stale lock 복구는 운영자 책임이다. 분산 DB/클러스터/공개 배포·실학생 운영 검증이 아니다.

## 고객 전달

문서 metadata의 client_export_allowed: true만 허용한다. internal/private/hidden 경로, symlink, ZIP 중첩, 패턴으로 탐지한 비밀값을 차단한다. UTF-8 md/txt/json만 허용하며 자동 검사 뒤에도 사람이 개인정보·업무 기밀을 검토한다. 실제 외부 전송/공개는 별도 사용자 승인이다.
