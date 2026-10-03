#!/usr/bin/env bash
set -e

# ==============================================================================
# オンライン環境用: オフライン配信用パッケージ作成スクリプト
# ==============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="${PROJECT_ROOT}/offline_dist"
IMAGE_TAG="keroppupu/ruri-rag-server:latest"

echo "=== [1/4] Dockerイメージのビルド (Ruriモデルを同梱) ==="
cd "${PROJECT_ROOT}"
docker build --build-arg PRELOAD_MODELS=true -t "${IMAGE_TAG}" .

echo "=== [2/4] 配信用フォルダの準備 (${PACKAGE_DIR}) ==="
rm -rf "${PACKAGE_DIR}"
mkdir -p "${PACKAGE_DIR}"

echo "=== [3/4] Dockerイメージを tar ファイルとしてエクスポート ==="
docker save -o "${PACKAGE_DIR}/ruri-rag-server.tar" "${IMAGE_TAG}"

echo "=== [4/4] 起動用ファイル・スクリプトのコピー ==="
cp "${PROJECT_ROOT}/docker-compose.offline.yml" "${PACKAGE_DIR}/docker-compose.yml"
cp "${PROJECT_ROOT}/scripts/run_offline.sh" "${PACKAGE_DIR}/start.sh"
chmod +x "${PACKAGE_DIR}/start.sh"

echo "======================================================================"
echo " [完了] オフライン配布パッケージが作成されました！"
echo " 保存先: ${PACKAGE_DIR}"
echo ""
echo " この 'offline_dist' フォルダ全体を USB メモリ等でオフライン環境へ持ち込み、"
echo " オフライン環境側で './start.sh' を実行するだけで即座に起動できます。"
echo "======================================================================"
