"""음성 받아쓰기(faster-whisper)와 현장 고장 기록 저장. 모두 이 PC 안에서만 처리합니다."""

import csv
import io
import sys
import threading
from datetime import datetime
from pathlib import Path

from classify import classify

WHISPER_MODEL = "Systran/faster-whisper-small"
DEFAULT_WHISPER_DIR = Path(__file__).resolve().parent / ".models" / "faster-whisper-small"
DEFAULT_RECORDS_PATH = Path.home() / "Downloads" / "현장고장기록.csv"
# 정비 용어를 더 잘 알아듣도록 주는 힌트 문장 (받아쓰기 결과에는 들어가지 않습니다)
PROMPT = "열차 고장 증상: 출입문 닫힘 불량, BC압 상승 불량, 완해불량, 역행불량, SIV 정지, MCB 차단, ATP 고장, 비상제동 체결, 냉방 불량."
RECORD_FIELDS = ("기록번호", "저장일시", "발생일시", "발생장소", "차량번호", "고장증상", "장치분류", "조치내용", "참고사례")


def decode_audio(data, rate=16000):
    """브라우저 녹음(webm 등)이나 wav를 16kHz 모노 float32 배열로 바꿉니다(메모리에서만 처리)."""
    import av
    import numpy as np

    chunks = []
    with av.open(io.BytesIO(data), mode="r") as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        for frame in container.decode(container.streams.audio[0]):
            chunks.extend(part.to_ndarray() for part in resampler.resample(frame))
        chunks.extend(part.to_ndarray() for part in resampler.resample(None))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks, axis=1).reshape(-1).astype(np.float32) / 32768.0


class Transcriber:
    def __init__(self, decoder=decode_audio):
        self.decode = decoder
        self.model = None
        self.state = "off"  # off / loading / ready / error
        self.status = "음성 입력을 켜지 않았습니다."
        self.lock = threading.Lock()

    def start(self, model_dir, model_loader=None):
        self.state, self.status = "loading", "음성 인식 모델을 준비하고 있습니다."
        try:
            if model_loader is None:
                if not (Path(model_dir) / "model.bin").is_file():
                    raise RuntimeError(f"음성 모델 파일이 없습니다: {model_dir}")
                from faster_whisper import WhisperModel

                def model_loader(path):
                    return WhisperModel(str(path), device="cpu", compute_type="int8")
            self.model = model_loader(model_dir)
        except Exception as error:
            self.state, self.status = "error", f"음성 입력을 쓸 수 없습니다: {error}"
            print(f"[음성] 로드 실패: {error}", file=sys.stderr, flush=True)
            return
        self.state, self.status = "ready", "음성 입력 사용 가능"
        print("[음성] 준비 완료", flush=True)

    def transcribe(self, audio_bytes):
        """녹음 데이터(webm, wav 등)를 한국어 글자로 바꿉니다. 녹음은 메모리에서만 쓰고 저장하지 않습니다."""
        if self.state != "ready":
            raise RuntimeError(self.status)
        with self.lock:  # CPU 한 대에서 동시에 여러 건을 돌리지 않도록
            segments, _ = self.model.transcribe(self.decode(audio_bytes), language="ko", beam_size=5,
                                                vad_filter=True, initial_prompt=PROMPT)
            return " ".join(segment.text.strip() for segment in segments).strip()


class RecordStore:
    """지금 발생한 고장과 조치를 CSV 파일 한 개에 덧붙여 저장합니다(원본 CSV와 별도 파일)."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def _read(self):
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8-sig", newline="") as source:
            return list(csv.DictReader(source))

    def add(self, fields):
        """fields: {"occurred", "location", "vehicle", "symptom", "action", "reference"} (문자열)."""
        clean = {key: " ".join(str(fields.get(key, "")).split())[:limit]
                 for key, limit in (("occurred", 20), ("location", 50), ("vehicle", 50),
                                    ("symptom", 500), ("action", 1000), ("reference", 100))}
        if not clean["symptom"] or not clean["action"]:
            raise ValueError("고장 증상과 조치 내용을 모두 입력해 주세요.")
        now = datetime.now()
        with self.lock:
            rows = self._read()
            today = now.strftime("%Y%m%d")
            serial = 1 + sum(1 for row in rows if row.get("기록번호", "").startswith(today + "-"))
            row = {
                "기록번호": f"{today}-{serial:03d}",
                "저장일시": now.strftime("%Y-%m-%d %H:%M"),
                "발생일시": clean["occurred"] or now.strftime("%Y-%m-%d %H:%M"),
                "발생장소": clean["location"],
                "차량번호": clean["vehicle"],
                "고장증상": clean["symptom"],
                "장치분류": classify(clean["symptom"] + " " + clean["action"]),
                "조치내용": clean["action"],
                "참고사례": clean["reference"],
            }
            new_file = not self.path.exists()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=RECORD_FIELDS)
                if new_file:
                    writer.writeheader()
                writer.writerow(row)
        return row

    def recent(self, limit=5):
        with self.lock:
            return list(reversed(self._read()))[:limit]


# "장소 용산역, 차량 311-14, 증상 출입문 닫힘 불량, 조치 구동부 교체" 처럼 한 번에 말한 내용을 칸별로 나눕니다.
FIELD_MARKERS = (
    ("location", r"발생\s*장소|장소|위치"),
    ("vehicle", r"차량\s*번호|차량|편성"),
    ("symptom", r"고장\s*증상|증상"),
    ("action", r"조치\s*내용|조치"),
)


def split_dictation(text):
    """말머리(장소·차량·증상·조치)를 기준으로 나눕니다. 각 말머리는 처음 나온 것만 씁니다.
    말머리가 하나도 없으면 전체를 'unsplit'으로 돌려줍니다."""
    import re

    found = []
    for field, pattern in FIELD_MARKERS:
        match = re.search(rf"(?:^|[\s,.])({pattern})\s*(?:은|는|:)?\s*", text)
        if match:
            found.append((match.start(1), match.end(), field))
    found.sort()
    if not found:
        return {"unsplit": text.strip(" ,.")}
    fields = {}
    for position, (start, content_start, field) in enumerate(found):
        end = found[position + 1][0] if position + 1 < len(found) else len(text)
        value = re.sub(r"\s*(이고|이며|이구요|이었고)$", "", text[content_start:end].strip(" ,."))
        if value:
            fields[field] = value
    head = text[:found[0][0]].strip(" ,.")
    if head:
        fields["unsplit"] = head
    return fields
