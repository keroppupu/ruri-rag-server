# Dockerコンテナ内差分ファイル上書きによる高速バージョンアップ手順

閉塞環境（オフライン環境）やすでに稼働中の `ruri-rag-server` Dockerコンテナに対して、数GBあるDockerイメージ全体を再ビルド・再転送することなく、**変更された差分ファイル（合計100KB以下）のみを `docker cp` で上書きコピーして即座にバージョンアップする手順**です。

---

## 📋 概要・前提条件

- **対象コンテナ名**: `ruri-rag-server`
- **所要時間**: 約10秒（コンテナ再起動の数秒のみ）
- **メリット**:
  - 数GBにおよぶDockerイメージの再ビルド・再配布が一切不要
  - 既存のベクトルDB（ChromaDB）や事前ダウンロード済みAIモデル（Ruri、EmbeddingGemma-2、Ruri Reranker）は一切消去されず完全に引き継がれます
- **必要な差分ファイル**:
  1. [`app/main.py`](../app/main.py): バックエンドAPI、質問添付ファイルの自動展開・比較プロンプト生成、`/rag_with_file`、HTTP/SSE MCP
  2. [`app/static/index.html`](../app/static/index.html): Web UI（質問入力欄の「📎 添付」ボタン、添付ファイルピル表示、Base64送信）
  3. [`mcp_server.py`](../mcp_server.py): GitLab Duo / VS Code / OpenClaw 向け Stdio MCPサーバー（添付引数対応）

---

## 🛠️ バージョンアップ手順（3ステップ）

### ステップ 1: 差分ファイルを作業ディレクトリに準備
本リポジトリの最新の3ファイル（`app/main.py`, `app/static/index.html`, `mcp_server.py`）をサーバー上に配置します。

```bash
# 配置確認
ls -l app/main.py app/static/index.html mcp_server.py
```

---

### ステップ 2: `docker cp` でコンテナ内へ上書きコピー
コンテナが起動した状態のまま、以下のコマンドを実行して差分ファイルをコンテナ内の該当パスへ上書きします。

```bash
# 1. バックエンド API と MCP HTTP/SSE の更新
docker cp app/main.py ruri-rag-server:/app/app/main.py

# 2. Web UI（ファイル添付ボタン対応）の更新
docker cp app/static/index.html ruri-rag-server:/app/app/static/index.html

# 3. Stdio MCP サーバーの更新
docker cp mcp_server.py ruri-rag-server:/app/mcp_server.py
```

> **確認コマンド**:
> ```bash
> # コンテナ内の更新日時を確認
> docker exec -it ruri-rag-server ls -l /app/app/main.py /app/app/static/index.html /app/mcp_server.py
> ```

---

### ステップ 3: コンテナの再起動とブラウザのキャッシュクリア

1. **コンテナを再起動**して新しい Python コードを反映させます：
   ```bash
   docker restart ruri-rag-server
   ```
   ※ 約3〜5秒でヘルスチェックが通り起動完了します。

2. **ヘルスチェックの確認**:
   ```bash
   curl http://localhost:8000/health
   ```
   `"status": "healthy"` が返ってくれば稼働成功です。

3. **ブラウザ側の強制再読み込み（重要）**:
   Web UIを開く際は、旧バージョンのキャッシュを破棄するためブラウザで**ハードリフレッシュ**を実行してください：
   - **Windows / Linux**: `Ctrl` + `F5` または `Ctrl` + `Shift` + `R`
   - **Mac**: `Cmd` + `Shift` + `R`

---

## 💡 コンテナ破棄時（`docker compose down`）の永続化対策

`docker cp` によるコンテナ内ファイル書き換えは、コンテナを破棄（`docker compose down`）して再作成するとイメージ初期状態に戻ります。  
将来コンテナを再作成した際にも常に最新の差分状態を維持したい場合は、以下のいずれかの方法を実施してください。

### 方法 A: 現在のコンテナ状態を新イメージとして保存（推奨・簡単）
```bash
docker commit ruri-rag-server ruri-rag-server:v3.1
```
※ 今後は `ruri-rag-server:v3.1` をベースイメージとして利用できます。

### 方法 B: `docker-compose.yml` にボリュームマウントを追加
差分ファイルをホスト側のファイルから直接マウントするように記述します：

```yaml
services:
  ruri-rag-server:
    # ...
    volumes:
      - ./data:/app/data
      - ./cache:/app/cache
      - ./models:/app/models
      # 差分コードのマウント
      - ./app/main.py:/app/app/main.py
      - ./app/static/index.html:/app/app/static/index.html
      - ./mcp_server.py:/app/mcp_server.py
```
