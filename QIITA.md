# 【完全オフライン対応】日本語特化モデルRuri＋マルチモーダルで作るハイブリッドRAGサーバー（Docker / 画像・ソースコード・COBOL対応 / Web UI付き）

こんにちは、keroppupu です。

「社内の機密文書や設計書を検索・要約したいが、クラウドサービスや外部API（OpenAIなど）への送信はセキュリティ上禁止されている」「ネットワークが遮断された閉域環境（エアギャップ環境）で高精度な日本語RAGを運用したい」「テキストだけでなく画像や図面、プログラム資産（COBOLやPro*C含む）もまとめてナレッジ化したい」という課題に直面したことはないでしょうか？

本記事では、名古屋大学CL研究室が公開している日本語特化の高性能モデル **Ruri（ruri-base / ruri-reranker-large）** と Google の **EmbeddingGemma-2** マルチモーダルモデルを採用し、**Office文書 / PDF / 画像 / 各種ソースコード（COBOL・Pro\*C含む）** の直接読み込みと **複数RAGの分離（チャネル機能）**、ブラウザから使える **WebフロントエンドUI**、さらに **GitLab Duo や OpenClaw と連携できる MCP (Model Context Protocol)** を備えた、**完全オフライン対応の日本語マルチモーダルRAGサーバー (v3.0)** の構築手順と使い方を紹介します。

