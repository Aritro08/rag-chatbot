from typing import Literal
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END
from graph.nodes import router_node, retriever_selector_node, rag_node, web_node, answer_node
from models.shared import AgentState

def from_router(state: AgentState) -> Literal['rag', 'answer', 'end']:
    return state['route']

def after_rag(state: AgentState) -> Literal['answer', 'web']:
    return state['route']

graph = StateGraph(AgentState)
graph.add_node("router", router_node)
graph.add_node("retriever_selector", retriever_selector_node)
graph.add_node("rag", rag_node)
graph.add_node("web", web_node)
graph.add_node("answer", answer_node)

graph.set_entry_point("router")
graph.add_conditional_edges("router", from_router, {"rag": "retriever_selector", "answer": "answer", "end": END})
graph.add_edge("retriever_selector", "rag")
graph.add_conditional_edges("rag", after_rag, {"answer": "answer", "web": "web"})
graph.add_edge("web", "answer")
graph.add_edge("answer", END)

agent = graph.compile()



