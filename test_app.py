"""모의(가짜) 모델 테스트. 실제 AI 모델이나 실제 CSV를 쓰지 않습니다.

    python -m unittest -v test_app
"""

import csv
import tempfile
import unittest
from pathlib import Path

from app import SearchService
from keyword_search import COLUMNS, CsvError, KeywordIndex, load_cases
from semantic import check_model_dir, combine_ranks

ROWS = [
    ("A1", "2020-01-01", "08:00", "서울역", "서울", "부산", "8", "2010-01-01", "출입문 닫힘 불량으로 재취급 후 정상"),
    ("A2", "2020-01-02", "09:30", "", "", "", "", "", "냉방장치 고장으로 객실 온도 상승"),
    ("A3", "2020-01-03", "10:15", "대전역", "대전", "목포", "4", "2015-05-05", "제동 지연으로 정위치 정차 실패"),
]


class FakeModel:
    """문장에 들어 있는 낱말로 3차원 벡터를 만드는 가짜 모델입니다."""

    groups = (("문", "닫"), ("더", "냉방", "온도"), ("멈", "정차", "제동"))

    def __init__(self):
        self.calls = 0

    def encode(self, texts, **_):
        import numpy as np

        self.calls += 1
        rows = [[float(any(word in text for word in group)) + 1e-6 for group in self.groups] for text in texts]
        vectors = np.array(rows)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def write_csv(folder, rows=ROWS, columns=COLUMNS):
    path = Path(folder) / "sample.csv"
    with open(path, "w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(columns)
        writer.writerows(rows)
    return path


class Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.cases = load_cases(write_csv(self.folder.name))

    def tearDown(self):
        self.folder.cleanup()

    def test_keyword_finds_door_case(self):
        ranking = KeywordIndex(self.cases).rank("출입문이 안 닫혀요")
        self.assertEqual(self.cases[ranking[0]].case_id, "A1")

    def test_missing_column_message(self):
        path = write_csv(self.folder.name, rows=[], columns=COLUMNS[:-1])
        with self.assertRaisesRegex(CsvError, "운행장애개요내용"):
            load_cases(path)

    def test_missing_file_message(self):
        with self.assertRaisesRegex(CsvError, "찾을 수 없습니다"):
            load_cases(Path(self.folder.name) / "none.csv")

    def test_rrf_combines_both_rankings(self):
        self.assertEqual(combine_ranks([0, 1], [1, 2]), [1, 0, 2])

    def test_hybrid_with_fake_model_and_embeddings_built_once(self):
        model = FakeModel()
        service = SearchService(self.cases)
        service.start_ai("unused", model_loader=lambda _: model, show_progress=False)
        self.assertTrue(service.ai_ready)
        results, used = service.search("객실이 너무 더워요", "hybrid")
        service.search("열차가 제때 멈추지 않아요", "hybrid")
        self.assertEqual(used, "hybrid")
        self.assertEqual(results[0].case_id, "A2")
        self.assertEqual(model.calls, 3)  # 사례 1번 + 검색어 2번

    def test_ai_failure_falls_back_to_keyword(self):
        def broken(_):
            raise RuntimeError("모델 파일 없음")

        service = SearchService(self.cases)
        service.start_ai("unused", model_loader=broken)
        data = service.api_search("출입문")
        self.assertEqual(data["mode"], "keyword")
        self.assertEqual(data["results"][0]["id"], "A1")
        self.assertEqual(service.status()["ai_state"], "error")
        self.assertIn("모델 파일 없음", service.status()["ai_status"])

    def test_api_uses_hybrid_when_ai_ready(self):
        service = SearchService(self.cases)
        service.start_ai("unused", model_loader=lambda _: FakeModel(), show_progress=False)
        self.assertEqual(service.api_search("객실이 너무 더워요")["mode"], "hybrid")

    def test_missing_values_show_mirokrok(self):
        data = SearchService(self.cases).api_search("냉방")
        case = data["results"][0]
        self.assertEqual(case["id"], "A2")
        self.assertEqual([case[k] for k in ("location", "origin", "destination", "vehicle_count", "introduced_on")],
                         ["미기록"] * 5)
        self.assertEqual(case["occurred"], "2020-01-02 09:30")

    def test_empty_query_message(self):
        self.assertEqual(SearchService(self.cases).api_search("  ")["error"], "고장 증상을 입력해 주세요.")

    def test_original_csv_has_no_action(self):
        self.assertIsNone(SearchService(self.cases).api_search("냉방")["results"][0]["action"])

    def test_demo_action_columns_are_labeled(self):
        columns = COLUMNS + ("정비단", "정비유형", "조치내용", "조치구분")
        rows = [ROWS[0] + ("가상 정비단", "출입문 개폐", "가상 점검", "가상 조치 (데모)"),
                ROWS[1] + ("", "", "재취급 후 정상", "기록된 조치 (원문 발췌)")]
        cases = load_cases(write_csv(self.folder.name, rows=rows, columns=columns))
        service = SearchService(cases)
        demo = service.api_search("출입문")["results"][0]["action"]
        recorded = service.api_search("냉방")["results"][0]["action"]
        self.assertEqual((demo["kind"], demo["is_demo"]), ("가상 조치 (데모)", True))
        self.assertEqual((recorded["is_demo"], recorded["team"]), (False, "미기록"))
        self.assertTrue(service.status()["has_actions"])

    def test_demo_filled_csv_marks_fake_values(self):
        import subprocess, sys
        target = Path(self.folder.name) / "filled.csv"
        subprocess.run([sys.executable, "make_demo_csv.py", str(write_csv(self.folder.name)), str(target)],
                       check=True, capture_output=True)
        service = SearchService(load_cases(target))
        filled = service.api_search("냉방")["results"][0]
        self.assertEqual(sorted(filled["filled"]),
                         ["destination", "introduced_on", "location", "origin", "vehicle_count"])
        self.assertNotIn("미기록", [filled[k] for k in filled["filled"]])
        self.assertNotEqual(filled["origin"], filled["destination"])
        untouched = service.api_search("출입문")["results"][0]
        self.assertEqual((untouched["filled"], untouched["origin"]), ([], "서울"))

    def test_results_newest_first_with_similarity_rank(self):
        results = SearchService(self.cases).api_search("출입문 닫힘 냉방 고장 제동 지연")["results"]
        self.assertEqual([r["id"] for r in results], ["A3", "A2", "A1"])
        self.assertEqual(sorted(r["similarity_rank"] for r in results), [1, 2, 3])

    def test_original_csv_has_no_fake_values(self):
        self.assertEqual(SearchService(self.cases).api_search("냉방")["results"][0]["filled"], [])

    def test_highlight_skips_common_terms(self):
        terms = KeywordIndex(self.cases).highlight_terms("출입문이 안 닫혀요", max_share=0.6)
        self.assertIn("출입", terms)

    def test_csv_error(self):
        service = SearchService(csv_error="CSV 파일을 찾을 수 없습니다: x.csv")
        self.assertIn("찾을 수 없습니다", service.api_search("문")["error"])

    def test_check_model_dir_reports_missing(self):
        self.assertTrue(check_model_dir(Path(self.folder.name)))


if __name__ == "__main__":
    unittest.main()
