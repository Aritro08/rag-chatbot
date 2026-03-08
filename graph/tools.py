from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from langchain_community.retrievers import BM25Retriever
from langchain_core.runnables import RunnableLambda
from langchain_core.documents import Document
from utils.vector_utils import fetch_all_vector_documents, search_similar_documents

tavily = TavilySearch(max_results=3, topic="general")


def _rrf_fuse(results_lists: list[list[Document]], weights: list[float], top_k: int, rrf_k: int = 60,) -> list[Document]:
    """Reciprocal Rank Fusion across multiple ranked result lists."""
    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}

    for results, weight in zip(results_lists, weights):
        for rank, doc in enumerate(results):
            key = doc.page_content
            scores[key] = scores.get(key, 0.0) + weight * (1.0 / (rrf_k + rank + 1))
            doc_map[key] = doc

    ranked = sorted(scores, key=scores.__getitem__, reverse=True)
    return [doc_map[k] for k in ranked[:top_k]]


def get_hybrid_retriever(k: int = 5, bm25_weight: float = 0.4, vector_weight: float = 0.6) -> RunnableLambda:
    """
    Returns a RunnableLambda that combines BM25 keyword search and vector
    search via Reciprocal Rank Fusion (RRF).

    The BM25 index is built fresh from pgvector-backed chunks on every call so it always
    reflects the latest indexed content.

    Args:
        k: final number of documents to return after fusion.
        bm25_weight: weight applied to BM25 ranked results in RRF (default 0.4).
        vector_weight: weight applied to vector ranked results in RRF (default 0.6).
    """
    def _search(query: str) -> list[Document]:
        all_docs = fetch_all_vector_documents()
        vector_docs = search_similar_documents(query=query, k=k, fetch_k=k * 3)

        if not all_docs:
            return vector_docs

        bm25_retriever = BM25Retriever.from_documents(all_docs)
        bm25_retriever.k = k
        bm25_docs = bm25_retriever.invoke(query)

        return _rrf_fuse(
            results_lists=[bm25_docs, vector_docs],
            weights=[bm25_weight, vector_weight],
            top_k=k,
        )

    return RunnableLambda(_search)


def get_vector_retriever(k: int = 5) -> RunnableLambda:
    """
    Returns a RunnableLambda that performs pure vector similarity search
    against pgvector-backed chunks. Use this when the query is conceptual and
    keyword matching would not add value.

    Args:
        k: number of documents to return.
    """
    def _search(query: str) -> list[Document]:
        return search_similar_documents(query=query, k=k, fetch_k=k * 3)

    return RunnableLambda(_search)


@tool
def web_search_tool(query: str) -> str:
    """Used for fetching real-time info via Tavily web search"""
    try:
        result = tavily.invoke({"query": query})

        if isinstance(result, dict) and 'results' in result:
            formatted_results = []
            for item in result['results']:
                title = item.get('title', 'No title')
                content = item.get('content', 'No content')
                url = item.get('url', '')
                formatted_results.append(f"Title: {title}\nContent: {content}\nURL: {url}")

            return "\n\n".join(formatted_results) if formatted_results else "No results found"
        else:
            return str(result)
    except Exception as e:
        return f"Web search error: {e}"