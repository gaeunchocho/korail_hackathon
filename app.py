import argparse
import csv
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, time
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def features(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    words = re.findall(r"[^\W_]+", normalized)
    counts = Counter(("글자", word[i:i + 2]) for word in words for i in range(len(word) - 1))
    counts.update(("단어", word) for word in words)
    return counts


@dataclass(frozen=True)
class Case:
    case_id: str
    occurred: str
    location: str
    description: str
    origin: str
    destination: str
    vehicle_count: str
    introduced_on: str


class CaseSearch:
    def __init__(self, path):
        self.cases = []
        documents = []
        seen = set()
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            columns = (
                "FRACAS관리번호", "고장발생일자", "고장발생시각", "발생장소명", "운행장애개요내용",
                "시발역명", "종착역명", "열차차량수", "차량도입일자",
            )
            if not set(columns).issubset(reader.fieldnames or ()):
                raise ValueError("CSV에 필요한 열이 없습니다.")
            for row in reader:
                try:
                    case_id, day, clock, location, description = (row[key] for key in columns[:5])
                    case_id = case_id.strip()
                    day = date.fromisoformat(day.strip()).isoformat()
                    clock = time.fromisoformat(clock.strip()).isoformat(timespec="minutes")
                    terms = features(description)
                    if not case_id or case_id in seen or not terms:
                        raise ValueError
                except (AttributeError, ValueError):
                    raise ValueError(f"CSV {reader.line_num}행의 관리번호, 발생 일시, 설명을 확인해 주세요.") from None
                seen.add(case_id)
                self.cases.append(Case(
                    case_id, f"{day} {clock}", (location or "").strip(), description,
                    origin=(row["시발역명"] or "").strip(),
                    destination=(row["종착역명"] or "").strip(),
                    vehicle_count=(row["열차차량수"] or "").strip(),
                    introduced_on=(row["차량도입일자"] or "").strip(),
                ))
                documents.append(terms)
        if not self.cases:
            raise ValueError("CSV에 검색할 사례가 없습니다.")

        frequencies = Counter(term for document in documents for term in document)
        self.weights = {
            term: 1 + math.log((1 + len(documents)) / (1 + frequency))
            for term, frequency in frequencies.items()
        }
        self.postings = defaultdict(list)
        for index, document in enumerate(documents):
            weights = {term: count * self.weights[term] for term, count in document.items()}
            norm = math.hypot(*weights.values())
            for term, weight in weights.items():
                self.postings[term].append((index, weight / norm))

    def search(self, query, limit=5):
        scores = defaultdict(float)
        for term, count in features(query).items():
            weight = count * self.weights.get(term, 0)
            for index, document_weight in self.postings.get(term, ()):
                scores[index] += weight * document_weight
        # For a fixed query, its norm is constant across results.
        ranked = sorted(scores, key=lambda index: (-scores[index], self.cases[index].case_id))
        return [self.cases[index] for index in ranked[:limit]]


def render(query="", results=()):
    if results:
        cards = "".join(
            f"""<li>
              <details>
                <summary>
                  <strong>관리번호 {escape(case.case_id)}</strong>
                  <span>발생 일시 <time datetime="{case.occurred}">{case.occurred}</time></span>
                  <span>발생 장소 {escape(case.location or "장소 미기록")}</span>
                </summary>
                <div class="description">
                  <dl class="metadata">
                    <div><dt>시발역</dt><dd>{escape(case.origin or "미기록")}</dd></div>
                    <div><dt>종착역</dt><dd>{escape(case.destination or "미기록")}</dd></div>
                    <div><dt>차량 수</dt><dd>{escape(case.vehicle_count + "량" if case.vehicle_count else "미기록")}</dd></div>
                    <div><dt>차량 도입일</dt><dd>{escape(case.introduced_on or "미기록")}</dd></div>
                  </dl>
                  <h3>운행장애 개요 원문</h3>
                  <p>{escape(case.description)}</p>
                </div>
              </details>
            </li>"""
            for case in results
        )
        content = f"""
        <section aria-labelledby="results">
          <h2 id="results">유사 사례 {len(results)}건</h2>
          <p>사례를 펼치면 당시 조치가 포함될 수 있는 운행장애 개요 원문을 볼 수 있습니다.</p>
          <ol>{cards}</ol>
        </section>"""
    elif query:
        content = '<p role="status">일치하는 사례가 없습니다. 다른 증상 표현으로 검색해 보세요.</p>'
    else:
        content = ""
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>열차 고장 유사 사례 검색</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f1f5fa; color: #18283b; font: 16px/1.55 system-ui, sans-serif; }}
    main {{ max-width: 760px; padding: 32px clamp(18px, 5vw, 48px); margin: clamp(20px, 8vw, 72px) auto;
            background: white; border: 1px solid #d5dfeb; border-radius: 16px; }}
    h1 {{ margin: 0 0 24px; font-size: clamp(24px, 5vw, 36px); }}
    label {{ font-weight: 700; }}
    .controls {{ display: flex; gap: 8px; margin-top: 6px; }}
    input, button {{ min-height: 46px; padding: 8px 12px; font: inherit; border-radius: 8px; }}
    input {{ flex: 1; min-width: 0; border: 1px solid #788aa1; }}
    button {{ border: 0; background: #174987; color: white; cursor: pointer; }}
    :focus-visible {{ outline: 3px solid #477bc0; outline-offset: 3px; }}
    section {{ margin-top: 28px; }}
    h2 {{ margin-bottom: 4px; font-size: 22px; }}
    section > p {{ margin-top: 0; color: #455a72; }}
    ol {{ list-style: none; padding: 0; }}
    li + li {{ margin-top: 10px; }}
    details {{ border: 1px solid #d5dfeb; border-radius: 10px; overflow-wrap: anywhere; }}
    summary {{ padding: 12px 16px; background: #eef4fb; border-radius: 10px; cursor: pointer; }}
    summary span {{ display: block; margin-left: 18px; color: #334c68; }}
    .description {{ padding: 0 16px 8px; }}
    .metadata {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px 16px; }}
    .metadata dt {{ font-weight: 700; }}
    .metadata dd {{ margin: 0; }}
    h3 {{ margin: 12px 0 6px; font-size: 16px; }}
    .description p {{ margin-top: 0; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <main>
    <h1>열차 고장 유사 사례 검색</h1>
    <form method="post" action="/">
      <label for="query">고장 증상</label>
      <div class="controls">
        <input id="query" name="query" value="{escape(query, quote=True)}" maxlength="300"
               placeholder="예시 · 정차 후 출입문이 닫히지 않음" required>
        <button type="submit">검색</button>
      </div>
    </form>
    {content}
  </main>
</body>
</html>"""


def make_server(search, port):
    class Handler(BaseHTTPRequestHandler):
        def page(self, html):
            payload = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if urlsplit(self.path).path == "/":
                self.page(render())
            else:
                self.send_error(404)

        def do_POST(self):
            if urlsplit(self.path).path != "/":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 8192:
                    raise ValueError
                body = self.rfile.read(length).decode("utf-8")
            except ValueError:
                self.send_error(400)
                return
            query = parse_qs(body).get("query", [""])[0].strip()[:300]
            self.page(render(query, search.search(query)))

        def log_message(self, format, *args):
            pass

    return HTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="열차 고장 유사 사례 로컬 검색")
    parser.add_argument("--csv", type=Path, required=True, help="원본 FRACAS CSV 파일 경로")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        server = make_server(CaseSearch(args.csv), args.port)
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    with server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
