#!/usr/bin/env python3
"""
モデルを事前にダウンロードしてキャッシュするスクリプト
オフライン環境での動作を確保します。
"""

import os
import sys
from pathlib import Path
from huggingface_hub import snapshot_download, login as hf_login
from transformers import AutoModel, AutoTokenizer
from sentence_transformers import SentenceTransformer
import torch

CHROMA_DIR = os.getenv("CHROMA_DIR", "/app/data/chroma")
HF_HOME = os.getenv("HF_HOME", "/app/cache/huggingface")
PRELOAD_MODELS = os.getenv("PRELOAD_MODELS", "true")

def log(msg: str):
    print(f"[preload] {msg}", file=sys.stderr)
    sys.stderr.flush()

class OfflineError(Exception):
    pass

def main():
    if PRELOAD_MODELS != "true":
        log("モデルプリロードがスキップされました (PRELOAD_MODELS=false)")
        return 0

    os.makedirs(HF_HOME, exist_ok=True)
    
    models = {
        "ruri-base": "cl-nagoya/ruri-base",
        "ruri-reranker-large": "cl-nagoya/ruri-reranker-large",
        "jina-clip-v1": "jinaai/jina-clip-v1",
    }

    log(f"モデルを {HF_HOME} にプリロード中...")

    try:
        # Ruri モデル群
        for name, repo_id in models.items():
            if repo_id.startswith("cl-nagoya/"):
                path = Path(HF_HOME) / repo_id.replace("/", "/")
                snapshot_download(
                    repo_id=repo_id,
                    cache_dir=str(path),
                    local_files_only=False,  # ネットワーク接続がある場合はダウンロード
                    resume_download=True
                )
                log(f"✅ {name} をプリロードしました")

        log("モデルプリロードが完了しました")
        return 0

    except Exception as e:
        # オフライン環境の場合、エラーを許容する
        log(f"❌ モデルダウンロードに失敗しました: {e}")
        log("オフラインモードのため、モデルなしで起動します。")
        sys.exit(0)

if __name__ == "__main__":
    exit(main())