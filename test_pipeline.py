"""Integration test: ingestion + chunking pipeline."""
from src.ingest import ingest_repository, save_metadata, load_metadata
from src.chunker import build_documents

print("=== Ingestion Test ===")
data = ingest_repository("sample_repo")
print("Files parsed:", len(data))
print("Methods found:", data[0]["methods"])
print("Has content field:", "content" in data[0])

save_metadata(data)
loaded = load_metadata()
print("Reload OK:", len(loaded), "records")

print()
print("=== Chunking Test ===")
docs = build_documents(data)
print("Documents created:", len(docs))
for d in docs:
    chunk_type = d.metadata.get("chunk_type", "")
    class_name = d.metadata.get("class", "")
    method_name = d.metadata.get("method", "")
    print(f"  chunk_type={chunk_type} class={class_name} method={method_name}")
    print(f"  content preview: {d.page_content[:100].strip()}")
    print()

print("=== Scanner Test ===")
from src.scanner import scan_repository
files = scan_repository("sample_repo")
print("Files found:", [str(f) for f in files])
