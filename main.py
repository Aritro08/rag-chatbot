import os
import tempfile
import json
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, AIMessage
import logging
import shutil

from models.pydantic_models import ModelName, QueryInput, QueryResponse, DocumentInfo, DeleteFileRequest
from utils.utils import get_or_create_session_id, history_to_messages, append_to_history
from utils.db_utils import get_chat_history, insert_chat_history, get_all_documents, insert_document_record, delete_document, create_chat_history, create_documents_store, get_all_sessions, get_session_messages
from utils.vector_utils import index_document_to_vector_store, delete_doc_from_vector_store
from utils.langchain_utils import context_chain
from graph.agent import agent

app = FastAPI()
load_dotenv()
logging.basicConfig(level=logging.INFO)

cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
allow_credentials = cors_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

create_documents_store()
create_chat_history()


@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/chat", response_model=QueryResponse)
def chat(query_input: QueryInput):
    session_id = get_or_create_session_id(query_input.session_id)
    logging.info(f"Session ID - {session_id} | User query - {query_input.question} | Model name - {query_input.model_name.value}")

    try:
        chat_history = get_chat_history(session_id)
        messages = history_to_messages(chat_history)

        standalone_query = context_chain.invoke({
            "chat_history": messages,
            "input_query": query_input.question
        })

        messages = append_to_history(messages, HumanMessage(content=standalone_query))
        result = agent.invoke({
            "messages": messages,
            "model_name": query_input.model_name.value,
        })

        last_message = next((message for message in reversed(result['messages']) if isinstance(message, AIMessage)), None)
        if last_message:
            answer = last_message.content
        else:
            answer = "I apologise but I couldn't generate a response this time."

        insert_chat_history(session_id, query_input.question, answer, query_input.model_name)
        logging.info(f"Session ID - {session_id} | AI Response - {answer}")

        return QueryResponse(answer=answer, session_id=session_id, model_name=query_input.model_name)
    
    except Exception as e:
        logging.error(f"Error while generating response - {e}")
        raise HTTPException(500, f"Error while generating response - {str(e)}")


def _chunk_to_text(chunk) -> str:
    """Extract textual content from a LangChain message chunk payload."""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(text)
        return "".join(parts)
    return ""


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


NODE_TITLES = {
    "router": "Route Query",
    "retriever_selector": "Pick Retrieval Strategy",
    "rag": "Retrieve Context",
    "web": "Run Web Search",
    "answer": "Compose Final Answer",
}

NODE_START_DETAILS = {
    "router": "Deciding whether to answer directly or gather context.",
    "retriever_selector": "Choosing between hybrid and vector retrieval.",
    "rag": "Searching indexed documents for relevant evidence.",
    "web": "Looking up additional information on the web.",
    "answer": "Preparing the final response.",
}


def _preview_text(value, max_len: int = 180) -> str:
    if value is None:
        return ""

    if isinstance(value, (str, int, float, bool)):
        text = str(value)
    else:
        try:
            text = json.dumps(value, default=str)
        except Exception:
            text = str(value)

    normalized = " ".join(text.split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 1] + "…"


def _node_end_detail(node: str, output) -> str:
    output_dict = output if isinstance(output, dict) else {}
    route = output_dict.get("route")

    if node == "router":
        if route == "rag":
            return "Route selected: use RAG context."
        if route == "answer":
            return "Route selected: answer directly."
        if route == "end":
            return "Route selected: end with a short conversational reply."
        return "Routing completed."

    if node == "retriever_selector":
        mode = output_dict.get("retriever_mode")
        if mode in {"hybrid", "vector"}:
            return f"Retriever selected: {mode}."
        return "Retriever strategy selected."

    if node == "rag":
        if route == "answer":
            return "Retrieved context is sufficient to answer."
        if route == "web":
            return "Context is insufficient; switching to web search."
        return "Retrieval completed."

    if node == "web":
        web_preview = _preview_text(output_dict.get("web"), 140)
        if web_preview:
            return f"Web results ready: {web_preview}"
        return "Web search completed."

    if node == "answer":
        return "Answer generation finished."

    return ""


def _thinking_payload_from_event(event: dict) -> dict | None:
    event_type = event.get("event")
    metadata = event.get("metadata") or {}
    data = event.get("data") or {}
    node = metadata.get("langgraph_node")

    if event_type == "on_chain_start" and node in NODE_TITLES:
        return {
            "type": "thinking",
            "key": f"node:{node}",
            "kind": "node",
            "status": "running",
            "title": NODE_TITLES[node],
            "detail": NODE_START_DETAILS.get(node, "Running step..."),
        }

    if event_type == "on_chain_end" and node in NODE_TITLES:
        return {
            "type": "thinking",
            "key": f"node:{node}",
            "kind": "node",
            "status": "done",
            "title": NODE_TITLES[node],
            "detail": _node_end_detail(node, data.get("output")),
        }

    if event_type == "on_tool_start":
        tool_name = str(event.get("name") or "Tool").strip() or "Tool"
        run_id = str(event.get("run_id") or tool_name)
        input_preview = _preview_text(data.get("input"))
        return {
            "type": "thinking",
            "key": f"tool:{run_id}",
            "kind": "tool",
            "status": "running",
            "title": f"Tool Call: {tool_name}",
            "detail": f"Input: {input_preview}" if input_preview else "Running tool call...",
        }

    if event_type == "on_tool_end":
        tool_name = str(event.get("name") or "Tool").strip() or "Tool"
        run_id = str(event.get("run_id") or tool_name)
        output_preview = _preview_text(data.get("output"))
        return {
            "type": "thinking",
            "key": f"tool:{run_id}",
            "kind": "tool",
            "status": "done",
            "title": f"Tool Call: {tool_name}",
            "detail": f"Output: {output_preview}" if output_preview else "Tool call finished.",
        }

    if event_type == "on_chat_model_start" and node == "answer":
        return {
            "type": "thinking",
            "key": "phase:answer_generation",
            "kind": "system",
            "status": "running",
            "title": "Draft Final Response",
            "detail": "Synthesizing the final answer.",
        }

    if event_type == "on_chat_model_end" and node == "answer":
        return {
            "type": "thinking",
            "key": "phase:answer_generation",
            "kind": "system",
            "status": "done",
            "title": "Draft Final Response",
            "detail": "Final answer draft is ready to stream.",
        }

    return None


