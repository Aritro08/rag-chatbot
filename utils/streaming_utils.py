import json
from typing import Any

from langchain_core.messages import AIMessage

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


def content_to_text(content: Any) -> str:
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


def chunk_to_text(chunk: Any) -> str:
    """Extract textual content from a LangChain message chunk payload."""
    content = getattr(chunk, "content", "")
    return content_to_text(content)


def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def extract_ai_answer_from_output(output: Any) -> str | None:
    output_dict = output if isinstance(output, dict) else {}
    messages = output_dict.get("messages")
    if not isinstance(messages, list):
        return None

    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = content_to_text(message.content)
            if text:
                return text
            continue

        if isinstance(message, dict):
            msg_type = (message.get("type") or message.get("role") or "").lower()
            if msg_type in {"ai", "assistant"}:
                text = content_to_text(message.get("content", ""))
                if text:
                    return text

    return None


def _preview_text(value: Any, max_len: int = 180) -> str:
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


def _node_end_detail(node: str, output: Any) -> str:
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


def thinking_payload_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
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
