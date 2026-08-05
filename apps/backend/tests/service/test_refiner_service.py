"""Service tests for refiner — async keyword-injection gating with mocked LLM."""

import copy
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.refinement import RefinementConfig
from app.services.refiner import refine_resume


class TestKeywordInjectionGating:
    """refine_resume must only inject keywords the master resume already backs.

    Unbacked JD skills go through the verified skill-target-plan + diff
    pipeline instead (which the candidate reviews before saving) — this pass
    has no such verification, so it must not add unbacked claims.
    """

    @patch("app.services.refiner.inject_keywords", new_callable=AsyncMock)
    async def test_only_injects_master_backed_required_skill(
        self, mock_inject, sample_resume, master_resume
    ):
        # "Docker" and "Redis" only appear in the skills list (not in any bullet
        # text), so removing them from technicalSkills makes them genuinely
        # missing from the tailored resume, not just reordered out of sight.
        tailored = copy.deepcopy(sample_resume)
        tailored["additional"]["technicalSkills"] = [
            s
            for s in tailored["additional"]["technicalSkills"]
            if s not in ("Docker", "Redis")
        ]
        mock_inject.return_value = copy.deepcopy(tailored)

        await refine_resume(
            initial_tailored=tailored,
            master_resume=master_resume,  # still has Docker + Redis
            job_description="Backend role needing strong API skills.",
            job_keywords={
                "required_skills": ["Docker", "Kubernetes"],  # Docker master-backed, Kubernetes not
                "preferred_skills": [],
                "keywords": ["Redis"],  # master-backed but loose field — must be excluded
            },
            config=RefinementConfig(
                enable_keyword_injection=True,
                enable_ai_phrase_removal=False,
                enable_master_alignment_check=False,
            ),
        )

        mock_inject.assert_called_once()
        keywords_to_inject = mock_inject.call_args.args[1]
        assert keywords_to_inject == ["Docker"]

    @patch("app.services.refiner.inject_keywords", new_callable=AsyncMock)
    async def test_skips_injection_when_nothing_is_master_backed(
        self, mock_inject, sample_resume, master_resume
    ):
        tailored = copy.deepcopy(sample_resume)

        await refine_resume(
            initial_tailored=tailored,
            master_resume=master_resume,
            job_description="Platform role.",
            job_keywords={
                "required_skills": ["Kubernetes"],  # not in resume or master
                "preferred_skills": [],
                "keywords": ["onsite", "benefits"],  # padding, and not master-backed either
            },
            config=RefinementConfig(
                enable_keyword_injection=True,
                enable_ai_phrase_removal=False,
                enable_master_alignment_check=False,
            ),
        )

        mock_inject.assert_not_called()
