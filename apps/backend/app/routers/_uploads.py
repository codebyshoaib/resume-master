"""Shared upload validation for endpoints that ingest user documents.

Lives in the router layer rather than ``services/`` because it raises
``HTTPException``: services in this codebase stay transport-agnostic (no
service module imports fastapi). Both the resume upload and the career-document
upload route through here so the guards — type, size, empty file, unparseable
file, image-only/scanned file — exist in exactly one place.
"""

import logging

from fastapi import HTTPException, UploadFile

from app.services.parser import parse_document

logger = logging.getLogger(__name__)

RESUME_TYPES = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
RESUME_TYPES_LABEL = "PDF, DOC, DOCX"
RESUME_MAX_BYTES = 4 * 1024 * 1024  # 4MB

# Career documents are pasted or exported from more places than resumes are, so
# plain text and markdown are allowed and the cap is higher.
CAREER_TYPES = RESUME_TYPES | frozenset({"text/plain", "text/markdown"})
CAREER_TYPES_LABEL = "PDF, DOC, DOCX, TXT, MD"
CAREER_MAX_BYTES = 10 * 1024 * 1024  # 10MB

# ``parse_document`` picks the markitdown converter off the filename suffix, so
# an upload with no filename still needs a plausible extension.
_SUFFIX_BY_TYPE = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}


async def read_and_extract(
    file: UploadFile,
    *,
    allowed_types: frozenset[str],
    allowed_label: str,
    max_bytes: int,
) -> tuple[str, int]:
    """Validate an upload and extract it to Markdown.

    Guards run in this order so the cheapest rejection happens first, and so a
    zero-byte file is reported as empty rather than as a parse failure:
    content type, size, emptiness, parseability, extractable text.

    Returns:
        ``(markdown_text, raw_byte_size)``. The byte size is the size of the
        *uploaded file*, not of the extracted text — callers report it in
        analytics, and the two differ for PDF and DOCX.

    Raises:
        HTTPException: 400 (bad type / empty), 413 (too large), 422 (unparseable
            or no extractable text). Details are logged; client messages stay
            generic.
    """
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Allowed: {allowed_label}",
        )

    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {max_bytes // (1024 * 1024)}MB",
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    filename = file.filename or f"document{_SUFFIX_BY_TYPE.get(file.content_type or '', '')}"
    try:
        text = await parse_document(content, filename)
    except Exception as e:
        logger.error(f"Document parsing failed for {filename!r}: {e}")
        raise HTTPException(
            status_code=422,
            detail="Failed to parse document. Please ensure the file is valid and not corrupted.",
        )

    # Image-based / scanned documents parse successfully but yield no text.
    # markitdown does not OCR, so this is a dead end for the user, not a retry.
    if not text or not text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not extract text from the uploaded file. The document may be "
                "image-based or scanned. Please upload a file with selectable text."
            ),
        )

    return text, len(content)
