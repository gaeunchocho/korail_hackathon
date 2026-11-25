"""장치 자동 분류와 지연 요약 테스트.

    python -m unittest -v test_classify
"""

import unittest

from app import delay_summary
from classify import classify
from keyword_search import Case


class ClassifyTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(classify("2위 출입문 닫힘 불량"), "출입문")
        self.assertEqual(classify("BC압 상승 불량"), "제동")
        self.assertEqual(classify("SIV정지"), "전력·보조전원")
        self.assertEqual(classify("ATP 고장"), "신호·제어")
        self.assertEqual(classify("냉방 불량"), "냉난방")
        self.assertEqual(classify("MR압 저하"), "공기·압축기")
        self.assertEqual(classify("창닦이 불량"), "기타")

    def test_delay_summary_uses_recorded_values_only(self):
        def case(delay):
            return Case("A", "", "", "", "", "", "", "", "x", delay_minutes=delay)

        self.assertEqual(delay_summary([case("0"), case("10"), case("20"), case("")]),
                         {"count": 3, "average": 10.0, "max": 20, "delayed": 2})
        self.assertIsNone(delay_summary([case(""), case("")]))


if __name__ == "__main__":
    unittest.main()
