"""Test vector store: rebuild index and run a retrieval query."""
from src.ingest import load_metadata
from src.chunker import build_documents
from src.embeddings import load_embeddings
from src.vector_store import build_vector_store, load_vector_store
from src.retriever import build_retriever

print("Loading metadata and chunks...")
metadata = load_metadata()
documents = build_documents(metadata)
print(f"  {len(documents)} chunks")

print("Loading embedding model...")
embeddings = load_embeddings()

print("Rebuilding vector store...")
build_vector_store(documents, embeddings)

print("Loading vector store for query...")
vectordb = load_vector_store(embeddings)

print("Building hybrid retriever...")
retriever = build_retriever(vectordb, documents)

print("Running test query...")
results = retriever.invoke("what methods does CustomerService have")
print(f"  Retrieved {len(results)} chunks")
for r in results:
    print(f"    file={r.metadata.get('file','').split(chr(92))[-1]} "
          f"method={r.metadata.get('method','')} "
          f"type={r.metadata.get('chunk_type','')}")

print("PASS")
