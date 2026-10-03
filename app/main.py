import os
from typing import List, Dict, Any, Optional
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.rag_engine import RuriRAGEngine
from app.document_parser import parse_and_chunk_file

# 環境変数
EMBED_MODEL = os.getenv("RURI_EMBED_MODEL", "cl-nagoya/ruri-base")
RERANK_MODEL = os.getenv("RURI_RERANK_MODEL", "cl-nagoya/ruri-reranker-large")
CHROMA_DIR = os.getenv("CHROMA_DIR", "/app/data/chroma")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")

app = FastAPI(
    title="Ruri 日本語 RAG サーバー",
    description="Excel/Word/PowerPoint/PDF対応、マルチチャネル対応、Ruri Embedding & Rerankerを搭載した日本語特化RAGサーバー",
    version="2.0.0"
)

# 静的ファイルのパス解決
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

rag_engine: Optional[RuriRAGEngine] = None

@app.on_event("startup")
def startup_event():
    global rag_engine
    rag_engine = RuriRAGEngine(
        embed_model_name=EMBED_MODEL,
        rerank_model_name=RERANK_MODEL,
        chroma_dir=CHROMA_DIR
    )

# --- スキーマ定義 ---

class CreateChannelRequest(BaseModel):
    name: str = Field(..., description="チャネル名（英数字またはハイフン、日本語も可）")

class AddDocumentsRequest(BaseModel):
    documents: List[str] = Field(..., description="テキストのリスト")
    metadatas: Optional[List[Dict[str, Any]]] = Field(None, description="メタデータ")
    ids: Optional[List[str]] = Field(None, description="ドキュメントID")
    channel_id: Optional[str] = Field("default", description="対象チャネル")

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

# --- Web UI ルーティング ---

@app.get("/", response_class=FileResponse)
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Ruri RAG Server Running. UI file not found."}

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "embedding_model": EMBED_MODEL,
        "reranker_model": RERANK_MODEL,
        "channel_count": len(rag_engine.list_channels()) if rag_engine else 0
    }

# --- チャネル管理 API ---

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

# --- ファイルアップロード (Excel/Word/PowerPoint/PDF/Text) ---

@app.post("/channels/{channel_id}/upload")
async def upload_file_to_channel(
    channel_id: str,
    file: UploadFile = File(...),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50)
):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")

    try:
        file_bytes = await file.read()
        chunks_data = parse_and_chunk_file(
            file_bytes=file_bytes,
            filename=file.filename,
            chunk_size=chunk_size,
            overlap=chunk_overlap
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ファイル解析エラー: {str(e)}")

    if not chunks_data:
        raise HTTPException(status_code=400, detail="テキストを抽出できませんでした")

    documents = [c["content"] for c in chunks_data]
    metadatas = [c["metadata"] for c in chunks_data]

    try:
        doc_ids = rag_engine.add_documents(
            documents=documents,
            metadatas=metadatas,
            channel_id=channel_id
        )
        return {
            "message": f"'{file.filename}' を {len(doc_ids)} チャンクに分割・登録しました",
            "filename": file.filename,
            "chunks_count": len(doc_ids),
            "channel": channel_id,
            "total_documents": rag_engine.count(channel_id)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ベクトルDB登録エラー: {str(e)}")

# --- 検索 & RAG API ---

@app.post("/channels/{channel_id}/search")
def search_channel(channel_id: str, req: SearchRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")
    try:
        results = rag_engine.search_and_rerank(
            query=req.query,
            channel_id=channel_id,
            initial_top_k=req.initial_top_k,
            final_top_n=req.final_top_n
        )
        return {
            "channel": channel_id,
            "query": req.query,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"検索エラー: {str(e)}")

@app.post("/channels/{channel_id}/rag")
async def rag_channel(channel_id: str, req: RAGRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="エンジン未初期化")

    # 1. 検索 & Rerank
    contexts = rag_engine.search_and_rerank(
        query=req.query,
        channel_id=channel_id,
        initial_top_k=req.initial_top_k,
        final_top_n=req.final_top_n
    )

    if not req.generate_answer:
        return {
            "channel": channel_id,
            "query": req.query,
            "contexts": contexts,
            "answer": None
        }

    # 2. プロンプト生成
    context_str = "\n\n".join([
        f"[{i+1}] (出典: {item.get('metadata', {}).get('source', '不明')}) {item['content']}"
        for i, item in enumerate(contexts)
    ])

    system = req.system_prompt or "あなたは親切なAIアシスタントです。提供された参考情報に基づいて、正確かつ簡潔に日本語で回答してください。参考情報にない場合はその旨を正直に述べてください。"
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
        "prompt_used": user_prompt
    }

# --- 後方互換エンドポイント (default チャネル) ---

@app.post("/documents")
def legacy_add_documents(req: AddDocumentsRequest):
    return rag_engine.add_documents(
        documents=req.documents,
        metadatas=req.metadatas,
        ids=req.ids,
        channel_id=req.channel_id or "default"
    )

@app.post("/search")
def legacy_search(req: SearchRequest):
    return search_channel(req.channel_id or "default", req)

@app.post("/rag")
async def legacy_rag(req: RAGRequest):
    return await rag_channel(req.channel_id or "default", req)
