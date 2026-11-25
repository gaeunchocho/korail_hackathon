"""장치 자동 분류: 운행장애 원문이나 고장 증상에 나온 단어로 장치를 정합니다(키워드 규칙, 학습 모델 아님).

위에서부터 먼저 맞는 규칙을 씁니다. 어느 규칙에도 없으면 '기타'입니다.
"""

import re

# (장치, 단어 목록). 영문 약어는 앞뒤가 다른 영문자가 아닐 때만 맞춥니다(예: "MR압"은 맞고 "SMRT"는 아님).
DEVICE_RULES = (
    ("출입문", ("출입문", "도어", "door", "승강문", "안닫힘", "닫힘")),
    ("신호·제어", ("atp", "ats", "atc", "신호", "열차방호", "보안장치", "tcms", "모니터", "btm", "통신", "tcu", "acu", "ibp")),
    ("제동", ("제동", "브레이크", "bc압", "bc", "bp", "완해", "제륜", "활주")),
    ("전력·보조전원", ("siv", "mcb", "vcb", "팬터", "판토", "보조전원", "축전지", "배터리", "변압기", "컨버터", "전원", "충전장치", "접지", "gr")),
    ("견인·추진", ("견인", "역행", "추진", "전동기", "인버터", "vvvf", "공전", "출력부족", "주변환기", "주전력변환", "tm")),
    ("냉난방", ("냉방", "난방", "에어컨", "공조", "히터", "온도")),
    ("공기·압축기", ("mr", "주공기", "압축기", "cm", "공기누설", "공기압")),
    ("연기·냄새", ("연기", "타는 냄새", "타는냄새", "화재", "불꽃")),
    ("객실·방송", ("방송", "조명", "객실", "화장실", "누수", "응결수")),
)
DEVICES = tuple(device for device, _ in DEVICE_RULES) + ("기타",)


def _pattern(word):
    if word.isascii():
        return rf"(?<![a-z]){re.escape(word)}(?![a-z])"
    return re.escape(word)


_COMPILED = tuple((device, re.compile("|".join(_pattern(w) for w in words))) for device, words in DEVICE_RULES)


def classify(text):
    lowered = (text or "").casefold()
    for device, pattern in _COMPILED:
        if pattern.search(lowered):
            return device
    return "기타"
