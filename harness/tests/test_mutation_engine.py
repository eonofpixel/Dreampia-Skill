"""무의존성 AST·렉서 기반 뮤테이션 테스팅 엔진(mutation_engine.py) 단위 및 통합 테스트."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

from harness import mutation_engine


class TestMutationEngine(unittest.TestCase):
    """Python AST 변이기, C-계열 렉서 변이기 및 무오염 샌드박스 러너 검증."""

    def test_python_ast_mutator_generates_syntactically_valid_mutants(self) -> None:
        source = (
            "def calc_discount(price: int, vip: bool) -> int:\n"
            "    if vip == True and price >= 100:\n"
            "        return price - 20\n"
            "    return price + 0\n"
        )
        mutator = mutation_engine.PythonAstLineMutator()
        mutants = mutator.generate_mutants("app/pricing.py", source, max_mutants=10)
        self.assertGreaterEqual(len(mutants), 3)
        operators = {m.operator for m in mutants}
        self.assertIn("ROR", operators)
        self.assertIn("AOR", operators)

    def test_cfamily_lexical_mutator_ignores_comments_and_strings(self) -> None:
        ts_source = (
            "// if (a === b) return true;\n"
            "const msg = 'a === b && true + false';\n"
            "export function isAdult(age: number): boolean {\n"
            "  return age >= 18;\n"
            "}\n"
        )
        mutator = mutation_engine.CFamilyLexicalMutator()
        mutants = mutator.generate_mutants("src/age.ts", ts_source, max_mutants=10)
        self.assertEqual(len(mutants), 1)
        self.assertEqual(mutants[0].line, 4)
        self.assertEqual(mutants[0].operator, "ROR")
        self.assertIn("age < 18", mutants[0].mutated_snippet)

    def test_sandbox_runner_detects_weak_test_and_preserves_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod_file = root / "calc.py"
            prod_code = "def add_numbers(a: int, b: int) -> int:\n    return a + b\n"
            prod_file.write_text(prod_code, encoding="utf-8")
            orig_sha = hashlib.sha256(prod_file.read_bytes()).hexdigest()

            weak_test = root / "test_calc.py"
            weak_test.write_text(
                "import unittest\n"
                "from calc import add_numbers\n"
                "class T(unittest.TestCase):\n"
                "    def test_weak(self) -> None:\n"
                "        res = add_numbers(2, 3)\n"
                "        self.assertIsNotNone(res)\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n",
                encoding="utf-8",
            )
            cmd = f'"{sys.executable}" -m unittest discover -s . -p "test_*.py"'
            res_weak = mutation_engine.run_mutation_check(
                root,
                ["calc.py"],
                cmd,
                min_score=0.8,
                apply=True,
            )
            self.assertEqual(res_weak["status"], "FAIL")
            self.assertEqual(res_weak["mutation_score"], 0.0)
            self.assertGreaterEqual(int(res_weak["survived_count"]), 1)  # type: ignore[arg-type]
            self.assertEqual(hashlib.sha256(prod_file.read_bytes()).hexdigest(), orig_sha)

            strong_test = root / "test_calc.py"
            strong_test.write_text(
                "import unittest\n"
                "from calc import add_numbers\n"
                "class T(unittest.TestCase):\n"
                "    def test_strong(self) -> None:\n"
                "        self.assertEqual(add_numbers(2, 3), 5)\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n",
                encoding="utf-8",
            )
            res_strong = mutation_engine.run_mutation_check(
                root,
                ["calc.py"],
                cmd,
                min_score=0.8,
                apply=True,
            )
            self.assertEqual(res_strong["status"], "PASS")
            self.assertEqual(res_strong["mutation_score"], 1.0)
            self.assertEqual(res_strong["survived_count"], 0)
            self.assertEqual(hashlib.sha256(prod_file.read_bytes()).hexdigest(), orig_sha)


if __name__ == "__main__":
    unittest.main()
