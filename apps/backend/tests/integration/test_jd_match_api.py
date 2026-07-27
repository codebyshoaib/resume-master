"""JD match + gap closing through the REAL routers and a REAL (isolated) DB.

Only the two LLM boundaries are mocked (`analyze_jd_match`'s `complete_json` and
`close_match_gaps`'s). Requirement extraction, caching in the job's metadata,
the diff safety gates, and persistence are all real.

What these lock:
- the analysis is cached per (resume data, JD) and re-served without a second call
- editing the resume invalidates that cache
- gap closing NEVER persists — the resume on disk is untouched until the client
  PATCHes it
- a gap-closing change aimed at an employer/title/date is rejected by the gates
  rather than written
"""

import copy
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.resumes import _hash_job_content


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_keywords(db, job_id: str, content: str, keywords: dict) -> None:
    """Prime the job's keyword cache so no test can reach the real extractor.

    ``_get_or_extract_job_keywords`` only trusts the cache when the stored hash
    matches the JD content, so the hash must be seeded alongside the keywords —
    without it the router silently falls through to a live LLM call.
    """
    await db.update_job(
        job_id,
        {"job_keywords": keywords, "job_keywords_hash": _hash_job_content(content)},
    )


JOB_KEYWORDS = {
    "required_skills": ["Python", "Kubernetes"],
    "preferred_skills": ["Terraform"],
    "key_responsibilities": [],
    "experience_requirements": [],
    "education_requirements": [],
    "keywords": ["microservices"],
}

JD_TEXT = "We need Python and Kubernetes. Terraform is a plus. Microservices."


def _judgment(python="covered", kubernetes="missing", terraform="missing"):
    """Build a judgment payload. A "covered" status carries evidence, since the
    service demotes an unquoted "covered" to "partial" on purpose."""

    def entry(name: str, status: str, note: str) -> dict:
        return {
            "requirement": name,
            "status": status,
            "evidence": f"used {name} in production" if status == "covered" else "",
            "gap_note": "" if status == "covered" else note,
        }

    return {
        "requirements": [
            entry("Python", python, "no Python depth shown"),
            entry("Kubernetes", kubernetes, "no container orchestration shown"),
            entry("Terraform", terraform, "no IaC shown"),
        ]
    }


@pytest.fixture
async def tailored(isolated_db, sample_resume):
    """A tailored resume linked to a job, the shape the JD Match tab requires."""
    master = await isolated_db.create_resume(
        content="# master", processed_data=sample_resume, processing_status="ready"
    )
    await isolated_db.set_master_resume(master["resume_id"])
    child = await isolated_db.create_resume(
        content="# tailored",
        processed_data=copy.deepcopy(sample_resume),
        processing_status="ready",
        parent_id=master["resume_id"],
    )
    job = await isolated_db.create_job(content=JD_TEXT)
    await _seed_keywords(isolated_db, job["job_id"], JD_TEXT, JOB_KEYWORDS)
    await isolated_db.create_improvement(
        original_resume_id=master["resume_id"],
        tailored_resume_id=child["resume_id"],
        job_id=job["job_id"],
        improvements=[],
    )
    return {"db": isolated_db, "resume_id": child["resume_id"], "job_id": job["job_id"]}


