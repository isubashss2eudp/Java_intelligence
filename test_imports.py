"""Test that all module imports resolve correctly end-to-end."""
errors = []

modules = [
    "src.models",
    "src.scanner",
    "src.parser",
    "src.ingest",
    "src.chunker",
    "src.embeddings",
    "src.vector_store",
    "src.retriever",
    "src.prompts",
    "src.llm",
    "src.rag_chain",
    "src.chat",
]

for mod in modules:
    try:
        __import__(mod)
        print(f"  OK  {mod}")
    except Exception as e:
        print(f"  FAIL {mod}: {e}")
        errors.append((mod, str(e)))

print()
if errors:
    print(f"FAILED: {len(errors)} module(s) have import errors")
else:
    print("ALL IMPORTS OK")
