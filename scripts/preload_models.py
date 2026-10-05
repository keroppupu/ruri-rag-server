"""
ビルド時モデル事前ダウンロードスクリプト。
Dockerfileの RUN python scripts/preload_models.py から呼ばれる。
"""
import sys

from sentence_transformers import SentenceTransformer, CrossEncoder

print("Pre-downloading Ruri text embedding (cl-nagoya/ruri-base)...")
SentenceTransformer("cl-nagoya/ruri-base")
print("  -> Done.")

print("Pre-downloading Ruri reranker (cl-nagoya/ruri-reranker-large)...")
CrossEncoder("cl-nagoya/ruri-reranker-large")
print("  -> Done.")

print("Pre-downloading jina-clip-v1 (multimodal)...")
try:
    SentenceTransformer("jinaai/jina-clip-v1", trust_remote_code=True)
    print("  -> Done.")
except Exception as e:
    print(f"  -> WARNING: jina-clip-v1 preload failed (will download at runtime): {e}", file=sys.stderr)

print("Pre-download complete!")
