"""Semantic JD match analysis and gap closing.

The old JD Match number was exact-token overlap against every non-stopword in
the posting, computed in the browser. Two independent problems: the denominator
was noise ("onsite", "benefits", "platform"), and the comparison was string
equality, so `K8s` never matched `Kubernetes`.

This module scores the *requirements* the keyword extractor already pulls off
the posting (cached on the job), grading each one semantically with one LLM
call. The percentage is computed here from those statuses — never asked of the
model — so the number is a deterministic function of judgments that each carry a
quotable piece of evidence.

``close_match_gaps`` then reuses ``improver.apply_diffs``, so gap-closing changes
pass exactly the same path allow/block gates as the tailoring pipeline: it can
append bullets to existing entries and add skills, and it cannot touch
employers, titles, dates, degrees, or personal info.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any, Literal

from app.llm import complete_json
from app.prompts.jd_match import CLOSE_GAPS_PROMPT, JD_MATCH_PROMPT
from app.prompts.templates import get_language_name
from app.schemas.models import ImproveDiffResult, ResumeChange
from app.services.improver import apply_diffs
from app.services.text_normalize import plain_ascii_deep

logger = logging.getLogger(__name__)

CoverageStatus = Literal["covered", "partial", "missing"]

# A required skill counts double: missing one is what actually loses the screen,
# and a resume that hits every "nice to have" while missing the core stack
# should not read as a strong match.
_WEIGHTS: dict[str, float] = {
    "required": 2.0,
    "preferred": 1.0,
    "responsibility": 1.0,
    "experience": 1.0,
    "education": 1.0,
}
_STATUS_CREDIT: dict[str, float] = {"covered": 1.0, "partial": 0.5, "missing": 0.0}

# Requirement kinds pulled from the extractor, in the order they are judged.
# Ordering is stable so the cache key and the UI list agree run to run.
_REQUIREMENT_SOURCES: list[tuple[str, str]] = [
    ("required_skills", "required"),
    ("preferred_skills", "preferred"),
    ("key_responsibilities", "responsibility"),
    ("experience_requirements", "experience"),
    ("education_requirements", "education"),
]

# Cap what one analysis judges. A posting that yields 60 "requirements" is mostly
# extractor noise, and the tail is always the boilerplate. Truncation is reported
# to the caller rather than hidden.
MAX_REQUIREMENTS = 30


def build_requirements(job_keywords: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten extracted job keywords into an ordered, deduped requirement list.

    Deliberately skips the extractor's loose ``keywords`` field: those are ATS
    padding terms ("agile", "microservices"), not requirements to grade, and
    they are what made the old denominator meaningless. They still drive the
    highlight colouring in the UI.
    """
    requirements: list[dict[str, str]] = []
    seen: set[str] = set()

    for field, kind in _REQUIREMENT_SOURCES:
        values = job_keywords.get(field, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, str):
                continue
            text = " ".join(value.split()).strip()
            key = text.casefold()
            if not text or key in seen:
                continue
            seen.add(key)
            requirements.append({"requirement": text, "kind": kind})

    return requirements[:MAX_REQUIREMENTS]


