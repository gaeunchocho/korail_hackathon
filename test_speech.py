"""음성 기능 모의 테스트. 실제 음성 모델을 쓰지 않습니다.

    python -m unittest -v test_speech
"""

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from app import SearchService, make_server
from speech import RecordStore, Transcriber, split_dictation


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeWhisper:
    def transcribe(self, audio, **options):
        assert options["language"] == "ko"
        return [FakeSegment(" 출입문 "), FakeSegment("닫힘 불량 ")], None


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.records_path = Path(self.folder.name) / "records.csv"

    def tearDown(self):
        self.folder.cleanup()

    def test_transcriber_joins_segments(self):
        transcriber = Transcriber(decoder=lambda data: data)
        transcriber.start("unused", model_loader=lambda _: FakeWhisper())
        self.assertEqual(transcriber.transcribe(b"audio"), "출입문 닫힘 불량")

    def test_missing_model_reports_reason(self):
        transcriber = Transcriber()
        transcriber.start(Path(self.folder.name) / "none")
        self.assertEqual(transcriber.state, "error")
        self.assertIn("음성 모델 파일이 없습니다", transcriber.status)
        with self.assertRaises(RuntimeError):
            transcriber.transcribe(b"audio")

    def test_record_store_saves_new_faults(self):
        store = RecordStore(self.records_path)
        first = store.add({"symptom": "  출입문   닫힘 불량 ", "action": "구동부 교체", "location": "용산"})
        store.add({"symptom": "냉방 불량", "action": "필터 청소", "occurred": "2026-11-25 14:00", "reference": "2015004432"})
        self.assertRegex(first["기록번호"], r"^\d{8}-001$")
        self.assertEqual(first["고장증상"], "출입문 닫힘 불량")
        recent = store.recent()
        self.assertEqual([r["고장증상"] for r in recent], ["냉방 불량", "출입문 닫힘 불량"])
        self.assertTrue(recent[0]["기록번호"].endswith("-002"))
        self.assertEqual((recent[0]["발생일시"], recent[0]["참고사례"]), ("2026-11-25 14:00", "2015004432"))
        with self.assertRaisesRegex(ValueError, "조치 내용"):
            store.add({"symptom": "출입문", "action": "  "})

    def test_split_dictation(self):
        self.assertEqual(split_dictation("장소 용산역, 차량 311-14, 증상 출입문 닫힘 불량, 조치 구동부 교체 후 정상 확인."),
                         {"location": "용산역", "vehicle": "311-14", "symptom": "출입문 닫힘 불량",
                          "action": "구동부 교체 후 정상 확인"})
        self.assertEqual(split_dictation("증상은 BC압 상승 불량이고 조치는 센서 교체"),
                         {"symptom": "BC압 상승 불량", "action": "센서 교체"})
        self.assertEqual(split_dictation("출입문 닫힘 불량 구동부 교체"), {"unsplit": "출입문 닫힘 불량 구동부 교체"})

    def test_http_endpoints(self):
        transcriber = Transcriber(decoder=lambda data: data)
        transcriber.start("unused", model_loader=lambda _: FakeWhisper())
        server = make_server(SearchService(csv_error="없음"), 0, transcriber, RecordStore(self.records_path))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            def post(path, data, kind="application/json"):
                request = urllib.request.Request(base + path, data=data, headers={"Content-Type": kind})
                return json.loads(urllib.request.urlopen(request).read())

            self.assertEqual(post("/api/transcribe", b"webm", "audio/webm")["text"], "출입문 닫힘 불량")
            body = json.dumps({"symptom": "SIV 정지", "action": "리셋 후 정상"}).encode()
            self.assertEqual(post("/api/records", body)["record"]["조치내용"], "리셋 후 정상")
            self.assertIn("error", post("/api/records", json.dumps({"symptom": "SIV 정지"}).encode()))
            listed = json.loads(urllib.request.urlopen(base + "/api/records").read())
            self.assertEqual(len(listed["records"]), 1)
            status = json.loads(urllib.request.urlopen(base + "/api/status").read())
            self.assertEqual((status["voice_state"], status["records_enabled"]), ("ready", True))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
