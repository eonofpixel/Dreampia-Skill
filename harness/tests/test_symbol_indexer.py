"""무의존성 다국어 시맨틱 심볼 맵 및 슬라이서(symbol_indexer.py) 단위 테스트."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness import symbol_indexer


class TestSymbolIndexer(unittest.TestCase):
    """Python AST 및 C-계열 심볼 목차 추출(토큰 절감)과 심볼 슬라이싱 검증."""

    def test_python_symbol_map_and_slice_achieves_high_token_reduction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            method_body = "\n".join(f"        x_{i} = call_{i % 10}({i})" for i in range(40))
            func_body = "\n".join(f"    y_{i} = {i} * 3" for i in range(40))
            py_code = (
                "class OrderProcessor(object):\n"
                '    """주문 처리 핵심 서비스."""\n'
                "    def validate_order(self, order_id: str) -> bool:\n"
                f"{method_body}\n"
                "        return len(order_id) > 0\n\n"
                "def calculate_tax(amount: int) -> int:\n"
                f"{func_body}\n"
                "    return int(amount * 0.1)\n"
            )
            (root / "service.py").write_text(py_code, encoding="utf-8")

            map_res = symbol_indexer.build_symbol_map(root, "service.py")
            self.assertEqual(map_res["status"], "PASS")
            self.assertEqual(map_res["total_symbols"], 3)
            self.assertGreaterEqual(float(map_res["token_reduction_ratio"]), 0.75)  # type: ignore[arg-type]

            files_list = map_res["files"]
            assert isinstance(files_list, list)
            syms = files_list[0]["symbols"]
            assert isinstance(syms, list)
            self.assertEqual(syms[0]["signature"], "class OrderProcessor(object)")
            self.assertEqual(syms[0]["line_count"], 44)
            self.assertEqual(syms[1]["signature"], "def validate_order(self, order_id: str) -> bool")
            self.assertEqual(syms[1]["line_count"], 42)
            self.assertEqual(len(syms[1]["calls"]), 8)
            self.assertEqual(syms[2]["signature"], "def calculate_tax(amount: int) -> int")
            self.assertEqual(syms[2]["line_count"], 42)
            self.assertEqual(syms[2]["calls"], ["int"])

            slice_res = symbol_indexer.extract_symbol_slice(root, "service.py::OrderProcessor.validate_order", "")
            self.assertEqual(slice_res["status"], "PASS")
            self.assertIn("def validate_order", str(slice_res["code_slice"]))
            self.assertNotIn("def calculate_tax", str(slice_res["code_slice"]))

    def test_typescript_and_rust_symbol_extraction_ignores_commented_braces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ts_code = (
                "// function fakeInComment() { return 1; }\n"
                "export interface OrderProps {\n"
                "  id: string;\n"
                "}\n"
                "export class CartManager {\n"
                "  /* } fake closing brace in comment */\n"
                "  clear(): void {}\n"
                "}\n"
                "export const computeTotal = (items: number[]): number => {\n"
                "  return items.length;\n"
                "};\n"
            )
            (root / "cart.ts").write_text(ts_code, encoding="utf-8")
            map_res = symbol_indexer.build_symbol_map(root, "cart.ts")
            self.assertEqual(map_res["status"], "PASS")
            self.assertEqual(map_res["total_symbols"], 3)

            slice_res = symbol_indexer.extract_symbol_slice(root, "cart.ts", "CartManager")
            self.assertEqual(slice_res["status"], "PASS")
            self.assertIn("clear(): void {}", str(slice_res["code_slice"]))

    def test_typescript_complex_generics_object_return_types_and_class_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ts_code = (
                "export class 레거시패킷분석기 {\n"
                "  public async 패킷복호화(\n"
                "    옵션: { 압축여부: boolean },\n"
                "  ): Promise<{ 복호화본문: string; 성공: boolean }> {\n"
                "    return { 복호화본문: String(옵션.압축여부), 성공: true };\n"
                "  }\n"
                "}\n\n"
                "export async function 복합함수<T extends { id: string }>(\n"
                "  입력: T,\n"
                "): Promise<{ 결과: T }> {\n"
                "  return { 결과: 입력 };\n"
                "}\n"
            )
            (root / "parser.ts").write_text(ts_code, encoding="utf-8")
            map_res = symbol_indexer.build_symbol_map(root, "parser.ts")
            self.assertEqual(map_res["status"], "PASS")
            self.assertEqual(map_res["total_symbols"], 3)

            method_slice = symbol_indexer.extract_symbol_slice(
                root, "parser.ts::레거시패킷분석기.패킷복호화", ""
            )
            self.assertEqual(method_slice["status"], "PASS")
            self.assertIn("패킷복호화", str(method_slice["code_slice"]))

            fn_slice = symbol_indexer.extract_symbol_slice(root, "parser.ts", "복합함수")
            self.assertEqual(fn_slice["status"], "PASS")
            self.assertIn("return { 결과: 입력 };", str(fn_slice["code_slice"]))


if __name__ == "__main__":
    unittest.main()

