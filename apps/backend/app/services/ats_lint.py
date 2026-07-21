"""ATS parseability linter.

A high keyword score does not mean a resume survives an ATS parse. Real
auto-rejections come from *content/structure* problems: a missing contact
field, dates the parser cannot align, absent core sections, punctuation the
parser mangles, or bullets so long they get truncated.

This module is a **pure, deterministic** linter over the parsed ``ResumeData``
JSON (``processed_data``). No LLM, no I/O — same input always yields the same
findings, so it is trivially testable. The rendered PDF is already
single-column / no-tables, so we treat the *output* as ATS-safe and only lint
the parsed *content*.

Each finding is a :class:`LintFinding` dict::

    {code, severity, message, fix, path}

``path`` uses the same dot+bracket convention as ``ResumeChange`` elsewhere in
the codebase (e.g. ``workExperience[0].description[1]``), or ``None`` for
resume-wide findings.
"""

import re
from typing import Any, Literal, TypedDict

Severity = Literal["error", "warn", "info"]


class LintFinding(TypedDict):
    """A single ATS parseability issue."""

    code: str
    severity: Severity
    message: str
    fix: str
    path: str | None


# Month tokens, mirroring the parser's date convention
# (app/services/parser.py::_MD_DATE_RE). Kept local so this module stays pure
# and free of the LLM-heavy improver/parser import graph.
_MONTH_PATTERN = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b",
    re.IGNORECASE,
)

# A years string is a *range* (rather than a single graduation year) when it
# contains a separator, an open-ended marker, or two distinct 4-digit years.
_RANGE_SEPARATOR = re.compile(r"[-–—]|\bto\b", re.IGNORECASE)
_OPEN_ENDED = re.compile(r"\b(?:present|current|now|ongoing)\b", re.IGNORECASE)
_YEAR = re.compile(r"\b\d{4}\b")

# Punctuation characters an ATS parser (or a plain-text extraction) commonly
# mangles into mojibake or drops. Deliberately a *curated* set — not "all
# non-ASCII" — so legitimate accented letters (café, naïve, résumé) in a bullet
# are never flagged. Em dash is called out explicitly by the spec.
_PROBLEM_PUNCT = set("—–‒―‑“”„‘’‚…•●▪◦·»«›‹")

# Custom-section titles that carry no meaning for an ATS (or a human reader).
_NON_DESCRIPTIVE_TITLES = {
    "",
    "section",
    "sections",
    "untitled",
    "untitled section",
    "custom",
    "custom section",
    "customsection",
    "new section",
    "misc",
    "other",
}

_SUMMARY_MIN_CHARS = 40
_SUMMARY_MAX_CHARS = 600
_BULLET_MAX_CHARS = 240


def _has_month(value: str) -> bool:
    return bool(_MONTH_PATTERN.search(value))


def _is_date_range(value: str) -> bool:
    """True when a ``years`` string represents a span, not a single date."""
    if _RANGE_SEPARATOR.search(value) or _OPEN_ENDED.search(value):
        return True
    return len(set(_YEAR.findall(value))) >= 2


def _iter_dated_entries(resume: dict[str, Any]) -> list[tuple[str, str]]:
    """Yield ``(path, years)`` for every entry that carries a ``years`` field."""
    results: list[tuple[str, str]] = []
    for section_key in ("workExperience", "education", "personalProjects"):
        entries = resume.get(section_key)
        if not isinstance(entries, list):
            continue
        for idx, entry in enumerate(entries):
            if isinstance(entry, dict):
                years = entry.get("years")
                if isinstance(years, str) and years.strip():
                    results.append((f"{section_key}[{idx}].years", years))

    custom = resume.get("customSections")
    if isinstance(custom, dict):
        for key, section in custom.items():
            if not isinstance(section, dict):
                continue
            if section.get("sectionType") != "itemList":
                continue
            items = section.get("items")
            if not isinstance(items, list):
                continue
            for idx, item in enumerate(items):
                if isinstance(item, dict):
                    years = item.get("years")
                    if isinstance(years, str) and years.strip():
                        results.append(
                            (f"customSections.{key}.items[{idx}].years", years)
                        )
    return results