def match_cache_key(resume_data: dict[str, Any], job_description: str) -> str:
    """Stable key for one (resume content, JD) pair.

    Keyed on the resume *data* rather than its id so editing a resume
    invalidates its analysis, and re-opening the tab after no edits does not
    spend a call.
    """
    payload = json.dumps(
        {"resume": resume_data, "jd": job_description},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def score_coverage(coverage: list[dict[str, Any]]) -> float:
    """Weighted match percentage from per-requirement statuses.

    Computed locally, never asked of the model. Required requirements carry
    double weight; a "partial" earns half credit.
    """
    total_weight = 0.0
    earned = 0.0
    for item in coverage:
        weight = _WEIGHTS.get(str(item.get("kind", "")), 1.0)
        credit = _STATUS_CREDIT.get(str(item.get("status", "")), 0.0)
        total_weight += weight
        earned += weight * credit
    if total_weight <= 0:
        return 0.0
    return round(earned / total_weight * 100, 1)


def _normalize_status(raw: Any) -> CoverageStatus:
    """Coerce a model-supplied status, defaulting unknown values to 'missing'.

    Failing closed matters: an unparseable status must not inflate the score,
    and 'missing' is the status that shows up as actionable in the UI.
    """
    value = str(raw).strip().casefold()
    if value in ("covered", "partial", "missing"):
        return value  # type: ignore[return-value]
    return "missing"


def _align_judgments(
    requirements: list[dict[str, str]],
    judged: Any,
) -> list[dict[str, Any]]:
    """Match model judgments back onto the requirement list we asked about.

    The model is told to return every requirement in order, but it drops and
    reorders in practice. Matching on the requirement text (falling back to
    positional order) keeps the score anchored to *our* list: an omitted
    requirement scores as missing rather than silently shrinking the
    denominator.
    """
    positional: list[dict[str, Any]] = [
        entry for entry in (judged if isinstance(judged, list) else []) if isinstance(entry, dict)
    ]

    # Two passes over the same pool, each judgment consumable once: exact text
    # matches claim their requirement first, then anything still unmatched falls
    # back to its slot (the model reworded a requirement but kept the order).
    # Without the consumed-set, one judgment could be counted for two
    # requirements.
    consumed: set[int] = set()
    matched: dict[int, dict[str, Any]] = {}
    for index, requirement in enumerate(requirements):
        key = requirement["requirement"].casefold()
        for slot, entry in enumerate(positional):
            if slot in consumed:
                continue
            if str(entry.get("requirement", "")).strip().casefold() == key:
                matched[index] = entry
                consumed.add(slot)
                break
    for index in range(len(requirements)):
        if index in matched or index >= len(positional) or index in consumed:
            continue
        matched[index] = positional[index]
        consumed.add(index)

    coverage: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements):
        text = requirement["requirement"]
        entry = matched.get(index) or {}
        status = _normalize_status(entry.get("status"))
        evidence = str(entry.get("evidence", "") or "").strip()
        # A "covered" claim with no quote is the model asserting rather than
        # showing. Demote it: the whole point of the evidence field is that the
        # score cannot be inflated by assertion.
        if status == "covered" and not evidence:
            status = "partial"
        coverage.append(
            {
                "requirement": text,
                "kind": requirement["kind"],
                "status": status,
                "evidence": evidence,
                "gap_note": str(entry.get("gap_note", "") or "").strip(),
            }
        )
    return coverage


async def analyze_jd_match(
    resume_data: dict[str, Any],
    job_description: str,
    job_keywords: dict[str, Any],
    language: str = "en",
) -> dict[str, Any]:
    """Grade every extracted job requirement against the resume (one LLM call).

    Returns a dict shaped for ``JdMatchResponse``. Raises when there is nothing
    to grade — the caller turns that into a 422 rather than reporting a
    meaningless 0%.
    """
    requirements = build_requirements(job_keywords)
    if not requirements:
        raise ValueError("No gradable requirements were extracted from this job description")

    prompt = JD_MATCH_PROMPT.format(
        output_language=get_language_name(language),
        requirements=json.dumps(
            [
                {"requirement": item["requirement"], "kind": item["kind"]}
                for item in requirements
            ],
            ensure_ascii=False,
            indent=2,
        ),
        resume_data=json.dumps(resume_data, ensure_ascii=False),
        job_description=job_description,
    )

    result = await complete_json(
        prompt=prompt,
        system_prompt=(
            "You are a technical recruiter screening a resume against a job's "
            "requirements. Judge meaning, not wording. Return only valid JSON."
        ),
    )

    coverage = _align_judgments(requirements, (result or {}).get("requirements"))
    return {
        "score": score_coverage(coverage),
        "coverage": coverage,
        "highlight_keywords": _highlight_keywords(job_keywords),
        "truncated": len(requirements) < _requirement_total(job_keywords),
    }


def _requirement_total(job_keywords: dict[str, Any]) -> int:
    """Requirement count before the MAX_REQUIREMENTS cap, for truncation reporting."""
    seen: set[str] = set()
    for field, _kind in _REQUIREMENT_SOURCES:
        values = job_keywords.get(field, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str):
                text = " ".join(value.split()).strip().casefold()
                if text:
                    seen.add(text)
    return len(seen)


