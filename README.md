# Ruri 日本語 RAG サーバー (v2.0)

名古屋大学 CL研究室が開発した高性能な日本語テキスト埋め込みモデル・リランカー **Ruri** を搭載した、マルチチャネル＆マルチフォーマット対応の Python / FastAPI 製 RAG サーバーです。

ブラウザから直接利用できる **Webフロントエンド**、**Office文書（Excel/Word/PowerPoint）および PDF の自動テキスト抽出・チャンク分割アップロード機能**、用途別に知識ベースを分離できる **チャネル機能** を備えています。

---

## 🌟 主な機能

- **日本語特化モデル（Ruriシリーズ）**:
  - **Embedding**: `cl-nagoya/ruri-base`（クエリには `クエリ: `、ドキュメントには `文章: ` を自動付与）
  - **Reranking**: `cl-nagoya/ruri-reranker-large`（CrossEncoder による高精度な再スコアリング）
- **マルチフォーマットファイル対応**:
  - 📊 **Excel**: `.xlsx`, `.xls`（シート・行ごとにテキスト抽出）
  - 📝 **Word**: `.docx`（段落・表組み抽出）
  - 📽️ **PowerPoint**: `.pptx`（スライド単位で図形・テキスト枠抽出）
  - 📄 **PDF**: `.pdf`（ページ単位抽出）
  - 📑 **テキスト**: `.txt`, `.md`, `.csv`（UTF-8 / CP932 自動判定）
- **RAG チャネル機能**:
  - 部署別、プロジェクト別、ドキュメント種別ごとに独立した知識ベース（コレクション）を作成・切り替え可能。
- **Web フロントエンド UI**:
  - ブラウザ（`http://localhost:8000`）から直感的に操作可能。
  - チャネルの作成・切替・削除
  - ファイルのドラッグ＆ドロップ登録
  - RAG 対話、検索結果および Rerank スコア・根拠文書のプレビュー
- **LLM 連携**:
  - ローカルの Ollama（`qwen3.5:9b` 等）へコンテキストを渡して回答生成。

---

## 📂 ディレクトリ構成

```
ruri-rag-server/
├── Dockerfile              # Docker ビルド定義
├── docker-compose.yml      # データとモデルキャッシュ永続化設定
├── requirements.txt        # 依存ライブラリ（FastAPI, PyPDF, python-docx, openpyxl等）
├── .dockerignore
├── README.md
├── test_client.py          # API テストスクリプト
└── app/
    ├── __init__.py
    ├── main.py             # FastAPI エンドポイント & Web ルーティング
    ├── rag_engine.py       # Ruri埋め込み・リランカー・ChromaDB操作ロジック
    ├── document_parser.py  # PDF/Word/PPTX/Excel パース & チャンカー
    └── static/
        └── index.html      # Webフロントエンド Single Page Application
```

---

## 🚀 起動方法

### 1. 通常の起動（オンライン環境）

```bash
cd /Users/pupu/.gemini/antigravity/scratch/ruri-rag-server

# ビルドしてバックグラウンド起動
docker compose up --build -d

# ログ確認（初回のモデルダウンロード状況など）
docker compose logs -f
```

起動後、ブラウザで **`http://localhost:8000`** にアクセスすると Web UI が利用できます。

---

## 🔒 完全オフライン（エアギャップ環境）でのセットアップ手順

インターネットに接続されていない閉域環境に持ち込んでセットアップ・稼働させる手順です。
本システムは **「Dockerイメージのパッケージ化」** と **「Ollamaモデルの移行」** の2ステップで完全にオフライン動作します。

### ステップ 1: オンラインマシンでの準備（USBへのエクスポート）

#### 1-1. RAG サーバーのオフラインパッケージを作成
同梱のパッケージ作成スクリプトを実行すると、Ruriモデルを内包したDockerイメージと起動設定が `offline_dist/` フォルダに自動出力されます。

```bash
cd ruri-rag-server
./scripts/export_offline_package.sh
```
出力された **`offline_dist` フォルダ** を USB メモリ等にコピーします。

#### 1-2. Ollama の LLM モデルをダウンロードしてコピー
ホストマシンで Ollama のモデル（`qwen3.5:9b` 等）を事前取得します。

```bash
ollama pull qwen3.5:9b
```
Ollama のモデルファイル一式（保存場所: `~/.ollama/models`）を USB メモリにコピーします。

---

### ステップ 2: オフライン（閉域）マシンでのセットアップ＆起動

USB メモリをオフラインマシンに接続します。

#### 2-1. Ollama の配置と起動
オフラインマシンの `~/.ollama/models` にモデルファイルを配置して起動します。

```bash
# モデルファイルを配置
mkdir -p ~/.ollama/models
cp -r /path/to/usb/models/* ~/.ollama/models/

# Ollama サーバーを起動
ollama serve
```

