FROM python:3.11-slim

# 作業ディレクトリの設定
WORKDIR /app

# 必要なOSパッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 依存パッケージのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# アプリケーションコードとMCPサーバーのコピー
COPY app /app/app
COPY mcp_server.py /app/mcp_server.py

# データ永続化およびHuggingFaceキャッシュディレクトリの作成
RUN mkdir -p /app/data/chroma /app/cache/huggingface

# 環境変数の設定
ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/app/cache/huggingface \
    CHROMA_DIR=/app/data/chroma \
    RURI_EMBED_MODEL=cl-nagoya/ruri-base \
    RURI_RERANK_MODEL=cl-nagoya/ruri-reranker-large \
    MM_EMBED_MODEL=jinaai/jina-clip-v1 \
    LOAD_MM_MODEL=true \
    PORT=8000

# オフライン完全対応: ビルド時にモデルをイメージ内キャッシュに事前ダウンロード
ARG PRELOAD_MODELS=true
RUN if [ "$PRELOAD_MODELS" = "true" ] ; then \
    python -c "\
import sys; \
from sentence_transformers import SentenceTransformer, CrossEncoder; \
print('Pre-downloading Ruri text embedding...'); \
SentenceTransformer('cl-nagoya/ruri-base'); \
print('Pre-downloading Ruri reranker...'); \
CrossEncoder('cl-nagoya/ruri-reranker-large'); \
print('Ruri models downloaded successfully!'); \
print('Pre-downloading jina-clip-v1 (multimodal)...'); \
try: \n\
    SentenceTransformer('jinaai/jina-clip-v1', trust_remote_code=True); \
    print('jina-clip-v1 downloaded successfully!') \n\
except Exception as e: \n\
    print(f'WARNING: jina-clip-v1 preload failed (will download at runtime): {e}', file=sys.stderr) \n\
print('Pre-download complete!')" ; \
    fi

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# ポートの公開
EXPOSE 8000

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# サーバー起動
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
