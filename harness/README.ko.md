# 로컬 개발 하네스 (v1.1.0)

Python 3.9 이상 표준 라이브러리만으로 **Windows 10/11 (Win32 Job Objects / `msvcrt`), macOS, Linux** 로컬 프로세스에서 실행한다. 실제 확인 조합은 [SUPPORT.ko.md](../SUPPORT.ko.md)와 검증 보고를 따른다. 별도 설치할 외부 pip 패키지는 없다. 실행 폴더는 사용자가 신뢰하고 수정 권한을 허용한 프로젝트여야 한다. 공급자 연결은 기본 비활성이고 선택 어댑터만 명시적으로 허용할 수 있다.

## 바로 실행
저장소 최상위 폴더에서 실행한다 (Windows는 `python`, macOS/Linux는 `python3`).

```sh
python3 harness/cli.py validate harness/examples/slots
python3 harness/cli.py run harness/examples/slots
python3 harness/cli.py trace harness/examples/slots
python3 harness/cli.py status harness/examples/slots
python3 -m unittest discover -s harness/tests -v
```

예제는 이미 작성된 순수 메모리 예약 함수에 실제 테스트를 실행한다. 결정적 어댑터는 코드 생성 없이 성공/실패/지연을 모의한다. 예제 PASS는 기존 가상 예약 서비스나 AI 개발 능력의 검증이 아니다. 서버·DB·인증·브라우저·배포는 예제 범위 밖이다.

## 내 프로젝트
프로젝트 루트에 `harness.json`을 만들고 요구/작업/테스트 ID와 실제 검증 명령을 적는다. 예제의 manifest를 복사해 시작한다. 모든 요구는 한 개 이상의 작업에 연결하고 모든 작업은 한 개 이상의 필수 check를 가져야 한다. ID는 영문자로 시작하는 영숫자·하이픈·밑줄 64자 이내이며 비밀·개인정보를 넣지 않는다. 요구 의미와 인수 조건은 프로젝트의 현재 명세가 소유한다.

```json
{
  "version": 1,
  "requirements": ["R1"],
  "tasks": [{
    "id": "T1", "requirements": ["R1"], "depends_on": [],
    "adapter": {"kind": "deterministic", "fail_attempts": 1},
    "max_attempts": 2, "timeout": 30,
    "checks": [{"id": "C1", "argv": ["python3", "-m", "unittest"]}]
  }]
}
```

`max_attempts`는 전체 시도 횟수(기본 2, 최대 10)다. `timeout`은 어댑터 또는 각 check 하나의 초 제한(기본 30, 최대 3600)이다. 전체 작업 제한은 대략 시도 수 × (어댑터+check 수) × timeout이며 프로세스 시작·소스 해시 계산 시간은 별도다. 재시도는 직렬로 즉시 실행하며 외부 서비스의 rate limit 백오프는 제공하지 않는다. 다수 프로젝트·대형 저장소·스케줄링 서버를 위한 프레임워크가 아니다.

## 중단과 재개

```sh
python3 harness/cli.py cancel /absolute/project
python3 harness/cli.py status /absolute/project
python3 harness/cli.py run /absolute/project
python3 harness/cli.py run /absolute/project --retry-failed
```

`cancel`은 별도 프로세스에서 취소 요청을 남긴다. SIGINT/SIGTERM도 체크포인트를 남기고 현재 자식 프로세스 그룹(Windows에서는 Job Object 및 `taskkill /T /F`)을 종료한다. 새 `run`은 기존 취소 요청을 지우고 명시적으로 재개한다. 취소 요청은 미래 run을 영구 차단하는 기능이 아니다. 취소·크래시도 시작한 시도를 소비한다. `--retry-failed`는 failed 작업에 새로운 유한 예산을 부여하며 이벤트에 기록한다. 단순 재시작은 소진된 예산을 자동 초기화하지 않는다.

SIGKILL/전원 중단은 마지막 원자적 체크포인트에서 재개한다. 외부 어댑터의 부작용은 정확히 한 번 실행을 보장하지 않으므로 계약의 idempotency_key를 사용해야 한다. 이전 외부 자식이 아직 실행 중이면 상속된 잠금 때문에 새 runner를 차단한다. 자식이 끝난 뒤 재개한다. 어댑터가 백그라운드로 분리되거나 잠금 FD를 닫으면 이 보장은 적용되지 않는다. 같은 프로젝트의 `.harness`를 실행 중에 삭제·이동하면 잠금이 깨진다. 공유 네트워크 파일 시스템은 지원하지 않는다.

