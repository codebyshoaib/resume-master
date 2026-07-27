"""Integration tests for GET /api/v1/analytics/summary.

Exercises the real analytics router over a real (isolated) SQLite DB: funnel
counts for a seeded event set, the ``days`` query guard, and one end-to-end
check that the upload endpoint actually emits a ``resume_uploaded`` event.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestAnalyticsSummaryAPI:
    async def test_summary_funnel_counts(self, isolated_db):
        for _ in range(2):
            await isolated_db.record_analytics_event("resume_uploaded", {})
        await isolated_db.record_analytics_event("tailor_completed", {"delta": 3.0})
        await isolated_db.record_analytics_event("resume_pdf_downloaded", {})

        async with _client() as client:
            resp = await client.get("/api/v1/analytics/summary")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["funnel"] == {"uploads": 2, "tailors": 1, "downloads": 1}
        assert body["total_events"] == 4
        assert body["event_totals"]["resume_uploaded"] == 2
        assert body["days"] is None

    async def test_summary_empty(self, isolated_db):
        async with _client() as client:
            resp = await client.get("/api/v1/analytics/summary")
        assert resp.status_code == 200
        assert resp.json()["funnel"] == {"uploads": 0, "tailors": 0, "downloads": 0}

    async def test_days_must_be_positive(self, isolated_db):
        async with _client() as client:
            resp = await client.get("/api/v1/analytics/summary?days=0")
        assert resp.status_code == 422

    @patch("app.routers.resumes.parse_resume_to_json", new_callable=AsyncMock)
    @patch("app.routers._uploads.parse_document", new_callable=AsyncMock)
    async def test_upload_endpoint_emits_resume_uploaded(
        self, mock_parse_document, mock_parse_json, isolated_db, sample_resume
    ):
        # Instrumentation is wired: a real upload lands a resume_uploaded event.
        mock_parse_document.return_value = "# Jane Doe\nExperienced engineer."
        mock_parse_json.return_value = sample_resume

        async with _client() as client:
            upload = await client.post(
                "/api/v1/resumes/upload",
                files={"file": ("resume.pdf", b"%PDF-1.4 real bytes", "application/pdf")},
            )
            assert upload.status_code == 200, upload.text
            summary = (await client.get("/api/v1/analytics/summary")).json()

        assert summary["funnel"]["uploads"] == 1
