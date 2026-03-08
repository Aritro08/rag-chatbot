import os
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _with_ipv4_hostaddr(database_url: str) -> str | None:
    parsed = urlsplit(database_url)
    host = parsed.hostname
    if not host:
        return None

    try:
        ipv4_records = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        return None
    if not ipv4_records:
        return None

    hostaddr = ipv4_records[0][4][0]
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["hostaddr"] = hostaddr
    new_query = urlencode(query)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))


def get_db_connection():
    database_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Missing SUPABASE_DB_URL or DATABASE_URL environment variable")

    if _truthy_env("DB_FORCE_IPV4"):
        ipv4_url = _with_ipv4_hostaddr(database_url)
        if not ipv4_url:
            raise RuntimeError(
                "DB_FORCE_IPV4 is set but no IPv4 address could be resolved for the DB hostname. "
                "Use a Supabase pooler URL (port 6543, sslmode=require) or disable DB_FORCE_IPV4."
            )
        return psycopg.connect(ipv4_url, row_factory=dict_row)

    try:
        return psycopg.connect(database_url, row_factory=dict_row)
    except psycopg.OperationalError as exc:
        if "Network is unreachable" not in str(exc):
            raise

        ipv4_url = _with_ipv4_hostaddr(database_url)
        if not ipv4_url:
            raise RuntimeError(
                "Database connection failed due to unreachable network and no IPv4 fallback address was found. "
                "Use a Supabase pooler URL (port 6543, sslmode=require), or set DB_FORCE_IPV4=false "
                "if your environment supports IPv6."
            ) from exc
        return psycopg.connect(ipv4_url, row_factory=dict_row)

def create_chat_history():
    SQL = '''
        CREATE TABLE if not exists chat_history
        (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT,
            user_query TEXT,
            llm_response TEXT,
            model TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    '''
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.commit()

def insert_chat_history(session_id, user_query, llm_response, model):
    SQL = 'INSERT INTO chat_history (session_id, user_query, llm_response, model) VALUES (%s, %s, %s, %s)'
    model_value = getattr(model, "value", model)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL, (session_id, user_query, llm_response, model_value))
        conn.commit()

def get_chat_history(session_id):
    SQL = 'SELECT user_query, llm_response FROM chat_history WHERE session_id = %s ORDER BY created_at, id'
    messages = []
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (session_id,))
            for row in cursor.fetchall():
                messages.extend([
                    {'role': 'human', 'content': row['user_query']},
                    {'role': 'ai', 'content': row['llm_response']}
                ])
    return messages

def create_documents_store():
    SQL = '''
        CREATE TABLE if not exists document_store
        (
            id BIGSERIAL PRIMARY KEY,
            file_name TEXT,
            upload_timestamp TIMESTAMPTZ DEFAULT NOW()
        )
    '''
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.commit()

def insert_document_record(filename):
    SQL = 'INSERT INTO document_store (file_name) VALUES (%s) RETURNING id'
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (filename,))
            file_id = cursor.fetchone()['id']
        conn.commit()
    return file_id

def get_all_documents():
    SQL = 'SELECT id, file_name, upload_timestamp FROM document_store ORDER BY upload_timestamp DESC, id DESC'
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL)
            docs = cursor.fetchall()
    return [dict(doc) for doc in docs]

def delete_document(file_id):
    SQL = 'DELETE FROM document_store WHERE id = %s'
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (file_id,))
        conn.commit()
    return True

def get_all_sessions():
    """Return each session's id, first user query and when it started."""
    SQL = '''
        SELECT DISTINCT ON (session_id) session_id, user_query, created_at
        FROM chat_history
        ORDER BY session_id, created_at ASC, id ASC
    '''
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL)
            rows = cursor.fetchall()

    sessions = [dict(row) for row in rows]
    sessions.sort(key=lambda item: item["created_at"], reverse=True)
    return sessions

def get_session_messages(session_id):
    """Return full user/assistant message pairs for a session (Streamlit display format)."""
    SQL = 'SELECT user_query, llm_response FROM chat_history WHERE session_id = %s ORDER BY created_at, id'
    messages = []
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (session_id,))
            for row in cursor.fetchall():
                messages.append({"role": "user", "content": row["user_query"]})
                messages.append({"role": "assistant", "content": row["llm_response"]})
    return messages

