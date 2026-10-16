# 고정 baseline/holdout 평가

suite.json은 4개 고정 요청·초기 파일·rubric을 담고 suite.lock.json은 바이트 SHA256을 고정한다. E1/E2는 baseline, E3/E4는 holdout이다. 시나리오를 변경하면 새 평가 버전과 lock을 명시적으로 만들어야 하며 이전 결과를 이어 붙이지 않는다.

```sh
python3 harness/eval_runner.py prepare evals/suite.json ./evaluation-work
python3 harness/eval_runner.py aggregate evals/suite.json ./evaluation-work/results.json
```

prepare는 기존 목적지를 덮어쓰지 않고 두 arm의 같은 초기 파일/요청을 독립 폴더에 준비한다. 결과 템플릿은 모두 NOT_RUN이며 초기 입력/시나리오 digest를 기록한다. runner는 API/CLI/모델을 호출하지 않는다. 이번 결과의 effect_score는 null이다.

실제 모델 비교는 별도 승인된 실행에서 with_skill/without_skill을 같은 모델·호스트·시간 한도·도구로 수행하고 원시 산출물을 보존한 뒤 사람이 rubric을 평가한다. 결과마다 controls의 model/host/time_budget_seconds/toolset을 실제 값으로 채운다. 각 criterion judgment는 score 0/1/2, evidence 상대 파일 경로, 그 파일의 SHA256을 갖는다. evidence는 results.json 부모 폴더 안에 있어야 하며 symlink/../를 허용하지 않는다. 초기 파일과 시나리오 digest는 prepare 값 그대로 유지한다.

aggregate는 고정 시나리오/분리/arm·중복·controls·rubric 전체·실제 evidence 파일/해시를 확인하고 두 arm의 controls가 일치하는 완료 쌍만 집계한다. baseline/holdout을 각각 보고하고 모든 쌍이 완료되기 전 전체 effect_score는 null이다. 치명 실패는 UNAUTHORIZED_CHANGE/SECRET_EXPOSURE/FALSE_COMPLETE/USER_WORK_LOSS로 별도 기록한다. 수치가 있어도 사람의 관찰 기록을 합산한 것이며 자동 품질 인증·통계적 유의성·모델 일반 성능 보장이 아니다.

로컬 단위 테스트의 합성 evidence/fixture-model은 runner의 거부/집계 계약만 시험한다. 그 점수를 사용자 모델 비교 결과로 공개하지 않는다. holdout을 개발 중 프롬프트 튜닝에 쓰지 않고, baseline 결과에 따라 조정한 뒤 별도 평가에서 확인한다. 현재 모델 baseline/holdout 둘 다 NOT_RUN이다.
