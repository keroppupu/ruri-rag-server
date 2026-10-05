import os
from typing import List, Dict, Any, Optional
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.rag_engine import HybridRAGEngine
from app.document_parser import parse_and_chunk_file, extract_images_from_file

# 環境変数
EMBED_MODEL = os.getenv("RURI_EMBED_MODEL", "cl-nagoya/ruri-base")
MM_EMBED_MODEL = os.getenv("MM_EMBED_MODEL", "jinaai/jina-clip-v1")
RERANK_MODEL = os.getenv("RURI_RERANK_MODEL", "cl-nagoya/ruri-reranker-large")
CHROMA_DIR = os.getenv("CHROMA_DIR", "/app/data/chroma")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
LOAD_MM_MODEL = os.getenv("LOAD_MM_MODEL", "true").lower() in ("true", "1", "yes")

app = FastAPI(
    title="Ruri ハイブリッド RAG サーバー",
    description=(
        "テキスト (Ruri) + 画像/図形 (jina-clip-v1) のハイブリッドEmbedding、"
        "RRF統合 & Ruri Rerankerによる高精度日本語RAGサーバー"
    ),
    version="3.0.0"
)

# 静的ファイルのパス解決
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

rag_engine: Optional[HybridRAGEngine] = None


@app.on_event("startup")
def startup_event():
    global rag_engine
    rag_engine = HybridRAGEngine(
        text_embed_model_name=EMBED_MODEL,
        mm_embed_model_name=MM_EMBED_MODEL,
        rerank_model_name=RERANK_MODEL,
        chroma_dir=CHROMA_DIR,
        load_mm_model=LOAD_MM_MODEL,
    )


# ------------------------------------------------------------------ #
#  スキーマ定義                                                         #
# ------------------------------------------------------------------ #

class CreateChannelRequest(BaseModel):
    name: str = Field(..., description="チャネル名（英数字またはハイフン、日本語も可）")

class AddDocumentsRequest(BaseModel):
    documents: List[str] = Field(..., description="テキストのリスト")
    metadatas: Optional[List[Dict[str, Any]]] = Field(None, description="メタデータ")
    ids: Optional[List[str]] = Field(None, description="ドキュメントID")
    channel_id: Optional[str] = Field("default", description="対象チャネル")
    modality: Optional[str] = Field("text", description="'text' または 'image'")

class SearchRequest(BaseModel):
    query: str = Field(..., description="検索クエリ")
    initial_top_k: int = Field(10, description="Embeddingベクトル検索で取得する件数")
    final_top_n: int = Field(3, description="Rerank後に返す上位件数")
    channel_id: Optional[str] = Field("default", description="対象チャネル")

class RAGRequest(BaseModel):
    query: str = Field(..., description="質問文")
    initial_top_k: int = Field(10, description="一次検索件数")
    final_top_n: int = Field(3, description="リランク後件数")
    generate_answer: bool = Field(True, description="LLMで回答を生成するか")
    system_prompt: Optional[str] = Field(None, description="カスタムシステムプロンプト")
    channel_id: Optional[str] = Field("default", description="対象チャネル")


# ------------------------------------------------------------------ #
#  Web UI & ヘルス                                                     #
# ------------------------------------------------------------------ #

@app.get("/", response_class=FileResponse)
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Ruri Hybrid RAG Server Running. UI file not found."}


@app.get("/health")
def health():
    mm_status = "loaded" if (rag_engine and rag_engine.mm_embed_model is not None) else "not_loaded"
    return {
        "status": "healthy",
        "version": "3.0.0",
        "text_embedding_model": EMBED_MODEL,
        "multimodal_embedding_model": MM_EMBED_MODEL,
        "multimodal_status": mm_status,
        "reranker_model": RERANK_MODEL,
        "channel_count": len(rag_engine.list_channels()) if rag_engine else 0,
    }


# ------------------------------------------------------------------ #
#  チャネル管理 API                                                    #
# ------------------------------------------------------------------ #

@app.get("/channels")
def list_channels():
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    return rag_engine.list_channels()


