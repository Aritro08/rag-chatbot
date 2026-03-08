from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

system_query = """
    Given chat history and the latest user query
    which might refer to context from the chat history,
    formulate a standalone question which can be understood
    without the chat history and passed to a RAG agent.

    Do NOT answer the question, just pass the standalone question as it is.
    Return only the formulated question and nothing else.

    If chat history is not present or empty and then return the question as it is.
"""

context_prompt = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(system_query),
    MessagesPlaceholder(variable_name="chat_history"),
    HumanMessagePromptTemplate.from_template("{input_query}")
])

llm = ChatOpenAI(model='gpt-4o-mini')

context_chain = (context_prompt | llm | StrOutputParser()).with_config(run_name="context_chain")