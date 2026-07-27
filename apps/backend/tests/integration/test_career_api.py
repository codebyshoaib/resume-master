"""Integration tests for the career-corpus document endpoints.

Phase 1 of ``docs/specs/career-corpus-spec.md``. These run against a real
(isolated) SQLite database via ``isolated_db`` and make no LLM calls — this
router has none. The upload guards are shared with the resume upload
(``app/routers/_uploads.py``), so the cases here pin the *career* wiring:
the wider type allowlist, the higher cap, and the filename→title derivation.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers._uploads import CAREER_MAX_BYTES
from app.schemas.career import PREVIEW_CHARS


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _create(client, **kwargs):
    payload = {"title": "Review 2024", "content": "Led the SQLite migration.", **kwargs}
    resp = await client.post("/api/v1/career/documents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestDocumentCrud:
    async def test_create_returns_full_document(self, isolated_db, client):
        async with client:
            doc = await _create(client, kind="review")
        assert doc["document_id"]
        assert doc["title"] == "Review 2024"
        assert doc["content"] == "Led the SQLite migration."
        assert doc["kind"] == "review"
        assert doc["include_in_context"] is True
        assert doc["char_count"] == len("Led the SQLite migration.")

    async def test_create_rejects_empty_content(self, isolated_db, client):
        async with client:
            resp = await client.post(
                "/api/v1/career/documents", json={"title": "t", "content": ""}
            )
        assert resp.status_code == 422

    async def test_create_rejects_unknown_kind(self, isolated_db, client):
        async with client:
            resp = await client.post(
                "/api/v1/career/documents",
                json={"title": "t", "content": "x", "kind": "nonsense"},
            )
        assert resp.status_code == 422

    async def test_list_truncates_body_to_preview(self, isolated_db, client):
        long_body = "x" * (PREVIEW_CHARS + 500)
        async with client:
            await _create(client, content=long_body)
            resp = await client.get("/api/v1/career/documents")
        assert resp.status_code == 200
        row = resp.json()["documents"][0]
        assert len(row["preview"]) == PREVIEW_CHARS
        assert row["char_count"] == PREVIEW_CHARS + 500
        # The list view must not ship the whole corpus to render a row.
        assert "content" not in row

    async def test_list_filters_by_kind(self, isolated_db, client):
        async with client:
            await _create(client, title="a", kind="review")
            await _create(client, title="b", kind="brag")
            resp = await client.get("/api/v1/career/documents", params={"kind": "review"})
        assert [d["title"] for d in resp.json()["documents"]] == ["a"]

    async def test_get_returns_full_body(self, isolated_db, client):
        async with client:
            created = await _create(client)
            resp = await client.get(f"/api/v1/career/documents/{created['document_id']}")
        assert resp.status_code == 200
        assert resp.json()["content"] == "Led the SQLite migration."

    async def test_get_missing_returns_404(self, isolated_db, client):
        async with client:
            resp = await client.get("/api/v1/career/documents/nope")
        assert resp.status_code == 404

    async def test_patch_updates_only_supplied_fields(self, isolated_db, client):
        async with client:
            created = await _create(client, kind="review")
            resp = await client.patch(
                f"/api/v1/career/documents/{created['document_id']}",
                json={"title": "Renamed"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Renamed"
        # Untouched fields survive the patch.
        assert body["content"] == created["content"]
        assert body["kind"] == "review"

    async def test_patch_can_mute_from_context(self, isolated_db, client):
        async with client:
            created = await _create(client)
            resp = await client.patch(
                f"/api/v1/career/documents/{created['document_id']}",
                json={"include_in_context": False},
            )
        assert resp.status_code == 200
        assert resp.json()["include_in_context"] is False

    async def test_patch_missing_returns_404(self, isolated_db, client):
        async with client:
            resp = await client.patch("/api/v1/career/documents/nope", json={"title": "x"})
        assert resp.status_code == 404

    async def test_patch_empty_body_is_a_noop_not_an_error(self, isolated_db, client):
        async with client:
            created = await _create(client)
            resp = await client.patch(
                f"/api/v1/career/documents/{created['document_id']}", json={}
            )
        assert resp.status_code == 200
        assert resp.json()["title"] == created["title"]

    async def test_patch_rejects_blanking_title(self, isolated_db, client):
        async with client:
            created = await _create(client)
            resp = await client.patch(
                f"/api/v1/career/documents/{created['document_id']}", json={"title": ""}
            )
        assert resp.status_code == 422

    async def test_delete_then_get_is_404(self, isolated_db, client):
        async with client:
            created = await _create(client)
            resp = await client.delete(f"/api/v1/career/documents/{created['document_id']}")
            assert resp.status_code == 204
            follow_up = await client.get(f"/api/v1/career/documents/{created['document_id']}")
        assert follow_up.status_code == 404

    async def test_delete_missing_returns_404(self, isolated_db, client):
        async with client:
            resp = await client.delete("/api/v1/career/documents/nope")
        assert resp.status_code == 404


class TestUploadWiring:
    """The guards live in ``_uploads``; these pin the career-specific wiring."""

    @patch("app.routers._uploads.parse_document", new_callable=AsyncMock)
    async def test_upload_stores_extracted_text(self, mock_parse, isolated_db, client):
        mock_parse.return_value = "# 2024 Review\n\nShipped the thing."
        async with client:
            resp = await client.post(
                "/api/v1/career/documents/upload",
                files={"file": ("2024 review.pdf", b"%PDF-1.4", "application/pdf")},
                params={"kind": "review"},
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["content"] == "# 2024 Review\n\nShipped the thing."
        assert body["kind"] == "review"
        assert body["filename"] == "2024 review.pdf"
        # Title is derived from the filename stem, extension dropped.
        assert body["title"] == "2024 review"

    @patch("app.routers._uploads.parse_document", new_callable=AsyncMock)
    async def test_upload_accepts_plain_text_which_resumes_reject(
        self, mock_parse, isolated_db, client
    ):
        """The career allowlist is deliberately wider than the resume one."""
        mock_parse.return_value = "some notes"
        async with client:
            career = await client.post(
                "/api/v1/career/documents/upload",
                files={"file": ("notes.txt", b"some notes", "text/plain")},
            )
            resume = await client.post(
                "/api/v1/resumes/upload",
                files={"file": ("notes.txt", b"some notes", "text/plain")},
            )
        assert career.status_code == 201
        assert resume.status_code == 400

    async def test_upload_rejects_unsupported_type(self, isolated_db, client):
        async with client:
            resp = await client.post(
                "/api/v1/career/documents/upload",
                files={"file": ("a.png", b"\x89PNG", "image/png")},
            )
        assert resp.status_code == 400
        assert "Invalid file type" in resp.json()["detail"]

    async def test_upload_rejects_oversized_file(self, isolated_db, client):
        async with client:
            resp = await client.post(
                "/api/v1/career/documents/upload",
                files={
                    "file": (
                        "big.pdf",
                        b"x" * (CAREER_MAX_BYTES + 1),
                        "application/pdf",
                    )
                },
            )
        assert resp.status_code == 413

    async def test_upload_rejects_empty_file(self, isolated_db, client):
        async with client:
            resp = await client.post(
                "/api/v1/career/documents/upload",
                files={"file": ("empty.pdf", b"", "application/pdf")},
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Empty file"

    @patch("app.routers._uploads.parse_document", new_callable=AsyncMock)
    async def test_upload_rejects_scanned_document_and_persists_nothing(
        self, mock_parse, isolated_db, client
    ):
        """markitdown does not OCR: an image-only PDF yields no text → 422."""
        mock_parse.return_value = "  \n "
        async with client:
            resp = await client.post(
                "/api/v1/career/documents/upload",
                files={"file": ("scan.pdf", b"%PDF-1.4 image", "application/pdf")},
            )
            listing = await client.get("/api/v1/career/documents")
        assert resp.status_code == 422
        assert "extract text" in resp.json()["detail"].lower()
        assert listing.json()["documents"] == []
