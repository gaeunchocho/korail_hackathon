"""CSV 읽기와 키워드(TF-IDF) 검색. 표준 라이브러리만 사용합니다."""

import csv
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

COLUMNS = (
    "FRACAS관리번호", "고장발생일자", "고장발생시각", "발생장소명",
    "시발역명", "종착역명", "열차차량수", "차량도입일자", "운행장애개요내용",
)
# 데모용 CSV(FRACAS_20220830_with_demo_maintenance.csv)에만 있는 선택 열. 없으면 빈 값으로 둡니다.
OPTIONAL_COLUMNS = ("정비단", "정비유형", "조치내용", "조치구분", "가상채움열", "고장지연분간시간수", "지장열차수량")


@dataclass(frozen=True)
class Case:
    case_id: str
    date: str
    clock: str
    location: str
    origin: str
    destination: str
    vehicle_count: str
    introduced_on: str
    description: str
    team: str = ""
    maintenance_type: str = ""
    action: str = ""
    action_kind: str = ""
    filled: str = ""  # make_demo_csv.py가 가상 값으로 채운 열 이름(쉼표로 구분)
    delay_minutes: str = ""  # 고장지연분간시간수 (원본 값)
    affected_trains: str = ""  # 지장열차수량 (원본 값)


class CsvError(Exception):
    """CSV를 읽을 수 없을 때 한국어 안내 문구를 담습니다."""


def load_cases(path):
    """CSV를 읽기 전용으로 열어 사례 목록을 돌려줍니다. 값은 바꾸지 않고 앞뒤 공백만 지웁니다."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            missing = [name for name in COLUMNS if name not in (reader.fieldnames or ())]
            if missing:
                raise CsvError("CSV에 필요한 열이 없습니다: " + ", ".join(missing))
            cases = [
                Case(*((row.get(name) or "").strip() for name in COLUMNS + OPTIONAL_COLUMNS))
                for row in reader
            ]
    except FileNotFoundError:
        raise CsvError(f"CSV 파일을 찾을 수 없습니다: {path}") from None
    except UnicodeDecodeError:
        raise CsvError("CSV를 UTF-8로 읽을 수 없습니다. UTF-8로 저장된 파일인지 확인해 주세요.") from None
    except (OSError, csv.Error) as error:
        raise CsvError(f"CSV를 읽는 중 오류가 났습니다: {error}") from None
    cases = [case for case in cases if case.description]
    if not cases:
        raise CsvError("CSV에 '운행장애개요내용'이 있는 사례가 없습니다.")
    return cases


def features(text):
    """한국어 단어와 연속 두 글자를 셉니다. 예: '출입문' -> 단어 '출입문', 두 글자 '출입', '입문'."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    words = re.findall(r"[^\W_]+", normalized)
    counts = Counter(("글자", word[i:i + 2]) for word in words for i in range(len(word) - 1))
    counts.update(("단어", word) for word in words)
    return counts


class KeywordIndex:
    """TF-IDF 코사인 유사도. 여러 기록에 흔한 표현일수록 가중치가 낮아집니다."""

    def __init__(self, cases):
        documents = [features(case.description) for case in cases]
        frequencies = Counter(term for document in documents for term in document)
        total = len(documents)
        self.idf = {term: 1 + math.log((1 + total) / (1 + count)) for term, count in frequencies.items()}
        self.postings = defaultdict(list)
        for index, document in enumerate(documents):
            weights = {term: count * self.idf[term] for term, count in document.items()}
            norm = math.sqrt(sum(weight * weight for weight in weights.values())) or 1.0
            for term, weight in weights.items():
                self.postings[term].append((index, weight / norm))

    def rank(self, query):
        """점수가 0보다 큰 사례 번호를 점수 높은 순으로 돌려줍니다."""
        scores = defaultdict(float)
        for term, count in features(query).items():
            weight = count * self.idf.get(term, 0.0)
            for index, document_weight in self.postings.get(term, ()):
                scores[index] += weight * document_weight
        return sorted(scores, key=lambda index: (-scores[index], index))

    def highlight_terms(self, query, max_share=0.1):
        """화면 강조용 표현: 검색어의 단어·두 글자 중 전체 기록의 max_share 미만에만 나오는 것."""
        threshold = 1 + math.log(1 / max_share)
        terms = {term[1] for term in features(query)
                 if len(term[1]) >= 2 and self.idf.get(term, 0) > threshold}  # 한 글자는 너무 흔하게 겹쳐 제외
        return sorted(terms, key=len, reverse=True)