#### 2-2. RAG サーバーの起動
USB の `offline_dist` フォルダ内で、起動スクリプトを実行するだけです。

```bash
cd /path/to/usb/offline_dist

# イメージのインポートとコンテナ起動をワンクリック実行
./start.sh
```

これだけで、**ネットワーク通信を一切行わずに** ブラウザ（`http://localhost:8000`）から全機能（ファイル読み込み・チャネル管理・Ruri検索・LLM回答）が即座に利用可能になります。


---

## 🌐 Web UI の使い方

1. **チャネルの選択・新規作成**:
   - 左サイドバーの「新規」ボタンから、用途に合わせたチャネル名（例: `sales_docs`, `manual`, `product_spec`）を作成し、クリックして選択します。
2. **ファイルのアップロード**:
   - 上部タブの「ファイル登録」を開き、PDF、Word、Excel、PowerPoint などをドラッグ＆ドロップします。
   - 自動的にテキストが抽出され、チャンク分割された上で Ruri ベクトル化されます。
3. **対話・検索**:
   - 「RAG 対話 / 検索」タブで質問を入力すると、Ruri による検索・リランクが行われ、関連するドキュメントとその Rerank スコアが表示されます。
   - 「Ollama で回答を生成」を有効にすると、ローカル LLM が自動的に回答を生成します。

---

## 📡 主な REST API エンドポイント

### 1. チャネル管理
- `GET /channels`: 全チャネル一覧の取得
- `POST /channels`: 新規チャネル作成 (`{"name": "tech_docs"}`)
- `DELETE /channels/{channel_id}`: チャネルとその全データの削除

### 2. ファイルアップロード
- `POST /channels/{channel_id}/upload`: マルチパート形式でファイルをアップロード
  - `file`: アップロードファイル（PDF, DOCX, PPTX, XLSX, TXT 等）
  - `chunk_size`: チャンク文字数（デフォルト: 500）
  - `chunk_overlap`: 重複文字数（デフォルト: 50）

```bash
curl -X POST "http://localhost:8000/channels/tech_docs/upload" \
  -F "file=@/path/to/document.pdf" \
  -F "chunk_size=500"
```

### 3. 検索 & Rerank
- `POST /channels/{channel_id}/search`: 指定チャネル内での 1次ベクトル検索 + 2次 CrossEncoder リランク

```bash
curl -X POST "http://localhost:8000/channels/tech_docs/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "システムの仕様について教えて",
    "initial_top_k": 10,
    "final_top_n": 3
  }'
```

### 4. RAG 回答生成
- `POST /channels/{channel_id}/rag`: 指定チャネルの関連文書を抽出して Ollama 等で回答生成

```bash
curl -X POST "http://localhost:8000/channels/tech_docs/rag" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "認証方式は何が採用されていますか？",
    "initial_top_k": 10,
    "final_top_n": 3,
    "generate_answer": true
  }'
```

---

## 🔌 Model Context Protocol (MCP) 連携

本 RAG サーバーには、**GitLab Duo / GitLab Workflow (VS Code) / Claude Desktop / Cursor / Antigravity** 等の AI クライアントから直接ナレッジ検索・質問ができる **MCP サーバー (`mcp_server.py`)** が同梱されています。

### 提供ツール一覧

| ツール名 | 説明 |
| :--- | :--- |
| `search_knowledge_base` | Ruriモデル（Embedding + Rerank）でチャネル内を検索し、高精度な根拠テキストを取得 |
| `ask_rag` | ドキュメント検索とローカル LLM（Ollama）回答生成を一括実行 |
| `list_channels` | 登録済みチャネル一覧と各ドキュメント件数を取得 |
| `index_text` | テキストデータを指定チャネルに直接登録・ベクトル化 |

### GitLab Duo / VS Code での設定例

VS Code の `settings.json`（または GitLab Duo の MCP 設定ファイル）に以下を追加します：

```json
{
  "gitlab.duo.mcpServers": {
    "ruri-rag": {
      "command": "python3",
      "args": ["/絶対パス/ruri-rag-server/mcp_server.py"],
      "env": {
        "RAG_SERVER_URL": "http://localhost:8000"
      }
    }
  }
}
```

※ Docker コンテナ経由で実行する場合:
```json
{
  "gitlab.duo.mcpServers": {
    "ruri-rag": {
      "command": "docker",
      "args": ["exec", "-i", "ruri-rag-server", "python3", "/app/mcp_server.py"]
    }
  }
}
```

設定後、GitLab Duo Chat や AI チャットで「社内規定チャネルから〇〇の仕様を調べて」と入力すると、自動的に Ruri RAG の検索ツールが実行されて高精度な回答が生成されます。

