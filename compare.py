"""세 검색어를 키워드 / 하이브리드로 검색해 상위 5건을 터미널에만 출력합니다(파일 저장 없음).

    .venv\\Scripts\\python.exe compare.py --csv "C:\\Users\\user\\Downloads\\FRACAS_20220830_utf8.csv"
"""

import argparse
from pathlib import Path

from app import SearchService
from keyword_search import load_cases
from semantic import DEFAULT_MODEL_DIR, MODEL_NAME

QUERIES = ("출입문이 안 닫혀요", "객실이 너무 더워요", "열차가 제때 멈추지 않아요")


def main():
    parser = argparse.ArgumentParser(description="키워드와 하이브리드 검색 비교")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--width", type=int, default=120, help="원문을 출력할 최대 글자 수")
    args = parser.parse_args()

    service = SearchService(load_cases(args.csv))
    service.start_ai(args.model_dir)
    if not service.ai_ready:
        raise SystemExit(service.ai_status)
    print(f"실제 모델: {MODEL_NAME} / 사례 {len(service.cases)}건\n")
    for query in QUERIES:
        for mode in ("keyword", "hybrid"):
            results, used = service.search(query, mode)
            print(f"=== {query} | {used} ===")
            for rank, case in enumerate(results, start=1):
                text = " ".join(case.description.split())[:args.width]
                print(f"{rank}. {case.case_id} {case.date} {case.clock} | {text}")
            print()


if __name__ == "__main__":
    main()
