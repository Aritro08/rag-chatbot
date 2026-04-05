import os
import tempfile
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, AIMessage
import logging
import shutil

from models.pydantic_models import (
    ModelName,
    QueryInput,
    QueryResponse,
    DocumentInfo,
    DeleteFileRequest,
)
from utils.utils import get_or_create_session_id, history_to_messages, append_to_history
from utils.db_utils import (
    get_chat_history,
    insert_chat_history,
    insert_chat_history_with_thinking_steps,
    get_all_documents,
    insert_document_record,
    delete_document,
    create_chat_history,
    create_documents_store,
    get_all_sessions,
    get_session_messages,
    create_thinking_steps_table,
    insert_thinking_steps,
    get_session_messages_with_thinking,
)
from utils.vector_utils import (
    index_document_to_vector_store,
    delete_doc_from_vector_store,
)
from utils.langchain_utils import context_chain
from utils.streaming_utils import (
    chunk_to_text,
    extract_ai_answer_from_output,
    sse_event,
    thinking_payload_from_event,
)
from graph.agent import agent

app = FastAPI()
load_dotenv()
logging.basicConfig(level=logging.INFO)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
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
create_thinking_steps_table()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/chat", response_model=QueryResponse)
def chat(query_input: QueryInput):
    session_id = get_or_create_session_id(query_input.session_id)
    logging.info(
        f"Session ID - {session_id} | User query - {query_input.question} | Model name - {query_input.model_name.value}"
    )

    try:
        chat_history = get_chat_history(session_id)
        messages = history_to_messages(chat_history)

        standalone_query = context_chain.invoke(
            {"chat_history": messages, "input_query": query_input.question}
        )

        messages = append_to_history(messages, HumanMessage(content=standalone_query))
        result = agent.invoke(
            {
                "messages": messages,
                "model_name": query_input.model_name.value,
            }
        )

        last_message = next(
            (
                message
                for message in reversed(result["messages"])
                if isinstance(message, AIMessage)
            ),
            None,
        )
        if last_message:
            answer = last_message.content
        else:
            answer = "I apologise but I couldn't generate a response this time."

        insert_chat_history(
            session_id, query_input.question, answer, query_input.model_name
        )
        logging.info(f"Session ID - {session_id} | AI Response - {answer}")

        return QueryResponse(
            answer=answer, session_id=session_id, model_name=query_input.model_name
        )

    except Exception as e:
        logging.error(f"Error while generating response - {e}")
        raise HTTPException(500, f"Error while generating response - {str(e)}")


