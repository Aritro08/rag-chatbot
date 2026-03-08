from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, UnstructuredHTMLLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from typing import List
from langchain_core.documents import Document
from dotenv import load_dotenv
from pathlib import Path
from uuid import uuid4
import json
import os

from utils.db_utils import get_db_connection

env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, length_function=len)
embedding_function = OpenAIEmbeddings(model='text-embedding-3-small')


def _ensure_vector_schema() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(
                '''
                CREATE TABLE IF NOT EXISTS rag_vector_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    file_id BIGINT NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    embedding VECTOR(1536) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                '''
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS rag_vector_chunks_file_id_idx ON rag_vector_chunks (file_id)"
            )
        conn.commit()


_ensure_vector_schema()


def _embedding_to_pgvector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.10f}" for value in values) + "]"

def load_and_split_documents(file_path: str) -> List[Document]:
    if file_path.endswith('.pdf'):
        loader = PyPDFLoader(file_path)
    elif file_path.endswith('.docx'):
        loader = Docx2txtLoader(file_path)
    elif file_path.endswith('.html'):
        loader = UnstructuredHTMLLoader(file_path)
    else:
        raise ValueError("File type is unsupported")
    
    documents = loader.load()
    return text_splitter.split_documents(documents)


def fetch_all_vector_documents() -> List[Document]:
    SQL = "SELECT content, metadata FROM rag_vector_chunks ORDER BY created_at DESC"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL)
            rows = cursor.fetchall()

    return [Document(page_content=row["content"], metadata=row["metadata"] or {}) for row in rows]


def search_similar_documents(query: str, k: int = 5, fetch_k: int | None = None) -> List[Document]:
    limit = fetch_k or k
    query_embedding = embedding_function.embed_query(query)
    query_vector = _embedding_to_pgvector_literal(query_embedding)

    SQL = '''
        SELECT content, metadata
        FROM rag_vector_chunks
        ORDER BY embedding <=> (%s)::vector
        LIMIT %s
    '''

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (query_vector, limit))
            rows = cursor.fetchall()

    docs = [Document(page_content=row["content"], metadata=row["metadata"] or {}) for row in rows]
    return docs[:k]

def index_document_to_vector_store(file_path: str, file_id: int) -> bool:
    try:
        chunks = load_and_split_documents(file_path)
        if not chunks:
            return True

        texts = [chunk.page_content for chunk in chunks]
        embeddings = embedding_function.embed_documents(texts)

        SQL = '''
            INSERT INTO rag_vector_chunks (chunk_id, file_id, content, metadata, embedding)
            VALUES (%s, %s, %s, %s::jsonb, (%s)::vector)
        '''

        rows = []
        for chunk, embedding in zip(chunks, embeddings):
            metadata = dict(chunk.metadata or {})
            metadata["file_id"] = file_id
            rows.append(
                (
                    str(uuid4()),
                    file_id,
                    chunk.page_content,
                    json.dumps(metadata),
                    _embedding_to_pgvector_literal(embedding),
                )
            )

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(SQL, rows)
            conn.commit()
        return True
    except Exception as e:
        print(f"Error indexing document due to - {e}")
        return False
    
def delete_doc_from_vector_store(file_id: int) -> bool:
    try:
        SQL = "DELETE FROM rag_vector_chunks WHERE file_id = %s"
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(SQL, (file_id,))
                deleted_count = cursor.rowcount
            conn.commit()

        print(f"Deleted {deleted_count} chunks with file id {file_id}")

        return True
    except Exception as e:
        print(f"Error deleting document with file id {file_id} due to - {e}")
        return False


# Backward-compatible aliases.
index_document_to_chroma = index_document_to_vector_store
delete_doc_from_chroma = delete_doc_from_vector_store