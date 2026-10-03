import os
import re
import uuid
from typing import List, Dict, Any, Optional
import torch
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder


def sanitize_channel_name(name: str) -> str:
    """ChromaDBのコレクション名規則に合わせてサニタイズ (3-63文字, 英数字, アンダースコア, ハイフン)"""
    # 英数字・ハイフン・アンダースコア以外を置換
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.strip())
    # 先頭が英数字でない場合はプレフィックス
    if not clean or not clean[0].isalnum():
        clean = "ch_" + clean
    # 末尾が英数字でない場合はサフィックス
    if not clean[-1].isalnum():
        clean = clean + "_ch"
    # 長さ制限
    if len(clean) < 3:
        clean = clean.ljust(3, '_')
    if len(clean) > 63:
        clean = clean[:63]
    return clean.lower()


class RuriRAGEngine:
    def __init__(
        self,
        embed_model_name: str = "cl-nagoya/ruri-base",
        rerank_model_name: str = "cl-nagoya/ruri-reranker-large",
        chroma_dir: str = "/app/data/chroma",
        default_channel: str = "default"
    ):
        self.device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
        print(f"[RuriRAG] Using device: {self.device}")

        # モデルの読み込み
        print(f"[RuriRAG] Loading Embedding Model: {embed_model_name}...")
        self.embed_model = SentenceTransformer(embed_model_name, device=self.device)

        print(f"[RuriRAG] Loading Reranker Model: {rerank_model_name}...")
        self.reranker = CrossEncoder(rerank_model_name, device=self.device)

        # ChromaDB クライアントの初期化
        os.makedirs(chroma_dir, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=chroma_dir)
        
        # デフォルトチャネルの初期化
        self.get_or_create_collection(default_channel)
        print(f"[RuriRAG] Initialized. Available channels: {len(self.list_channels())}")

    def get_collection_name(self, channel_id: str) -> str:
        return sanitize_channel_name(channel_id)

    def get_or_create_collection(self, channel_id: str):
        col_name = self.get_collection_name(channel_id)
        return self.chroma_client.get_or_create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine", "display_name": channel_id}
        )

    def list_channels(self) -> List[Dict[str, Any]]:
        """全チャネルのリストと各チャネルのドキュメント数を返す"""
        collections = self.chroma_client.list_collections()
        channels = []
        for col in collections:
            meta = col.metadata or {}
            display_name = meta.get("display_name", col.name)
            channels.append({
                "id": col.name,
                "name": display_name,
                "count": col.count()
            })
        return channels

    def delete_channel(self, channel_id: str) -> bool:
        col_name = self.get_collection_name(channel_id)
        try:
            self.chroma_client.delete_collection(col_name)
            return True
        except Exception:
            return False

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        channel_id: str = "default"
    ) -> List[str]:
        """指定チャネルにドキュメントを埋め込み登録"""
        if not documents:
            return []

        col = self.get_or_create_collection(channel_id)

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(documents))]
        if metadatas is None:
            metadatas = [{} for _ in range(len(documents))]

        # Ruriの推奨プレフィックス「文章: 」付与
        prefixed_docs = [f"文章: {doc}" for doc in documents]
        embeddings = self.embed_model.encode(prefixed_docs, normalize_embeddings=True).tolist()

        col.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        return ids

    def search_and_rerank(
        self,
        query: str,
        channel_id: str = "default",
        initial_top_k: int = 10,
        final_top_n: int = 3
    ) -> List[Dict[str, Any]]:
        """指定チャネルでの検索とRuri-rerankerによる再順位付け"""
        col = self.get_or_create_collection(channel_id)
        if col.count() == 0:
            return []

        # クエリ用プレフィックス「クエリ: 」付与
        prefixed_query = f"クエリ: {query}"
        query_embedding = self.embed_model.encode([prefixed_query], normalize_embeddings=True)[0].tolist()

        k = min(initial_top_k, col.count())
        query_results = col.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=["documents", "metadatas", "distances"]
        )

        retrieved_docs = query_results["documents"][0] if query_results["documents"] else []
        retrieved_ids = query_results["ids"][0] if query_results["ids"] else []
        retrieved_metas = query_results["metadatas"][0] if query_results["metadatas"] else []

        if not retrieved_docs:
            return []

        # CrossEncoder リランク
        pairs = [[query, doc] for doc in retrieved_docs]
        rerank_scores = self.reranker.predict(pairs)

        ranked_items = []
        for doc_id, doc, meta, score in zip(retrieved_ids, retrieved_docs, retrieved_metas, rerank_scores):
            ranked_items.append({
                "id": doc_id,
                "content": doc,
                "metadata": meta,
                "rerank_score": float(score)
            })

        ranked_items.sort(key=lambda x: x["rerank_score"], reverse=True)
        return ranked_items[:final_top_n]

    def count(self, channel_id: str = "default") -> int:
        col = self.get_or_create_collection(channel_id)
        return col.count()

    def clear(self, channel_id: str = "default"):
        col_name = self.get_collection_name(channel_id)
        try:
            self.chroma_client.delete_collection(col_name)
        except Exception:
            pass
        self.get_or_create_collection(channel_id)
