#!/usr/bin/env python3
"""
Ruri RAG Server 用 Model Context Protocol (MCP) stdio サーバー
GitLab Duo / VS Code GitLab Workflow / Claude Desktop / Cursor 等から
RAGサーバーの検索・知識取得・チャネル管理を呼び出すためのブリッジです。
外部依存関係なし（Python 3 標準ライブラリのみ）で動作します。
"""

import sys
import json
import os
import urllib.request
import urllib.error

RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8000").rstrip("/")

def log(msg: str):
    sys.stderr.write(f"[ruri-mcp] {msg}\n")
    sys.stderr.flush()

def http_get(path: str):
    url = f"{RAG_SERVER_URL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Ruri-MCP-Server/1.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))

def http_post(path: str, data: dict):
    url = f"{RAG_SERVER_URL}{path}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Ruri-MCP-Server/1.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))

TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "Ruriモデル（ruri-base + ruri-reranker-large）を用いて、指定チャネルのナレッジベースから高精度なセマンティック検索とリランクを実行し、関連ドキュメントを取得します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索クエリ・質問文"
                },
                "channel_id": {
                    "type": "string",
                    "description": "検索対象のチャネル名（デフォルト: 'default'）",
                    "default": "default"
                },
                "top_n": {
                    "type": "integer",
                    "description": "リランク後に返す上位ドキュメント件数（デフォルト: 3）",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "ask_rag",
        "description": "指定チャネル内のドキュメントを検索・リランクし、OllamaなどのローカルLLMを用いて回答を生成して返します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "質問文"
                },
                "channel_id": {
                    "type": "string",
                    "description": "対象チャネル名（デフォルト: 'default'）",
                    "default": "default"
                },
                "top_n": {
                    "type": "integer",
                    "description": "参照する根拠ドキュメント件数",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_channels",
        "description": "利用可能なすべてのRAGチャネル名と、各チャネルに登録されているドキュメント件数のリストを取得します。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "index_text",
        "description": "テキストデータを指定チャネルのナレッジベースに登録・ベクトル化します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "登録するテキスト本文"
                },
                "channel_id": {
                    "type": "string",
                    "description": "登録先チャネル名（デフォルト: 'default'）",
                    "default": "default"
                },
                "source": {
                    "type": "string",
                    "description": "ドキュメントの出典・識別名（例: 'GitLab Issue #12'）"
                }
            },
            "required": ["text"]
        }
    }
]

def handle_tool_call(tool_name: str, arguments: dict) -> str:
    try:
        if tool_name == "list_channels":
            channels = http_get("/channels")
            return json.dumps(channels, ensure_ascii=False, indent=2)

        elif tool_name == "search_knowledge_base":
            query = arguments["query"]
            channel_id = arguments.get("channel_id", "default")
            top_n = arguments.get("top_n", 3)
            res = http_post(f"/channels/{channel_id}/search", {
                "query": query,
                "initial_top_k": top_n * 3,
                "final_top_n": top_n
            })
            results = res.get("results", [])
            if not results:
                return f"チャネル '{channel_id}' 内に関連するドキュメントは見つかりませんでした。"

            formatted = []
            for i, r in enumerate(results, 1):
                src = r.get("metadata", {}).get("source", "不明")
                score = r.get("rerank_score", 0)
                formatted.append(f"[{i}] 出典: {src} (Rerankスコア: {score:.3f})\n{r['content']}")
            return "\n\n".join(formatted)

        elif tool_name == "ask_rag":
            query = arguments["query"]
            channel_id = arguments.get("channel_id", "default")
            top_n = arguments.get("top_n", 3)
            res = http_post(f"/channels/{channel_id}/rag", {
                "query": query,
                "initial_top_k": top_n * 3,
                "final_top_n": top_n,
                "generate_answer": True
            })
            answer = res.get("answer") or "回答を生成できませんでした。"
            contexts = res.get("contexts", [])
            sources = ", ".join(set([c.get("metadata", {}).get("source", "不明") for c in contexts]))
            return f"{answer}\n\n(参照元: {sources})"

        elif tool_name == "index_text":
            text = arguments["text"]
            channel_id = arguments.get("channel_id", "default")
            source = arguments.get("source", "MCP Client")
            res = http_post(f"/documents", {
                "documents": [text],
                "metadatas": [{"source": source}],
                "channel_id": channel_id
            })
            return json.dumps(res, ensure_ascii=False)

        else:
            return f"未知のツール名です: {tool_name}"

    except urllib.error.URLError as e:
        return f"RAGサーバー ({RAG_SERVER_URL}) への通信エラー: {str(e)}"
    except Exception as e:
        return f"ツール実行エラー: {str(e)}"

def process_message(msg: dict):
    msg_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "ruri-rag-mcp",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "notifications/initialized":
        return None

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": TOOLS
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        result_text = handle_tool_call(tool_name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": result_text
                    }
                ]
            }
        }

    else:
        if msg_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
        return None

def main():
    log("Ruri RAG MCP Server started (stdio mode)")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            response = process_message(msg)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as e:
            log(f"Error parsing message: {e}")

if __name__ == "__main__":
    main()
