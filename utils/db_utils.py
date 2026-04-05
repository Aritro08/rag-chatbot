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
        ipv4_records = socket.getaddrinfo(
            host, None, socket.AF_INET, socket.SOCK_STREAM
        )
    except socket.gaierror:
        return None
    if not ipv4_records:
        return None

    hostaddr = ipv4_records[0][4][0]
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["hostaddr"] = hostaddr
    new_query = urlencode(query)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
    )


def get_db_connection():
    database_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Missing SUPABASE_DB_URL or DATABASE_URL environment variable"
        )

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
    SQL = """
        CREATE TABLE if not exists chat_history
        (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT,
            user_query TEXT,
            llm_response TEXT,
            model TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.commit()


def insert_chat_history(session_id, user_query, llm_response, model):
    """Insert chat history and return the message id."""
    SQL = "INSERT INTO chat_history (session_id, user_query, llm_response, model) VALUES (%s, %s, %s, %s) RETURNING id"
    model_value = getattr(model, "value", model)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL, (session_id, user_query, llm_response, model_value))
            message_id = cur.fetchone()["id"]
        conn.commit()
    return message_id


def insert_chat_history_with_thinking_steps(
    session_id, user_query, llm_response, model, thinking_steps
):
    """
    Insert chat history and thinking steps atomically in a single transaction.
    Either both operations succeed, or both fail (ensuring data consistency).
    Returns the message_id of the inserted chat history record.
    """
    model_value = getattr(model, "value", model)

    CHAT_HISTORY_SQL = """
        INSERT INTO chat_history (session_id, user_query, llm_response, model)
        VALUES (%s, %s, %s, %s) RETURNING id
    """

    THINKING_STEPS_SQL = """
        INSERT INTO thinking_steps (message_id, step_key, step_kind, step_status, step_title, step_detail, step_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    with get_db_connection() as conn:
        try:
            with conn.cursor() as cur:
                # Insert chat history and get the message_id
                cur.execute(
                    CHAT_HISTORY_SQL,
                    (session_id, user_query, llm_response, model_value),
                )
                message_id = cur.fetchone()["id"]

                # Insert thinking steps if any were collected
                if thinking_steps:
                    for order, step in enumerate(thinking_steps):
                        cur.execute(
                            THINKING_STEPS_SQL,
                            (
                                message_id,
                                step.get("key"),
                                step.get("kind"),
                                step.get("status"),
                                step.get("title"),
                                step.get("detail"),
                                order,
                            ),
                        )

            # Commit the transaction (both operations succeed)
            conn.commit()
            return message_id

        except Exception:
            # Rollback on any error (ensures both operations fail together)
            conn.rollback()
            raise


def get_chat_history(session_id):
    SQL = "SELECT user_query, llm_response FROM chat_history WHERE session_id = %s ORDER BY created_at, id"
    messages = []
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (session_id,))
            for row in cursor.fetchall():
                messages.extend(
                    [
                        {"role": "human", "content": row["user_query"]},
                        {"role": "ai", "content": row["llm_response"]},
                    ]
                )
    return messages


def create_documents_store():
    SQL = """
        CREATE TABLE if not exists document_store
        (
            id BIGSERIAL PRIMARY KEY,
            file_name TEXT,
            upload_timestamp TIMESTAMPTZ DEFAULT NOW()
        )
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.commit()


def insert_document_record(filename):
    SQL = "INSERT INTO document_store (file_name) VALUES (%s) RETURNING id"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (filename,))
            file_id = cursor.fetchone()["id"]
        conn.commit()
    return file_id


def get_all_documents():
    SQL = "SELECT id, file_name, upload_timestamp FROM document_store ORDER BY upload_timestamp DESC, id DESC"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL)
            docs = cursor.fetchall()
    return [dict(doc) for doc in docs]


def delete_document(file_id):
    SQL = "DELETE FROM document_store WHERE id = %s"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (file_id,))
        conn.commit()
    return True


def get_all_sessions():
    """Return each session's id, first user query and when it started."""
    SQL = """
        SELECT DISTINCT ON (session_id) session_id, user_query, created_at
        FROM chat_history
        ORDER BY session_id, created_at ASC, id ASC
    """
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL)
            rows = cursor.fetchall()

    sessions = [dict(row) for row in rows]
    sessions.sort(key=lambda item: item["created_at"], reverse=True)
    return sessions


def get_session_messages(session_id):
    """Return full user/assistant message pairs for a session (Streamlit display format)."""
    SQL = "SELECT id, user_query, llm_response FROM chat_history WHERE session_id = %s ORDER BY created_at, id"
    messages = []
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (session_id,))
            for row in cursor.fetchall():
                messages.append({"role": "user", "content": row["user_query"]})
                messages.append(
                    {
                        "role": "assistant",
                        "content": row["llm_response"],
                        "message_id": row["id"],
                    }
                )
    return messages


def create_thinking_steps_table():
    SQL = """
        CREATE TABLE IF NOT EXISTS thinking_steps (
            id BIGSERIAL PRIMARY KEY,
            message_id BIGINT REFERENCES chat_history(id) ON DELETE CASCADE,
            step_key TEXT NOT NULL,
            step_kind TEXT NOT NULL,
            step_status TEXT NOT NULL,
            step_title TEXT NOT NULL,
            step_detail TEXT,
            step_order INTEGER NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """
    INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_thinking_steps_message_id ON thinking_steps(message_id);"
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
            cur.execute(INDEX_SQL)
        conn.commit()


def insert_thinking_steps(message_id, steps):
    """Insert thinking steps for a message. Steps should be a list of dicts with keys: key, kind, status, title, detail."""
    SQL = """
        INSERT INTO thinking_steps (message_id, step_key, step_kind, step_status, step_title, step_detail, step_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for order, step in enumerate(steps):
                cur.execute(
                    SQL,
                    (
                        message_id,
                        step.get("key"),
                        step.get("kind"),
                        step.get("status"),
                        step.get("title"),
                        step.get("detail"),
                        order,
                    ),
                )
        conn.commit()


def get_thinking_steps(message_id):
    """Retrieve thinking steps for a message, ordered by step_order."""
    SQL = """
        SELECT step_key, step_kind, step_status, step_title, step_detail, step_order
        FROM thinking_steps
        WHERE message_id = %s
        ORDER BY step_order, id
    """
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (message_id,))
            rows = cursor.fetchall()
    return [
        {
            "key": row["step_key"],
            "kind": row["step_kind"],
            "status": row["step_status"],
            "title": row["step_title"],
            "detail": row["step_detail"],
            "order": row["step_order"],
        }
        for row in rows
    ]


def get_session_messages_with_thinking(session_id):
    """Return full user/assistant message pairs with thinking steps for a session."""
    SQL = """
        SELECT id, user_query, llm_response FROM chat_history
        WHERE session_id = %s ORDER BY created_at, id
    """
    messages = []
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL, (session_id,))
            rows = cursor.fetchall()
            for row in rows:
                message_id = row["id"]
                # Get thinking steps for this assistant message
                thinking_steps = get_thinking_steps(message_id)
                messages.append({"role": "user", "content": row["user_query"]})
                messages.append(
                    {
                        "role": "assistant",
                        "content": row["llm_response"],
                        "thinking_steps": thinking_steps if thinking_steps else None,
                    }
                )
    return messages