class TestJdMatchEndpoint:
    async def test_scores_requirements_semantically(self, tailored):
        with patch(
            "app.services.jd_match.complete_json",
            new=AsyncMock(return_value=_judgment()),
        ):
            async with _client() as client:
                res = await client.get(f"/api/v1/resumes/{tailored['resume_id']}/jd-match")

        assert res.status_code == 200
        body = res.json()
        # Python covered (required, weight 2), Kubernetes missing (2), Terraform missing (1)
        assert body["score"] == 40.0
        assert [c["status"] for c in body["coverage"]] == ["covered", "missing", "missing"]
        assert body["cached"] is False
        # Highlight set is wider than the graded requirements.
        assert "microservices" in body["highlight_keywords"]

    async def test_second_call_is_served_from_cache_without_the_llm(self, tailored):
        mock = AsyncMock(return_value=_judgment())
        with patch("app.services.jd_match.complete_json", new=mock):
            async with _client() as client:
                first = await client.get(f"/api/v1/resumes/{tailored['resume_id']}/jd-match")
            async with _client() as client:
                second = await client.get(f"/api/v1/resumes/{tailored['resume_id']}/jd-match")

        assert first.json()["cached"] is False
        assert second.json()["cached"] is True
        assert second.json()["score"] == first.json()["score"]
        assert mock.await_count == 1

    async def test_refresh_forces_a_regrade(self, tailored):
        mock = AsyncMock(side_effect=[_judgment(), _judgment(kubernetes="covered")])
        with patch("app.services.jd_match.complete_json", new=mock):
            async with _client() as client:
                await client.get(f"/api/v1/resumes/{tailored['resume_id']}/jd-match")
            async with _client() as client:
                res = await client.get(
                    f"/api/v1/resumes/{tailored['resume_id']}/jd-match?refresh=true"
                )

        assert mock.await_count == 2
        assert res.json()["cached"] is False

    async def test_editing_the_resume_invalidates_the_cache(self, tailored, sample_resume):
        mock = AsyncMock(return_value=_judgment())
        with patch("app.services.jd_match.complete_json", new=mock):
            async with _client() as client:
                await client.get(f"/api/v1/resumes/{tailored['resume_id']}/jd-match")

            edited = copy.deepcopy(sample_resume)
            edited["summary"] = "Now mentions Kubernetes and Terraform."
            await tailored["db"].update_resume(
                tailored["resume_id"], {"processed_data": edited}
            )

            with patch("app.services.jd_match.complete_json", new=mock):
                async with _client() as client:
                    res = await client.get(
                        f"/api/v1/resumes/{tailored['resume_id']}/jd-match"
                    )

        assert res.json()["cached"] is False
        assert mock.await_count == 2

    async def test_untailored_resume_is_rejected(self, isolated_db, sample_resume):
        master = await isolated_db.create_resume(
            content="# master", processed_data=sample_resume, processing_status="ready"
        )
        async with _client() as client:
            res = await client.get(f"/api/v1/resumes/{master['resume_id']}/jd-match")
        assert res.status_code == 400

    async def test_missing_resume_is_404(self):
        async with _client() as client:
            res = await client.get("/api/v1/resumes/does-not-exist/jd-match")
        assert res.status_code == 404

    async def test_no_gradable_requirements_is_422_not_a_zero_score(self, tailored):
        await _seed_keywords(
            tailored["db"], tailored["job_id"], JD_TEXT, {"keywords": ["agile"]}
        )
        async with _client() as client:
            res = await client.get(f"/api/v1/resumes/{tailored['resume_id']}/jd-match")
        assert res.status_code == 422


class TestCloseGapsEndpoint:
    async def test_proposes_changes_for_open_gaps_without_saving(self, tailored):
        gap_changes = {
            "changes": [
                {
                    "path": "additional.technicalSkills",
                    "action": "add_skill",
                    "original": None,
                    "value": "Kubernetes",
                    "reason": "closes the Kubernetes gap; suggested addition to confirm",
                },
                {
                    "path": "workExperience[0].description",
                    "action": "append",
                    "original": None,
                    "value": "Ran service deployments on Kubernetes across three environments.",
                    "reason": "closes the orchestration gap; suggested addition to confirm",
                },
            ],
            "strategy_notes": "closed two gaps",
        }
        with patch(
            "app.services.jd_match.complete_json",
            new=AsyncMock(side_effect=[_judgment(), gap_changes]),
        ):
            async with _client() as client:
                res = await client.post(
                    f"/api/v1/resumes/{tailored['resume_id']}/close-gaps"
                )

        assert res.status_code == 200
        body = res.json()
        assert len(body["changes"]) == 2
        skills = body["proposed_data"]["additional"]["technicalSkills"]
        assert "Kubernetes" in skills
        bullets = body["proposed_data"]["workExperience"][0]["description"]
        assert any("Kubernetes across three environments" in b for b in bullets)
        assert "Kubernetes" in body["closed_requirements"]

        # The stored resume must be untouched — nothing is persisted here.
        stored = await tailored["db"].get_resume(tailored["resume_id"])
        assert "Kubernetes" not in stored["processed_data"]["additional"]["technicalSkills"]

    async def test_change_targeting_an_employer_is_rejected_by_the_gates(self, tailored):
        forbidden = {
            "changes": [
                {
                    "path": "workExperience[0].company",
                    "action": "replace",
                    "original": "Acme Corp",
                    "value": "Google",
                    "reason": "sounds better",
                },
            ],
            "strategy_notes": "",
        }
        with patch(
            "app.services.jd_match.complete_json",
            new=AsyncMock(side_effect=[_judgment(), forbidden]),
        ):
            async with _client() as client:
                res = await client.post(
                    f"/api/v1/resumes/{tailored['resume_id']}/close-gaps"
                )

        body = res.json()
        assert body["changes"] == []
        assert body["rejected_count"] == 1
        assert body["proposed_data"]["workExperience"][0]["company"] == "Acme Corp"
        assert any("rejected by the safety gates" in w for w in body["warnings"])

    async def test_fully_covered_resume_has_nothing_to_close(self, tailored):
        with patch(
            "app.services.jd_match.complete_json",
            new=AsyncMock(
                return_value=_judgment(kubernetes="covered", terraform="covered")
            ),
        ):
            async with _client() as client:
                res = await client.post(
                    f"/api/v1/resumes/{tailored['resume_id']}/close-gaps"
                )

        body = res.json()
        assert body["changes"] == []
        assert any("already covered" in w for w in body["warnings"])
