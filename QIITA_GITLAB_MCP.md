# 【GitLab × MCP】GitLab Duoから自作の日本語特化RAGサーバー（Ruriモデル）を呼び出す方法

こんにちは、keroppupu です。

GitLab の AI 支援機能である **GitLab Duo**（GitLab Duo Chat）を使っている中で、**「自社の社内規定、設計書、API仕様などの独自ナレッジを GitLab Duo に参照させたい」** と感じたことはないでしょうか？

Anthropic が提唱し、オープン標準として急速に普及している **Model Context Protocol (MCP)** を活用することで、GitLab Duo や VS Code (GitLab Workflow 拡張) から自作の RAG サーバーをシームレスに呼び出すことが可能になります。

本記事では、名古屋大学CL研究室の日本語特化モデル **Ruri（Embedding & Reranker）** を搭載した Docker RAG サーバーに、**MCP ブリッジ（`mcp_server.py`）** を介して GitLab から接続する手順を解説します。

リポジトリ一式（Docker / MCP サーバー / Web UI）は GitHub で公開しています：
👉 **GitHub: [https://github.com/keroppupu/ruri-rag-server](https://github.com/keroppupu/ruri-rag-server)**

---

## 🏗️ 全体アーキテクチャ

```
┌────────────────────────────────────────────────────────┐
│ 開発環境 (VS Code / GitLab Duo / GitLab Web IDE)         │
│                                                        │
│  [ GitLab Duo Chat ] ──(プロンプト入力)                  │
│          │                                             │
│          ▼ (MCP Tool Call: JSON-RPC over stdio)        │
│  [ mcp_server.py ] ──(軽量な標準ライブラリ製ブリッジ)    │
└──────────┬─────────────────────────────────────────────┘
           │ HTTP (REST API: localhost:8000)
           ▼
┌────────────────────────────────────────────────────────┐
│ Ruri RAG サーバー (Docker コンテナ)                     │
│                                                        │
│  ├─ Multi-format Parser (PDF, Word, Excel, PPTX)       │
│  ├─ Embedding: cl-nagoya/ruri-base (文章/クエリプレフィックス) │
│  ├─ Reranking: cl-nagoya/ruri-reranker-large           │
│  ├─ Vector Store: ChromaDB (マルチチャネル分離)        │
│  └─ LLM 生成: Ollama (qwen3.5:9b 等)                   │
└────────────────────────────────────────────────────────┘
```

---

## 🔌 提供する MCP ツール一覧

同梱の `mcp_server.py` は、GitLab Duo に対して以下の 4 つのツールを提供します：

| ツール名 | 説明 | 主な引数 |
| :--- | :--- | :--- |
| `search_knowledge_base` | Ruriモデルでセマンティック検索＋CrossEncoderリランクを実行し、高精度な根拠テキストを取得 | `query` (質問), `channel_id` (チャネル), `top_n` (件数) |
| `ask_rag` | ドキュメント検索とローカル LLM による回答生成を一括実行 | `query` (質問), `channel_id` (チャネル), `top_n` (件数) |
| `list_channels` | 登録済みチャネル一覧と各ドキュメント件数を取得 | なし |
| `index_text` | テキストデータを指定チャネルのナレッジベースに登録・ベクトル化 | `text` (本文), `channel_id` (チャネル), `source` (出典) |

---

## 🛠️ 事前準備：RAG サーバーの起動

まだサーバーを起動していない場合は、Docker Compose で起動しておきます。

```bash
git clone https://github.com/keroppupu/ruri-rag-server.git
cd ruri-rag-server

# Docker コンテナをバックグラウンド起動 (http://localhost:8000)
docker compose up -d
```

ブラウザで `http://localhost:8000` を開き、社内資料（PDF / Word / Excel / PowerPoint）をドラッグ＆ドロップしてチャネル（例: `社内規定` や `設計書`）に登録しておきます。

---

## ⚙️ GitLab 側の設定手順 (settings.json)

VS Code の **GitLab Workflow 拡張機能**（または GitLab Duo の MCP 設定ファイル）に MCP サーバーを登録します。

VS Code の `settings.json`（またはプロジェクトの `.vscode/settings.json`）を開き、以下の設定を追加します。

### パターン A: ローカル Python で実行する場合（推奨・シンプル）

```json
{
  "gitlab.duo.mcpServers": {
    "ruri-rag": {
      "command": "python3",
      "args": [
        "/path/to/ruri-rag-server/mcp_server.py"
      ],
      "env": {
        "RAG_SERVER_URL": "http://localhost:8000"
      }
    }
  }
}
```
※ `/path/to/ruri-rag-server/mcp_server.py` は、お使いの環境における絶対パスに置き換えてください。

### パターン B: 起動中の Docker コンテナ経由で実行する場合

ホスト環境に Python を直接用意したくない場合、Docker コンテナ内の `mcp_server.py` を直接呼び出すことができます。

```json
{
  "gitlab.duo.mcpServers": {
    "ruri-rag": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "ruri-rag-server",
        "python3",
        "/app/mcp_server.py"
      ]
    }
  }
}
```

---

## 💬 実際の対話例（GitLab Duo Chat）

設定を保存すると、GitLab Duo のチャット画面から自動的にツールが認識されます。

### 実行例 1: ナレッジベースの検索

> **ユーザー**:  
> 「社内規定チャネルから、夏季休暇の取得条件について調べて」

> **GitLab Duo の動作**:  
> ツール `search_knowledge_base` を引数 `{"query": "夏季休暇 取得条件", "channel_id": "社内規定"}` で呼び出し。  
> ➜ Ruri によるベクトル検索とリランキングが行われ、最も関連性の高い条文を抽出。  
> ➜ **「社内規定によると、夏季休暇は7月から9月の間に最大3日間取得可能です（出典: 就業規則.docx, Rerankスコア: 2.84）」** と回答。

### 実行例 2: チャネル一覧の確認

> **ユーザー**:  
> 「利用可能なナレッジチャネルを教えて」

> **GitLab Duo の動作**:  
> ツール `list_channels` を呼び出し。  
> ➜ **「現在、以下の3つのチャネルが利用可能です：1. default (5件), 2. 社内規定 (18件), 3. API仕様書 (42件)」** と案内。

---

## 💡 この構成のメリット

1. **機密情報の完全ローカル保護**:
   - ドキュメントのベクトル化（`ruri-base`）とリランキング（`ruri-reranker-large`）はすべてローカルの Docker コンテナ内で完結します。
   - 機密資料の生データを外部のクラウド AI サービスにアップロードする必要がありません。
2. **高い日本語精度**:
   - 日本語の言語構造に最適化された Ruri モデルを採用しているため、業務文書や技術仕様書のニュアンスを正確に捉えた検索が可能です。
3. **他ツールとの共通利用**:
   - MCP はオープン標準であるため、GitLab Duo だけでなく **Cursor、Claude Desktop、Antigravity** などでも全く同じ設定で流用できます。

---

## 📝 まとめ

Model Context Protocol (MCP) を導入することで、GitLab Duo などの先進的なコーディング支援 AI に自社のナレッジベースを極めて手軽に接続できるようになりました。

「社内のドキュメントを探すためにブラウザを開いて検索する」という手間がなくなり、**エディタや GitLab の画面内で直接質問して仕様を確認できる** 快適な開発体験が得られます。

ぜひお試しください！

👉 **リポジトリ: [https://github.com/keroppupu/ruri-rag-server](https://github.com/keroppupu/ruri-rag-server)**