def _iter_bullets(resume: dict[str, Any]) -> list[tuple[str, str]]:
    """Yield ``(path, text)`` for every bullet-like string in the resume.

    Covers work/project/custom-item description lists, the single-string
    education description, and custom string-list sections.
    """
    results: list[tuple[str, str]] = []

    def _add_list(path_prefix: str, values: Any) -> None:
        if not isinstance(values, list):
            return
        for idx, value in enumerate(values):
            if isinstance(value, str) and value.strip():
                results.append((f"{path_prefix}[{idx}]", value))

    for section_key in ("workExperience", "personalProjects"):
        entries = resume.get(section_key)
        if not isinstance(entries, list):
            continue
        for idx, entry in enumerate(entries):
            if isinstance(entry, dict):
                _add_list(f"{section_key}[{idx}].description", entry.get("description"))

    education = resume.get("education")
    if isinstance(education, list):
        for idx, entry in enumerate(education):
            if isinstance(entry, dict):
                desc = entry.get("description")
                if isinstance(desc, str) and desc.strip():
                    results.append((f"education[{idx}].description", desc))

    custom = resume.get("customSections")
    if isinstance(custom, dict):
        for key, section in custom.items():
            if not isinstance(section, dict):
                continue
            _add_list(f"customSections.{key}.strings", section.get("strings"))
            items = section.get("items")
            if isinstance(items, list):
                for idx, item in enumerate(items):
                    if isinstance(item, dict):
                        _add_list(
                            f"customSections.{key}.items[{idx}].description",
                            item.get("description"),
                        )
    return results


def _custom_section_title(
    key: str,
    section_meta_by_key: dict[str, str],
) -> str:
    """Resolve a custom section's user-visible title (displayName or its key)."""
    display = section_meta_by_key.get(key, "")
    return display if display.strip() else key


def _check_contact(resume: dict[str, Any]) -> list[LintFinding]:
    findings: list[LintFinding] = []
    info = resume.get("personalInfo")
    info = info if isinstance(info, dict) else {}

    email = info.get("email")
    if not (isinstance(email, str) and email.strip()):
        findings.append(
            LintFinding(
                code="contact.missing_email",
                severity="error",
                message="No contact email found.",
                fix="Add an email address to your personal information — most ATS require it to route your application.",
                path="personalInfo.email",
            )
        )

    phone = info.get("phone")
    if not (isinstance(phone, str) and phone.strip()):
        findings.append(
            LintFinding(
                code="contact.missing_phone",
                severity="error",
                message="No contact phone number found.",
                fix="Add a phone number to your personal information so recruiters and ATS can reach you.",
                path="personalInfo.phone",
            )
        )
    return findings


def _check_core_sections(resume: dict[str, Any]) -> list[LintFinding]:
    findings: list[LintFinding] = []

    work = resume.get("workExperience")
    if not (isinstance(work, list) and work):
        findings.append(
            LintFinding(
                code="section.missing_work_experience",
                severity="warn",
                message="No work experience section found.",
                fix="Add at least one work experience entry — ATS rank resumes heavily on relevant experience.",
                path="workExperience",
            )
        )

    additional = resume.get("additional")
    skills = additional.get("technicalSkills") if isinstance(additional, dict) else None
    if not (isinstance(skills, list) and skills):
        findings.append(
            LintFinding(
                code="section.missing_skills",
                severity="warn",
                message="No skills section found.",
                fix="Add a skills section listing your core tools and technologies so ATS keyword matching can find them.",
                path="additional.technicalSkills",
            )
        )

    education = resume.get("education")
    if not (isinstance(education, list) and education):
        findings.append(
            LintFinding(
                code="section.missing_education",
                severity="warn",
                message="No education section found.",
                fix="Add an education entry — many ATS filters expect a degree or qualification field.",
                path="education",
            )
        )
    return findings


def _check_dates(resume: dict[str, Any]) -> list[LintFinding]:
    dated = _iter_dated_entries(resume)
    if not any(_has_month(years) for _, years in dated):
        # Months appear nowhere; a year-only resume is internally consistent
        # and parsers align it fine. Nothing to flag.
        return []

    findings: list[LintFinding] = []
    for path, years in dated:
        if _is_date_range(years) and not _has_month(years):
            findings.append(
                LintFinding(
                    code="dates.missing_month",
                    severity="warn",
                    message=f"Date range '{years}' is missing months while other dates include them.",
                    fix="Use a consistent month + year format (e.g. 'Jun 2020 - Aug 2021') so the ATS can order your history correctly.",
                    path=path,
                )
            )
    return findings


