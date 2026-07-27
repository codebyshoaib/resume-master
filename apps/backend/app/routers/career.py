"""Career corpus endpoints.

Phase 1 of ``docs/specs/career-corpus-spec.md``: the store the corpus is
assembled from. No LLM calls here — this router is pure CRUD plus the shared
upload extraction.
"""

import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.database import db
from app.routers._uploads import (
    CAREER_MAX_BYTES,
    CAREER_TYPES,
    CAREER_TYPES_LABEL,
    read_and_extract,
)
from app.schemas import (
    CareerDocumentCreate,
    CareerDocumentKind,
    CareerDocumentListResponse,
    CareerDocumentResponse,
    CareerDocumentSummary,
    CareerDocumentUpdate,
    PREVIEW_CHARS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/career", tags=["Career Corpus"])


def _summary(doc: dict) -> CareerDocumentSummary:
    """Project a stored document to its list-view form (body truncated)."""
    content = doc.get("content") or ""
    return CareerDocumentSummary(
        document_id=doc["document_id"],
        title=doc["title"],
        kind=doc["kind"],
        filename=doc.get("filename"),
        include_in_context=doc["include_in_context"],
        preview=content[:PREVIEW_CHARS],
        char_count=len(content),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _full(doc: dict) -> CareerDocumentResponse:
    """Project a stored document to its detail form (full body)."""
    return CareerDocumentResponse(**_summary(doc).model_dump(), content=doc.get("content") or "")


def _title_from_filename(filename: str | None) -> str:
    """Derive a human title from an upload's filename.

    Falls back to a constant rather than an empty string: ``title`` is
    non-nullable and an untitled row is unusable in the list UI.
    """
    if not filename:
        return "Untitled document"
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0].strip()
    return stem or "Untitled document"


@router.get("/documents", response_model=CareerDocumentListResponse)
async def list_career_documents(
    kind: CareerDocumentKind | None = Query(default=None),
) -> CareerDocumentListResponse:
    """List career documents, oldest first, with truncated bodies."""
    docs = await db.list_career_documents(kind=kind.value if kind else None)
    return CareerDocumentListResponse(documents=[_summary(d) for d in docs])


@router.get("/documents/{document_id}", response_model=CareerDocumentResponse)
async def get_career_document(document_id: str) -> CareerDocumentResponse:
    """Fetch one document with its full body."""
    doc = await db.get_career_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _full(doc)


@router.post("/documents", response_model=CareerDocumentResponse, status_code=201)
async def create_career_document(payload: CareerDocumentCreate) -> CareerDocumentResponse:
    """Create a document from pasted text."""
    try:
        doc = await db.create_career_document(
            title=payload.title,
            content=payload.content,
            kind=payload.kind.value,
        )
    except Exception as e:
        logger.error(f"Career document create failed: {e}")
        raise HTTPException(status_code=500, detail="Could not save document. Please try again.")
    return _full(doc)


@router.post("/documents/upload", response_model=CareerDocumentResponse, status_code=201)
async def upload_career_document(
    file: UploadFile = File(...),
    kind: CareerDocumentKind = Query(default=CareerDocumentKind.other),
) -> CareerDocumentResponse:
    """Upload a document (PDF/DOC/DOCX/TXT/MD) and store its extracted text."""
    content, _size = await read_and_extract(
        file,
        allowed_types=CAREER_TYPES,
        allowed_label=CAREER_TYPES_LABEL,
        max_bytes=CAREER_MAX_BYTES,
    )
    try:
        doc = await db.create_career_document(
            title=_title_from_filename(file.filename),
            content=content,
            kind=kind.value,
            filename=file.filename,
        )
    except Exception as e:
        logger.error(f"Career document upload persist failed: {e}")
        raise HTTPException(status_code=500, detail="Could not save document. Please try again.")
    return _full(doc)


@router.patch("/documents/{document_id}", response_model=CareerDocumentResponse)
async def update_career_document(
    document_id: str, payload: CareerDocumentUpdate
) -> CareerDocumentResponse:
    """Patch a document. Omitted fields are left untouched."""
    updates = payload.model_dump(exclude_unset=True)
    if "kind" in updates and updates["kind"] is not None:
        updates["kind"] = payload.kind.value if payload.kind else None
    # Drop explicit nulls: PATCH omission and PATCH null both mean "leave alone"
    # here, since none of these columns are meaningfully nullable.
    updates = {k: v for k, v in updates.items() if v is not None}
    if not updates:
        doc = await db.get_career_document(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return _full(doc)

    doc = await db.update_career_document(document_id, updates)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _full(doc)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_career_document(document_id: str) -> None:
    """Delete a document. 404 when it does not exist, so retries are honest."""
    if not await db.delete_career_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
