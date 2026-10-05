import os
import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
import torch
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder


def sanitize_channel_name(name: str) -> str:
    """ChromaDBのコレクション名規則に合わせてサニタイズ (3-63文字, 英数字, アンダースコア, ハイフン)"""
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.strip())
    if not clean or not clean[0].isalnum():
        clean = "ch_" + clean
    if not clean[-1].isalnum():
        clean = clean + "_ch"
    if len(clean) < 3:
        clean = clean.ljust(3, '_')
    if len(clean) > 63:
        clean = clean[:63]
    return clean.lower()


def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion (RRF) で複数のランキングリストをマージ。
    各リストの各アイテムに 1/(k+rank) のスコアを付与して合算する。
    """
    scores: Dict[str, float] = {}
    items_by_id: Dict[str, Dict[str, Any]] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            doc_id = item["id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in items_by_id:
                items_by_id[doc_id] = item

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    merged = []
    for doc_id in sorted_ids:
        item = items_by_id[doc_id].copy()
        item["rrf_score"] = scores[doc_id]
        merged.append(item)
    return merged


class HybridRAGEngine:
    """
    ハイブリッドRAGエンジン:
    - Ruri (cl-nagoya/ruri-base): テキスト用 Embedding
    - Multimodal (jinaai/jina-clip-v1 または互換モデル): 画像・図形対応 Embedding
    - ChromaDB: テキスト用コレクション ({channel}_txt) + 画像用コレクション ({channel}_img)
    - Ruri Reranker: 両インデックスの結果を統合してリランク
    """

    def __init__(
        self,
        text_embed_model_name: str = "cl-nagoya/ruri-base",
        mm_embed_model_name: str = "jinaai/jina-clip-v1",
        rerank_model_name: str = "cl-nagoya/ruri-reranker-large",
        chroma_dir: str = "/app/data/chroma",
        default_channel: str = "default",
        load_mm_model: bool = True,
    ):
        self.device = "cuda" if torch.cuda.is_available() else (
            "mps" if torch.backends.mps.is_available() else "cpu"
        )
        print(f"[HybridRAG] Using device: {self.device}")

        # --- テキスト用 Embedding (Ruri) ---
        print(f"[HybridRAG] Loading Text Embedding: {text_embed_model_name}...")
        self.text_embed_model = SentenceTransformer(text_embed_model_name, device=self.device)
        self.text_embed_dim = self.text_embed_model.get_sentence_embedding_dimension()

        # --- マルチモーダル Embedding ---
        self.mm_embed_model = None
        self.mm_embed_dim = None
        self.load_mm_model = load_mm_model
        if load_mm_model:
            try:
                print(f"[HybridRAG] Loading Multimodal Embedding: {mm_embed_model_name}...")
                self.mm_embed_model = SentenceTransformer(
                    mm_embed_model_name,
                    device=self.device,
                    trust_remote_code=True,
                )
                self.mm_embed_dim = self.mm_embed_model.get_sentence_embedding_dimension()
                print(f"[HybridRAG] Multimodal model loaded. dim={self.mm_embed_dim}")
            except Exception as e:
                print(f"[HybridRAG] WARNING: Failed to load multimodal model: {e}")
                print("[HybridRAG] Falling back to text-only mode.")
                self.mm_embed_model = None

        # --- Reranker ---
        print(f"[HybridRAG] Loading Reranker: {rerank_model_name}...")
        self.reranker = CrossEncoder(rerank_model_name, device=self.device)

        # --- ChromaDB ---
        os.makedirs(chroma_dir, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=chroma_dir)

        # デフォルトチャネル初期化
        self._get_or_create_text_collection(default_channel)
        if self.mm_embed_model is not None:
            self._get_or_create_image_collection(default_channel)

        print(f"[HybridRAG] Ready. channels={len(self.list_channels())}, "
              f"multimodal={'ON' if self.mm_embed_model else 'OFF (text-only)'}")

    # ------------------------------------------------------------------ #
    #  コレクション名ヘルパー                                               #
    # ------------------------------------------------------------------ #

    def _text_col_name(self, channel_id: str) -> str:
        """テキスト用コレクション名: {sanitized}_txt"""
        base = sanitize_channel_name(channel_id)
        name = f"{base}_txt"
        return name[:63]

    def _image_col_name(self, channel_id: str) -> str:
        """画像用コレクション名: {sanitized}_img"""
        base = sanitize_channel_name(channel_id)
        name = f"{base}_img"
        return name[:63]

    def _get_or_create_text_collection(self, channel_id: str):
        col_name = self._text_col_name(channel_id)
        return self.chroma_client.get_or_create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine", "display_name": channel_id, "type": "text"}
        )

    def _get_or_create_image_collection(self, channel_id: str):
        col_name = self._image_col_name(channel_id)
        return self.chroma_client.get_or_create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine", "display_name": channel_id, "type": "image"}
        )

    # 後方互換用エイリアス
    def get_collection_name(self, channel_id: str) -> str:
        return self._text_col_name(channel_id)

    def get_or_create_collection(self, channel_id: str):
        return self._get_or_create_text_collection(channel_id)

    # ------------------------------------------------------------------ #
    #  チャネル管理                                                         #
    # ------------------------------------------------------------------ #

    def list_channels(self) -> List[Dict[str, Any]]:
        """全チャネルのリスト（テキスト+画像のペアを1チャネルとして集約）"""
        collections = self.chroma_client.list_collections()
        seen: Dict[str, Dict[str, Any]] = {}
        for col in collections:
            name = col.name
            # _txt / _img サフィックスを取り除いてチャネル名を特定
            if name.endswith("_txt"):
                base = name[:-4]
                col_type = "text"
            elif name.endswith("_img"):
                base = name[:-4]
                col_type = "image"
            else:
                base = name
                col_type = "text"

            meta = col.metadata or {}
            display_name = meta.get("display_name", base)
            if base not in seen:
                seen[base] = {
                    "id": base,
                    "name": display_name,
                    "text_count": 0,
                    "image_count": 0,
                }
            if col_type == "text":
                seen[base]["text_count"] = col.count()
            else:
                seen[base]["image_count"] = col.count()

        result = list(seen.values())
        for r in result:
            r["count"] = r["text_count"] + r["image_count"]
        return result

    def delete_channel(self, channel_id: str) -> bool:
        deleted = False
        for col_name in [self._text_col_name(channel_id), self._image_col_name(channel_id)]:
            try:
                self.chroma_client.delete_collection(col_name)
                deleted = True
            except Exception as e:
                print(f"[HybridRAG] delete_channel '{col_name}': {type(e).__name__}")
        return deleted

    def count(self, channel_id: str = "default") -> int:
        txt = self._get_or_create_text_collection(channel_id).count()
        img = 0
        if self.mm_embed_model is not None:
            try:
                img = self._get_or_create_image_collection(channel_id).count()
            except Exception:
                pass
        return txt + img

    def clear(self, channel_id: str = "default"):
        for col_name in [self._text_col_name(channel_id), self._image_col_name(channel_id)]:
            try:
                self.chroma_client.delete_collection(col_name)
            except Exception:
                pass
        self._get_or_create_text_collection(channel_id)
        if self.mm_embed_model is not None:
            self._get_or_create_image_collection(channel_id)

    # ------------------------------------------------------------------ #
    #  ドキュメント登録                                                     #
    # ------------------------------------------------------------------ #

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        channel_id: str = "default",
        modality: str = "text",   # "text" | "image"
    ) -> List[str]:
        """
        テキストまたは画像キャプション/alt-textをインデックスに登録。
        modality="text"  → Ruriモデルでテキストコレクションに登録
        modality="image" → マルチモーダルモデルで画像コレクションに登録
        """
        if not documents:
            return []

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(documents))]
        if metadatas is None:
            metadatas = [{} for _ in range(len(documents))]

        if modality == "image" and self.mm_embed_model is not None:
            # 画像説明テキストをマルチモーダルモデルでエンコード
            col = self._get_or_create_image_collection(channel_id)
            embeddings = self.mm_embed_model.encode(
                documents, normalize_embeddings=True, batch_size=8
            ).tolist()
        else:
            # テキストをRuriでエンコード（推奨プレフィックス付与）
            col = self._get_or_create_text_collection(channel_id)
            prefixed = [f"文章: {doc}" for doc in documents]
            embeddings = self.text_embed_model.encode(
                prefixed, normalize_embeddings=True
            ).tolist()

        # モダリティをメタデータに記録
        for meta in metadatas:
            meta["modality"] = modality

        col.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )
        return ids

    def add_image_bytes(
        self,
        image_bytes_list: List[bytes],
        captions: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        channel_id: str = "default",
    ) -> List[str]:
        """
        実画像バイト列からマルチモーダルEmbeddingを生成してインデックスに登録。
        jinaai/jina-clip-v1 は PIL.Image を直接受け取れる。
        """
        if self.mm_embed_model is None:
            raise RuntimeError("マルチモーダルモデルが読み込まれていません")

        from PIL import Image
        import io

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(image_bytes_list))]
        if metadatas is None:
            metadatas = [{} for _ in range(len(image_bytes_list))]
        if captions is None:
            captions = [f"image_{i}" for i in range(len(image_bytes_list))]

        pil_images = [Image.open(io.BytesIO(b)).convert("RGB") for b in image_bytes_list]

        col = self._get_or_create_image_collection(channel_id)
        embeddings = self.mm_embed_model.encode(
            pil_images, normalize_embeddings=True, batch_size=4
        ).tolist()

        for meta in metadatas:
            meta["modality"] = "image"

        col.add(
            documents=captions,   # キャプションをドキュメントとして保存
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )
        return ids

    # ------------------------------------------------------------------ #
    #  ハイブリッド検索 & Rerank                                           #
    # ------------------------------------------------------------------ #

    def _search_collection(
        self,
        col,
        query_embedding: List[float],
        k: int,
        modality_label: str,
    ) -> List[Dict[str, Any]]:
        """ChromaDBコレクションに対してベクトル検索を実行しリストを返す"""
        if col.count() == 0:
            return []
        actual_k = min(k, col.count())
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=actual_k,
            include=["documents", "metadatas", "distances"],
        )
        docs = [d for dl in (results.get("documents") or [[]]) for d in dl]
        ids_ = [i for il in (results.get("ids") or [[]]) for i in il]
        metas = [m for ml in (results.get("metadatas") or [[]]) for m in ml]
        items = []
        for doc_id, doc, meta in zip(ids_, docs, metas):
            items.append({
                "id": doc_id,
                "content": doc,
                "metadata": meta or {},
                "source_modality": modality_label,
            })
        return items

    def search_and_rerank(
        self,
        query: str,
        channel_id: str = "default",
        initial_top_k: int = 10,
        final_top_n: int = 3,
        query_image_bytes: Optional[bytes] = None,
    ) -> List[Dict[str, Any]]:
        """
        ハイブリッド検索 + Rerank:
        1. Ruri でテキストインデックスを検索
        2. マルチモーダルモデルで画像インデックスを検索（モデルがあれば）
        3. RRF でスコア統合
        4. Ruri Reranker で最終ランキング
        """
        # --- テキスト検索 ---
        text_col = self._get_or_create_text_collection(channel_id)
        ruri_query = f"クエリ: {query}"
        text_embedding = self.text_embed_model.encode(
            [ruri_query], normalize_embeddings=True
        )[0].tolist()
        text_results = self._search_collection(
            text_col, text_embedding, initial_top_k, "text"
        )

        # --- 画像インデックス検索 ---
        image_results: List[Dict[str, Any]] = []
        if self.mm_embed_model is not None:
            image_col = self._get_or_create_image_collection(channel_id)
            if image_col.count() > 0:
                if query_image_bytes is not None:
                    # 実画像でクエリ
                    from PIL import Image
                    import io
                    pil_img = Image.open(io.BytesIO(query_image_bytes)).convert("RGB")
                    mm_embedding = self.mm_embed_model.encode(
                        [pil_img], normalize_embeddings=True
                    )[0].tolist()
                else:
                    # テキストクエリをマルチモーダルモデルでエンコード
                    mm_embedding = self.mm_embed_model.encode(
                        [query], normalize_embeddings=True
                    )[0].tolist()
                image_results = self._search_collection(
                    image_col, mm_embedding, initial_top_k, "image"
                )

        # --- RRF マージ ---
        all_lists = [r for r in [text_results, image_results] if r]
        if not all_lists:
            return []
        if len(all_lists) == 1:
            merged = all_lists[0]
        else:
            merged = reciprocal_rank_fusion(all_lists)

        # 上位候補を Reranker にかける
        rerank_pool = merged[:min(initial_top_k * 2, len(merged))]

        pairs = [[query, item["content"]] for item in rerank_pool]
        rerank_scores = self.reranker.predict(pairs)

        for item, score in zip(rerank_pool, rerank_scores):
            item["rerank_score"] = float(score)

        rerank_pool.sort(key=lambda x: x["rerank_score"], reverse=True)
        return rerank_pool[:final_top_n]

    # ------------------------------------------------------------------ #
    #  ドキュメント一覧取得                                                 #
    # ------------------------------------------------------------------ #

    def get_documents_list(self, channel_id: str = "default") -> List[Dict[str, Any]]:
        """テキスト+画像の全ドキュメント一覧を返す"""
        results = []
        for col_getter, label in [
            (self._get_or_create_text_collection, "text"),
            (self._get_or_create_image_collection, "image"),
        ]:
            if label == "image" and self.mm_embed_model is None:
                continue
            col = col_getter(channel_id)
            if col.count() == 0:
                continue
            raw = col.get(include=["documents", "ids", "metadatas"])
            docs_flat = [d for dl in (raw.get("documents") or [[]]) for d in dl]
            ids_flat = [i for il in (raw.get("ids") or [[]]) for i in il]
            metas_flat = [m for ml in (raw.get("metadatas") or [[]]) for m in ml]
            for doc_id, content, meta in zip(ids_flat, docs_flat, metas_flat):
                results.append({
                    "id": doc_id,
                    "content": content,
                    "metadata": meta or {},
                    "length": len(content),
                    "modality": label,
                })
        return results


# 後方互換エイリアス
RuriRAGEngine = HybridRAGEngine
