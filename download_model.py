"""공개 사전학습 모델 파일만 내려받습니다. CSV나 검색어는 보내지 않습니다.

    .venv\\Scripts\\python.exe download_model.py          # 내려받기(끊기면 다시 실행하면 이어받음)
    .venv\\Scripts\\python.exe download_model.py --check  # 파일 완전성만 검사
"""

import argparse
import sys
from pathlib import Path

from semantic import DEFAULT_MODEL_DIR, MODEL_NAME, REQUIRED_FILES, check_model_dir


def download(destination, attempts=5):
    from huggingface_hub import HfApi, snapshot_download

    for attempt in range(1, attempts + 1):
        try:
            snapshot_download(MODEL_NAME, local_dir=str(destination), allow_patterns=list(REQUIRED_FILES)
                              + ["config_sentence_transformers.json"])
            break
        except Exception as error:
            print(f"[{attempt}/{attempts}] 다운로드 실패: {error}", file=sys.stderr)
            if attempt == attempts:
                raise
    info = HfApi().model_info(MODEL_NAME, files_metadata=True)
    for sibling in info.siblings:
        local = destination / sibling.rfilename
        if sibling.rfilename in REQUIRED_FILES and sibling.size and local.stat().st_size != sibling.size:
            raise RuntimeError(f"{sibling.rfilename} 크기가 다릅니다: {local.stat().st_size} / {sibling.size} 바이트")


def main():
    parser = argparse.ArgumentParser(description=f"{MODEL_NAME} 모델 다운로드")
    parser.add_argument("--dest", default=DEFAULT_MODEL_DIR, type=Path)
    parser.add_argument("--check", action="store_true", help="다운로드 없이 파일만 검사")
    args = parser.parse_args()
    if not args.check:
        download(args.dest)
    problems = check_model_dir(args.dest)
    if problems:
        print("모델 파일 문제: " + ", ".join(problems), file=sys.stderr)
        sys.exit(1)
    print(f"모델 파일 확인 완료: {args.dest}")


if __name__ == "__main__":
    main()
