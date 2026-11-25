"""열차 고장 유사 사례 검색 — 로컬 웹앱.

    python app.py --csv "C:\\Users\\user\\Downloads\\FRACAS_20220830_utf8.csv"
"""

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from classify import classify
from keyword_search import CsvError, KeywordIndex, load_cases
from speech import DEFAULT_RECORDS_PATH, DEFAULT_WHISPER_DIR, RecordStore, Transcriber, split_dictation
from semantic import DEFAULT_MODEL_DIR, MODEL_NAME, SemanticIndex, combine_ranks, load_model

RESULT_LIMIT = 5
MISSING = "미기록"
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 약 10MB (수 분 분량)
PAGE = Path(__file__).resolve().parent / "static" / "index.html"


class SearchService:
    """CSV 사례, 키워드 색인, (가능하면) AI 색인을 갖고 있습니다."""

    def __init__(self, cases=None, csv_error=None):
        self.cases = cases or []
        self.csv_error = csv_error
        self.keyword = KeywordIndex(self.cases) if self.cases else None
        self.semantic = None
        self.ai_state = "off"  # off / loading / ready / error
        self.ai_status = "AI 의미 검색을 켜지 않았습니다."

    @property
    def ai_ready(self):
        return self.ai_state == "ready"

    def start_ai(self, model_dir, model_loader=load_model, show_progress=True):
        """모델을 읽고 사례 임베딩을 만듭니다. 실패해도 키워드 검색은 계속 쓸 수 있습니다."""
        if not self.cases:
            self.ai_state, self.ai_status = "error", "CSV를 읽지 못해 AI 의미 검색을 준비하지 않았습니다."
            return
        self.ai_state, self.ai_status = "loading", "AI 모델을 준비하고 있습니다 (CPU에서 약 3~4분)."
        try:
            model = model_loader(model_dir)
            self.semantic = SemanticIndex(self.cases, model, show_progress=show_progress)
        except Exception as error:
            self.ai_state, self.ai_status = "error", f"AI 의미 검색을 쓸 수 없습니다: {error}"
            print(f"[AI] 로드 실패: {error}", file=sys.stderr, flush=True)
            return
        self.ai_state, self.ai_status = "ready", f"AI 의미 검색 사용 가능 ({MODEL_NAME}, 이 PC에서 실행)"
        print(f"[AI] 준비 완료: 사례 {len(self.cases)}건 임베딩", flush=True)

    def search(self, query, mode):
        """(사례 목록, 실제 사용한 방식)을 돌려줍니다. AI를 못 쓰면 키워드로 검색합니다."""
        ranking = self.keyword.rank(query)
        if mode == "hybrid" and self.ai_ready:
            ranking = combine_ranks(ranking, self.semantic.rank(query))
        else:
            mode = "keyword"
        return [self.cases[index] for index in ranking[:RESULT_LIMIT]], mode

    def status(self):
        return {
            "csv_error": self.csv_error,
            "case_count": len(self.cases),
            "ai_state": self.ai_state,
            "ai_status": self.ai_status,
            "has_actions": any(case.action_kind for case in self.cases),
        }

    def api_search(self, query):
        """화면에 보낼 검색 결과(JSON용 dict)를 만듭니다."""
        if self.csv_error:
            return {"error": self.csv_error}
        query = query.strip()[:300]
        if not query:
            return {"error": "고장 증상을 입력해 주세요."}
        # AI가 준비되어 있으면 자동으로 하이브리드, 아니면 키워드 검색
        results, used = self.search(query, "hybrid")
        return {
            "query": query,
            "mode": used,
            # 유사도로 고른 상위 5건을 최근 발생 순으로 보여줍니다(유사도 순위는 similarity_rank로 함께 보냄).
            "results": sorted(
                (dict(case_to_dict(case), similarity_rank=rank) for rank, case in enumerate(results, start=1)),
                key=lambda item: (item["occurred"] != MISSING, item["occurred"]), reverse=True),
            "highlight": self.keyword.highlight_terms(query),
            "delay_summary": delay_summary(results),
            "device": classify(query),
        }


def as_int(text):
    return int(text) if text.isdigit() else None


def delay_summary(cases):
    """유사 사례의 지연 시간(분) 요약. 지연 값이 기록된 사례만 셉니다."""
    delays = [d for d in (as_int(case.delay_minutes) for case in cases) if d is not None]
    if not delays:
        return None
    return {"count": len(delays), "average": round(sum(delays) / len(delays), 1), "max": max(delays),
            "delayed": sum(1 for d in delays if d > 0)}


def value(text):
    return text if text else MISSING


FILLED_KEYS = {"발생장소명": "location", "시발역명": "origin", "종착역명": "destination",
               "열차차량수": "vehicle_count", "차량도입일자": "introduced_on", "정비단": "team"}