@app.post("/chat/stream")
async def chat_stream(query_input: QueryInput):
    session_id = get_or_create_session_id(query_input.session_id)
    logging.info(
        f"Session ID - {session_id} | User query - {query_input.question} | Model name - {query_input.model_name.value}"
    )

    try:
        chat_history = get_chat_history(session_id)
        messages = history_to_messages(chat_history)

        standalone_query = context_chain.invoke({
            "chat_history": messages,
            "input_query": query_input.question
        })

        messages = append_to_history(messages, HumanMessage(content=standalone_query))
    except Exception as e:
        logging.error(f"Failed to prepare chat stream - {e}")
        raise HTTPException(500, f"Error while preparing response stream - {str(e)}")

    async def event_stream():
        answer_chunks: list[str] = []
        try:
            # Send session metadata early so clients can recover if the stream drops mid-response.
            yield _sse_event({
                "type": "start",
                "session_id": session_id,
                "model_name": query_input.model_name.value,
            })

            stream_iter = agent.astream_events(
                {
                    "messages": messages,
                    "model_name": query_input.model_name.value,
                },
                version="v2",
            ).__aiter__()

            next_event_task: asyncio.Task | None = None
            while True:
                if next_event_task is None:
                    next_event_task = asyncio.create_task(stream_iter.__anext__())

                done, _ = await asyncio.wait({next_event_task}, timeout=12.0)
                if not done:
                    # Heartbeat helps prevent intermediary proxy idle timeouts.
                    yield _sse_event({"type": "ping"})
                    continue

                try:
                    event = next_event_task.result()
                except StopAsyncIteration:
                    next_event_task = None
                    break
                finally:
                    next_event_task = None

                thinking_payload = _thinking_payload_from_event(event)
                if thinking_payload:
                    yield _sse_event(thinking_payload)

                event_type = event.get("event")
                if event_type != "on_chat_model_stream":
                    continue

                metadata = event.get("metadata") or {}
                if metadata.get("langgraph_node") != "answer":
                    continue

                chunk = ((event.get("data") or {}).get("chunk"))
                token_text = _chunk_to_text(chunk)
                if not token_text:
                    continue

                answer_chunks.append(token_text)
                yield _sse_event({"type": "token", "content": token_text})

            final_answer = "".join(answer_chunks).strip()
            if not final_answer:
                result = await agent.ainvoke({
                    "messages": messages,
                    "model_name": query_input.model_name.value,
                })
                last_message = next((message for message in reversed(result["messages"]) if isinstance(message, AIMessage)), None)
                final_answer = last_message.content if last_message else "I apologise but I couldn't generate a response this time."
                yield _sse_event({"type": "token", "content": final_answer})

            yield _sse_event({
                "type": "done",
                "session_id": session_id,
                "model_name": query_input.model_name.value,
            })
            
            try:
                insert_chat_history(session_id, query_input.question, final_answer, query_input.model_name)
                logging.info(f"Session ID - {session_id} | AI Response - {final_answer}")
            except Exception as persist_error:
                logging.error(f"Failed to persist chat history for session {session_id} - {persist_error}")

        except Exception as e:
            logging.error(f"Error while streaming response - {e}")
            yield _sse_event({"type": "error", "message": f"Error while generating response - {str(e)}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    
@app.post("/upload-doc")
def upload_and_index_document(file: UploadFile = File(...)):
    allowed_extensions = [".pdf", ".docx", ".html"]
    file_extension = os.path.splitext(file.filename)[1].lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(400, f"Unsupported file types. Allowed file types are - {', '.join(allowed_extensions)}")
    
    temp_file_path = None
    try:
        suffix = os.path.splitext(file.filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name

        file_id = insert_document_record(file.filename)
        success = index_document_to_vector_store(temp_file_path, file_id)

        if success:
            return {"message": f"File {file.filename} has been successfully uploaded and ingested.", "file_id": file_id}
        else:
            delete_document(file_id)
            raise HTTPException(500, f"Failed to ingest file {file.filename}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)  

@app.get("/list-docs", response_model=list[DocumentInfo])
def list_documents():
    docs = get_all_documents()
    return docs

@app.get("/chat-sessions")
def list_chat_sessions():
    """Return all sessions with their session_id, first user query and start time."""
    return get_all_sessions()

@app.get("/chat-sessions/{session_id}")
def get_chat_session_messages(session_id: str):
    """Return all user/assistant message pairs for a given session."""
    return get_session_messages(session_id)

@app.post("/delete-doc")
def delete_uploaded_document(request: DeleteFileRequest):
    chroma_delete_success = delete_doc_from_vector_store(request.file_id)

    if chroma_delete_success:
        db_delete_success = delete_document(request.file_id)
        if db_delete_success:
            return {"message": f"Successfully deleted document with file_id - {request.file_id}"}
        else:
            return {"message": f"Deleted document with file_id - {request.file_id} from chroma but failed to delete from db."}
    else:
        return {"message": f"Failed to delete document with file_id - {request.file_id}"}
