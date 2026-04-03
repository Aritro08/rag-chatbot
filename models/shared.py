from typing import TypedDict, List, Literal
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage

class AgentState(TypedDict, total=False):
    messages: List[BaseMessage]
    route: Literal["rag", "answer", "end", "web"]
    retriever_mode: Literal["hybrid", "vector"]
    rag: str
    web: str
    model_name: str

class RouteDecision(BaseModel):
    route: Literal["rag", "answer", "end"]
    reply: str | None = Field(None, description="Filled only when route == 'end'")

class RagJudge(BaseModel):
    sufficient: bool

class RetrieverChoice(BaseModel):
    mode: Literal["hybrid", "vector"] = Field(
        description="'hybrid' for keyword-heavy queries; 'vector' for conceptual/thematic queries"
    )
    reason: str = Field(description="One-sentence justification for the choice")

router_llm = ChatOpenAI(model='gpt-4o-mini').with_structured_output(RouteDecision)
judge_llm = ChatOpenAI(model='gpt-4o-mini').with_structured_output(RagJudge)
retriever_selector_llm = ChatOpenAI(model='gpt-4o-mini').with_structured_output(RetrieverChoice)