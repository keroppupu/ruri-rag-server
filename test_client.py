import time
import requests

BASE_URL = "http://localhost:8000"

def test_rag_pipeline():
    print("1. サーバーのヘルスチェック...")
    for _ in range(15):
        try:
            res = requests.get(f"{BASE_URL}/health", timeout=5)
            if res.status_code == 200:
                print("   サーバー正常稼働中:", res.json())
                break
        except Exception:
            print("   待機中...")
            time.sleep(3)
    else:
        print("エラー: サーバーに接続できませんでした。")
        return

    print("\n2. サンプルドキュメントのインデックス登録...")
    sample_docs = [
        "Pythonはシンプルで読みやすい文法を特徴とする汎用高水準プログラミング言語です。機械学習やデータ分析で広く使用されています。",
        "Ruriは名古屋大学CL研究室が開発した高性能な日本語テキスト埋め込みモデル・リランカーシリーズです。",
        "Dockerはコンテナ仮想化技術を用いてアプリケーションとその依存関係をパッケージ化し、環境間の差異なく実行できるようにします。",
        "FastAPIはPython 3.8以降の型ヒントを基盤とした、高速でモダンなWebフレームワークです。",
        "富士山は日本最高峰の山であり、標高は3776メートルです。古くから霊峰として親しまれています。"
    ]
    res = requests.post(f"{BASE_URL}/documents", json={"documents": sample_docs})
    print("   登録結果:", res.json())

    print("\n3. ベクトル検索 + Rerankテスト (クエリ: '名古屋大学の日本語モデルについて教えて')...")
    query = "名古屋大学の日本語モデルについて教えて"
    res = requests.post(f"{BASE_URL}/search", json={
        "query": query,
        "initial_top_k": 5,
        "final_top_n": 2
    })
    search_data = res.json()
    print("   検索・リランク結果:")
    for i, item in enumerate(search_data.get("results", [])):
        print(f"     [{i+1}] (Score: {item['rerank_score']:.4f}) {item['content']}")

    print("\n4. RAGエンドポイントテスト (コンテキスト抽出)...")
    res = requests.post(f"{BASE_URL}/rag", json={
        "query": "コンテナ仮想化とは何ですか？",
        "generate_answer": False
    })
    rag_data = res.json()
    print("   取得されたコンテキスト:")
    for item in rag_data.get("contexts", []):
        print(f"     - (Score: {item['rerank_score']:.4f}) {item['content']}")

if __name__ == "__main__":
    test_rag_pipeline()