ソースコードおよびDocker一式はGitHubで公開しています：
👉 **GitHub リポジトリ: [https://github.com/keroppupu/ruri-rag-server](https://github.com/keroppupu/ruri-rag-server)**

---

## 📌 システムの主な特徴

1. **日本語テキスト（Ruri）＋画像（EmbeddingGemma-2）のハイブリッド検索**
   - **テキスト Embedding**: `cl-nagoya/ruri-base`（クエリ側には「クエリ: 」、ドキュメント側には「文章: 」プレフィックスを自動付与）
   - **マルチモーダル Embedding**: `google/embeddinggemma-2`（写真・図面・スライド内オブジェクトのベクトル化）
   - **Reranker**: `cl-nagoya/ruri-reranker-large`（CrossEncoderによる精密な再順位付けでハルシネーションを抑制）
2. **圧倒的なファイルフォーマット・プログラミング言語対応**
   - 📊 **Office 文書**: Excel (`.xlsx`, `.xls`), Word (`.docx`), PowerPoint (`.pptx`)（スライドや文書内の埋め込み画像も自動抽出）
   - 📄 **PDF**: ページ単位テキスト抽出 ＋ 埋め込み画像抽出
   - 💻 **ソースコード**: Python, JavaScript/TypeScript, Go, Java, C/C++, C#, Rust, Ruby, PHP, Shell, HTML/CSS, SQL, YAML, Dockerfile 等
   - 🏛️ **レガシー資産・業務言語**: **Pro\*C (`.pc`)**, **COBOL (`.cbl`, `.cob`, `.cobol`, `.cpy`)**, **Pro\*COBOL (`.pco`)**
     - Shift-JIS / CP932 / UTF-8 自動エンコーディングフォールバック対応
   - 🖼️ **画像ファイル**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.tiff`, `.webp`
3. **複数ナレッジを分離管理できる「チャネル機能」**
   - ChromaDBのコレクションを活用し、「営業資料」「技術仕様書」「メインフレームCOBOL資産」などを用途ごとに完全分離。
4. **完全オフライン対応の Web フロントエンド UI**
   - 外部CDNに一切依存しないセルフコンテインドなWeb画面を内蔵。
   - ドラッグ＆ドロップでのファイル登録、テキストチャンク数・画像数の表示、画像プレビューバッジ付き一覧管理が可能。
5. **柔軟な LLM 連携（回答生成）**
   - ローカルの **Ollama**（`qwen3.5:9b` 等）や、同一LAN上の **LiteLLM / OpenAI互換ゲートウェイ**（`gpt-4o-mini`, `gpt-oss-120b` 等）を Web UI 設定タブからワンクリック切り替え可能。
6. **GitLab Duo & OpenClaw 対応の MCP (Model Context Protocol)**
   - GitLab Duo WebUI 用の **HTTP / SSE ストリーミング (`/sse`)** と、OpenClaw / VS Code 用の **stdio 接続 (`mcp_server.py`)** の双方を完備。

---

## 🏗️ 全体アーキテクチャ

```text
[ ブラウザ Web UI (localhost:8000) ]     [ GitLab Duo WebUI / OpenClaw ]
        │  ▲                                    │  ▲
        ▼  │ HTTP (REST API)                     ▼  │ MCP (HTTP SSE / stdio)
┌─────────────────────────────────────────────────────────────┐
│ FastAPI バックエンドコンテナ (Docker: ruri-rag-server)          │
│                                                             │
│  ├─ Multi-format Parser (PDF, Office, Code, Legacy, Image)  │
│  │                                                          │
│  ├─ Text Embedding: cl-nagoya/ruri-base                     │
│  │                                                          │
│  ├─ Multimodal Embedding: google/embeddinggemma-2           │
│  │                                                          │
│  ├─ Rerank Engine: cl-nagoya/ruri-reranker-large            │
│  │                                                          │
│  ├─ Vector Store: ChromaDB (テキスト/画像コレクション分離)     │
│  │                                                          │
│  └─ MCP Endpoints: GET /sse & POST /messages (JSON-RPC)     │
└─────────────────────────────────────────────────────────────┘
        │ (コンテキスト引き渡し)
        ▼
[ ローカル Ollama (qwen3.5) / LAN上 LiteLLM (OpenAI互換) ] ──> 回答生成
```

---

## 🚀 クイックスタート（オンライン・開発環境）

まずはインターネット接続のあるマシンで動かしてみましょう。

```bash
# リポジトリのクローン
git clone https://github.com/keroppupu/ruri-rag-server.git
cd ruri-rag-server

# Dockerコンテナのビルド＆起動
docker compose up --build -d

# ログ確認
docker compose logs -f
```

起動完了後、ブラウザで **`http://localhost:8000`** にアクセスすると Web UI が立ち上がります。

---

## 🔒 完全オフライン（エアギャップ・閉塞LAN）でのセットアップ手順

インターネットに接続されていない閉域環境（RHEL / CentOS / Rocky Linux / AlmaLinux 等）へは、GitHub Releases に配置されている事前ビルド済みパッケージを利用してワンクリック導入できます。

### ステップ 1: パッケージのダウンロード（オンライン側）
[GitHub Releases ページ](https://github.com/keroppupu/ruri-rag-server/releases) から最新タグ（例: `ver7`）のアセットをダウンロードし、USBメモリ等にコピーします：
- `offline_dist.tar.gz.part_aa`
- `offline_dist.tar.gz.part_ab`
- `join_and_extract.sh`

### ステップ 2: オフラインサーバーでの結合・展開
オフラインサーバーにファイルを配置し、以下を実行します：

```bash
chmod +x join_and_extract.sh
./join_and_extract.sh
```

### ステップ 3: 起動
```bash
cd offline_dist
./start.sh
```

これだけで、**外部ネットワーク通信を一切行わずに** 全モデル（Ruri-base, Ruri-reranker, EmbeddingGemma-2）を内包したコンテナが起動し、ブラウザ（`http://<サーバーIP>:8000`）から全機能が即座に利用可能になります。

---

## 💻 Web UI の操作フロー

1. **チャネルの作成・選択**
   - 画面左のチャネル一覧から用途に合わせたチャネル名（例: `社内規定`, `開発設計書`, `COBOLソース`）を作成し選択します。
2. **ファイルのドラッグ＆ドロップ登録**
   - 「ファイル登録」タブを開き、PDF、Office文書、ソースコード、画像ファイルなどをまとめてドロップします。
   - テキストはチャンク分割されて Ruri に、画像は EmbeddingGemma-2 に自動でインデックス化されます。
3. **登録ドキュメントの確認・削除**
   - 「登録ドキュメント」タブで、チャネル内の文書・画像一覧、文字数、登録形式をプレビュー・個別削除できます。
4. **対話＆検索**
   - 「RAG 対話 / 検索」タブで質問を入力すると、Ruri ＋ Gemma-2 ＋ Reranker による最高精度の関連ドキュメントと適合スコアが提示されます。
   - 「回答を生成」を有効にすると、ローカル LLM（Ollama / LiteLLM）が文脈を踏まえて回答を作成します。

---

## 📡 主な REST API エンドポイント

| エンドポイント | メソッド | 用途 |
| :--- | :--- | :--- |
| `GET /health` | `GET` | サーバーおよび各モデルの健全性確認 |
| `GET /channels` | `GET` | チャネル一覧とドキュメント件数の取得 |
| `POST /channels` | `POST` | 新規チャネル作成 (`{"name": "sales"}`) |
| `GET /channels/{channel}/documents` | `GET` | チャネル内ドキュメント一覧取得 |
| `DELETE /channels/{channel}/documents/{id}` | `DELETE` | ドキュメントの個別削除 |
| `POST /channels/{channel}/upload` | `POST` | ファイル（Office/PDF/ソースコード/画像）のアップロード |
| `POST /channels/{channel}/search` | `POST` | ハイブリッドベクトル検索 + CrossEncoder リランク |
| `POST /channels/{channel}/rag` | `POST` | RAG回答生成（Ollama / LiteLLM 連携） |
| `GET /sse` | `GET` | GitLab Duo 向け MCP Server-Sent Events 接続 |
| `POST /messages` | `POST` | MCP JSON-RPC メッセージ受付 |

---

## 📝 まとめ

- 名古屋大学の **Ruri シリーズ** と **EmbeddingGemma-2** を組み合わせることで、日本語文書のみならず画像・図面・各種ソースコード・レガシー言語（COBOL/Pro\*C）までを最高精度で検索・要約できるようになりました。
- **GitLab Duo WebUI（HTTP SSE）** や **OpenClaw (stdio)** への MCP 接続も標準対応しており、エディタやチャット画面から直接自社ナレッジを呼び出すことができます。
- 全モデルをDockerイメージ内に同梱しているため、**機密保持が厳格な閉塞環境（オンプレミス）でも安心して即日運用**が可能です。

ぜひ試してみてください！

👉 **GitHub: [https://github.com/keroppupu/ruri-rag-server](https://github.com/keroppupu/ruri-rag-server)**
