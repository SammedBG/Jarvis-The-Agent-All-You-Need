"""
Build (or rebuild) the document index.

1. Put .txt, .md or .pdf files into the docs/ folder
2. Run:  python ingest.py
Run it again whenever you add or change documents (or type /reindex in the agent).
"""
from rag import DOCS_DIR, build_index

if __name__ == "__main__":
    DOCS_DIR.mkdir(exist_ok=True)
    print(f"Reading documents from: {DOCS_DIR}")
    print("(first run downloads the embedding model, about 100 MB)")
    try:
        stats = build_index()
    except ValueError as e:
        raise SystemExit(f"Error: {e}")
    print(f"Indexed {stats['files']} file(s) into {stats['chunks']} chunks.")
    if stats["skipped"]:
        print(f"Skipped (no text found, maybe scanned PDFs): {', '.join(stats['skipped'])}")