def _check_custom_sections(resume: dict[str, Any]) -> list[LintFinding]:
    custom = resume.get("customSections")
    if not isinstance(custom, dict) or not custom:
        return []

    section_meta = resume.get("sectionMeta")
    section_meta_by_key: dict[str, str] = {}
    if isinstance(section_meta, list):
        for meta in section_meta:
            if isinstance(meta, dict):
                key = meta.get("key")
                display = meta.get("displayName")
                if isinstance(key, str) and isinstance(display, str):
                    section_meta_by_key[key] = display

    findings: list[LintFinding] = []
    for key in custom:
        if not isinstance(key, str):
            continue
        title = _custom_section_title(key, section_meta_by_key)
        if title.strip().lower() in _NON_DESCRIPTIVE_TITLES:
            findings.append(
                LintFinding(
                    code="custom_section.non_descriptive_title",
                    severity="warn",
                    message=f"Custom section '{title or key}' has an empty or non-descriptive title.",
                    fix="Give the section a clear, conventional heading (e.g. 'Certifications', 'Publications') the ATS can categorize.",
                    path=f"customSections.{key}",
                )
            )
    return findings


def _check_summary(resume: dict[str, Any]) -> list[LintFinding]:
    summary = resume.get("summary")
    text = summary.strip() if isinstance(summary, str) else ""

    if not text:
        return [
            LintFinding(
                code="summary.missing",
                severity="info",
                message="No professional summary found.",
                fix="Consider adding a 2-3 sentence summary — it gives the ATS and recruiter an immediate role match.",
                path="summary",
            )
        ]

    length = len(text)
    if length < _SUMMARY_MIN_CHARS:
        return [
            LintFinding(
                code="summary.too_short",
                severity="info",
                message=f"Summary is very short ({length} characters).",
                fix="Expand the summary to 2-3 sentences so it conveys your value and relevant keywords.",
                path="summary",
            )
        ]
    if length > _SUMMARY_MAX_CHARS:
        return [
            LintFinding(
                code="summary.too_long",
                severity="warn",
                message=f"Summary is very long ({length} characters).",
                fix="Trim the summary to a tight 2-4 sentences; long blocks bury keywords and get skimmed past.",
                path="summary",
            )
        ]
    return []


def _check_bullets(resume: dict[str, Any]) -> list[LintFinding]:
    findings: list[LintFinding] = []
    for path, text in _iter_bullets(resume):
        offending = sorted({ch for ch in text if ch in _PROBLEM_PUNCT})
        if offending:
            findings.append(
                LintFinding(
                    code="bullet.non_ascii_punctuation",
                    severity="warn",
                    message=(
                        "Bullet contains punctuation an ATS may mangle: "
                        f"{' '.join(offending)}."
                    ),
                    fix="Replace em/en dashes, smart quotes, and special bullets with plain ASCII ('-', straight quotes).",
                    path=path,
                )
            )
        if len(text) > _BULLET_MAX_CHARS:
            findings.append(
                LintFinding(
                    code="bullet.too_long",
                    severity="info",
                    message=f"Bullet is very long ({len(text)} characters).",
                    fix="Split long bullets into two, or tighten to a single achievement — concise bullets parse and read better.",
                    path=path,
                )
            )
    return findings


def lint_resume(resume: dict[str, Any]) -> list[LintFinding]:
    """Lint a parsed resume for ATS parseability problems.

    Args:
        resume: A parsed ``ResumeData`` JSON dict (the stored ``processed_data``).

    Returns:
        A deterministic list of findings. Order is stable: contact → core
        sections → dates → custom sections → summary → bullets.
    """
    findings: list[LintFinding] = []
    findings.extend(_check_contact(resume))
    findings.extend(_check_core_sections(resume))
    findings.extend(_check_dates(resume))
    findings.extend(_check_custom_sections(resume))
    findings.extend(_check_summary(resume))
    findings.extend(_check_bullets(resume))
    return findings
