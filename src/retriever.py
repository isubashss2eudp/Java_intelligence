"""
Hybrid retriever: BM25 (keyword/symbol matching) + dense MMR (semantic).
Results are merged with Reciprocal Rank Fusion (EnsembleRetriever).

Why hybrid?
-----------
Pure vector search fails on exact symbol queries like "getUserById" or
"@Transactional".  BM25 handles exact token matches; dense handles semantic
queries like "service that manages user accounts".  Combining both gives
the best of each.
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever


def build_retriever(vectordb, documents: list[Document] | None = None):
    """
    Build a hybrid retriever.

    Parameters
    ----------
    vectordb   : Chroma vector store (already loaded with embeddings).
    documents  : Optional list of Documents for BM25 index.
                 If None, BM25 is skipped and a pure MMR retriever is returned.
                 Pass the full document list from build_documents() to enable
                 hybrid mode.
    """
    # Dense MMR retriever - diverse semantic results
    dense_retriever = vectordb.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": 8,
            "fetch_k": 40,
            "lambda_mult": 0.6,   # 0 = max diversity, 1 = max relevance
        },
    )

    if not documents:
        return dense_retriever

    # BM25 retriever - exact token/symbol matching
    bm25_retriever = BM25Retriever.from_documents(documents)
    bm25_retriever.k = 8

    # EnsembleRetriever fuses results with Reciprocal Rank Fusion
    # Weight: 40% BM25 (exact match), 60% dense (semantic)
    return EnsembleRetriever(
        retrievers=[bm25_retriever, dense_retriever],
        weights=[0.4, 0.6],
    )
