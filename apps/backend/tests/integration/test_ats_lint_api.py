"""Integration tests for GET /api/v1/resumes/{id}/ats-lint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _record(processed_data: dict | None) -> dict:
    return {
        "resume_id": "res-123",
        "content": "# Jane Doe",
        "content_type": "md",
        "processed_data": processed_data,
        "processing_status": "ready",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


class TestAtsLintEndpoint:
    @patch("app.routers.resumes.db", new_callable=AsyncMock)
    async def test_missing_resume_returns_404(self, mock_db, client):
        mock_db.get_resume.return_value = None
        async with client:
            resp = await client.get("/api/v1/resumes/nope/ats-lint")
        assert resp.status_code == 404

    @patch("app.routers.resumes.db", new_callable=AsyncMock)
    async def test_returns_findings_and_summary(self, mock_db, client):
        # Missing email + phone (2 errors) on an otherwise sparse resume.
        mock_db.get_resume.return_value = _record(
            {
                "personalInfo": {"email": "", "phone": ""},
                "workExperience": [],
                "education": [],
                "additional": {"technicalSkills": []},
                "summary": "",
            }
        )
        async with client:
            resp = await client.get("/api/v1/resumes/res-123/ats-lint")

        assert resp.status_code == 200
        body = resp.json()
        codes = {f["code"] for f in body["findings"]}
        assert "contact.missing_email" in codes
        assert "contact.missing_phone" in codes
        # Summary counts must match the findings list by severity.
        errors = sum(1 for f in body["findings"] if f["severity"] == "error")
        warnings = sum(1 for f in body["findings"] if f["severity"] == "warn")
        infos = sum(1 for f in body["findings"] if f["severity"] == "info")
        assert body["summary"] == {
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
        }
        assert body["summary"]["errors"] >= 2

    @patch("app.routers.resumes.db", new_callable=AsyncMock)
    async def test_unparsed_resume_returns_empty_result(self, mock_db, client):
        mock_db.get_resume.return_value = _record(None)
        async with client:
            resp = await client.get("/api/v1/resumes/res-123/ats-lint")
        assert resp.status_code == 200
        assert resp.json() == {
            "findings": [],
            "summary": {"errors": 0, "warnings": 0, "infos": 0},
        }
