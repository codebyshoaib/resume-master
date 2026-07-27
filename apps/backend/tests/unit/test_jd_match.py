"""Pure-logic tests for semantic JD match scoring.

The score must be a deterministic function of per-requirement statuses — the
model is never asked for a percentage. These tests lock the scoring, the
requirement list construction, and the two ways a model can try to inflate the
number (omitting requirements, claiming coverage without evidence).
"""

import pytest

from app.services.jd_match import (
    MAX_REQUIREMENTS,
    _align_judgments,
    _highlight_keywords,
    build_requirements,
    match_cache_key,
    open_gaps,
    score_coverage,
)


@pytest.fixture
def job_keywords():
    return {
        "required_skills": ["Python", "Kubernetes"],
        "preferred_skills": ["Terraform"],
        "key_responsibilities": ["Lead migrations"],
        "experience_requirements": ["5+ years backend"],
        "education_requirements": ["Bachelor's in CS"],
        "keywords": ["microservices", "agile"],
    }


class TestBuildRequirements:
    def test_orders_by_kind_and_tags_each(self, job_keywords):
        reqs = build_requirements(job_keywords)
        assert [r["kind"] for r in reqs] == [
            "required",
            "required",
            "preferred",
            "responsibility",
            "experience",
            "education",
        ]
        assert reqs[0] == {"requirement": "Python", "kind": "required"}

    def test_excludes_loose_keywords_field(self, job_keywords):
        """The noisy `keywords` field is what made the old denominator garbage."""
        texts = [r["requirement"] for r in build_requirements(job_keywords)]
        assert "microservices" not in texts
        assert "agile" not in texts

    def test_dedupes_case_insensitively_across_fields(self):
        reqs = build_requirements(
            {"required_skills": ["Python"], "preferred_skills": ["python", "Go"]}
        )
        assert [r["requirement"] for r in reqs] == ["Python", "Go"]

    def test_normalizes_whitespace(self):
        reqs = build_requirements({"required_skills": ["  REST   APIs "]})
        assert reqs[0]["requirement"] == "REST APIs"

    def test_caps_requirement_count(self):
        reqs = build_requirements(
            {"required_skills": [f"skill-{i}" for i in range(MAX_REQUIREMENTS + 10)]}
        )
        assert len(reqs) == MAX_REQUIREMENTS

    def test_ignores_non_list_and_non_string_values(self):
        reqs = build_requirements({"required_skills": "Python", "preferred_skills": [None, 3, "Go"]})
        assert [r["requirement"] for r in reqs] == ["Go"]


class TestScoreCoverage:
    def test_all_covered_is_100(self):
        coverage = [
            {"kind": "required", "status": "covered"},
            {"kind": "preferred", "status": "covered"},
        ]
        assert score_coverage(coverage) == 100.0

    def test_all_missing_is_zero(self):
        assert score_coverage([{"kind": "required", "status": "missing"}]) == 0.0

    def test_partial_earns_half_credit(self):
        assert score_coverage([{"kind": "preferred", "status": "partial"}]) == 50.0

    def test_required_counts_double(self):
        """Missing the core stack must cost more than missing a nice-to-have."""
        missing_required = score_coverage(
            [
                {"kind": "required", "status": "missing"},
                {"kind": "preferred", "status": "covered"},
            ]
        )
        missing_preferred = score_coverage(
            [
                {"kind": "required", "status": "covered"},
                {"kind": "preferred", "status": "missing"},
            ]
        )
        assert missing_required < missing_preferred
        assert (missing_required, missing_preferred) == (33.3, 66.7)

    def test_empty_coverage_is_zero_not_a_crash(self):
        assert score_coverage([]) == 0.0

    def test_unknown_status_scores_as_missing(self):
        assert score_coverage([{"kind": "required", "status": "banana"}]) == 0.0


class TestAlignJudgments:
    def test_matches_judgments_by_requirement_text(self):
        requirements = [
            {"requirement": "Python", "kind": "required"},
            {"requirement": "Kubernetes", "kind": "required"},
        ]
        judged = [
            {"requirement": "Kubernetes", "status": "covered", "evidence": "ran k8s"},
            {"requirement": "Python", "status": "partial", "evidence": "", "gap_note": "no depth"},
        ]
        coverage = _align_judgments(requirements, judged)
        assert [c["requirement"] for c in coverage] == ["Python", "Kubernetes"]
        assert coverage[0]["status"] == "partial"
        assert coverage[1]["status"] == "covered"
        assert coverage[1]["evidence"] == "ran k8s"

    def test_omitted_requirement_scores_missing_not_dropped(self):
        """A shrinking denominator would silently inflate the score."""
        requirements = [
            {"requirement": "Python", "kind": "required"},
            {"requirement": "Kubernetes", "kind": "required"},
        ]
        coverage = _align_judgments(
            requirements, [{"requirement": "Python", "status": "covered", "evidence": "built X"}]
        )
        assert len(coverage) == 2
        assert coverage[1] == {
            "requirement": "Kubernetes",
            "kind": "required",
            "status": "missing",
            "evidence": "",
            "gap_note": "",
        }
        assert score_coverage(coverage) == 50.0

    def test_covered_without_evidence_is_demoted_to_partial(self):
        """'Covered' with nothing quotable is assertion, not evidence."""
        coverage = _align_judgments(
            [{"requirement": "Python", "kind": "required"}],
            [{"requirement": "Python", "status": "covered", "evidence": "   "}],
        )
        assert coverage[0]["status"] == "partial"

    def test_falls_back_to_position_when_text_drifts(self):
        coverage = _align_judgments(
            [{"requirement": "REST APIs", "kind": "required"}],
            [{"requirement": "REST API", "status": "covered", "evidence": "built REST endpoints"}],
        )
        assert coverage[0]["status"] == "covered"
        assert coverage[0]["requirement"] == "REST APIs"

    def test_garbage_payload_yields_all_missing(self):
        coverage = _align_judgments([{"requirement": "Python", "kind": "required"}], None)
        assert coverage[0]["status"] == "missing"
        assert score_coverage(coverage) == 0.0


class TestOpenGaps:
    def test_missing_before_partial_and_covered_excluded(self):
        coverage = [
            {"requirement": "a", "status": "partial"},
            {"requirement": "b", "status": "covered"},
            {"requirement": "c", "status": "missing"},
        ]
        assert [g["requirement"] for g in open_gaps(coverage)] == ["c", "a"]


class TestCacheKey:
    def test_same_inputs_same_key(self):
        assert match_cache_key({"a": 1}, "jd") == match_cache_key({"a": 1}, "jd")

    def test_key_is_insensitive_to_dict_ordering(self):
        assert match_cache_key({"a": 1, "b": 2}, "jd") == match_cache_key({"b": 2, "a": 1}, "jd")

    def test_resume_edit_invalidates(self):
        assert match_cache_key({"a": 1}, "jd") != match_cache_key({"a": 2}, "jd")

    def test_jd_change_invalidates(self):
        assert match_cache_key({"a": 1}, "jd") != match_cache_key({"a": 1}, "other jd")


class TestHighlightKeywords:
    def test_includes_loose_keywords_unlike_graded_requirements(self, job_keywords):
        terms = _highlight_keywords(job_keywords)
        assert "microservices" in terms
        assert "Python" in terms
        # Responsibilities are graded but not highlighted — they are sentences.
        assert "Lead migrations" not in terms

    def test_dedupes_case_insensitively_keeping_first_spelling(self):
        terms = _highlight_keywords(
            {"required_skills": ["Python"], "keywords": ["python", "Go"]}
        )
        assert terms == ["Python", "Go"]
