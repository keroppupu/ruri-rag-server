# Ruri マルチモーダル・ハイブリッド RAG サーバー (v3.0)

名古屋大学 CL研究室が開発した高性能日本語テキスト埋め込みモデル・リランカー **Ruri** と、Google の **EmbeddingGemma-2** マルチモーダルモデルを統合した、完全オフライン対応の Python / FastAPI 製 RAG サーバーです。

テキスト文書・Office資料・ソースコード（レガシー言語含む）・画像ファイルを自動判別してベクトル化し、Reciprocal Rank Fusion (RRF) と CrossEncoder リランキングによる極めて精度の高い検索を実現します。

ブラウザから直感的に操作できる **Webフロントエンド (Single Page App)**、用途別の **ナレッジチャネル機能**、**GitLab Duo (WebUI / VS Code) や OpenClaw 対応の Model Context Protocol (MCP)** を標準搭載しています。

---

## 🌟 主な機能と特徴

### 1. ハイブリッド Embedding & Rerank（テキスト＋マルチモーダル）
- **日本語テキスト Embedding**: `cl-nagoya/ruri-base`（検索クエリには `クエリ: `、ドキュメントには `文章: ` を自動付与）
- **画像・マルチモーダル Embedding**: `google/embeddinggemma-2`（図面、写真、スライド内埋め込み画像のセマンティックベクトル化）
- **高精度リランキング**: `cl-nagoya/ruri-reranker-large`（CrossEncoder により検索候補を日本語文脈で再スコアリング）
- **RRF (Reciprocal Rank Fusion)**: テキスト・画像それぞれの検索結果スコアを統合

### 2. 豊富なファイルフォーマット・ソースコード対応
- 📊 **Office 文書**:
  - **Excel**: `.xlsx`, `.xls`（シート・行ごとのテキスト抽出）
  - **Word**: `.docx`（段落・表組み抽出および埋め込み画像の自動抽出）
  - **PowerPoint**: `.pptx`（スライド単位のテキスト抽出および埋め込み画像抽出）
- 📄 **PDF**: `.pdf`（ページ単位のテキスト抽出およびページ内画像の自動抽出）
- 💻 **ソースコード & 設定ファイル**:
  - Python (`.py`, `.pyw`), JavaScript / TypeScript (`.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx`)
  - Go (`.go`), Java (`.java`, `.gradle`, `.kt`), C / C++ (`.c`, `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`)
  - C# (`.cs`), Rust (`.rs`), Ruby (`.rb`), PHP (`.php`), Shell (`.sh`, `.bash`, `.zsh`)
  - HTML (`.html`, `.htm`), CSS (`.css`, `.scss`), SQL (`.sql`), YAML (`.yaml`, `.yml`), JSON, XML
  - 設定・定義: `.env`, `.toml`, `.ini`, `.conf`, `Dockerfile`, `Makefile` 等
- 🏛️ **レガシー資産・業務言語**:
  - **Pro\*C**: `.pc`
  - **COBOL**: `.cbl`, `.cob`, `.cobol`, `.cpy`（Copybook）
  - **Pro\*COBOL**: `.pco`
  - エンコーディングフォールバック（UTF-8 $\rightarrow$ CP932 / Shift-JIS $\rightarrow$ UTF-8 ignore）により、レガシー文字コードも文字化けなくインデックス化
- 🖼️ **単体画像ファイル**:
  - `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.tiff`, `.webp`（マルチモーダルモデルによる画像ベクトル登録）

### 3. 多彩な LLM 連携（回答生成）
- **ローカル Ollama**: `qwen3.5:9b` 等のモデルと連携
- **LAN上 LiteLLM (OpenAI互換)**: `gpt-4o-mini`, `gpt-oss-120b` などのプライベートゲートウェイと連携
- Web UI の設定タブから API キー・エンドポイント URL・モデル名をワンクリックで即座に切り替え可能

### 4. 2種類の MCP (Model Context Protocol) インターフェース
- **HTTP / SSE トランスポート (`/sse`, `/messages`)**:
  - GitLab Duo セルフホスト版の Web UI（Duo Chat / Duo Workflow）から同一LAN経由で直接 `http://<IP>:8000/sse` に接続可能
  - CORS 全開放により、外部ホスト・ブラウザからの接続に対応
