"""
RAG 推論 API クライアント (Python)

RAG サーバーの /rag (または /channels/{channel_id}/rag) エンドポイントを呼び出し、
ハイブリッド検索（Ruri + EmbeddingGemma）＋ Rerank ＋ LLM推論結果を取得・表示するスクリプトです。
"""

import json
import requests
from typing import Optional, Dict, Any

# RAG サーバーのホストURL (デフォルト: http://localhost:8000)
RAG_SERVER_URL = "http://localhost:8000"


def ask_rag(
    query: str,
    channel_id: str = "default",
    initial_top_k: int = 10,
    final_top_n: int = 3,
    system_prompt: Optional[str] = None,
    # 必要に応じてLLM接続情報をリクエスト単位で上書き可能
    llm_provider: Optional[str] = None,   # "ollama" または "litellm"
    llm_base_url: Optional[str] = None,   # 例: "http://host.docker.internal:11434"
    llm_model: Optional[str] = None,      # 例: "qwen3.5:9b"
    server_url: str = RAG_SERVER_URL,
) -> Optional[Dict[str, Any]]:
    """
    RAGサーバーの推論API (/rag) をキックして、
    ハイブリッド検索(Ruri+EmbeddingGemma) + Rerank + LLM推論結果を取得します。
    """
    endpoint = f"{server_url.rstrip('/')}/channels/{channel_id}/rag"

    payload = {
        "query": query,
        "channel_id": channel_id,
        "generate_answer": True,   # LLMによる回答生成を有効化
        "initial_top_k": initial_top_k,
        "final_top_n": final_top_n,
    }

    if system_prompt:
        payload["system_prompt"] = system_prompt
    if llm_provider:
        payload["llm_provider"] = llm_provider
    if llm_base_url:
        payload["llm_base_url"] = llm_base_url
    if llm_model:
        payload["llm_model"] = llm_model

    try:
        response = requests.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=120,  # 検索+LLM推論の処理時間を考慮
        )
        response.raise_for_status()
        data = response.json()

        print("=" * 60)
        print(f"【質問】: {data.get('query')}")
        print(f"【対象チャネル】: {data.get('channel')}")
        print(f"【LLMステータス】: {data.get('llm_status')}")
        print("=" * 60)

        # 1. LLM 推論結果の表示
        answer = data.get("answer")
        if answer:
            print("\n【AIの回答】:\n")
            print(answer)
        else:
            print("\n【AIの回答】: 回答なし（LLM接続設定またはモデル出力を確認してください）")

        # 2. 根拠となったドキュメント（コンテキスト）の表示
        contexts = data.get("contexts", [])
        print("\n" + "-" * 60)
        print(f"【参照コンテキスト (上位 {len(contexts)} 件)】:")
        for idx, item in enumerate(contexts, start=1):
            source = item.get("metadata", {}).get("source", "不明")
            modality = item.get("source_modality", "text")
            score = item.get("rerank_score", 0.0)
            content = item.get("content", "").strip()

            print(f"\n[{idx}] 出典: {source} (種別: {modality}, Rerankスコア: {score:.4f})")
            print(f"内容:\n{content[:200]}..." if len(content) > 200 else f"内容:\n{content}")

        print("=" * 60)
        return data

    except requests.exceptions.HTTPError as http_err:
        print(f"[HTTP エラー]: {http_err} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"[通信エラー]: {e}")
    return None


if __name__ == "__main__":
    # 実行例
    question = "RAGサーバーの特徴や対応しているファイル形式を教えてください。"

    # Docker内のサーバーからMacホスト上のOllamaへ接続する場合は host.docker.internal を指定可能
    ask_rag(
        query=question,
        channel_id="default",
        final_top_n=3,
        llm_base_url="http://host.docker.internal:11434",
        llm_model="qwen3.5:9b"
    )
