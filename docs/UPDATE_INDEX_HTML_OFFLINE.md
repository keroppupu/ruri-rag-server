# オフライン環境のDockerコンテナ内 `index.html` 差し替え手順

閉塞環境（オフライン環境）ですでに起動している `ruri-rag-server` Dockerコンテナに対して、イメージ全体を再ビルド・再転送することなく、修正版の `index.html` のみを差し替える手順です。

---

## 📋 概要・前提条件

- **対象コンテナ名**: `ruri-rag-server`
- **コンテナ内配置先パス**: `/app/app/static/index.html`
- **必要な持ち込みファイル**: 
  - 本リポジトリの修正済み [`app/static/index.html`](app/static/index.html) 単体（約42KB）

---

## 🛠️ 差し替え手順（3ステップ）

### ステップ 1: 修正版 `index.html` の持ち込み
USBメモリやファイル転送ツール等で、修正済みの `index.html` をオフラインサーバー上の任意の作業ディレクトリ（例: `~/` や `offline_dist/`）に配置します。

```bash
# 配置確認
ls -l index.html
```

---

### ステップ 2: `docker cp` コマンドでコンテナ内に上書きコピー
Dockerが起動している状態で、以下のコマンドを実行してコンテナ内のファイルを直接差し替えます。

```bash
# コンテナ内の静的ファイルディレクトリへ上書き
docker cp index.html ruri-rag-server:/app/app/static/index.html
```

> **確認コマンド**:
> ```bash
> # コンテナ内のファイル更新日時またはMD5ハッシュを確認
> docker exec -it ruri-rag-server ls -l /app/app/static/index.html
> ```

---

### ステップ 3: ブラウザのキャッシュクリア（重要）
FastAPIは静的ファイルをリロードなしで即座に配信しますが、**ブラウザ側に旧バージョンの JavaScript/HTML がキャッシュされている**場合があります。

1. ブラウザで Web UI（`http://<サーバーIP>:8000`）を開きます。
2. 強制再読み込み（ハードリフレッシュ）を実行してください：
   - **Windows / Linux**: `Ctrl` + `F5` または `Ctrl` + `Shift` + `R`
   - **Mac**: `Cmd` + `Shift` + `R`

これで、Web UIからのドラッグ＆ドロップおよびクリックによるファイルアップロードが正常に動作するようになります。

---

## 💡 （参考）コンテナ再起動時も永続化させたい場合
将来的にコンテナを破棄・再作成（`docker compose down` → `up` など）した際にも差し替え状態を維持したい場合は、`docker-compose.yml` にボリュームマウントを1行追加しておくと安全です。

```yaml
services:
  ruri-rag-server:
    ...
    volumes:
      - chroma_data:/app/data/chroma
      # ホスト側の index.html を直接コンテナへマウント
      - ./index.html:/app/app/static/index.html:ro
```
