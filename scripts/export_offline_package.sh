#!/usr/bin/env bash
set -e

# ==============================================================================
# オンライン環境用: オフライン配信用パッケージ作成スクリプト
# ==============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="${PROJECT_ROOT}/offline_dist"
IMAGE_TAG="keroppupu/ruri-rag-server:latest"

echo "=== [1/4] Dockerイメージのビルド (RHEL/Linux x86_64用: --platform linux/amd64, モデル事前同梱) ==="
cd "${PROJECT_ROOT}"
docker build --platform linux/amd64 --build-arg PRELOAD_MODELS=true -t "${IMAGE_TAG}" .

echo "=== [2/4] 配信用フォルダの準備 (${PACKAGE_DIR}) ==="
rm -rf "${PACKAGE_DIR}"
mkdir -p "${PACKAGE_DIR}"

echo "=== [3/4] Dockerイメージを tar.gz としてエクスポート・圧縮 ==="
docker save "${IMAGE_TAG}" | gzip > "${PACKAGE_DIR}/ruri-rag-server.tar.gz"

echo "=== [4/4] 起動用ファイル・スクリプトのコピーおよび配布パッケージアーカイブ ==="
cp "${PROJECT_ROOT}/docker-compose.offline.yml" "${PACKAGE_DIR}/docker-compose.yml"
cp "${PROJECT_ROOT}/scripts/run_offline.sh" "${PACKAGE_DIR}/start.sh"
chmod +x "${PACKAGE_DIR}/start.sh"

echo "=== [追加] 配布用フォルダ全体を tar.gz でアーカイブ ==="
tar -czf "${PROJECT_ROOT}/offline_dist.tar.gz" -C "${PROJECT_ROOT}" offline_dist

echo "======================================================================"
echo " [完了] RHEL (linux/amd64) 向けオフライン配布パッケージが作成されました！"
echo " フォルダ: ${PACKAGE_DIR}"
echo " 圧縮ファイル: ${PROJECT_ROOT}/offline_dist.tar.gz"
echo ""
echo " 'offline_dist.tar.gz' を RHEL サーバーへ転送して展開 (tar -xzf offline_dist.tar.gz) し、"
echo " 'cd offline_dist && ./start.sh' を実行するだけで即座に起動できます。"
echo "======================================================================"