def _highlight_keywords(job_keywords: dict[str, Any]) -> list[str]:
    """Terms the UI highlights inside the resume.

    Wider than the graded requirements on purpose — the loose ``keywords`` field
    is useful as a reading aid even though it is too noisy to score against.
    """
    terms: list[str] = []
    seen: set[str] = set()
    for field in ("required_skills", "preferred_skills", "keywords"):
        values = job_keywords.get(field, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, str):
                continue
            text = " ".join(value.split()).strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                terms.append(text)
    return terms


def open_gaps(coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Requirements worth closing: missing first, then partial."""
    missing = [item for item in coverage if item.get("status") == "missing"]
    partial = [item for item in coverage if item.get("status") == "partial"]
    return missing + partial


def _entry_index(resume_data: dict[str, Any]) -> str:
    """Human-readable index of appendable entries, so the model picks a real one."""
    lines: list[str] = []
    for key, label in (("workExperience", "workExperience"), ("personalProjects", "personalProjects")):
        entries = resume_data.get(key, [])
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            parts = [
                str(entry.get("title") or entry.get("name") or "").strip(),
                str(entry.get("company") or entry.get("role") or "").strip(),
            ]
            label_text = " - ".join(part for part in parts if part) or "(untitled)"
            lines.append(f"{label}[{index}].description  =>  {label_text}")
    return "\n".join(lines) if lines else "(no appendable entries)"


async def close_match_gaps(
    resume_data: dict[str, Any],
    job_description: str,
    gaps: list[dict[str, Any]],
    language: str = "en",
) -> tuple[dict[str, Any], list[ResumeChange], list[ResumeChange]]:
    """Propose changes that close the given gaps. Does not persist anything.

    Returns ``(proposed_resume_data, applied_changes, rejected_changes)``.
    Every change is routed through ``apply_diffs``, so the identity floor
    (employers, titles, dates, degrees, personal info) is enforced by the same
    gates the tailoring pipeline uses — a model that ignores its instructions
    gets its change rejected here rather than written to the resume.
    """
    if not gaps:
        return copy.deepcopy(resume_data), [], []

    existing_skills = resume_data.get("additional", {}).get("technicalSkills", [])
    prompt = CLOSE_GAPS_PROMPT.format(
        output_language=get_language_name(language),
        gaps=json.dumps(
            [
                {
                    "requirement": item.get("requirement", ""),
                    "status": item.get("status", ""),
                    "gap_note": item.get("gap_note", ""),
                }
                for item in gaps
            ],
            ensure_ascii=False,
            indent=2,
        ),
        existing_skills=json.dumps(existing_skills, ensure_ascii=False),
        entry_index=_entry_index(resume_data),
        resume_data=json.dumps(resume_data, ensure_ascii=False),
        job_description=job_description,
    )

    raw = await complete_json(
        prompt=prompt,
        system_prompt=(
            "You are a resume editor closing specific gaps against a job "
            "description. Return only valid JSON."
        ),
        schema_type="diff",
    )

    # Models slip non-breaking hyphens and curly quotes into bullets ("Self‑studied"),
    # and ats_lint flags exactly that as an ATS parseability problem. Normalise the
    # generated changes before they can reach the resume; the prompt's ASCII rule
    # alone is not enforceable.
    diff_result = ImproveDiffResult.model_validate(
        plain_ascii_deep(raw) if isinstance(raw, dict) else {"changes": []}
    )
    # add_skill is gated on an allow-list; the gap skills ARE the allow-list here,
    # otherwise every proposed skill would be rejected by apply_diffs.
    allowed = [
        {"skill": str(change.value)}
        for change in diff_result.changes
        if change.action == "add_skill" and isinstance(change.value, str)
    ]
    proposed, applied, rejected = apply_diffs(
        original=resume_data,
        changes=diff_result.changes,
        allowed_skill_targets=allowed,
    )
    if rejected:
        logger.info(
            "Gap closing: %d change(s) applied, %d rejected by the diff gates",
            len(applied),
            len(rejected),
        )
    return proposed, applied, rejected
