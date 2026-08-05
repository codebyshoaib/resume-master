"""Unit tests for improver._prepare_keywords_for_prompt — pure formatting, no LLM."""

from app.services.improver import _prepare_keywords_for_prompt


class TestPrepareKeywordsForPrompt:
    def test_includes_required_and_preferred_skills(self):
        text = _prepare_keywords_for_prompt(
            {"required_skills": ["Python"], "preferred_skills": ["Kubernetes"]}
        )
        assert "Python" in text
        assert "Kubernetes" in text

    def test_includes_key_responsibilities(self):
        """Regression: the JD Match tab grades against key_responsibilities
        (services/jd_match.py) but the tailoring prompt used to never see them,
        so bullets were optimized for skill keywords only, not the actual role."""
        text = _prepare_keywords_for_prompt(
            {"key_responsibilities": ["Lead technical architecture decisions"]}
        )
        assert "Lead technical architecture decisions" in text

    def test_includes_experience_requirements(self):
        text = _prepare_keywords_for_prompt(
            {"experience_requirements": ["5+ years backend development"]}
        )
        assert "5+ years backend development" in text

    def test_empty_keywords_returns_placeholder(self):
        assert _prepare_keywords_for_prompt({}) == "No specific keywords extracted."
