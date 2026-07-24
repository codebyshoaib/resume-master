"""Content guards on the tailoring prompts.

Two invariants this locks:
1. JD-keyword incorporation is the DEFAULT across sections (the maintainer goal).
2. The retained anti-fabrication clauses stay present. The default tailoring
   strategy ("full") now deliberately permits appending qualitative,
   JD-relevant bullets and skills (surfaced in the preview for the candidate to
   confirm). What must NEVER be invented — because it is the fabrication that
   burns a candidate in an interview and is not caught downstream — is
   *numeric* achievement (metrics, percentages, counts) and identity facts
   (employers, job titles, dates). Those clauses are the ONLY guard against
   fabricated numbers/narrative; if a future edit drops them, this test fails
   loudly.
"""

from app.prompts.templates import (
    COVER_LETTER_PROMPT,
    DIFF_IMPROVE_PROMPT,
    DIFF_STRATEGY_INSTRUCTIONS,
    INTERVIEW_PREP_PROMPT,
)
from app.prompts.refinement import KEYWORD_INJECTION_PROMPT


class TestJdIncorporationIsDefault:
    def test_diff_prompt_reframes_by_default(self):
        assert "By DEFAULT" in DIFF_IMPROVE_PROMPT
        assert "reframe" in DIFF_IMPROVE_PROMPT.lower()

    def test_keyword_injection_targets_every_section_by_default(self):
        assert "EVERY section" in KEYWORD_INJECTION_PROMPT
        assert "DEFAULT" in KEYWORD_INJECTION_PROMPT

    def test_cover_letter_reframes_in_jd_terminology(self):
        assert "terminology" in COVER_LETTER_PROMPT.lower()


class TestAntiFabricationClausesPresent:
    def test_diff_prompt_keeps_no_invented_work_clauses(self):
        # rule 2: no invented numbers (the guard that survives even under the
        # aggressive default gap-filling strategy)
        assert "Do not invent numeric metrics" in DIFF_IMPROVE_PROMPT
        # rule 11's reframe permission must still ship with its no-invented-metrics clause
        assert "do NOT invent numeric metrics" in DIFF_IMPROVE_PROMPT
        # the aggressive "full" strategy must forbid inventing identity facts
        assert "Do NOT invent numeric metrics, employers, job titles, dates" in DIFF_STRATEGY_INSTRUCTIONS["full"]

    def test_keyword_injection_keeps_no_invent_clauses(self):
        assert "do not invent new content, metrics, or work history" in KEYWORD_INJECTION_PROMPT
        assert "Do NOT add skills, technologies, or certifications not in the master resume" in KEYWORD_INJECTION_PROMPT

    def test_cover_letter_keeps_no_invent_clauses(self):
        assert "Do NOT invent information not in the resume" in COVER_LETTER_PROMPT
        assert "proven experience supports it" in COVER_LETTER_PROMPT

    def test_interview_prep_keeps_no_fabrication_guardrails(self):
        assert "Do NOT invent experience" in INTERVIEW_PREP_PROMPT
        assert "tools, employers, metrics, certifications, skills" in INTERVIEW_PREP_PROMPT
        assert "Skill gaps are preparation targets only" in INTERVIEW_PREP_PROMPT
        assert "Do NOT translate JSON property names" in INTERVIEW_PREP_PROMPT
        assert "role_fit_analysis" in INTERVIEW_PREP_PROMPT
        assert "talking_points" in INTERVIEW_PREP_PROMPT
