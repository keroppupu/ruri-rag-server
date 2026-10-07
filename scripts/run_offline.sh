#!/usr/bin/env bash
set -e

# ==============================================================================
# オフライン（エアギャップ）環境用: ワンクリック起動スクリプト
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAR_FILE="${DIR}/ruri-rag-server.tar"
TARGZ_FILE="${DIR}/ruri-rag-server.tar.gz"

if [ -f "${TARGZ_FILE}" ]; then
  echo "=== [1/2] Dockerイメージ (tar.gz) をインポートしています... ==="
  docker load < "${TARGZ_FILE}"
elif [ -f "${TAR_FILE}" ]; then
  echo "=== [1/2] Dockerイメージ (tar) をインポートしています... ==="
  docker load -i "${TAR_FILE}"
else
  echo "※ tar / tar.gz ファイルが見つかりません。既存のイメージを使用して起動します。"
fi

echo "=== [2/2] コンテナをバックグラウンド起動しています... ==="
cd "${DIR}"
docker compose up -d

echo ""
echo "======================================================================"
echo " [起動完了] Ruri RAG サーバーがオフラインで稼働しました！"
echo " ブラウザでアクセス: http://localhost:8000"
echo " ログ確認: docker compose logs -f"
echo " 停止コマンド: docker compose down"
echo "======================================================================"