@app.post("/channels")
def create_channel(req: CreateChannelRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    try:
        col = rag_engine.get_or_create_collection(req.name)
        return {"message": "チャネルを作成しました", "channel": req.name, "id": col.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"チャネル作成失敗: {str(e)}")


@app.delete("/channels/{channel_id}")
def delete_channel(channel_id: str):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    success = rag_engine.delete_channel(channel_id)
    if not success:
        raise HTTPException(status_code=404, detail="チャネル削除失敗または存在しません")
    return {"message": f"チャネル '{channel_id}' を削除しました"}


@app.get("/channels/{channel_id}/documents/count")
def get_channel_doc_count(channel_id: str):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    return {"channel": channel_id, "count": rag_engine.count(channel_id)}


@app.delete("/channels/{channel_id}/documents")
def clear_channel_documents(channel_id: str):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    rag_engine.clear(channel_id)
    return {"message": f"チャネル '{channel_id}' 内の全ドキュメントをクリアしました"}


@app.delete("/channels/{channel_id}/documents/{doc_id}")
def delete_document(channel_id: str, doc_id: str):
    """指定ドキュメントを個別削除"""
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    # テキスト・画像両コレクションで削除を試みる
    deleted = False
    for col_getter in [
        rag_engine._get_or_create_text_collection,
        rag_engine._get_or_create_image_collection,
    ]:
        try:
            col = col_getter(channel_id)
            col.delete(ids=[doc_id])
            deleted = True
        except Exception:
            pass
    if not deleted:
        raise HTTPException(status_code=400, detail=f"ドキュメント削除失敗: '{doc_id}'")
    return {"message": f"ドキュメント '{doc_id}' を削除しました", "channel": channel_id, "id": doc_id}


# ------------------------------------------------------------------ #
#  ファイルアップロード（テキスト + 画像の両方を自動インデックス化）     #
# ------------------------------------------------------------------ #

@app.post("/channels/{channel_id}/upload")
async def upload_file_to_channel(
    channel_id: str,
    file: UploadFile = File(...),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50),
    index_images: bool = Form(True),   # 画像もインデックスするか
):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")

    file_bytes = await file.read()
    filename = file.filename

    text_chunks_count = 0
    image_chunks_count = 0

    # --- テキストチャンク登録 ---
    try:
        chunks_data = parse_and_chunk_file(
            file_bytes=file_bytes,
            filename=filename,
            chunk_size=chunk_size,
            overlap=chunk_overlap
        )
        if chunks_data:
            documents = [c["content"] for c in chunks_data]
            metadatas = [c["metadata"] for c in chunks_data]
            doc_ids = rag_engine.add_documents(
                documents=documents,
                metadatas=metadatas,
                channel_id=channel_id,
                modality="text",
            )
            text_chunks_count = len(doc_ids)
    except ValueError:
        pass  # 画像ファイルなどテキスト抽出できない場合はスキップ
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"テキスト解析エラー: {str(e)}")

    # --- 画像抽出・登録 ---
    if index_images and rag_engine.mm_embed_model is not None:
        try:
            image_data = extract_images_from_file(file_bytes, filename)
            if image_data:
                image_bytes_list = [d["image_bytes"] for d in image_data]
                captions = [d["caption"] for d in image_data]
                metadatas_img = [d["metadata"] for d in image_data]
                img_ids = rag_engine.add_image_bytes(
                    image_bytes_list=image_bytes_list,
                    captions=captions,
                    metadatas=metadatas_img,
                    channel_id=channel_id,
                )
                image_chunks_count = len(img_ids)
        except Exception as e:
            # 画像登録失敗はエラーにせず警告として返す
            print(f"[Upload] Image indexing failed for '{filename}': {e}")

    if text_chunks_count == 0 and image_chunks_count == 0:
        raise HTTPException(status_code=400, detail="テキストも画像も抽出できませんでした")

    return {
        "message": f"'{filename}' を登録しました",
        "filename": filename,
        "text_chunks": text_chunks_count,
        "image_chunks": image_chunks_count,
        "channel": channel_id,
        "total_documents": rag_engine.count(channel_id),
    }


