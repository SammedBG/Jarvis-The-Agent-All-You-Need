"""
RAG building blocks: read documents -> chunk -> embed -> save index -> search.

Embeddings run locally with `fastembed` (small ONNX model, downloaded once on
first use). The index is just two files, so there is no database to run:
    rag_index/embeddings.npy   one vector per chunk
    rag_index/chunks.json      the chunk text + source file (+ page for PDFs)
"""
import json
import re
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
INDEX_DIR = BASE_DIR / "rag_index"

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_SIZE = 500      # characters per chunk (smaller = more precise for short notes)
CHUNK_OVERLAP = 80    # characters shared between neighbouring chunks
SUPPORTED = {".txt", ".md", ".pdf"}

# --------------------------------------------------------------------------
# 1. EMBEDDINGS
# --------------------------------------------------------------------------

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding  # downloads the model on first use

        _model = TextEmbedding(model_name=EMBED_MODEL)
    return _model


def _normalize(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=-1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms


def embed_docs(texts: list[str]) -> np.ndarray:
    """Embed document chunks. Returns an (n, dim) array of unit vectors."""
    vecs = np.array(list(_get_model().embed(texts)), dtype="float32")
    return _normalize(vecs)


def embed_query(query: str) -> np.ndarray:
    """Embed a search query. Returns a (dim,) unit vector."""
    vec = np.array(list(_get_model().query_embed(query))[0], dtype="float32")
    return _normalize(vec)


# --------------------------------------------------------------------------
# 2. READING + CHUNKING
# --------------------------------------------------------------------------


def read_file(path: Path) -> list[tuple[str | None, str]]:
    """Return [(page_label, text), ...]. Page label is only set for PDFs."""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return [(None, path.read_text(encoding="utf-8", errors="ignore"))]
    if suffix == ".pdf":
        from pypdf import PdfReader

        pages = []
        for n, page in enumerate(PdfReader(str(path)).pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((f"p{n}", text))
        return pages
    return []


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph/sentence breaks."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            for sep in ("\n\n", "\n", ". ", " "):
                idx = window.rfind(sep)
                if idx > size * 0.5:  # only break late enough to keep chunks sizeable
                    end = start + idx + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)  # always move forward
    return chunks


# --------------------------------------------------------------------------
# 3. INDEXING + SEARCH
# --------------------------------------------------------------------------

_cache = None


def build_index() -> dict:
    """Read everything in docs/, embed it, and save the index."""
    DOCS_DIR.mkdir(exist_ok=True)
    files = [p for p in sorted(DOCS_DIR.rglob("*")) if p.is_file() and p.suffix.lower() in SUPPORTED]

    records, skipped = [], []
    for path in files:
        rel = str(path.relative_to(DOCS_DIR))
        before = len(records)
        for label, text in read_file(path):
            for chunk in chunk_text(text):
                records.append({"source": rel, "page": label, "text": chunk})
        if len(records) == before:
            skipped.append(rel)  # e.g. a scanned PDF with no text layer

    if not records:
        raise ValueError("No readable text found in docs/. Add .txt, .md or .pdf files.")

    vecs = embed_docs([r["text"] for r in records])
    INDEX_DIR.mkdir(exist_ok=True)
    np.save(INDEX_DIR / "embeddings.npy", vecs)
    (INDEX_DIR / "chunks.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    global _cache
    _cache = None  # force reload on next search
    return {"files": len(files) - len(skipped), "chunks": len(records), "skipped": skipped}


def _load_index() -> dict:
    global _cache
    if _cache is None:
        emb_path, chunks_path = INDEX_DIR / "embeddings.npy", INDEX_DIR / "chunks.json"
        if not emb_path.exists() or not chunks_path.exists():
            raise FileNotFoundError("No document index found. Run: python ingest.py")
        _cache = {
            "emb": np.load(emb_path),
            "chunks": json.loads(chunks_path.read_text(encoding="utf-8")),
        }
    return _cache


def search(query: str, k: int = 3) -> list[dict]:
    """Return the top-k chunks for a query, each with a similarity score."""
    index = _load_index()
    scores = index["emb"] @ embed_query(query)  # cosine similarity (unit vectors)
    top = np.argsort(-scores)[:k]
    return [dict(index["chunks"][int(i)], score=float(scores[int(i)])) for i in top]