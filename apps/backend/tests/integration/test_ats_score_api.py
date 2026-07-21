"""Integration tests for the baseline ATS-score endpoint.

`POST /api/v1/resumes/{resume_id}/ats-score` scores the current, untailored
resume against a job WITHOUT running the LLM tailoring pipeline. These tests
prove it returns a valid ATSScore and that no tailoring function is invoked.
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def resume_record(sample_resume):
    return {
        "resume_id": "res-123",
        "content": "# Jane Doe",
        "content_type": "md",
        "filename": "resume.pdf",
        "is_master": True,
        "processed_data": sample_resume,
        "processing_status": "ready",
    }


@pytest.fixture
def cached_job(sample_job_description, sample_job_keywords):
    """A job whose keyword cache is valid — no extraction call should happen."""
    return {
        "job_id": "job-123",
        "content": sample_job_description,
        "job_keywords": sample_job_keywords,
        "job_keywords_hash": _content_hash(sample_job_description),
    }


class TestAtsScoreEndpoint:
    """POST /api/v1/resumes/{resume_id}/ats-score"""

    @patch("app.routers.resumes.generate_skill_target_plan", new_callable=AsyncMock)
    @patch("app.routers.resumes.generate_resume_diffs", new_callable=AsyncMock)
    @patch("app.routers.resumes.improve_resume", new_callable=AsyncMock)
    @patch("app.routers.resumes.refine_resume", new_callable=AsyncMock)
    @patch("app.routers.resumes.extract_job_keywords", new_callable=AsyncMock)
    @patch("app.routers.resumes.db", new_callable=AsyncMock)
    async def test_returns_score_without_tailoring(
        self,
        mock_db,
        mock_extract,
        mock_refine,
        mock_improve,
        mock_diffs,
        mock_skill_plan,
        client,
        resume_record,
        cached_job,
    ):
        mock_db.get_resume.return_value = resume_record
        mock_db.get_job.return_value = cached_job

        async with client:
            resp = await client.post(
                "/api/v1/resumes/res-123/ats-score",
                json={"job_id": "job-123"},
            )

        assert resp.status_code == 200
        body = resp.json()
        # Valid ATSScore shape
        assert 0.0 <= body["overall_score"] <= 100.0
        assert set(body["sub_scores"]) == {
            "keyword_match",
            "skills_coverage",
            "section_completeness",
        }
        assert isinstance(body["missing_keywords"], list)
        assert isinstance(body["recommendations"], list)
        # sample_resume has Python/FastAPI/Docker but not Kubernetes → non-zero
        # but imperfect keyword match, so the score is meaningfully computed.
        assert body["sub_scores"]["keyword_match"] > 0.0

        # The tailoring pipeline (and its LLM calls) must NOT run.
        mock_skill_plan.assert_not_called()
        mock_diffs.assert_not_called()
        mock_improve.assert_not_called()
        mock_refine.assert_not_called()
        # Keyword cache was valid, so no extraction LLM call either.
        mock_extract.assert_not_called()
        # Score-only path never persists anything.
        mock_db.update_job.assert_not_called()

    @patch("app.routers.resumes.generate_resume_diffs", new_callable=AsyncMock)
    @patch("app.routers.resumes.refine_resume", new_callable=AsyncMock)
    @patch("app.routers.resumes.extract_job_keywords", new_callable=AsyncMock)
    @patch("app.routers.resumes.db", new_callable=AsyncMock)
    async def test_cold_cache_extracts_keywords_but_not_tailor(
        self,
        mock_db,
        mock_extract,
        mock_refine,
        mock_diffs,
        client,
        resume_record,
        sample_job_description,
        sample_job_keywords,
    ):
        mock_db.get_resume.return_value = resume_record
        mock_db.get_job.return_value = {
            "job_id": "job-123",
            "content": sample_job_description,
            "job_keywords": None,
            "job_keywords_hash": None,
        }
        mock_extract.return_value = sample_job_keywords
        mock_db.update_job.return_value = {"job_id": "job-123"}

        async with client:
            resp = await client.post(
                "/api/v1/resumes/res-123/ats-score",
                json={"job_id": "job-123"},
            )

        assert resp.status_code == 200
        # Cache miss → one extraction call + one cache write, but still no tailoring.
        mock_extract.assert_awaited_once()
        mock_db.update_job.assert_awaited_once()
        mock_diffs.assert_not_called()
        mock_refine.assert_not_called()

    @patch("app.routers.resumes.db", new_callable=AsyncMock)
    async def test_job_not_found_returns_404(self, mock_db, client, resume_record):
        mock_db.get_resume.return_value = resume_record
        mock_db.get_job.return_value = None

        async with client:
            resp = await client.post(
                "/api/v1/resumes/res-123/ats-score",
                json={"job_id": "missing"},
            )
        assert resp.status_code == 404

    @patch("app.routers.resumes.db", new_callable=AsyncMock)
    async def test_resume_not_found_returns_404(self, mock_db, client):
        mock_db.get_resume.return_value = None

        async with client:
            resp = await client.post(
                "/api/v1/resumes/missing/ats-score",
                json={"job_id": "job-123"},
            )
        assert resp.status_code == 404

    @patch("app.routers.resumes.db", new_callable=AsyncMock)
    async def test_missing_processed_data_returns_422(
        self, mock_db, client, cached_job
    ):
        mock_db.get_resume.return_value = {
            "resume_id": "res-123",
            "content": "# Jane Doe",
            "content_type": "md",
            "processed_data": None,
        }
        mock_db.get_job.return_value = cached_job

        async with client:
            resp = await client.post(
                "/api/v1/resumes/res-123/ats-score",
                json={"job_id": "job-123"},
            )
        assert resp.status_code == 422
        assert "process" in resp.json()["detail"].lower()
