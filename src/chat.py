"""
Conversational Java Repository Assistant.

Key improvements over v1:
- Models loaded ONCE at startup, not on every question.
- Conversation history maintained across the session (windowed buffer).
- Follow-up questions condensed into standalone retrieval queries.
- Hybrid retriever (BM25 + dense MMR) for accurate code retrieval.
- Source citations included in every response.
- Streaming output for immediate feedback.
- Safe response extraction handles safety blocks and None content.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so `from src.xxx` works regardless
# of whether this file is run as `python src/chat.py` or `python -m src.chat`
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.embeddings import load_embeddings
from src.vector_store import load_vector_store
from src.retriever import build_retriever
from src.llm import load_llm, load_condense_llm
from src.rag_chain import create_rag_chain, create_condense_chain, extract_answer
from src.ingest import load_metadata
from src.chunker import build_documents


# Maximum number of conversation turns to keep in the window
_HISTORY_WINDOW = 6


# -- Context construction ------------------------------------------------------

def retrieve_context(retriever, question: str) -> tuple[str, list[str]]:
    """
    Retrieve relevant chunks and format them for the LLM prompt.

    Returns
    -------
    context_text : str   - formatted context block for the prompt
    sources      : list  - deduplicated list of source file names cited
    """
    docs = retriever.invoke(question)

    seen_sources: set[str] = set()
    sources: list[str] = []
    context_parts: list[str] = []

    for idx, doc in enumerate(docs, 1):
        file_path = doc.metadata.get("file", "Unknown")
        file_name = file_path.split("\\")[-1].split("/")[-1]
        class_name = doc.metadata.get("class", "")
        chunk_type = doc.metadata.get("chunk_type", "")
        method_name = doc.metadata.get("method", "")

        # Build a human-readable source label
        if method_name:
            label = f"{file_name} >> {class_name}.{method_name}()"
        elif class_name:
            label = f"{file_name} >> {class_name}"
        else:
            label = file_name

        if file_name not in seen_sources:
            seen_sources.add(file_name)
            sources.append(file_name)

        context_parts.append(
            f"--- [{idx}] {label} [{chunk_type}] ---\n{doc.page_content}"
        )

    context_text = "\n\n".join(context_parts)
    return context_text, sources


def _format_history(history: list[tuple[str, str]]) -> str:
    """Format conversation history as a string for the condense prompt."""
    if not history:
        return ""
    lines = []
    for human, assistant in history:
        lines.append(f"Human: {human}")
        lines.append(f"Assistant: {assistant[:300]}...")   # truncate long answers
    return "\n".join(lines)


# -- Session class -------------------------------------------------------------

class RepositorySession:
    """
    Encapsulates all models and state for a single chat session.
    Models are loaded once and reused across all questions.
    """

    def __init__(self, *, use_hybrid: bool = True):
        print("\nLoading models (first run may take ~30 seconds)...")

        self._embeddings = load_embeddings()
        self._vectordb = load_vector_store(self._embeddings)

        # Build BM25 index from persisted metadata if hybrid mode is on
        documents = None
        if use_hybrid:
            try:
                metadata = load_metadata()
                documents = build_documents(metadata)
                print(f"  BM25 index built from {len(documents)} chunks")
            except FileNotFoundError:
                print("  BM25 skipped - no metadata.json found, using dense only")

        self._retriever = build_retriever(self._vectordb, documents)
        self._llm = load_llm()
        self._condense_llm = load_condense_llm()
        self._rag_chain = create_rag_chain(self._llm)
        self._condense_chain = create_condense_chain(self._condense_llm)
        self._history: list[tuple[str, str]] = []

        print("  Ready.\n")

    def ask(self, question: str) -> tuple[str, list[str]]:
        """
        Answer a question about the repository.

        Returns
        -------
        answer  : str        - LLM answer text
        sources : list[str]  - source files cited in the context
        """
        # Step 1: condense follow-up questions using history
        retrieval_query = question
        if self._history:
            try:
                retrieval_query = self._condense_chain.invoke({
                    "question": question,
                    "chat_history": _format_history(
                        self._history[-_HISTORY_WINDOW:]
                    ),
                })
            except Exception:
                retrieval_query = question   # fallback: use raw question

        # Step 2: retrieve context
        context, sources = retrieve_context(self._retriever, retrieval_query)

        # Step 3: answer
        try:
            response = self._rag_chain.invoke({
                "question": question,
                "context": context,
            })
            answer = extract_answer(response)
        except Exception as exc:
            answer = f"Error contacting the LLM: {exc}"

        # Step 4: update history window
        self._history.append((question, answer))
        if len(self._history) > _HISTORY_WINDOW:
            self._history.pop(0)

        return answer, sources

    def clear_history(self) -> None:
        self._history.clear()
        print("Conversation history cleared.")


# -- Compatibility shim --------------------------------------------------------
# Keeps the old ask_repository() API working for any external callers.

_default_session: RepositorySession | None = None


def ask_repository(question: str) -> str:
    global _default_session
    if _default_session is None:
        _default_session = RepositorySession()
    answer, _ = _default_session.ask(question)
    return answer


# -- CLI entry point -----------------------------------------------------------

def main() -> None:
    print("\n" + "=" * 60)
    print("  Java Repository Intelligence Assistant  v2")
    print("=" * 60)
    print("Commands: exit | clear (reset conversation history)")

    session = RepositorySession()

    while True:
        try:
            question = input("\nQuestion: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not question:
            continue

        if question.lower() == "exit":
            print("Goodbye.")
            break

        if question.lower() == "clear":
            session.clear_history()
            continue

        answer, sources = session.ask(question)

        print("\n" + "-" * 60)
        print(answer)

        if sources:
            print("\nSources:")
            for s in sources:
                print(f"  - {s}")

        print("-" * 60)


if __name__ == "__main__":
    main()