- **標準入出力 (stdio) トランスポート (`mcp_server.py`)**:
  - **OpenClaw**、VS Code (GitLab Duo 拡張)、Claude Desktop、Cursor 等から直接起動して利用可能

---

## 📂 ディレクトリ構成

```text
ruri-rag-server/
├── Dockerfile                  # マルチステージ・完全オフライン対応 Dockerfile
├── docker-compose.yml          # オンライン・開発環境用 Docker Compose
├── docker-compose.offline.yml  # オフライン配信用 Docker Compose
├── requirements.txt            # 依存パッケージ (sentence-transformers>=6.1.0, transformers>=5.0.0等)
├── mcp_server.py               # stdio 形式 MCP サーバー (OpenClaw / VS Code用)
├── README.md
├── docs/
│   └── UPDATE_INDEX_HTML_OFFLINE.md # オフライン環境での Web UI 差し替え手順書
├── scripts/
│   ├── export_offline_package.sh    # RHEL / Linux x86_64 用オフラインパッケージ作成
│   ├── preload_models.py            # ビルド時のモデル事前キャッシュスクリプト
│   └── run_offline.sh               # 配布パッケージ自動起動スクリプト
└── app/
    ├── main.py                 # FastAPI エンドポイント, SSE MCP, CORS
    ├── rag_engine.py           # Ruri + Gemma-2 + Reranker + ChromaDB エンジン
    ├── document_parser.py      # マルチフォーマット文書・コード・画像パーサー
    └── static/
        └── index.html          # Web フロントエンド SPA
```

---

## 🚀 起動方法

### A. 通常の起動（オンライン環境・開発用）

```bash
cd ruri-rag-server

# Docker コンテナをビルドして起動
docker compose up --build -d

# ログ確認
docker compose logs -f
```

起動後、ブラウザで **`http://localhost:8000`** にアクセスすると Web UI を利用できます。

---

### B. 完全オフライン環境（RHEL / 閉塞LAN）での起動

インターネットに接続されていないエアギャップ（閉塞）環境へは、GitHub Releases に配置されている事前ビルド済みパッケージを利用してデプロイできます。

