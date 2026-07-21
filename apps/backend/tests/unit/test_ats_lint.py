"""Unit tests for the pure ATS parseability linter (app.services.ats_lint).

Each check has one resume that trips it and one that does not, so a regression
in any single rule fails a specific test rather than silently passing.
"""

import copy

from app.services.ats_lint import lint_resume


def _codes(resume: dict) -> set[str]:
    return {finding["code"] for finding in lint_resume(resume)}


# A minimal, fully ATS-clean resume: contact complete, all core sections
# present, month-precise ranges, healthy summary, plain-ASCII bullets.
CLEAN_RESUME: dict = {
    "personalInfo": {"email": "jane@example.com", "phone": "+1-555-0100"},
    "summary": (
        "Backend engineer with six years building scalable Python services "
        "and leading small teams to ship reliable APIs."
    ),
    "workExperience": [
        {
            "id": 1,
            "title": "Engineer",
            "years": "Jan 2021 - Present",
            "description": ["Built REST APIs serving 50K requests per day."],
        }
    ],
    "education": [{"id": 1, "degree": "BS", "years": "Sep 2014 - Jun 2018"}],
    "personalProjects": [],
    "additional": {"technicalSkills": ["Python", "FastAPI"]},
    "customSections": {},
    "sectionMeta": [],
}


def test_clean_resume_has_no_findings():
    assert lint_resume(copy.deepcopy(CLEAN_RESUME)) == []


class TestContact:
    def test_missing_email_and_phone_trip(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["personalInfo"] = {"email": "  ", "phone": ""}
        codes = _codes(resume)
        assert "contact.missing_email" in codes
        assert "contact.missing_phone" in codes

    def test_present_contact_does_not_trip(self):
        codes = _codes(copy.deepcopy(CLEAN_RESUME))
        assert "contact.missing_email" not in codes
        assert "contact.missing_phone" not in codes


class TestCoreSections:
    def test_missing_sections_trip(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["workExperience"] = []
        resume["education"] = []
        resume["additional"] = {"technicalSkills": []}
        codes = _codes(resume)
        assert "section.missing_work_experience" in codes
        assert "section.missing_skills" in codes
        assert "section.missing_education" in codes

    def test_present_sections_do_not_trip(self):
        codes = _codes(copy.deepcopy(CLEAN_RESUME))
        assert "section.missing_work_experience" not in codes
        assert "section.missing_skills" not in codes
        assert "section.missing_education" not in codes


class TestDates:
    def test_year_only_range_trips_when_months_present_elsewhere(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        # Work uses months; education range is year-only -> inconsistent.
        resume["education"] = [{"id": 1, "degree": "BS", "years": "2014 - 2018"}]
        codes = _codes(resume)
        assert "dates.missing_month" in codes

    def test_all_year_only_is_consistent_no_trip(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["workExperience"][0]["years"] = "2021 - 2023"
        resume["education"] = [{"id": 1, "degree": "BS", "years": "2014 - 2018"}]
        assert "dates.missing_month" not in _codes(resume)

    def test_single_graduation_year_is_not_flagged_as_range(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        # Months present in work; a single year (not a range) must not trip.
        resume["education"] = [{"id": 1, "degree": "BS", "years": "2018"}]
        assert "dates.missing_month" not in _codes(resume)


class TestCustomSections:
    def test_non_descriptive_title_trips(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["customSections"] = {
            "custom_1": {"sectionType": "stringList", "strings": ["Chess club"]}
        }
        resume["sectionMeta"] = [
            {"key": "custom_1", "displayName": "Untitled", "sectionType": "stringList"}
        ]
        assert "custom_section.non_descriptive_title" in _codes(resume)

    def test_descriptive_title_does_not_trip(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["customSections"] = {
            "custom_1": {"sectionType": "stringList", "strings": ["Spanish"]}
        }
        resume["sectionMeta"] = [
            {
                "key": "custom_1",
                "displayName": "Publications",
                "sectionType": "stringList",
            }
        ]
        assert "custom_section.non_descriptive_title" not in _codes(resume)


class TestSummary:
    def test_absent_summary_trips_info(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["summary"] = "   "
        assert "summary.missing" in _codes(resume)

    def test_short_summary_trips_info(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["summary"] = "Engineer."
        assert "summary.too_short" in _codes(resume)

    def test_overlong_summary_trips_warn(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["summary"] = "word " * 200  # 1000 chars
        assert "summary.too_long" in _codes(resume)

    def test_healthy_summary_does_not_trip(self):
        codes = _codes(copy.deepcopy(CLEAN_RESUME))
        assert not any(c.startswith("summary.") for c in codes)


class TestBullets:
    def test_em_dash_bullet_trips(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["workExperience"][0]["description"] = [
            "Led migration — improving throughput by 40%."
        ]
        assert "bullet.non_ascii_punctuation" in _codes(resume)

    def test_ascii_bullet_does_not_trip(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["workExperience"][0]["description"] = [
            "Led migration - improving throughput by 40%."
        ]
        assert "bullet.non_ascii_punctuation" not in _codes(resume)

    def test_accented_letters_are_not_flagged(self):
        # Legitimate accents (café, résumé) must not be mistaken for mojibake.
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["workExperience"][0]["description"] = [
            "Built the café ordering résumé parser with naive heuristics."
        ]
        assert "bullet.non_ascii_punctuation" not in _codes(resume)

    def test_overlong_bullet_trips_info(self):
        resume = copy.deepcopy(CLEAN_RESUME)
        resume["workExperience"][0]["description"] = ["x" * 250]
        assert "bullet.too_long" in _codes(resume)

    def test_normal_length_bullet_does_not_trip(self):
        codes = _codes(copy.deepcopy(CLEAN_RESUME))
        assert "bullet.too_long" not in codes
