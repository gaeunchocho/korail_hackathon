"""시연용 CSV 만들기: 빈 칸(발생 장소, 시발·종착역, 차량 수, 차량 도입일)을 가상 값으로 채우고,
데모 조치의 정비단을 발생 장소 지역에 맞는 실제 코레일 차량정비단 이름으로 배정합니다.

입력 CSV는 읽기만 하고, 결과는 새 파일로 저장합니다. 채운 칸 이름은 '가상채움열' 열에 남겨
화면에서 "가상" 표시를 붙일 수 있게 합니다. 같은 관리번호는 항상 같은 값으로 채워집니다.

    python make_demo_csv.py "C:\\Users\\user\\Downloads\\FRACAS_20220830_with_demo_maintenance.csv" ^
                            "C:\\Users\\user\\Downloads\\FRACAS_20220830_demo_filled.csv"
"""

import argparse
import csv
import random
import zlib
from datetime import date, timedelta
from pathlib import Path

FILL_COLUMN = "가상채움열"
# 실제 노선과 역 이름 (같은 노선 안에서 시발·종착·발생 장소를 고릅니다)
LINES = (
    ("서울", "용산", "노량진", "영등포", "신도림", "구로", "금천구청", "안양", "수원", "천안", "대전"),
    ("청량리", "성북", "창동", "의정부", "동두천", "소요산"),
    ("구로", "개봉", "부평", "주안", "동인천", "인천"),
    ("천안", "아산", "신례원", "홍성", "대천", "서천", "익산"),
    ("청량리", "상봉", "평내호평", "가평", "남춘천", "춘천"),
    ("청량리", "양평", "원주", "만종", "제천", "단양", "풍기", "영주"),
    ("용산", "서대전", "익산", "정읍", "광주송정", "나주", "목포"),
    ("마산", "창원중앙", "진주", "하동", "순천"),
    ("조치원", "오송", "청주", "충주", "제천"),
    ("신판교", "경기광주", "이천", "여주"),
    ("영등포", "신길", "대방", "노량진", "남영", "서울"),
    ("구로", "가리봉", "독산", "시흥", "석수", "관악", "안양"),
)
# 코레일 철도차량정비단 (공개 보도로 확인한 4곳). 발생 장소의 지역에 따라 배정합니다.
TEAM_SUDOGWON, TEAM_DAEJEON, TEAM_BUSAN, TEAM_HONAM = (
    "수도권철도차량정비단", "대전철도차량정비단", "부산철도차량정비단", "호남철도차량정비단")
REGION_TEAMS = {
    TEAM_DAEJEON: ("천안", "아산", "신례원", "홍성", "대천", "서천", "대전", "서대전", "조치원", "오송", "청주",
                   "충주", "원주", "만종", "제천", "단양", "풍기", "영주"),
    TEAM_BUSAN: ("마산", "창원중앙", "진주", "하동"),
    TEAM_HONAM: ("익산", "정읍", "광주송정", "나주", "목포", "순천"),
}
VEHICLE_COUNTS = (4, 6, 6, 8, 8, 10, 10, 10, 10, 12, 16, 20, 20)


def fill_row(row, rng):
    filled = []
    origin, destination = row["시발역명"].strip(), row["종착역명"].strip()
    known = origin or destination or row["발생장소명"].strip()
    lines = [line for line in LINES if known in line] or list(LINES)
    line = rng.choice(lines)
    if not origin:
        origin = rng.choice([s for s in line if s != destination])
        row["시발역명"] = origin
        filled.append("시발역명")
    if not destination:
        destination = rng.choice([s for s in line if s != origin])
        row["종착역명"] = destination
        filled.append("종착역명")
    if not row["발생장소명"].strip():
        row["발생장소명"] = rng.choice(line)
        filled.append("발생장소명")
    if not row["열차차량수"].strip():
        row["열차차량수"] = str(rng.choice(VEHICLE_COUNTS))
        filled.append("열차차량수")
    if not row["차량도입일자"].strip():
        try:
            latest = date.fromisoformat(row["고장발생일자"].strip()) - timedelta(days=365)
        except ValueError:
            latest = date(2012, 12, 31)
        start = date(1995, 1, 1)
        row["차량도입일자"] = (start + timedelta(days=rng.randrange(max((latest - start).days, 1)))).isoformat()
        filled.append("차량도입일자")
    if "정비단" in row and row.get("조치구분", "").strip() != "기록된 조치 (원문 발췌)":
        place = row["발생장소명"].strip()
        row["정비단"] = next((team for team, places in REGION_TEAMS.items() if place in places), TEAM_SUDOGWON)
        filled.append("정비단")
    row[FILL_COLUMN] = ",".join(filled)
    return row


def main():
    parser = argparse.ArgumentParser(description="빈 칸을 가상 값으로 채운 시연용 CSV 만들기")
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    if args.target.resolve() == args.source.resolve():
        raise SystemExit("원본을 덮어쓸 수 없습니다. 다른 파일 이름을 지정해 주세요.")
    if args.target.exists():
        raise SystemExit(f"이미 있는 파일입니다: {args.target}")
    with open(args.source, encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fields = list(reader.fieldnames) + [FILL_COLUMN]
        rows = [fill_row(row, random.Random(zlib.crc32(row["FRACAS관리번호"].encode("utf-8")))) for row in reader]
    with open(args.target, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)}건 저장: {args.target} (가상으로 채운 행 {sum(1 for r in rows if r[FILL_COLUMN])}건)")


if __name__ == "__main__":
    main()
