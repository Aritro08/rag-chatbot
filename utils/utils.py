import uuid
from typing import Optional, List, Dict
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

def get_or_create_session_id(session_id: Optional[str]) -> str:
    return session_id or str(uuid.uuid4())

def history_to_messages(history: List[Dict]) -> List[BaseMessage]:
    messages = []
    for i in range(0, len(history), 2):
        if i < len(history):
            messages.append(HumanMessage(content=history[i]['content']))
        if i+1 < len(history):
            messages.append(AIMessage(content=history[i+1]['content']))
    return messages

def append_to_history(history: List[BaseMessage], message: BaseMessage) -> List[BaseMessage]:
    return history + [message]