"""
Conversational RAG chain.

Architecture:
  1. CONDENSE step - rewrites the follow-up question using conversation
     history into a standalone retrieval query.  Uses gemini-2.5-flash
     (fast, cheap).
  2. RETRIEVE step - hybrid retriever returns relevant code chunks.
  3. ANSWER step - gemini-2.5-pro answers from context + original question.

This separates retrieval-optimised queries from user-readable answers
and enables coherent multi-turn conversations.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

from src.prompts import SYSTEM_PROMPT, CONDENSE_PROMPT


# -- Answer chain -------------------------------------------------------------

def create_rag_chain(llm):
    """
    Returns a LCEL chain that expects:
      {"question": str, "context": str}
    and returns the LLM message object.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        (
            "human",
            "Question:\n{question}\n\nRepository Context:\n{context}\n\nAnswer:",
        ),
    ])

    return prompt | llm


# -- Condense chain ------------------------------------------------------------

def create_condense_chain(condense_llm):
    """
    Returns a LCEL chain that expects:
      {"question": str, "chat_history": str}
    and returns a standalone search query string.
    """
    condense_prompt = PromptTemplate.from_template(CONDENSE_PROMPT)
    return condense_prompt | condense_llm | StrOutputParser()


# -- Safe response extraction --------------------------------------------------

def extract_answer(response) -> str:
    """
    Safely extract text from an LLM response.
    Handles safety blocks, None content, and unexpected types.
    """
    if response is None:
        return "No response received from the LLM."

    # LangChain AIMessage
    if hasattr(response, "content"):
        content = response.content
        if content:
            return content
        # Safety-blocked response
        return (
            "The response was blocked. "
            "This may be due to content safety filters. "
            "Try rephrasing your question."
        )

    return str(response)
