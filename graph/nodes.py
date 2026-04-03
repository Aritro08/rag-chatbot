from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from models.shared import AgentState, router_llm, judge_llm, retriever_selector_llm, RouteDecision, RagJudge, RetrieverChoice
from graph.tools import web_search_tool, get_hybrid_retriever, get_vector_retriever

def retriever_selector_node(state: AgentState) -> AgentState:
    query = next((message.content for message in reversed(state['messages']) if isinstance(message, HumanMessage)), "")

    system_prompt = """
        You are a retrieval strategy classifier. Your sole job is to decide which
        search strategy will yield the most relevant document chunks for a given query.

        Choose 'hybrid' when the query:
        - Contains specific entity names, product names, acronyms, or codes
        - Uses exact technical terms, identifiers, or proper nouns
        - Asks for a specific fact, definition, or value that hinges on a keyword match
        - Would benefit from both term-frequency matching AND semantic similarity

        Choose 'vector' when the query:
        - Is conceptual, thematic, or exploratory in nature
        - Uses natural language without anchoring on specific keyword matches
        - Involves paraphrases, synonyms, or high-level ideas where semantic
          understanding is more important than exact term matching
    """

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=query)]
    result: RetrieverChoice = retriever_selector_llm.invoke(messages)

    return {
        **state,
        "retriever_mode": result.mode,
    }


def router_node(state: AgentState) -> AgentState:
    system_prompt = """
        You are a router that decides how to handle user queries. Simply output the following keywords based on the condition
        - Use 'end' for greetings/small-talk and provide a 'reply' based on what is already present in the chat history.
        - Use 'rag' when additional knowledge or context look-up is required.
        - Use 'answer' when you can answer directly without any look-up.
    """

    messages = [SystemMessage(content=system_prompt)] + state['messages']
    result: RouteDecision = router_llm.invoke(messages)

    out = {'messages': state['messages'], 'route': result.route}
    if result.route == "end":
        out['messages'] = state['messages'] + [AIMessage(content=result.reply or "Hello!")]

    return out

def rag_node(state: AgentState) -> AgentState:
    query = next((message.content for message in reversed(state['messages']) if isinstance(message, HumanMessage)), "")

    mode = state.get('retriever_mode', 'hybrid')
    retriever = get_hybrid_retriever(k=5) if mode == 'hybrid' else get_vector_retriever(k=5)
    docs = retriever.invoke(query)
    chunks = "\n\n".join(doc.page_content for doc in docs) if docs else ""

    judge_system_prompt = """
        You are a judge evaluating if the retrieved information is sufficient to answer the user's query.
        Consider both relevance and completeness.
    """

    user_prompt = """
        User query:
        {query}

        Retrieved Info:
        {context}

        Is this sufficient to answer the user query?
    """

    judge_rag_prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=judge_system_prompt),
        ("human", user_prompt)
    ])

    judge_pipeline = judge_rag_prompt | judge_llm
    verdict: RagJudge = judge_pipeline.invoke({'query': query, 'context': chunks})

    return {
        **state,
        "rag": chunks,
        "route": "answer" if verdict.sufficient else "web"
    }

def web_node(state: AgentState) -> AgentState:
    query = next((message.content for message in reversed(state['messages']) if isinstance(message, HumanMessage)), "")
    results = web_search_tool.invoke({'query': query})
    return {
        **state,
        "web": results,
        "route": "answer"
    }

def answer_node(state: AgentState) -> AgentState:
    query = next((message.content for message in reversed(state['messages']) if isinstance(message, HumanMessage)), "")

    context_parts = []
    if state.get('rag'):
        context_parts.append(f"Retrieved information:\n{state.get('rag')}")
    if state.get('web'):
        context_parts.append(f"Web search information:\n{state.get('web')}")
    
    context = "\n\n".join(context_parts) if context_parts else "No external context available."

    prompt = f"""
        Provide a helpful, accurate and concise response to the user's question based on the context provided.

        Question:
        {query}

        Context:
        {context}
    """

    messages = state['messages'] + [HumanMessage(content=prompt)]
    model_name = state.get("model_name") or "gpt-4o-mini"
    llm = ChatOpenAI(model=model_name, temperature=0.5)
    answer = llm.invoke(messages).content

    return {
        **state,
        "messages": state['messages'] + [AIMessage(content=answer)]
    }


