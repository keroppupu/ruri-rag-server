# 【GitLab × MCP】GitLab Duoから自作の日本語特化RAGサーバー（Ruri＋Gemma2モデル）を呼び出す方法（WebUI / VS Code両対応）

こんにちは、keroppupu です。

GitLab の AI 支援機能である **GitLab Duo**（GitLab Duo Chat や Duo Workflow）を使っている中で、**「自社の社内規定、設計書、API仕様、そしてCOBOLやC言語等のレガシー資産を含む独自ナレッジを GitLab Duo に参照させたい」** と感じたことはないでしょうか？

Anthropic が提唱し、オープン標準として急速に普及している **Model Context Protocol (MCP)** を活用することで、GitLab Duo や VS Code (GitLab Workflow 拡張) から自作の RAG サーバーをシームレスに呼び出すことが可能になります。

本記事では、名古屋大学CL研究室の日本語特化モデル **Ruri（ruri-base / ruri-reranker-large）** および Google の **EmbeddingGemma-2** を搭載した Docker RAG サーバーに、**GitLab Duo WebUI（HTTP / SSE接続）** および **VS Code / OpenClaw（stdio接続）** の両方から接続する手順を解説します。

リポジトリ一式（Docker / MCP サーバー / Web UI）は GitHub で公開しています：
👉 **GitHub: [https://github.com/keroppupu/ruri-rag-server](https://github.com/keroppupu/ruri-rag-server)**

---

## 🏗️ 全体アーキテクチャ

本 RAG サーバーは、**2系統の MCP トランスポート** に対応しています：

```text
【パターン 1: GitLab Duo WebUI (ブラウザ/サーバー直接通信)】
  GitLab Duo WebUI ──(HTTP / Server-Sent Events)──> [ GET /sse & POST /messages ]
                                                              │
                                                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Ruri RAG サーバー (Docker コンテナ: ruri-rag-server)            │
│                                                             │
│  ├─ Multi-format Parser (Office, PDF, Code, COBOL, Image)   │
│  ├─ Text Embedding: cl-nagoya/ruri-base                     │
│  ├─ Image Embedding: google/embeddinggemma-2                │
│  ├─ Reranking: cl-nagoya/ruri-reranker-large                │
│  ├─ Vector Store: ChromaDB (マルチチャネル分離)             │
│  └─ LLM 生成: Ollama (qwen3.5) / LiteLLM (OpenAI互換)       │
└─────────────────────────────────────────────────────────────┘
                                                              ▲
                                                              │
【パターン 2: VS Code / OpenClaw (ローカル・コンテナ起動)】     │
  VS Code / OpenClaw ──(JSON-RPC over stdio)──> [ mcp_server.py ]
```

---

## 🔌 提供する MCP ツール一覧

GitLab Duo に対して以下の 4 つのツールを提供します：

| ツール名 | 説明 | 主な引数 |
| :--- | :--- | :--- |
| `search_knowledge_base` | Ruri + Gemma-2 でセマンティック検索＋CrossEncoderリランクを実行し、高精度な根拠テキストを取得 | `query` (質問), `channel_id` (チャネル), `top_n` (件数) |
| `ask_rag` | ドキュメント検索とローカル LLM による回答生成を一括実行 | `query` (質問), `channel_id` (チャネル), `top_n` (件数) |
| `list_channels` | 登録済みチャネル一覧と各ドキュメント件数を取得 | なし |
| `add_document_to_channel` | テキスト・ソースコードデータを指定チャネルのナレッジベースに登録・ベクトル化 | `text` (本文), `channel_id` (チャネル), `source` (出典) |

---

## 🛠️ 事前準備：RAG サーバーの起動

Docker Compose で RAG サーバーを起動します（完全オフライン環境の場合は GitHub Releases のパッケージをご利用ください）。

```bash
git clone https://github.com/keroppupu/ruri-rag-server.git
cd ruri-rag-server

# Docker コンテナを起動 (http://localhost:8000)
docker compose up -d
```

ブラウザで `http://localhost:8000` を開き、社内資料（PDF / Office / ソースコード / COBOL / 画像等）をドラッグ＆ドロップしてチャネル（例: `社内規定` や `設計書`）に登録しておきます。

---

## ⚙️ 設定手順 1: GitLab Duo WebUI から HTTP / SSE で接続する場合（推奨）

GitLab Duo セルフホスト版の Web UI（Duo Chat や Duo Workflow）から同一LAN経由で接続する場合、SSHやコマンド実行は不要です。

### 1. GitLab Duo の MCP 設定画面を開く
GitLab 管理画面またはプロジェクト設定の **[AI Features]** / **[Model Context Protocol]** 設定を開きます。

### 2. HTTP / SSE URL を登録
以下の URL を設定します：

```text
http://<RAGサーバーのLAN_IP>:8000/sse
```
（例: `http://192.168.1.100:8000/sse`）

> **⚠️ 閉塞環境（RHEL等）の注意点**:
> RAGサーバー側でファイアウォール（firewalld）が稼働している場合は、事前にポート 8000 を開放してください：
> ```bash
> sudo firewall-cmd --add-port=8000/tcp --permanent
> sudo firewall-cmd --reload
> ```

---

## ⚙️ 設定手順 2: VS Code (GitLab Workflow) から接続する場合

VS Code の **GitLab Workflow 拡張機能** から接続する場合は、`settings.json` に以下を追加します。

### パターン A: 起動中の Docker コンテナ経由で実行（推奨・追加依存なし）

```json
{
  "gitlab.duo.mcpServers": {
    "ruri-rag": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "ruri-rag-server",
        "python",
        "mcp_server.py"
      ]
    }
  }
}
```

### パターン B: 手元の Python で実行し、リモート RAG サーバーに接続

```json
{
  "gitlab.duo.mcpServers": {
    "ruri-rag": {
      "command": "python3",
      "args": [
        "/path/to/mcp_server.py"
      ],
      "env": {
        "RAG_SERVER_URL": "http://192.168.1.100:8000"
      }
    }
  }
}
```

---

## ⚙️ 設定手順 3: OpenClaw から利用する場合

OpenClaw 環境をご利用の場合、CLI からワンコマンドで登録できます：

```bash
openclaw mcp add ruri-rag \
  --command docker \
  --arg exec \
  --arg -i \
  --arg ruri-rag-server \
  --arg python \
  --arg mcp_server.py
```

疎通確認:
```bash
openclaw mcp probe ruri-rag
```

---

## 💬 実際の対話例（GitLab Duo Chat）

設定完了後、GitLab Duo Chat や Duo Workflow から自然言語で質問すると、自動的にツールが呼び出されます。

### 実行例 1: ナレッジベースの検索
> **ユーザー**:  
> 「社内規定チャネルから、育児休業の申請期限について調べて」
> 
> **GitLab Duo**:  
> ツール `search_knowledge_base` を実行  
> ➜ **「社内規定によると、育児休業の申請は希望開始日の1ヶ月前までに総務部へ申請書を提出する必要があります（出典: 育児介護休業規程.docx, Rerankスコア: 0.892）」**

### 実行例 2: COBOLやレガシープログラムの仕様確認
> **ユーザー**:  
> 「COBOLソースチャネルから、バッチ処理でのエラーコード一覧を確認して」
> 
> **GitLab Duo**:  
> ツール `search_knowledge_base` を実行  
> ➜ **「`BATCH01.cbl` の記述によると、リターンコード `99` はDB接続タイムアウト、`12` はデータ形式不正を示しています。」**

---

## 💡 この構成のメリット

1. **機密情報の完全オンプレミス保護**:
   - 生データはすべて社内LANの Docker コンテナ内で完結し、外部の商用クラウドAPIに漏洩しません。
2. **WebUI ＆ エディタ両対応の柔軟性**:
   - HTTP/SSE 経由でブラウザ画面（GitLab WebUI）から直接使える上、VS Code や OpenClaw からも同一コンテナのナレッジを共用できます。
3. **日本語・レガシー資産への圧倒的な強さ**:
   - 名古屋大学の Ruri モデルと Shift-JIS フォールバック機能により、日本の業務システムで頻出する各種資料やレガシーコードも正確に検索できます。

ぜひお試しください！

👉 **リポジトリ: [https://github.com/keroppupu/ruri-rag-server](https://github.com/keroppupu/ruri-rag-server)**
