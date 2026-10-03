# 【完全オフライン対応】日本語特化モデルRuriで作るマルチチャネルRAGサーバー（Docker / Office・PDF対応 / Web UI付き）

こんにちは、keroppupu です。

「社内の機密文書を検索・要約したいが、クラウドサービスや外部API（OpenAIなど）への送信はセキュリティ上禁止されている」「ネットワークが遮断された閉域環境（エアギャップ環境）で高精度な日本語RAGを運用したい」という課題に直面したことはないでしょうか？

本記事では、名古屋大学CL研究室が公開している日本語特化の高性能モデル **Ruri（ruri-base / ruri-reranker-large）** を採用し、**Excel / Word / PowerPoint / PDF** の直接読み込みと **複数RAGの分離（チャネル機能）**、さらにブラウザから使える **WebフロントエンドUI** を備えた、**完全オフライン対応の日本語RAGサーバー** の構築手順と使い方を紹介します。

ソースコードおよびDocker一式はGitHubで公開しています：
👉 **GitHub リポジトリ: [https://github.com/keroppupu/ruri-rag-server](https://github.com/keroppupu/ruri-rag-server)**

---

## 📌 システムの主な特徴

1. **日本語に強い Ruri シリーズを採用**
   - **Embedding**: `cl-nagoya/ruri-base`（クエリ側には「クエリ: 」、ドキュメント側には「文章: 」プレフィックスを自動付与してベクトル化）
   - **Reranker**: `cl-nagoya/ruri-reranker-large`（CrossEncoderによる精密な再順位付けでハルシネーションを抑制）
2. **Office文書・PDFのマルチフォーマット対応**
   - 📊 **Excel** (`.xlsx`, `.xls`): シート・行単位でのテキスト抽出
   - 📝 **Word** (`.docx`): 本文段落および表組みのテキスト抽出
   - 📽️ **PowerPoint** (`.pptx`): スライドごとのテキスト枠・図形内テキスト抽出
   - 📄 **PDF** (`.pdf`): ページごとの抽出
   - 📑 **テキスト** (`.txt`, `.md`, `.csv`): UTF-8 / CP932（Shift-JIS）自動判定
3. **複数ナレッジを分離管理できる「チャネル機能」**
   - ChromaDBのコレクションを活用し、「営業資料」「技術仕様書」「総務マニュアル」などを用途ごとに完全分離。
4. **完全オフライン対応の Web フロントエンド UI**
   - 外部CDN（Tailwind CDNやフォント等）に依存しないセルフコンテインドなWeb画面を内蔵。
   - ドラッグ＆ドロップでのファイルアップロードや、Rerankスコア付きの回答表示が可能。
5. **ローカル LLM（Ollama）連携**
   - ホストマシン上の Ollama（`qwen3.5:9b` など）と連携し、検索したコンテキストに基づいた回答をローカル完結で生成。

---

## 🏗️ 全体アーキテクチャ

```
[ ブラウザ Web UI (localhost:8000) ]
        │  ▲
        ▼  │ HTTP (REST API)
┌──────────────────────────────────────────────┐
│ FastAPI バックエンドコンテナ (Docker)          │
│                                              │
│  ├─ Multi-format Parser (PDF/Word/PPTX/Excel)│
│  │                                           │
│  ├─ Embedding Engine (cl-nagoya/ruri-base)   │
│  │                                           │
│  ├─ Rerank Engine (ruri-reranker-large)      │
│  │                                           │
│  └─ Vector Store (ChromaDB マルチチャネル)   │
└──────────────────────────────────────────────┘
        │ (コンテキスト引き渡し)
        ▼
[ ローカル Ollama (qwen3.5:9b 等) ] ──> 回答生成
```

---

## 🚀 クイックスタート（オンライン環境での動作確認）

まずはインターネット接続のある環境で動かしてみましょう。

```bash
# リポジトリのクローン
git clone https://github.com/keroppupu/ruri-rag-server.git
cd ruri-rag-server

# Dockerコンテナのビルド＆起動
docker compose up --build -d

# ログ確認（モデルダウンロード状況など）
docker compose logs -f
```

起動完了後、ブラウザで **`http://localhost:8000`** にアクセスすると、Web UI が立ち上がります。

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

## 💻 Web UI の操作フロー

1. **チャネルの作成・選択**
   - サイドバーの「+ 新規チャネル」ボタンから、例えば `社内規定` や `技術資料` といったチャネルを作成・選択します。
2. **ファイルアップロード**
   - 「ファイル登録」タブを開き、対象の Office ファイルや PDF をドラッグ＆ドロップします。
   - バックエンドで自動的にセクション抽出・チャンク分割・Ruri埋め込みが行われます。
3. **対話＆検索**
   - 「RAG 対話 / 検索」タブで質問を入力すると、該当チャネル内からRuriが最適なドキュメントを検索・リランクして回答します。
   - 各コンテキストの Rerank スコア（CrossEncoderによる適合度スコア）も確認できます。

---

## 📡 主な API エンドポイント

プログラムや外部システムから直接呼び出すことも可能です。

| エンドポイント | メソッド | 用途 |
| :--- | :--- | :--- |
| `GET /channels` | `GET` | チャネル一覧と各ドキュメント数の取得 |
| `POST /channels` | `POST` | 新規チャネルの作成 (`{"name": "sales"}`) |
| `POST /channels/{channel}/upload` | `POST` | PDF/Word/PPTX/Excel/Text ファイルのアップロード |
| `POST /channels/{channel}/search` | `POST` | 1次ベクトル検索 + 2次リランク |
| `POST /channels/{channel}/rag` | `POST` | RAG回答生成（Ollama連携） |
| `DELETE /channels/{channel}/documents` | `DELETE` | チャネル内全データのクリア |

---

## 📝 まとめ

- 名古屋大学の **Ruri シリーズ** を使うことで、日本語文書に対する検索およびリランキングの精度が飛躍的に向上しました。
- Dockerイメージ内にモデルやセルフコンテインドWeb UIを内包したため、**インターネット接続が一切ない環境でもUSBメモリ経由でワンクリック導入**が可能です。
- OfficeやPDFの面倒なテキスト抽出やチャネル管理も自動化されているため、手軽にセキュアなオンプレミスRAGを立ち上げることができます。

ぜひ社内の閉域環境やセキュアなプロジェクトで試してみてください！

👉 **GitHub: [https://github.com/keroppupu/ruri-rag-server](https://github.com/keroppupu/ruri-rag-server)**
