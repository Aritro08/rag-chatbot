import streamlit as st
import requests
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

def load_css(file_path: str) -> None:
    """Load and inject custom CSS from a file."""
    css_content = Path(file_path).read_text()
    st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="RAG Chat", layout="wide")
st.title("RAG ChatBot")

# Load custom styling
load_css("styles/custom.css")

# ── Session state init ────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []       # {"role": "user"|"assistant", "content": str}
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "last_uploaded" not in st.session_state:
    st.session_state.last_uploaded = None
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "all_sessions" not in st.session_state:
    st.session_state.all_sessions = []  # [{session_id, user_query, created_at}]
if "model_name" not in st.session_state:
    st.session_state.model_name = "gpt-4o-mini"
if "input_key" not in st.session_state:
    st.session_state.input_key = 0


# ── Helper functions ──────────────────────────────────────────────────────────
def fetch_documents():
    try:
        r = requests.get(f"{API_BASE}/list-docs", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Failed to fetch documents: {e}")
        return []


def delete_document(file_id: int):
    try:
        r = requests.post(
            f"{API_BASE}/delete-doc",
            json={"file_id": file_id},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Failed to delete document: {e}")
        return False


def upload_document(uploaded_file):
    try:
        r = requests.post(
            f"{API_BASE}/upload-doc",
            files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None


def send_message(question: str, model_name: str):
    payload = {
        "question": question,
        "model_name": model_name,
    }
    if st.session_state.session_id:
        payload["session_id"] = st.session_state.session_id

    try:
        r = requests.post(f"{API_BASE}/chat", json=payload, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Chat request failed: {e}")
        return None


def fetch_sessions():
    try:
        r = requests.get(f"{API_BASE}/chat-sessions", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Failed to fetch sessions: {e}")
        return []


def fetch_session_messages(session_id: str):
    try:
        r = requests.get(f"{API_BASE}/chat-sessions/{session_id}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Failed to load session: {e}")
        return []


def start_new_chat():
    """Clear the active chat and start a blank session."""
    st.session_state.session_id = None
    st.session_state.messages = []


def switch_to_session(session_id: str):
    """Load a past session into the chat window."""
    msgs = fetch_session_messages(session_id)
    st.session_state.session_id = session_id
    st.session_state.messages = msgs


# ── Handle session switch via query param ─────────────────────────────────
_sw = st.query_params.get("sw")
if _sw:
    st.query_params.clear()
    switch_to_session(_sw)
    st.rerun()


# ── Layout: three columns (history | chat | docs) ────────────────────────────
history_col, chat_col, docs_col = st.columns([1, 3, 1])

# ── Chat history panel ────────────────────────────────────────────────────────
with history_col:
    if st.button("＋ New Chat", use_container_width=True):
        start_new_chat()
        st.rerun()

    sessions = fetch_sessions()
    sessions_container = st.container(height=520)
    with sessions_container:
        if sessions:
            # Build all sessions as a single HTML block — no Streamlit widgets
            items_html = []
            for s in sessions:
                is_active = s["session_id"] == st.session_state.session_id
                first_query = s["user_query"] or "Empty session"
                label = (first_query[:55] + "…") if len(first_query) > 55 else first_query
                ts = datetime.fromisoformat(s["created_at"]).strftime("%b %d")
                # Escape HTML in label
                label = label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

                if is_active:
                    items_html.append(
                        f'<div class="sess-item active">'
                        f'<p class="sess-query">{label}</p>'
                        f'<p class="sess-date">{ts}</p>'
                        f'</div>'
                    )
                else:
                    items_html.append(
                        f'<a class="sess-item" href="?sw={s["session_id"]}" target="_parent">'
                        f'<p class="sess-query">{label}</p>'
                        f'<p class="sess-date">{ts}</p>'
                        f'</a>'
                    )

            st.markdown(
                '<div class="sessions-list">' + "".join(items_html) + '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No past chats yet.")

# ── Documents panel ───────────────────────────────────────────────────────────
with docs_col:
    # File uploader — key is cycled after each successful upload to reset the widget
    uploaded_file = st.file_uploader(
        "Upload a document",
        type=["pdf", "docx", "html"],
        label_visibility="collapsed",
        key=f"uploader_{st.session_state.uploader_key}",
    )
    if uploaded_file is None:
        st.session_state.last_uploaded = None
    elif uploaded_file.name != st.session_state.last_uploaded:
        st.session_state.last_uploaded = uploaded_file.name
        with st.spinner("Uploading and indexing…"):
            result = upload_document(uploaded_file)
        if result:
            st.success(result.get("message", "Upload successful"))
            st.session_state.uploader_key += 1  # reset the widget
            st.rerun()

    # Document list
    docs = fetch_documents()
    doc_list = st.container(height=400)
    with doc_list:
        if docs:
            for doc in docs:
                col_name, col_btn = st.columns([4, 1])
                with col_name:
                    ts = datetime.fromisoformat(doc["upload_timestamp"]).strftime("%b %d, %Y")
                    st.markdown(f"**{doc['file_name']}**  \n*{ts}*")
                with col_btn:
                    if st.button("🗑", key=f"del_{doc['id']}", help="Delete document"):
                        with st.spinner("Deleting…"):
                            if delete_document(doc["id"]):
                                st.success("Deleted")
                                st.rerun()
        else:
            st.caption("No documents uploaded yet.")


# ── Chat panel ────────────────────────────────────────────────────────────────
with chat_col:
    # Message history
    chat_container = st.container(height=570)
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # ── Custom chat input (form styled to look like chat input) ────────
    with st.form("chat_form", enter_to_submit=True, border=False):
        input_col, btn_col, model_col= st.columns([8, 0.5, 2], gap="small")
        with input_col:
            prompt = st.text_input(
                "message",
                placeholder="Ask a question…",
                label_visibility="collapsed",
                key=f"msg_input_{st.session_state.input_key}",
            )
        with btn_col:
            submitted = st.form_submit_button("➤")
        with model_col:
            chosen_model = st.selectbox(
                "Model",
                options=["gpt-4o-mini", "gpt-4o"],
                index=0 if st.session_state.model_name == "gpt-4o-mini" else 1,
                label_visibility="collapsed",
                key="model_selector",
            ) 

    if submitted and prompt.strip():
        st.session_state.model_name = chosen_model
        st.session_state.input_key += 1  # resets the text input on next render
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    response = send_message(prompt, chosen_model)

                if response:
                    answer = response.get("answer", "No response received.")
                    st.session_state.session_id = response.get("session_id")
                    st.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                else:
                    st.error("Failed to get a response. Is the API server running?")
        st.rerun()
