import os
import tempfile
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException
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
            "messages": messages
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