# ------------------------------------------------------------------ #
#  画像単体アップロード API                                            #
# ------------------------------------------------------------------ #

@app.post("/channels/{channel_id}/upload_image")
async def upload_image_to_channel(
    channel_id: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
):
    """画像ファイル単体をマルチモーダルインデックスに登録"""
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    if rag_engine.mm_embed_model is None:
        raise HTTPException(status_code=503, detail="マルチモーダルモデルが読み込まれていません")

    file_bytes = await file.read()
    cap = caption or file.filename

    try:
        img_ids = rag_engine.add_image_bytes(
            image_bytes_list=[file_bytes],
            captions=[cap],
            metadatas=[{"source": file.filename, "section": file.filename, "modality": "image"}],
            channel_id=channel_id,
        )
        return {
            "message": f"画像 '{file.filename}' を登録しました",
            "id": img_ids[0],
            "caption": cap,
            "channel": channel_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"画像登録エラー: {str(e)}")


# ------------------------------------------------------------------ #
#  検索 & RAG API                                                     #
# ------------------------------------------------------------------ #

@app.post("/channels/{channel_id}/search")
def search_channel(channel_id: str, req: SearchRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    try:
        results = rag_engine.search_and_rerank(
            query=req.query,
            channel_id=channel_id,
            initial_top_k=req.initial_top_k,
            final_top_n=req.final_top_n,
        )
        return {
            "channel": channel_id,
            "query": req.query,
            "results": results,
            "text_index": "ruri-base",
            "image_index": "jina-clip-v1" if rag_engine.mm_embed_model else "disabled",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"検索エラー: {str(e)}")


@app.post("/channels/{channel_id}/rag")
async def rag_channel(channel_id: str, req: RAGRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")

    # 1. ハイブリッド検索 & Rerank
    contexts = rag_engine.search_and_rerank(
        query=req.query,
        channel_id=channel_id,
        initial_top_k=req.initial_top_k,
        final_top_n=req.final_top_n,
    )

    if not req.generate_answer:
        return {
            "channel": channel_id,
            "query": req.query,
            "contexts": contexts,
            "answer": None,
        }

    # 2. プロンプト生成
    context_str = "\n\n".join([
        f"[{i+1}] (出典: {item.get('metadata', {}).get('source', '不明')}"
        f", モダリティ: {item.get('source_modality', '?')}) {item['content']}"
        for i, item in enumerate(contexts)
    ])

    system = req.system_prompt or (
        "あなたは親切なAIアシスタントです。"
        "提供された参考情報（テキスト・図表のキャプションを含む）に基づいて、"
        "正確かつ簡潔に日本語で回答してください。"
        "参考情報にない場合はその旨を正直に述べてください。"
    )
    user_prompt = f"""以下の参考情報を基に質問に答えてください。

【参考情報】
{context_str if context_str else "（関連する参考情報は見つかりませんでした）"}

【質問】
{req.query}
"""

    answer = None
    llm_status = "ok"

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("message", {}).get("content", "")
            else:
                llm_status = f"Ollama error: HTTP {resp.status_code}"
    except Exception as e:
        llm_status = f"LLM 接続スキップ/エラー: {str(e)}"

    return {
        "channel": channel_id,
        "query": req.query,
        "contexts": contexts,
        "answer": answer,
        "llm_status": llm_status,
        "prompt_used": user_prompt,
    }


# ------------------------------------------------------------------ #
#  後方互換エンドポイント (default チャネル)                           #
# ------------------------------------------------------------------ #

@app.post("/documents")
def legacy_add_documents(req: AddDocumentsRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    return rag_engine.add_documents(
        documents=req.documents,
        metadatas=req.metadatas,
        ids=req.ids,
        channel_id=req.channel_id or "default",
        modality=req.modality or "text",
    )


@app.post("/search")
def legacy_search(req: SearchRequest):
    return search_channel(req.channel_id or "default", req)


@app.post("/rag")
async def legacy_rag(req: RAGRequest):
    return await rag_channel(req.channel_id or "default", req)
