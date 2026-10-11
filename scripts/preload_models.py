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
    }

    models_dir = Path("/app/models")
    models_dir.mkdir(parents=True, exist_ok=True)

    log(f"モデルを {models_dir} にプリロード中...")

    try:
        # Ruri Embedding モデル
        base_dest = models_dir / "ruri-base"
        log("Downloading cl-nagoya/ruri-base...")
        snapshot_download(
            repo_id="cl-nagoya/ruri-base",
            local_dir=str(base_dest),
            local_dir_use_symlinks=False,
            local_files_only=False,
            resume_download=True
        )
        log("✅ ruri-base をプリロードしました")

        # Ruri Reranker モデル
        rerank_dest = models_dir / "ruri-reranker-large"
        log("Downloading cl-nagoya/ruri-reranker-large...")
        snapshot_download(
            repo_id="cl-nagoya/ruri-reranker-large",
            local_dir=str(rerank_dest),
            local_dir_use_symlinks=False,
            local_files_only=False,
            resume_download=True
        )
        log("✅ ruri-reranker-large をプリロードしました")

        log("モデルプリロードが完了しました")
        return 0

    except Exception as e:
        log(f"❌ モデルダウンロードに失敗しました: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())