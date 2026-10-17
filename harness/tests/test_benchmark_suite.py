"""다국어 적대적 슬롭·결함 벤치마크 스위트(benchmark_suite.py) 단위 및 통합 테스트."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness import benchmark_suite


class TestBenchmarkSuite(unittest.TestCase):
    """50종 골든 코퍼스 기반 Recall 100% 및 False Positive Rate 0% 검증."""

    def test_default_corpus_has_50_cases_across_5_languages(self) -> None:
        corpus = benchmark_suite.DefaultBenchmarkCorpus()
        all_cases = corpus.list_cases("all")
        self.assertEqual(len(all_cases), 50)
        defects = [c for c in all_cases if len(c.expected_rule_ids) > 0]
        cleans = [c for c in all_cases if len(c.expected_rule_ids) == 0]
        self.assertEqual(len(defects), 30)
        self.assertEqual(len(cleans), 20)
        self.assertTrue(len(corpus.list_cases("python")) >= 10)
        self.assertTrue(len(corpus.list_cases("ts")) >= 15)
        self.assertTrue(len(corpus.list_cases("rust")) >= 8)
        self.assertTrue(len(corpus.list_cases("go")) >= 8)

    def test_full_benchmark_suite_achieves_100_percent_recall_and_zero_fpr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = benchmark_suite.run_benchmark_suite(root, language="all", apply=True)
            self.assertEqual(report["status"], "PASS", f"Failed cases: {report.get('failed_cases')}")
            metrics = report["metrics"]
            assert isinstance(metrics, dict)
            self.assertEqual(metrics["true_positives"], 30)
            self.assertEqual(metrics["true_negatives"], 20)
            self.assertEqual(metrics["false_positives"], 0)
            self.assertEqual(metrics["false_negatives"], 0)
            self.assertEqual(metrics["recall"], 1.0)
            self.assertEqual(metrics["precision"], 1.0)
            self.assertEqual(metrics["false_positive_rate"], 0.0)
            self.assertTrue((root / benchmark_suite.DEFAULT_BENCHMARK_REPORT_REL).is_file())


if __name__ == "__main__":
    unittest.main()
