"""Documents endpoints: list, upload, search, reindex, delete for the RAG index."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_413_CONTENT_TOO_LARGE,
)

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["documents"])

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(BASE_DIR))

from rag import (  # noqa: E402
    DOCS_DIR,
    INDEX_DIR,
    SUPPORTED,
    build_index,
    read_file,
    search as rag_search,
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_EXTRACTED_CHARS = 40_000


@router.post("/documents/extract")
async def extract_document_text(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Dict[str, str]:
    """Extract a selected document for one chat turn without storing it."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(SUPPORTED))}",
        )
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=HTTP_413_CONTENT_TOO_LARGE, detail="file too large (max 25 MB)")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_file.write(data)
            temp_path = Path(temp_file.name)
        pages = read_file(temp_path)
        text = "\n\n".join(
            (f"[{page}]\n" if page else "") + content for page, content in pages if content.strip()
        ).strip()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Could not read this document.") from exc
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)

    if not text:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No readable text found in this document.")
    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[:MAX_EXTRACTED_CHARS] + "\n\n[Document text truncated]"
    return {"filename": Path(file.filename or "document").name, "text": text}


class ReindexOut(BaseModel):
    files: int
    chunks: int
    skipped: List[str]


@router.get("/documents")
def list_documents(
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Dict[str, Any]:
    """List files available in the docs/ folder and whether the index exists."""
    DOCS_DIR.mkdir(exist_ok=True)
    files = sorted(
        str(p.relative_to(DOCS_DIR))
        for p in DOCS_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED
    )
    index_exists = (INDEX_DIR / "embeddings.npy").exists() and (
        INDEX_DIR / "chunks.json"
    ).exists()
    return {
        "documents": files,
        "index_exists": index_exists,
        "count": len(files),
    }


class UploadOut(BaseModel):
    ok: bool
    filename: str
    size: int
    message: str


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> UploadOut:
    """Upload a document into docs/ (txt, md, pdf)."""
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(SUPPORTED))}",
        )

    # Read one byte beyond the limit so large uploads are rejected without
    # buffering an unbounded request body in memory.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=HTTP_413_CONTENT_TOO_LARGE,
            detail="file too large (max 25 MB)",
        )

    DOCS_DIR.mkdir(exist_ok=True)
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="invalid filename")
    dest = DOCS_DIR / filename
    # prevent path traversal
    if not str(dest.resolve()).startswith(str(DOCS_DIR.resolve()) + os.sep) and str(
        dest.resolve()
    ) != str(DOCS_DIR.resolve()):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="invalid filename")

    with open(dest, "wb") as f:
        f.write(data)

    # invalidate RAG cache so next search re-reads index
    try:
        import rag as _rag

        _rag._cache = None  # type: ignore[attr-defined]
    except Exception:
        pass

    return UploadOut(
        ok=True,
        filename=filename,
        size=len(data),
        message=f"Uploaded '{filename}'. Reindex to make it searchable.",
    )


@router.get("/documents/search")
def search_documents(
    q: str = "",
    k: int = Query(5, ge=1, le=20),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Dict[str, Any]:
    """Search the RAG document index."""
    if not q.strip():
        return {"results": []}
    try:
        hits = rag_search(q, k=k)
    except FileNotFoundError:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="No document index found. Upload documents and click Reindex.",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"search failed: {e}")
    return {
        "results": [
            {
                "source": h.get("source", ""),
                "page": h.get("page"),
                "score": round(float(h.get("score", 0)), 3),
                "text": h.get("text", ""),
            }
            for h in hits
        ]
    }


@router.post("/documents/reindex")
def reindex_documents(
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> ReindexOut:
    """Rebuild the RAG search index from docs/."""
    try:
        stats = build_index()
    except ValueError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"reindex failed: {e}")
    return ReindexOut(
        files=stats.get("files", 0),
        chunks=stats.get("chunks", 0),
        skipped=stats.get("skipped", []),
    )


@router.delete("/documents/{filename:path}")
def delete_document(
    filename: str,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Dict[str, Any]:
    """Delete a document from docs/."""
    DOCS_DIR.mkdir(exist_ok=True)
    target = (DOCS_DIR / filename).resolve()
    if DOCS_DIR.resolve() not in target.parents and target != DOCS_DIR.resolve():
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="invalid filename")
    if not target.is_file():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="document not found")
    try:
        target.unlink()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"delete failed: {e}")
    # invalidate RAG cache
    try:
        import rag as _rag

        _rag._cache = None  # type: ignore[attr-defined]
    except Exception:
        pass
    return {"ok": True, "filename": filename, "message": f"Deleted '{filename}'."}