def case_to_dict(case):
    """CSV 값을 그대로 옮기고 빈 값만 '미기록'으로 바꿉니다. 없는 정보는 만들지 않습니다."""
    occurred = " ".join(part for part in (case.date, case.clock) if part)
    action = None
    if case.action or case.action_kind:
        action = {
            "kind": value(case.action_kind),
            "team": value(case.team),
            "type": value(case.maintenance_type),
            "text": value(case.action),
            "is_demo": not case.action_kind.startswith("기록된 조치"),
        }
    return {
        "id": value(case.case_id),
        "occurred": value(occurred),
        "location": value(case.location),
        "origin": value(case.origin),
        "destination": value(case.destination),
        "vehicle_count": value(case.vehicle_count),
        "introduced_on": value(case.introduced_on),
        "description": case.description,
        "action": action,
        "device": classify(case.description),
        "delay_minutes": as_int(case.delay_minutes),
        "affected_trains": as_int(case.affected_trains),
        "filled": [FILLED_KEYS[name] for name in case.filled.split(",") if name in FILLED_KEYS],
    }


def make_server(service, port, transcriber=None, records=None):
    transcriber = transcriber or Transcriber()

    class Handler(BaseHTTPRequestHandler):
        def send(self, payload, content_type):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def send_json(self, data):
            self.send(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def read_body(self, limit):
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= limit:
                raise ValueError
            return self.rfile.read(length)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/":
                self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/status":
                status = service.status()
                status.update(voice_state=transcriber.state, voice_status=transcriber.status,
                              records_enabled=records is not None)
                self.send_json(status)
            elif url.path == "/api/records" and records is not None:
                self.send_json({"records": records.recent()})
            else:
                self.send_error(404)

        def do_POST(self):
            path = urlsplit(self.path).path
            try:
                if path == "/api/transcribe":
                    audio = self.read_body(MAX_AUDIO_BYTES)
                elif path in ("/api/search", "/api/records", "/api/split"):
                    body = json.loads(self.read_body(8192).decode("utf-8"))
                    if not isinstance(body, dict):
                        raise ValueError
                else:
                    self.send_error(404)
                    return
            except (ValueError, UnicodeDecodeError):
                self.send_error(400)
                return
            if path == "/api/search":
                self.send_json(service.api_search(str(body.get("query", ""))))
            elif path == "/api/transcribe":
                try:
                    text = transcriber.transcribe(audio)
                except Exception as error:
                    self.send_json({"error": f"음성을 글자로 바꾸지 못했습니다: {error}"})
                    return
                self.send_json({"text": text} if text else {"error": "알아들은 말이 없습니다. 다시 말해 주세요."})
            elif path == "/api/split":
                self.send_json({"fields": split_dictation(str(body.get("text", ""))[:2000])})
            elif records is None:
                self.send_json({"error": "현장 기록 저장을 켜지 않았습니다."})
            else:
                try:
                    row = records.add(body)
                except (ValueError, OSError) as error:
                    self.send_json({"error": f"기록을 저장하지 못했습니다: {error}"})
                    return
                self.send_json({"record": row})

        def log_message(self, format, *args):
            pass  # 검색어와 음성 내용을 로그에 남기지 않습니다.

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def build_service(csv_path):
    try:
        cases = load_cases(csv_path)
    except CsvError as error:
        print(f"[CSV] {error}", file=sys.stderr, flush=True)
        return SearchService(csv_error=str(error))
    print(f"[CSV] 사례 {len(cases)}건을 읽었습니다.", flush=True)
    return SearchService(cases)


def main():
    parser = argparse.ArgumentParser(description="열차 고장 유사 사례 로컬 검색")
    parser.add_argument("--csv", type=Path, required=True, help="원본 FRACAS CSV 경로 (읽기 전용)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR, help="로컬 모델 폴더")
    parser.add_argument("--no-ai", action="store_true", help="AI 의미 검색을 켜지 않고 키워드만 사용")
    parser.add_argument("--whisper-dir", type=Path, default=DEFAULT_WHISPER_DIR, help="음성 인식 모델 폴더")
    parser.add_argument("--no-voice", action="store_true", help="음성 입력을 켜지 않음")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS_PATH,
                        help="현장 고장 기록을 저장할 CSV (원본과 다른 파일)")
    args = parser.parse_args()
    if args.records.resolve() == args.csv.resolve():
        parser.exit(2, "기록 파일을 원본 CSV와 같은 경로로 지정할 수 없습니다.\n")

    service = build_service(args.csv)
    try:
        transcriber = Transcriber()
        server = make_server(service, args.port, transcriber, RecordStore(args.records))
    except OSError as error:
        parser.exit(2, f"포트 {args.port}를 열 수 없습니다: {error}. --port 8001 처럼 다른 번호를 써 보세요.\n")
    if not args.no_ai:
        # 모델 준비(수 분)를 기다리지 않고 키워드 검색부터 쓸 수 있도록 뒤에서 준비합니다.
        threading.Thread(target=service.start_ai, args=(args.model_dir,), daemon=True).start()
    if not args.no_voice:
        threading.Thread(target=transcriber.start, args=(args.whisper_dir,), daemon=True).start()
    print(f"[기록] 현장 고장 기록 파일: {args.records}", flush=True)
    with server:
        print(f"브라우저에서 여세요: http://127.0.0.1:{server.server_port}  (종료: Ctrl+C)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
