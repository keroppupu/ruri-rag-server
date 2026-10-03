FROM python:3.11-slim

# 作業ディレクトリの設定
WORKDIR /app

# 必要なOSパッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 依存パッケージのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
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
    PORT=8000

# オフライン完全対応: ビルド時にRuriモデルをイメージ内キャッシュに事前ダウンロード
# （イメージ作成後に完全オフライン・エアギャップ環境に持ち込んでも即座に動作可能）
ARG PRELOAD_MODELS=true
RUN if [ "$PRELOAD_MODELS" = "true" ] ; then \
    python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
print('Pre-downloading Ruri models for offline use...'); \
SentenceTransformer('cl-nagoya/ruri-base'); \
CrossEncoder('cl-nagoya/ruri-reranker-large'); \
print('Pre-download complete!')" ; \
    fi

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# ポートの公開
EXPOSE 8000

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# サーバー起動
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
