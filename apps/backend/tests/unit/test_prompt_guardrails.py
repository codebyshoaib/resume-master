"""Content guards on the tailoring prompts.

Two invariants this locks:
1. JD-keyword incorporation in the diff/full-strategy tailoring pass
   (`DIFF_IMPROVE_PROMPT`) is the DEFAULT across sections (the maintainer goal).
   The separate, unverified `KEYWORD_INJECTION_PROMPT` refinement pass is
   deliberately NOT this aggressive: it has no path allow-list or per-field
   verification like the diff pass does, so it must stay scoped to keywords
   the master resume already evidences — an earlier version told it to stuff
   every JD keyword into every section by default (including the extractor's
   loose "keywords" field, which jd_match.py itself documents as ATS padding),
   which produced generic buzzword-stuffed resumes instead of real tailoring.
2. The remaining floor stays present. The default tailoring strategy ("full") is
   deliberately JD-first: it claims the job description's skills, appends
   JD-relevant bullets, and states concrete figures, all surfaced in the preview
   for the candidate to confirm. What must NEVER be invented is the set of facts
   a background check resolves — employers, job titles, dates, degrees,
   certifications — because a mismatch there costs the offer no matter how the
   interview goes. Those clauses are the only remaining guard; if a future edit
   drops them, this test fails loudly.
"""

from app.prompts.templates import (
    COVER_LETTER_PROMPT,
    CRITICAL_TRUTHFULNESS_RULES,
    DIFF_IMPROVE_PROMPT,
    DIFF_STRATEGY_INSTRUCTIONS,
    INTERVIEW_PREP_PROMPT,
)
from app.prompts.refinement import KEYWORD_INJECTION_PROMPT


class TestJdIncorporationIsDefault:
    def test_diff_prompt_reframes_by_default(self):
        assert "By DEFAULT" in DIFF_IMPROVE_PROMPT
        assert "reframe" in DIFF_IMPROVE_PROMPT.lower()

    def test_keyword_injection_stays_evidence_gated(self):
        """Regression: this pass must not force keywords into every section —
        that produced buzzword-stuffed resumes (see module docstring)."""
        assert "already has matching evidence in the candidate's master resume" in KEYWORD_INJECTION_PROMPT
        assert "unchanged rather than forcing a mention" in KEYWORD_INJECTION_PROMPT
        assert "EVERY section" not in KEYWORD_INJECTION_PROMPT
        assert "the DEFAULT across all content sections" not in KEYWORD_INJECTION_PROMPT

    def test_cover_letter_reframes_in_jd_terminology(self):
        assert "terminology" in COVER_LETTER_PROMPT.lower()

    def test_full_strategy_claims_jd_skills_and_quantifies(self):
        rules = CRITICAL_TRUTHFULNESS_RULES["full"]
        assert "Claim the skills, tools, frameworks" in rules
        assert "Quantify" in rules
        # The old evidence ceiling must be gone from the default path.
        assert "not explicitly mentioned in the original resume" not in rules

    def test_conservative_strategies_keep_the_evidence_ceiling(self):
        """nudge/keywords are the opt-in light touch; they stay evidence-bound."""
        for strategy in ("nudge", "keywords"):
            rules = CRITICAL_TRUTHFULNESS_RULES[strategy]
            assert "not explicitly mentioned in the original resume" in rules
            assert "DO NOT invent numeric achievements" in rules


class TestRecordCheckableFloorPresent:
    def test_every_strategy_carries_the_hard_floor(self):
        for strategy, rules in CRITICAL_TRUTHFULNESS_RULES.items():
            assert "company / employer names" in rules, strategy
            assert "job titles held at those employers" in rules, strategy
            assert "employment and education date ranges" in rules, strategy
            assert "degrees, institutions, certifications" in rules, strategy

    def test_diff_prompt_keeps_identity_fields_immutable(self):
        assert (
            "never change names, companies, job titles, dates, institutions, "
            "degrees, or certifications" in DIFF_IMPROVE_PROMPT
        )
        # the aggressive "full" strategy must still forbid inventing identity facts
        assert (
            "Never invent employers, job titles, dates, degrees, or certifications"
            in DIFF_STRATEGY_INSTRUCTIONS["full"]
        )

    def test_keyword_injection_keeps_the_floor(self):
        assert (
            "Never invent employers, job titles, dates, degrees, or certifications"
            in KEYWORD_INJECTION_PROMPT
        )

    def test_cover_letter_keeps_the_floor(self):
        assert (
            "Do NOT invent employers, job titles, dates, degrees, or certifications"
            in COVER_LETTER_PROMPT
        )

    def test_interview_prep_keeps_no_fabrication_guardrails(self):
        # Interview prep generates the candidate's own study notes, not the
        # submitted resume, so it stays fully evidence-bound on purpose.
        assert "Do NOT invent experience" in INTERVIEW_PREP_PROMPT
        assert "tools, employers, metrics, certifications, skills" in INTERVIEW_PREP_PROMPT
        assert "Skill gaps are preparation targets only" in INTERVIEW_PREP_PROMPT
        assert "Do NOT translate JSON property names" in INTERVIEW_PREP_PROMPT
        assert "role_fit_analysis" in INTERVIEW_PREP_PROMPT
        assert "talking_points" in INTERVIEW_PREP_PROMPT