1. **パッケージのダウンロード（GitHub Releases）**:
   - [Releases ページ](https://github.com/keroppupu/ruri-rag-server/releases) から最新タグ（例: `ver7`）のアセットをダウンロードします：
     - `offline_dist.tar.gz.part_aa`
     - `offline_dist.tar.gz.part_ab`
     - `join_and_extract.sh`
2. **オフラインサーバーでの結合・展開**:
   ```bash
   chmod +x join_and_extract.sh
   ./join_and_extract.sh
   ```
3. **起動**:
   ```bash
   cd offline_dist
   ./start.sh
   ```
   ※ Dockerイメージの自動ロードとコンテナ起動が行われ、外部ネットワーク通信なしで全モデル（Ruri-base, Ruri-reranker, EmbeddingGemma-2）が即座に立ち上がります。

---

## 🌐 Web UI の使い方

1. **チャネルの作成・切替**:
   - 画面左のチャネル一覧から用途別のナレッジベース（例: `system-manual`, `legacy-cobol-src`, `design-docs`）を作成・選択します。
2. **ファイルの登録**:
   - 「ファイル登録」タブを開き、PDF、Office文書、各種ソースコード（.py, .java, .pc, .cbl等）、画像（.png, .jpg等）をドラッグ＆ドロップします。
   - テキストはチャンク分割されて Ruri に、画像は EmbeddingGemma-2 に自動でインデックス化されます。
3. **ドキュメント管理**:
   - 「登録ドキュメント」タブで、チャネル内に登録された文書や画像を一覧確認し、個別削除できます。
4. **RAG 検索 & チャット**:
   - 「RAG 対話 / 検索」タブで質問を入力すると、セマンティック検索とリランキングを実行し、スコアと参照元を表示します。
   - 「回答を生成」を有効にすると、設定された LLM（Ollama または LiteLLM）から根拠に基づく回答が生成されます。
5. **LLM 設定タブ**:
   - 回答生成に使用するプロバイダ（Ollama / LiteLLM）、接続先 URL、モデル名を GUI から変更・保存できます。

---

## 🔌 Model Context Protocol (MCP) 連携

### 1. 提供ツール一覧

| ツール名 | 説明 |
| :--- | :--- |
| `search_knowledge_base` | Ruri + Gemma-2 + Reranker による高精度なハイブリッドセマンティック検索 |
| `ask_rag` | 指定チャネル内ドキュメントを検索・リランクし、LLM による回答生成を一括実行 |
| `list_channels` | 登録済みチャネル一覧とドキュメント件数を取得 |
| `add_document_to_channel` | テキスト・ソースコード等のデータを指定チャネルに直接登録・ベクトル化 |

---

### 2. GitLab Duo WebUI（セルフホスト版）での設定
GitLab Duo WebUI（Duo Chat / Duo Workflow）の MCP 設定画面にて、**HTTP / SSE URL** を指定します：

```text
http://<RAGサーバーのLAN_IP>:8000/sse
```

> **閉塞環境でのファイアウォール確認**:
> RAGサーバー側（RHEL 等）でファイアウォールが有効な場合は、ポート 8000 を開放してください：
> ```bash
> sudo firewall-cmd --add-port=8000/tcp --permanent
> sudo firewall-cmd --reload
> ```

---

### 3. OpenClaw での設定
OpenClaw の CLI から Docker コンテナ経由で MCP サーバーを登録します：

```bash
openclaw mcp add ruri-rag \
  --command docker \
  --arg exec \
  --arg -i \
  --arg ruri-rag-server \
  --arg python \
  --arg mcp_server.py
```

登録確認:
```bash
openclaw mcp probe ruri-rag
```

---

### 4. VS Code (GitLab Duo / Claude / Cursor) での設定
VS Code の設定ファイル（`settings.json` または MCP 設定）に以下を追加します：

```json
{
  "mcpServers": {
    "ruri-rag": {
      "command": "docker",
      "args": ["exec", "-i", "ruri-rag-server", "python", "mcp_server.py"]
    }
  }
}
```

※ リモートホスト上の RAG サーバーに手元の PC から接続する場合は、手元に `mcp_server.py` を配置し、環境変数 `RAG_SERVER_URL` に `http://<RAGサーバーIP>:8000` を指定して実行することも可能です。

---

## 📡 主な REST API エンドポイント

| メソッド | パス | 説明 |
| :--- | :--- | :--- |
| `GET` | `/health` | サーバーおよび各モデル（テキスト・マルチモーダル）の稼働状態確認 |
| `GET` | `/channels` | 全チャネル一覧の取得 |
| `POST` | `/channels` | 新規チャネルの作成 (`{"name": "..."}`) |
| `DELETE` | `/channels/{id}` | チャネルおよびデータの削除 |
| `GET` | `/channels/{id}/documents` | チャネル内のドキュメント（テキスト・画像）一覧取得 |
| `DELETE` | `/channels/{id}/documents/{doc_id}` | 指定ドキュメントの個別削除 |
| `POST` | `/channels/{id}/upload` | マルチパート形式によるファイル・ソースコード・画像の登録 |
| `POST` | `/channels/{id}/search` | ベクトル検索 + CrossEncoder リランキング |
| `POST` | `/channels/{id}/rag` | RAG 検索 + LLM 回答生成 |
| `GET` | `/sse` | MCP Server-Sent Events エンドポイント |
| `POST` | `/messages` | MCP JSON-RPC メッセージ受付エンドポイント |

---

## 🛠️ オフライン運用・メンテナンス

- **[オフラインDockerコンテナ内の `index.html` 差し替え手順](docs/UPDATE_INDEX_HTML_OFFLINE.md)**:
  Dockerイメージ全体を再転送することなく、稼働中コンテナのWeb UI（`index.html`）のみを即座に上書き更新する手順書です。