@app.post("/chat/stream")
async def chat_stream(query_input: QueryInput):
    session_id = get_or_create_session_id(query_input.session_id)
    logging.info(
        f"Session ID - {session_id} | User query - {query_input.question} | Model name - {query_input.model_name.value}"
    )

    try:
        chat_history = get_chat_history(session_id)
        messages = history_to_messages(chat_history)

        standalone_query = context_chain.invoke(
            {"chat_history": messages, "input_query": query_input.question}
        )

        messages = append_to_history(messages, HumanMessage(content=standalone_query))
    except Exception as e:
        logging.error(f"Failed to prepare chat stream - {e}")
        raise HTTPException(500, f"Error while preparing response stream - {str(e)}")

    async def event_stream():
        answer_chunks: list[str] = []
        non_streamed_answer: str = ""
        # Use dict to track unique thinking steps by key to prevent duplicates
        thinking_steps_map: dict[str, dict] = {}
        last_activity = asyncio.get_event_loop().time()
        try:
            # Send session metadata early so clients can recover if the stream drops mid-response.
            yield sse_event(
                {
                    "type": "start",
                    "session_id": session_id,
                    "model_name": query_input.model_name.value,
                }
            )

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

                # Dynamic timeout: use shorter timeout (8s) if we've seen recent activity,
                # longer timeout (20s) if the stream has been idle
                current_time = asyncio.get_event_loop().time()
                idle_time = current_time - last_activity
                timeout_duration = 20.0 if idle_time > 10.0 else 8.0

                done, _ = await asyncio.wait(
                    {next_event_task}, timeout=timeout_duration
                )
                if not done:
                    # Heartbeat helps prevent intermediary proxy idle timeouts.
                    yield sse_event({"type": "ping"})
                    continue

                try:
                    event = next_event_task.result()
                except StopAsyncIteration:
                    next_event_task = None
                    break
                finally:
                    next_event_task = None
                    last_activity = asyncio.get_event_loop().time()

                thinking_payload = thinking_payload_from_event(event)
                if thinking_payload:
                    # Track thinking steps for persistence using dict to prevent duplicates
                    step_key = thinking_payload.get("key")
                    if step_key:
                        thinking_steps_map[step_key] = {
                            "key": step_key,
                            "kind": thinking_payload.get("kind"),
                            "status": thinking_payload.get("status"),
                            "title": thinking_payload.get("title"),
                            "detail": thinking_payload.get("detail"),
                        }
                    last_activity = asyncio.get_event_loop().time()
                    yield sse_event(thinking_payload)

                if event.get("event") == "on_chain_end":
                    chain_end_answer = extract_ai_answer_from_output(
                        (event.get("data") or {}).get("output")
                    )
                    if chain_end_answer:
                        non_streamed_answer = chain_end_answer

                event_type = event.get("event")
                if event_type != "on_chat_model_stream":
                    continue

                metadata = event.get("metadata") or {}
                if metadata.get("langgraph_node") != "answer":
                    continue

                chunk = (event.get("data") or {}).get("chunk")
                token_text = chunk_to_text(chunk)
                if not token_text:
                    continue

                answer_chunks.append(token_text)
                last_activity = asyncio.get_event_loop().time()
                yield sse_event({"type": "token", "content": token_text})

            final_answer = "".join(answer_chunks).strip()
            if not final_answer:
                final_answer = non_streamed_answer.strip()
            if not final_answer:
                final_answer = (
                    "I apologise but I couldn't generate a response this time."
                )
            if not answer_chunks and final_answer:
                yield sse_event({"type": "token", "content": final_answer})

            # Always send done event, even if stream was interrupted
            try:
                yield sse_event(
                    {
                        "type": "done",
                        "session_id": session_id,
                        "model_name": query_input.model_name.value,
                    }
                )
            except Exception as done_error:
                logging.error(
                    f"Failed to send done event for session {session_id}: {done_error}"
                )

            # Convert thinking steps dict to list and ensure all steps are marked as done
            thinking_steps_list = list(thinking_steps_map.values())
            for step in thinking_steps_list:
                if step.get("status") == "running":
                    step["status"] = "done"

            # Persist chat history and thinking steps atomically in a single transaction
            try:
                message_id = insert_chat_history_with_thinking_steps(
                    session_id,
                    query_input.question,
                    final_answer,
                    query_input.model_name,
                    thinking_steps_list if thinking_steps_list else None,
                )
                logging.info(
                    f"Session ID - {session_id} | AI Response - {final_answer[:200]}..."
                )
                logging.info(
                    f"Session ID - {session_id} | Stream complete - {len(answer_chunks)} chunks, "
                    f"final answer length: {len(final_answer)} chars"
                )
                if thinking_steps_list:
                    logging.info(
                        f"Session ID - {session_id} | Persisted {len(thinking_steps_list)} thinking steps "
                        f"for message_id {message_id}"
                    )
            except Exception as persist_error:
                logging.error(
                    f"Failed to persist chat history for session {session_id} - {persist_error}"
                )

        except Exception as e:
            logging.error(f"Error while streaming response - {e}")
            yield sse_event(
                {
                    "type": "error",
                    "message": f"Error while generating response - {str(e)}",
                }
            )

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
        raise HTTPException(
            400,
            f"Unsupported file types. Allowed file types are - {', '.join(allowed_extensions)}",
        )

    temp_file_path = None
    try:
        suffix = os.path.splitext(file.filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name

        file_id = insert_document_record(file.filename)
        success = index_document_to_vector_store(temp_file_path, file_id)

        if success:
            return {
                "message": f"File {file.filename} has been successfully uploaded and ingested.",
                "file_id": file_id,
            }
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
    """Return all user/assistant message pairs for a given session, including thinking steps."""
    return get_session_messages_with_thinking(session_id)


@app.post("/delete-doc")
def delete_uploaded_document(request: DeleteFileRequest):
    chroma_delete_success = delete_doc_from_vector_store(request.file_id)

    if chroma_delete_success:
        db_delete_success = delete_document(request.file_id)
        if db_delete_success:
            return {
                "message": f"Successfully deleted document with file_id - {request.file_id}"
            }
        else:
            return {
                "message": f"Deleted document with file_id - {request.file_id} from chroma but failed to delete from db."
            }
    else:
        return {
            "message": f"Failed to delete document with file_id - {request.file_id}"
        }
