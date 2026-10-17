"""Dreampia 다국어 적대적 슬롭·결함 벤치마크 스위트 (Adversarial Slop & Defect Benchmark Suite).

SOLID 아키텍처:
- BenchmarkCase: 단일 벤치마크 시나리오 불변 값 객체 (SRP)
- BenchmarkEvaluation: 단일 케이스 실행 결과 및 TP/FP/TN/FN 판정 객체 (SRP)
- CorpusProvider: 언어별·카테고리별 코퍼스 제공 추상 프로토콜 (OCP/DIP)
- DefaultBenchmarkCorpus: 5개 언어(Python/TS/TSX/Rust/Go) 50종 골든 코퍼스 레지스트리 (LSP)
- BenchmarkSuiteRunner: 격리 샌드박스 실행 및 Recall/FPR/Precision 정량 산출기 (SRP/ISP)
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import time
from typing import Protocol

try:
    from . import autopilot_engine
except ImportError:
    import autopilot_engine  # type: ignore[no-redef]

BENCHMARK_SUITE_VERSION = "0.7.5"
DEFAULT_BENCHMARK_REPORT_REL = "evidence/benchmark-report.json"


@dataclass(frozen=True)
class BenchmarkCase:
    """단일 정적 감사 벤치마크 케이스 정의."""

    case_id: str
    language: str
    category: str
    description_ko: str
    files: dict[str, str]
    expected_rule_ids: tuple[str, ...]
    check_ui_rules: bool = False


@dataclass(frozen=True)
class BenchmarkEvaluation:
    """단일 벤치마크 케이스 판정 결과."""

    case_id: str
    language: str
    category: str
    expected_defect: bool
    detected_defect: bool
    expected_rule_ids: list[str]
    actual_rule_ids: list[str]
    outcome: str
    passed: bool
    elapsed_ms: float

    def to_dict(self) -> dict[str, object]:
        """판정 결과를 직렬화 가능한 딕셔너리로 변환한다."""
        return {
            "case_id": self.case_id,
            "language": self.language,
            "category": self.category,
            "expected_defect": self.expected_defect,
            "detected_defect": self.detected_defect,
            "expected_rule_ids": self.expected_rule_ids,
            "actual_rule_ids": self.actual_rule_ids,
            "outcome": self.outcome,
            "passed": self.passed,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


class CorpusProvider(Protocol):
    """벤치마크 코퍼스 제공자 추상 인터페이스 (DIP/OCP)."""

    def list_cases(self, language_filter: str = "all") -> tuple[BenchmarkCase, ...]:
        """지정된 언어 필터에 해당하는 벤치마크 케이스 목록을 반환한다."""
        ...


def _build_python_defect_cases() -> tuple[BenchmarkCase, ...]:
    return (
        BenchmarkCase(
            case_id="py-defect-01",
            language="python",
            category="hollow_tdd",
            description_ko="Python 테스트 내 항상 참인 assert True 적발",
            files={"tests/test_sample.py": "def test_always_true() -> None:\n    assert True\n"},
            expected_rule_ids=("hollow-tdd-assert-true",),
        ),
        BenchmarkCase(
            case_id="py-defect-02",
            language="python",
            category="hollow_tdd",
            description_ko="Python 테스트 내 단언문(assertion) 완전 누락 적발",
            files={"tests/test_empty.py": "def test_no_assert() -> None:\n    value = 1 + 2\n    _ = value\n"},
            expected_rule_ids=("hollow-tdd-no-assertion",),
        ),
        BenchmarkCase(
            case_id="py-defect-03",
            language="python",
            category="hollow_tdd",
            description_ko="Python 테스트 내 단순 존재 확인(assert res is not None) 단독 사용 적발",
            files={"tests/test_weak.py": "def test_weak_only() -> None:\n    res = sum([1, 2])\n    assert res is not None\n"},
            expected_rule_ids=("hollow-tdd-weak-assertion",),
        ),
        BenchmarkCase(
            case_id="py-defect-04",
            language="python",
            category="slop",
            description_ko="Python 프로덕션 코드 내 bare except: pass 슬롭 적발",
            files={"app/service.py": "def run_task() -> int:\n    try:\n        return 1\n    except:\n        pass\n    return 0\n"},
            expected_rule_ids=("slop-bare-except-pass",),
        ),
        BenchmarkCase(
            case_id="py-defect-05",
            language="python",
            category="type_safety",
            description_ko="Python 공개 함수 반환 타입 어노테이션 누락 적발",
            files={"app/calc.py": "def calculate_total(a: int, b: int):\n    return a + b\n"},
            expected_rule_ids=("missing-return-type",),
        ),
        BenchmarkCase(
            case_id="py-defect-06",
            language="python",
            category="type_safety",
            description_ko="Python 공개 함수 금지된 Any 반환 타입 적발",
            files={
                "app/loader.py": (
                    "from typing import "
                    "Any\ndef load_payload() -> Any:\n    return {}\n"
                )
            },
            expected_rule_ids=("forbidden-any-type",),
        ),
        BenchmarkCase(
            case_id="py-defect-07",
            language="python",
            category="slop",
            description_ko="Python 구문 오류(SyntaxError) 즉시 적발",
            files={"app/broken.py": "def broken_func( -> int:\n    return 1\n"},
            expected_rule_ids=("python-syntax-error",),
        ),
        BenchmarkCase(
            case_id="py-defect-08",
            language="python",
            category="hollow_tdd",
            description_ko="unittest assertIsNotNone 단독 약한 단언 적발",
            files={"tests/test_unit_weak.py": "class MyTest:\n    def test_only_not_none(self) -> None:\n        self.assertIsNotNone(len([1]))\n"},
            expected_rule_ids=("hollow-tdd-weak-assertion",),
        ),
    )


def _build_ts_defect_cases() -> tuple[BenchmarkCase, ...]:
    return (
        BenchmarkCase(
            case_id="ts-defect-01",
            language="typescript",
            category="hollow_tdd",
            description_ko="TypeScript expect(true).toBe(true) 가짜 단언 적발",
            files={"src/calc.test.ts": "it('fakes pass', () => {\n  expect(true).toBe(true);\n});\n"},
            expected_rule_ids=("hollow-tdd-assert-true",),
        ),
        BenchmarkCase(
            case_id="ts-defect-02",
            language="typescript",
            category="hollow_tdd",
            description_ko="TypeScript 단언문 없는 빈 it() 테스트 블록 적발",
            files={"src/empty.test.ts": "it('does nothing', () => {\n  const val = 10 + 20;\n  console.log(val);\n});\n"},
            expected_rule_ids=("hollow-tdd-no-assertion",),
        ),
        BenchmarkCase(
            case_id="ts-defect-03",
            language="typescript",
            category="hollow_tdd",
            description_ko="TypeScript toBeDefined() 단독 약한 단언 적발",
            files={"src/weak.test.ts": "test('weak check', () => {\n  const res = { ok: true };\n  expect(res).toBeDefined();\n});\n"},
            expected_rule_ids=("hollow-tdd-weak-assertion",),
        ),
        BenchmarkCase(
            case_id="ts-defect-04",
            language="typescript",
            category="type_safety",
            description_ko="TypeScript 변수 선언 내 금지된 any 타입 적발",
            files={"src/service.ts": "export function parseData(raw: string): void {\n  const item: any = JSON.parse(raw);\n  console.log(item);\n}\n"},
            expected_rule_ids=("forbidden-any-type",),
        ),
        BenchmarkCase(
            case_id="ts-defect-05",
            language="typescript",
            category="type_safety",
            description_ko="TypeScript Record<string, any> 금지 타입 적발",
            files={"src/model.ts": "export type ConfigMap = Record<string, any>;\n"},
            expected_rule_ids=("forbidden-any-type",),
        ),
        BenchmarkCase(
            case_id="ts-defect-06",
            language="typescript",
            category="slop",
            description_ko="TypeScript 주석만 있는 빈 catch 블록 슬롭 적발",
            files={"src/api.ts": "export function callApi(): void {\n  try {\n    fetch('/api');\n  } catch (err) {\n    // ignore error\n  }\n}\n"},
            expected_rule_ids=("slop-bare-except-pass",),
        ),
        BenchmarkCase(
            case_id="tsx-defect-07",
            language="tsx",
            category="ui_rule",
            description_ko="TSX 버튼 bg-transparent 기본 스타일 누락 적발",
            files={"src/Button.tsx": "export function ActionBtn() {\n  return <button className=\"px-4 py-2 bg-blue-600\">저장</button>;\n}\n"},
            expected_rule_ids=("button-bg-transparent-missing",),
            check_ui_rules=True,
        ),
        BenchmarkCase(
            case_id="tsx-defect-08",
            language="tsx",
            category="ui_rule",
            description_ko="TSX 화살표 함수(>=) 포함 버튼에서 bg-transparent 누락 적발",
            files={
                "src/ComplexBtn.tsx": (
                    "export function ComplexBtn({ count }: { count: number }) {\n"
                    "  return <button onClick={() => { if (count >= 1) alert('ok'); }} className=\"px-2\">실행</button>;\n"
                    "}\n"
                )
            },
            expected_rule_ids=("button-bg-transparent-missing",),
            check_ui_rules=True,
        ),
        BenchmarkCase(
            case_id="tsx-defect-09",
            language="tsx",
            category="ui_rule",
            description_ko="TSX 금지된 @heroicons 아이콘 라이브러리 임포트 적발",
            files={
                "src/Header.tsx": (
                    "import { UserIcon } from '"
                    "@heroicons/react/24/solid';\nexport const Header = () => <div />;\n"
                )
            },
            expected_rule_ids=("forbidden-icon-library",),
            check_ui_rules=True,
        ),
        BenchmarkCase(
            case_id="tsx-defect-10",
            language="tsx",
            category="ui_rule",
            description_ko="TSX 금지된 react-icons 라이브러리 임포트 적발",
            files={
                "src/Nav.tsx": (
                    "import { FiMenu } from '"
                    "react-icons/fi';\nexport const Nav = () => <nav />;\n"
                )
            },
            expected_rule_ids=("forbidden-icon-library",),
            check_ui_rules=True,
        ),
        BenchmarkCase(
            case_id="ts-defect-11",
            language="typescript",
            category="hollow_tdd",
            description_ko="TypeScript assert.equal(true, true) 가짜 단언 적발",
            files={"src/legacy.spec.ts": "test('legacy', function() {\n  assert.equal(true, true);\n});\n"},
            expected_rule_ids=("hollow-tdd-assert-true",),
        ),
        BenchmarkCase(
            case_id="ts-defect-12",
            language="typescript",
            category="hollow_tdd",
            description_ko="TypeScript async 테스트 콜백 내 단언문 누락 적발",
            files={"src/async.test.ts": "test('async noop', async () => {\n  await Promise.resolve(42);\n});\n"},
            expected_rule_ids=("hollow-tdd-no-assertion",),
        ),
    )


def _build_rust_and_go_defect_cases() -> tuple[BenchmarkCase, ...]:
    return (
        BenchmarkCase(
            case_id="rs-defect-01",
            language="rust",
            category="hollow_tdd",
            description_ko="Rust assert!(true) 가짜 테스트 적발",
            files={"src/lib_test.rs": "#[test]\nfn test_fake() {\n    assert!(true);\n}\n"},
            expected_rule_ids=("hollow-tdd-assert-true",),
        ),
        BenchmarkCase(
            case_id="rs-defect-02",
            language="rust",
            category="hollow_tdd",
            description_ko="Rust 단언 매크로 없는 빈 #[test] 함수 적발",
            files={"src/empty_test.rs": "#[test]\nfn test_empty() {\n    let x = 1 + 1;\n    let _ = x;\n}\n"},
            expected_rule_ids=("hollow-tdd-no-assertion",),
        ),
        BenchmarkCase(
            case_id="rs-defect-03",
            language="rust",
            category="slop",
            description_ko="Rust 프로덕션 코드 내 todo!() 미완성 매크로 적발",
            files={"src/engine.rs": "pub fn compute() -> i32 {\n    todo!(\"implement later\")\n}\n"},
            expected_rule_ids=("slop-unimplemented-macro",),
        ),
        BenchmarkCase(
            case_id="rs-defect-04",
            language="rust",
            category="slop",
            description_ko="Rust 프로덕션 코드 내 unimplemented!() 매크로 적발",
            files={"src/handler.rs": "pub fn handle_request() {\n    unimplemented!()\n}\n"},
            expected_rule_ids=("slop-unimplemented-macro",),
        ),
        BenchmarkCase(
            case_id="rs-defect-05",
            language="rust",
            category="hollow_tdd",
            description_ko="Rust #[tokio::test] 비동기 테스트 단언문 누락 적발",
            files={"src/async_test.rs": "#[tokio::test]\nasync fn test_async_empty() {\n    let _ = 42;\n}\n"},
            expected_rule_ids=("hollow-tdd-no-assertion",),
        ),
        BenchmarkCase(
            case_id="go-defect-01",
            language="go",
            category="hollow_tdd",
            description_ko="Go assert.True(t, true) 가짜 단언 적발",
            files={"pkg/calc_test.go": "package calc\nimport \"testing\"\nfunc TestFake(t *testing.T) {\n    assert.True(t, true)\n}\n"},
            expected_rule_ids=("hollow-tdd-assert-true",),
        ),
        BenchmarkCase(
            case_id="go-defect-02",
            language="go",
            category="hollow_tdd",
            description_ko="Go Test* 함수 내 검증 로직 누락 적발",
            files={"pkg/empty_test.go": "package calc\nimport \"testing\"\nfunc TestEmpty(t *testing.T) {\n    _ = 10 + 20\n}\n"},
            expected_rule_ids=("hollow-tdd-no-assertion",),
        ),
        BenchmarkCase(
            case_id="go-defect-03",
            language="go",
            category="type_safety",
            description_ko="Go 파라미터 내 비타입 interface{} 사용 적발",
            files={"pkg/service.go": "package calc\nfunc Handle(payload interface{}) error {\n    return nil\n}\n"},
            expected_rule_ids=("forbidden-any-type",),
        ),
        BenchmarkCase(
            case_id="go-defect-04",
            language="go",
            category="hollow_tdd",
            description_ko="Go require.Equal(t, true, true) 가짜 단언 적발",
            files={"pkg/req_test.go": "package calc\nimport \"testing\"\nfunc TestReqFake(t *testing.T) {\n    require.Equal(t, true, true)\n}\n"},
            expected_rule_ids=("hollow-tdd-assert-true",),
        ),
        BenchmarkCase(
            case_id="go-defect-05",
            language="go",
            category="type_safety",
            description_ko="Go 맵 타입 내 interface{} 사용 적발",
            files={"pkg/store.go": "package calc\ntype Store map[string]interface{}\n"},
            expected_rule_ids=("forbidden-any-type",),
        ),
    )


def _build_clean_guard_cases() -> tuple[BenchmarkCase, ...]:
    return (
        BenchmarkCase(
            case_id="py-clean-01",
            language="python",
            category="clean_guard",
            description_ko="명시적 반환 타입과 구체적 예외 처리를 갖춘 정상 Python 모듈",
            files={
                "app/clean.py": (
                    "def divide(a: int, b: int) -> float:\n"
                    "    try:\n"
                    "        return a / b\n"
                    "    except ZeroDivisionError as exc:\n"
                    "        raise ValueError('0으로 나눌 수 없습니다.') from exc\n"
                )
            },
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="py-clean-02",
            language="python",
            category="clean_guard",
            description_ko="구체적 값 비교(assert actual == expected)를 수행하는 정상 Python 테스트",
            files={"tests/test_clean.py": "def test_addition() -> None:\n    assert 2 + 3 == 5\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="py-clean-03",
            language="python",
            category="clean_guard",
            description_ko="is not None 확인과 실제 값 비교를 함께 수행하는 정상 Python 테스트",
            files={"tests/test_combo.py": "def test_combo() -> None:\n    res = {'ok': 1}\n    assert res is not None\n    assert res['ok'] == 1\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="py-clean-04",
            language="python",
            category="clean_guard",
            description_ko="커스텀 assert_ 헬퍼 함수를 호출하는 정상 Python 테스트",
            files={"tests/test_helper.py": "def assert_valid_item(x: int) -> None:\n    assert x > 0\ndef test_with_helper() -> None:\n    assert_valid_item(10)\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="py-clean-05",
            language="python",
            category="clean_guard",
            description_ko="비공개 헬퍼 함수(_prefix)는 반환 타입 생략 시에도 오탐하지 않음",
            files={"app/internal.py": "def _helper(x: int):\n    return x * 2\ndef public_api(x: int) -> int:\n    return _helper(x)\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="ts-clean-01",
            language="typescript",
            category="clean_guard",
            description_ko="명시적 타입과 정상 에러 복구 로직을 갖춘 TypeScript 모듈",
            files={
                "src/service.ts": (
                    "export interface User { id: string; }\n"
                    "export function parseUser(raw: string): User {\n"
                    "  try {\n"
                    "    return JSON.parse(raw) as User;\n"
                    "  } catch (err) {\n"
                    "    throw new Error('파싱 실패');\n"
                    "  }\n"
                    "}\n"
                )
            },
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="ts-clean-02",
            language="typescript",
            category="clean_guard",
            description_ko="주석 내부의 : any 및 빈 catch {} 구문 오탐 방지",
            files={"src/commented.ts": "// const bad: any = 1; try {} catch (e) {}\nexport const count: number = 1;\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="ts-clean-03",
            language="typescript",
            category="clean_guard",
            description_ko="문자열 리터럴 내부의 expect(true).toBe(true) 및 : any 오탐 방지",
            files={"src/strings.test.ts": "it('checks message', () => {\n  const msg = 'avoid : any and expect(true).toBe(true)';\n  expect(msg).toContain('avoid');\n});\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="ts-clean-04",
            language="typescript",
            category="clean_guard",
            description_ko="toBeDefined()와 toEqual()을 함께 사용한 정상 테스트 오탐 방지",
            files={"src/strong.test.ts": "test('strong check', () => {\n  const user = { name: 'Hero' };\n  expect(user).toBeDefined();\n  expect(user.name).toBe('Hero');\n});\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="ts-clean-05",
            language="typescript",
            category="clean_guard",
            description_ko="커스텀 verify* 헬퍼를 호출하는 정상 TypeScript 테스트",
            files={"src/custom.test.ts": "it('verifies schema', () => {\n  verifyContract({ ok: true });\n});\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="tsx-clean-06",
            language="tsx",
            category="clean_guard",
            description_ko="bg-transparent와 hover/focus 및 화살표 함수를 포함한 정상 TSX 버튼",
            files={
                "src/GoodButton.tsx": (
                    "import { Check } from 'lucide-react';\n"
                    "export function GoodButton({ val }: { val: number }) {\n"
                    "  return (\n"
                    "    <button onClick={() => { if (val > 0) console.log(val); }} className=\"bg-transparent hover:bg-gray-100 focus:ring-2\">\n"
                    "      <Check />\n"
                    "    </button>\n"
                    "  );\n"
                    "}\n"
                )
            },
            expected_rule_ids=(),
            check_ui_rules=True,
        ),
        BenchmarkCase(
            case_id="tsx-clean-07",
            language="tsx",
            category="clean_guard",
            description_ko="블록 주석 내부의 위반 <button> 및 금지 아이콘 임포트 오탐 방지",
            files={
                "src/CommentedBtn.tsx": (
                    "/* <button className=\"bg-red-500\">Bad</button>\n"
                    "   import { X } from '"
                    "react-icons/fi'; */\n"
                    "export const SafeView = () => <div>안전</div>;\n"
                )
            },
            expected_rule_ids=(),
            check_ui_rules=True,
        ),
        BenchmarkCase(
            case_id="ts-clean-08",
            language="typescript",
            category="clean_guard",
            description_ko="정규식 리터럴 내부의 any 패턴 오탐 방지",
            files={"src/regex.ts": "export const ANY_PATTERN = /:\\s*any\\b/;\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="ts-clean-09",
            language="typescript",
            category="clean_guard",
            description_ko="콜백이 없는 test.todo() 선언 오탐 방지",
            files={"src/todo.test.ts": "test.todo('추후 구현 예정인 통합 테스트');\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="rs-clean-01",
            language="rust",
            category="clean_guard",
            description_ko="assert_eq!를 포함한 정상 Rust 단위 테스트",
            files={"src/math_test.rs": "#[test]\nfn test_add() {\n    assert_eq!(2 + 2, 4);\n}\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="rs-clean-02",
            language="rust",
            category="clean_guard",
            description_ko="#[should_panic] 속성을 가진 정상 Rust 패닉 테스트",
            files={"src/panic_test.rs": "#[test]\n#[should_panic]\nfn test_panic_case() {\n    panic!(\"expected\");\n}\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="rs-clean-03",
            language="rust",
            category="clean_guard",
            description_ko="Result<(), String>을 반환하고 주석에만 todo!가 있는 정상 Rust 코드",
            files={"src/res_test.rs": "// todo!(\"in comment\")\n#[test]\nfn test_result() -> Result<(), String> {\n    Ok(())\n}\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="go-clean-01",
            language="go",
            category="clean_guard",
            description_ko="t.Fatalf를 사용한 정상 Go 단위 테스트",
            files={"pkg/add_test.go": "package pkg\nimport \"testing\"\nfunc TestAdd(t *testing.T) {\n    if 1 + 2 != 3 {\n        t.Fatalf(\"mismatch\")\n    }\n}\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="go-clean-02",
            language="go",
            category="clean_guard",
            description_ko="커스텀 check* 헬퍼를 호출하는 정상 Go 테스트",
            files={"pkg/helper_test.go": "package pkg\nimport \"testing\"\nfunc TestHelper(t *testing.T) {\n    checkResult(t, 42)\n}\n"},
            expected_rule_ids=(),
        ),
        BenchmarkCase(
            case_id="go-clean-03",
            language="go",
            category="clean_guard",
            description_ko="구체적 구조체와 주석 속 interface{}만 있는 정상 Go 코드",
            files={"pkg/model.go": "package pkg\n// legacy interface{} replaced\ntype Request struct {\n    ID string\n}\n"},
            expected_rule_ids=(),
        ),
    )


class DefaultBenchmarkCorpus:
    """5개 언어 50종 골든 코퍼스(적대적 결함 30종 + 정상 가드 20종) 기본 제공자."""

    def __init__(self) -> None:
        self._cases: tuple[BenchmarkCase, ...] = (
            *_build_python_defect_cases(),
            *_build_ts_defect_cases(),
            *_build_rust_and_go_defect_cases(),
            *_build_clean_guard_cases(),
        )

    def list_cases(self, language_filter: str = "all") -> tuple[BenchmarkCase, ...]:
        """언어 필터(all, python, typescript, ts, tsx, rust, go)에 맞는 케이스를 반환한다."""
        norm = (language_filter or "all").strip().lower()
        if norm in ("", "all", "*"):
            return self._cases
        if norm == "ts":
            return tuple(c for c in self._cases if c.language in ("typescript", "tsx"))
        return tuple(c for c in self._cases if c.language == norm)


class BenchmarkSuiteRunner:
    """격리 샌드박스에서 벤치마크 코퍼스를 실행하고 정량 지표(Recall, FPR, Precision)를 계산한다."""

    def __init__(self, corpus_provider: CorpusProvider | None = None) -> None:
        self._corpus: CorpusProvider = corpus_provider or DefaultBenchmarkCorpus()

    def evaluate_case(self, case: BenchmarkCase, sandbox_base: Path) -> BenchmarkEvaluation:
        """단일 벤치마크 케이스를 격리 디렉터리에 기록하고 audit_project_code로 판정한다."""
        case_dir = sandbox_base / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        for rel_path, content in case.files.items():
            fpath = case_dir / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

        t0 = time.perf_counter()
        audit_res = autopilot_engine.audit_project_code(
            case_dir,
            check_ui_rules=case.check_ui_rules,
            changed_only=False,
            force_all=True,
            apply=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        raw_findings = audit_res.get("findings", [])
        actual_rules: list[str] = []
        if isinstance(raw_findings, list):
            for item in raw_findings:
                if isinstance(item, dict):
                    rid = str(item.get("rule_id") or "")
                    if rid and rid not in actual_rules:
                        actual_rules.append(rid)

        expected_defect = len(case.expected_rule_ids) > 0
        detected_defect = len(actual_rules) > 0
        if expected_defect:
            matched_all = all(exp in actual_rules for exp in case.expected_rule_ids)
            outcome = "TP" if matched_all else "FN"
            passed = matched_all
        else:
            outcome = "TN" if not detected_defect else "FP"
            passed = not detected_defect

        return BenchmarkEvaluation(
            case_id=case.case_id,
            language=case.language,
            category=case.category,
            expected_defect=expected_defect,
            detected_defect=detected_defect,
            expected_rule_ids=list(case.expected_rule_ids),
            actual_rule_ids=actual_rules,
            outcome=outcome,
            passed=passed,
            elapsed_ms=elapsed_ms,
        )

    def run_suite(
        self,
        project_root: Path,
        *,
        language: str = "all",
        apply: bool = False,
    ) -> dict[str, object]:
        """전체 또는 필터링된 벤치마크 스위트를 실행하고 정량 리포트를 반환한다."""
        resolved = project_root.resolve()
        cases = self._corpus.list_cases(language)
        if not cases:
            raise ValueError(f"지원하지 않거나 케이스가 없는 언어 필터입니다: {language}")

        t_start = time.perf_counter()
        evaluations: list[BenchmarkEvaluation] = []
        with tempfile.TemporaryDirectory(prefix="dreampia-bench-") as tmp_dir:
            sandbox_base = Path(tmp_dir)
            for case in cases:
                evaluations.append(self.evaluate_case(case, sandbox_base))
        total_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        tp = sum(1 for e in evaluations if e.outcome == "TP")
        tn = sum(1 for e in evaluations if e.outcome == "TN")
        fp = sum(1 for e in evaluations if e.outcome == "FP")
        fn = sum(1 for e in evaluations if e.outcome == "FN")

        recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 1.0
        precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 1.0
        fpr = round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0.0
        passed_all = (fn == 0 and fp == 0)

        report: dict[str, object] = {
            "action": "benchmark",
            "schema_version": BENCHMARK_SUITE_VERSION,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": "PASS" if passed_all else "FAIL",
            "applied": apply,
            "report_path": DEFAULT_BENCHMARK_REPORT_REL if apply else None,
            "language_filter": language,
            "total_cases": len(evaluations),
            "defect_cases": tp + fn,
            "clean_guard_cases": tn + fp,
            "metrics": {
                "true_positives": tp,
                "true_negatives": tn,
                "false_positives": fp,
                "false_negatives": fn,
                "recall": recall,
                "precision": precision,
                "false_positive_rate": fpr,
                "total_elapsed_ms": round(total_elapsed_ms, 2),
                "avg_case_ms": round(total_elapsed_ms / len(evaluations), 2),
            },
            "failed_cases": [e.to_dict() for e in evaluations if not e.passed],
            "evaluations": [e.to_dict() for e in evaluations],
            "message_ko": (
                f"다국어 적대적 벤치마크 스위트({len(evaluations)}종) 검증 통과: "
                f"적발률(Recall)={recall * 100:.1f}%, 오탐률(FPR)={fpr * 100:.1f}%, 소요시간={total_elapsed_ms:.1f}ms"
                if passed_all
                else f"벤치마크 스위트 실패: 미탐(FN)={fn}건, 오탐(FP)={fp}건"
            ),
        }
        canonical = json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
        report["report_sha256"] = hashlib.sha256(canonical).hexdigest()

        if apply:
            autopilot_engine.ensure_local_git_exclude(resolved)
            out_path = resolved / DEFAULT_BENCHMARK_REPORT_REL
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return report


def run_benchmark_suite(
    project_root: Path,
    *,
    language: str = "all",
    apply: bool = False,
) -> dict[str, object]:
    """벤치마크 스위트 실행 진입점."""
    runner = BenchmarkSuiteRunner()
    return runner.run_suite(project_root, language=language, apply=apply)