## 상태와 증거
`.harness/state.json`은 원자적 상태 스냅샷이고 `.harness/events.jsonl`은 메타데이터 이벤트다. 실행 중 중복 runner는 즉시 오류(2)로 종료한다. `status`와 `trace`는 소스 해시를 다시 계산하여 과거 PASS의 최신 여부를 표시한다. 변경된 소스의 성공 작업은 `stale`이며 다음 `run`에서 코드를 다시 생성하지 않고 검증을 재실행한다. 기능 요구가 바뀌었으면 manifest 작업/계약도 갱신한다. manifest가 바뀌면 과거 증거를 무효화하고 모든 작업을 recovery_hold로 둔다. 새 명세를 reverify하거나 작업별 authorize-replay로 새 유한 예산을 명시해야 한다. 계획 변경도 복구 보류를 자동 해제하지 않는다.

`verified`는 manifest의 필수 명령들이 현재 프로젝트 소스 해시에서 성공했다는 뜻이다. 제품 인수나 시각적 품질 승인과는 별개다. 검증 도중 소스가 변경되면 실패한다. 뒤 작업이 앞 작업의 소스 증거를 바꾸면 마지막에 앞 작업도 최종 소스로 재검증한다. 루트 `.git`, `.harness`만 소스 해시에서 제외하고 중첩 같은 이름과 모든 `__pycache__`는 포함한다. 소스 심볼릭 링크는 허용하지 않는다. 외부 의존성/원격 DB/전역 도구 버전은 소스 해시로 자동 고정되지 않으므로 명세와 검증 환경에 별도로 기록한다.

`trace`는 요구→작업→check→state.json 증거의 구조적 연결과 최신 여부를 출력한다. 파일 의미·테스트 충분성·검토자 승인 판단은 사람/스킬 지침의 책임이다. argv는 manifest에 있고 증거에는 digest만 저장한다. 로그에는 명령 인자·환경·표준출력·표준오류·프롬프트를 저장하지 않는다. 실패 상세가 필요하면 안전하게 정제한 결과를 별도 기록하되 비밀을 복제하지 않는다.

종료 코드: 0 = 현재 필수 검사 모두 verified(또는 validate/cancel 성공), 1 = 실패·미완료·stale, 2 = manifest/환경/중복 runner 오류. `status`는 영속 작업 상태를 고치지 않으며, `run`만 실행 상태를 갱신한다. 이벤트는 append+fsync이나 상태 스냅샷과 하나의 트랜잭션은 아니다. 충돌 시 상태 스냅샷과 실제 현재 검증을 기준으로 삼는다.

## 외부 코딩 CLI
`adapter.kind="command"`와 `argv` 배열로 연결한다. shell 문자열은 실행하지 않는다. stdin JSON을 읽어 현재 작업을 수행하는 foreground wrapper를 직접 제공한다. 계약은 [아키텍처](../ARCHITECTURE.ko.md)에 있다. 외부 명령을 넣으면 로컬 호스트 권한으로 실행되며 비용·파일·네트워크 부작용이 생길 수 있다. 사용자가 승인한 CLI·작업·계정·예산만 연결한다. 이 패키지는 어떠한 실제 AI CLI도 호출하거나 인증 우회 옵션을 기본 설정하지 않았다.

## 1.1.0 설치·업데이트와 복구

현재 제품 버전은 `1.1.0`이다. Windows 10/11, macOS, Linux 및 Python 3.9 이상을 지원하며, NFS 등 공유 네트워크 파일 시스템은 잠금 보장 범위 밖이다.

소스는 그대로 `python3 harness/cli.py ...` 또는 `python3 -m harness ...`로 실행한다. 무의존 단일 실행 파일(`.pyz`) 산출물은 다음 명령으로 명시한 새 경로에 만든다.

```sh
python3 harness/build.py ./local-install/harness-1.1.0.pyz
python3 ./local-install/harness-1.1.0.pyz --version
python3 ./local-install/harness-1.1.0.pyz status /absolute/project
python3 harness/local_ci.py
```

