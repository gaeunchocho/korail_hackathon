"""AI 의미 검색(문장 임베딩)과 하이브리드 순위 결합."""

from pathlib import Path

MODEL_NAME = "intfloat/multilingual-e5-small"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent / ".models" / "multilingual-e5-small"
# sentence-transformers가 모델을 읽는 데 필요한 파일
REQUIRED_FILES = (
    "config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
    "special_tokens_map.json", "sentencepiece.bpe.model", "modules.json",
    "sentence_bert_config.json", "1_Pooling/config.json",
)
RRF_K = 60
RRF_DEPTH = 100


def check_model_dir(model_dir):
    """모델 폴더에서 빠졌거나 비어 있는 파일 목록을 돌려줍니다. 빈 목록이면 완전합니다."""
    model_dir = Path(model_dir)
    if not model_dir.is_dir():
        return [f"폴더 없음: {model_dir}"]
    problems = [name for name in REQUIRED_FILES
                if not (model_dir / name).is_file() or (model_dir / name).stat().st_size == 0]
    weights = model_dir / "model.safetensors"
    if weights.is_file() and weights.stat().st_size > 0:
        try:
            from safetensors import safe_open
            with safe_open(str(weights), framework="numpy") as handle:
                handle.keys()
        except ImportError:
            pass
        except Exception as error:  # 다운로드가 중간에 끊긴 파일
            problems.append(f"model.safetensors 손상 ({error})")
    return problems


class SemanticIndex:
    """서버 시작 시 사례 임베딩을 한 번 만들어 메모리에만 보관합니다."""

    def __init__(self, cases, model, batch_size=32, show_progress=True):
        import numpy as np

        self.model = model
        texts = list(dict.fromkeys(case.description for case in cases))  # 같은 원문은 한 번만 계산
        position = {text: index for index, text in enumerate(texts)}
        vectors = model.encode(
            ["passage: " + text for text in texts],
            batch_size=batch_size, normalize_embeddings=True, show_progress_bar=show_progress,
        )
        self.vectors = np.asarray(vectors, dtype="float32")[[position[case.description] for case in cases]]

    def scores(self, query):
        vector = self.model.encode(["query: " + query], normalize_embeddings=True)[0]
        return self.vectors @ vector  # 정규화된 벡터의 내적 = 코사인 유사도

    def rank(self, query):
        scores = self.scores(query)
        return sorted(range(len(scores)), key=lambda index: (-scores[index], index))


def load_model(model_dir):
    """로컬 파일만으로 모델을 읽습니다. 인터넷 접속을 시도하지 않습니다."""
    import os

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    problems = check_model_dir(model_dir)
    if problems:
        raise RuntimeError("모델 파일이 완전하지 않습니다: " + ", ".join(problems)
                           + " — 'python download_model.py'를 다시 실행해 주세요.")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise RuntimeError(f"AI 패키지가 설치되지 않았습니다 ({error}). README의 설치 단계를 확인해 주세요.") from None
    return SentenceTransformer(str(model_dir), device="cpu", local_files_only=True)


def combine_ranks(keyword_ranking, semantic_ranking, k=RRF_K, depth=RRF_DEPTH):
    """RRF(Reciprocal Rank Fusion): 각 방식 상위 depth위 안의 순위를 1/(k+순위)로 바꿔 더합니다."""
    scores = {}
    for ranking in (keyword_ranking, semantic_ranking):
        for rank, index in enumerate(ranking[:depth], start=1):
            scores[index] = scores.get(index, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda index: (-scores[index], index))