빌더는 기존 목적지를 덮어쓰지 않으며 전역 PATH·설정·인증을 바꾸지 않는다. 업데이트는 새 버전 경로에 별도 ZIP/zipapp을 만들고 버전·로컬 CI를 확인한 뒤 사용 명령의 경로를 바꾼다. 기존 설치는 보존한다. 선택 pip 메타데이터는 pyproject.toml에 있지만 wheel/pip 설치를 실제 확인했다고 주장하지 않는다. 공개 배포 라이선스는 미선정이며 THIRD_PARTY_NOTICES.md를 읽는다.

```sh
python3 harness/cli.py recover /absolute/project
python3 harness/cli.py reverify /absolute/project
python3 harness/cli.py authorize-replay /absolute/project --task T1 --accept-side-effects
python3 harness/cli.py run /absolute/project
```

상태 손상은 구조화된 STATE_CORRUPT 오류로 중단한다. 매 상태 저장 전에 이전 유효 스냅샷을 state.backup.json에 보존한다. recover는 현재/백업 원문을 runtime quarantine에 보관하고 모든 작업을 recovery_hold로 만든다. 과거 verified는 복원하지 않고 어떤 어댑터도 실행하지 않는다. run도 held 작업을 자동 재실행하지 않는다. reverify는 현재 실제 check만 실행하며 PASS인 경우에만 새 증거를 만든다. 실패하면 부작용 재실행 제한이 유지된다. authorize-replay는 지정한 held 작업에 새 유한 예산을 주며, 실제 명령 실행은 다음 run에서 한다. 복구는 사용자 소스 파일을 삭제하지 않는다. 격리 원문에는 손상 파일의 원래 민감 내용이 있을 수 있으므로 공개 업로드하지 않는다.

v1 상태는 알려진 스키마를 검증해 읽으며 새 해시 방식으로 과거 증거가 stale이 될 수 있다. 손상/알 수 없는 필드는 임의 무시하지 않고 명시적 복구를 요구한다. 제품/상태 버전 변경은 새 검증 증거를 필요로 하며 외부 부작용의 exactly-once를 만들지 않는다.

## 소스 입력 계약 변경

0.2.0은 **루트 .harness/.git**만 런타임/저장소 메타데이터로 제외한다. 중첩 .harness/.git 및 모든 __pycache__ 경로는 실제 소스 범위에 포함한다. 파일 내용·상대 경로·권한 비트와 디렉터리 구조/권한을 해시에 넣는다. inode·mtime 자체는 소스 digest에 넣지 않는다. Python check/어댑터는 PYTHONDONTWRITEBYTECODE=1로 실행한다. 이전 캐시나 빌드 출력도 소스 범위이므로 검증 단계가 이를 수정하면 실패할 수 있다. 빌드/포맷은 어댑터 작업으로 수행하고 check는 관찰 단계로 설계한다.

check.inputs는 검증이 소비하는 중요한 파일을 상대 경로로 명시하는 선택 계약이다. 어댑터가 생성한 입력도 검사 직전에 존재 여부를 확인한다. ../, 절대 경로, 루트 런타임 입력, 심볼릭 링크는 거부한다. 전체 프로젝트가 기본 해시 범위이며 inputs가 해시를 일부 파일로 축소하지 않는다. 임의 argv의 모든 외부 입력을 추론하거나 OS 접근을 막지는 못한다. check는 루트 런타임·외부 파일·원격 상태에 의존하지 않는 계약으로 사용하고, 필요한 외부 연동은 별도 증거로 기록한다.

디렉터리 FD 및 O_NOFOLLOW로 소스 탐색의 심볼릭 링크 탈출을 거부하고 해시를 읽는 동안 파일/디렉터리 상태 변화도 검사한다. 전체 트리의 원자적 스냅샷이나 악의적 동시 변경에 대한 attestation은 아니다. 검증 전후 동일 digest 조건과 신뢰된 단일 작성자 작업 공간의 경계를 유지한다.

## 선택적 Codex 어댑터

[Codex 계약](CODEX_ADAPTER.ko.md)을 읽고 명시적으로 선택한다. doctor는 help/version만 확인하며 공급자 추론/로그인/키 수집을 하지 않는다.

```sh
python3 harness/cli.py doctor /absolute/project
```

실제 공급자 사용은 사용자에게 비용·범위·인증 방식이 승인된 별도 세션에서만 run --allow-provider로 허용한다. 이번 작업에서는 실제 공급자 run을 한 번도 실행하지 않았다. 가짜 CLI 통합 검사는 AI 코딩 성능이 아니다.
