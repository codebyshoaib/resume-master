# JD Match Feature

> **Shows how well a tailored resume matches the job description it was tailored for — graded by meaning, with a one-click path to close the gaps.**

## Overview

The Resume Builder's "JD MATCH" tab (tailored resumes only) answers two questions: *how well does this resume answer the posting*, and *what is still missing*. It has two layers:

| Layer | Where | Cost | What it is |
|-------|-------|------|------------|
| **Semantic score + requirement coverage** | Backend (`services/jd_match.py`) | 1 LLM call, then cached | Every requirement the extractor pulled off the posting, graded `covered` / `partial` / `missing` with a quoted piece of evidence |
| **Keyword highlighting** | Browser (`lib/utils/keyword-matcher.ts`) | free | Yellow highlights on the resume, as a reading aid |

## Why the score is not keyword overlap

The tab originally scored by exact token overlap against every non-stopword in the posting. That was wrong in both the numerator and the denominator:

- **Denominator noise** — `extractKeywords` counted `onsite`, `benefits`, `platform`, `collaborate` as requirements, so the percentage measured vocabulary sharing, not fit.
- **Numerator misses** — string equality meant `K8s` never matched `Kubernetes`, `RESTful services` never matched `REST APIs`, and `CI/CD` tokenized into junk.

Now the graded set is the extractor's `required_skills`, `preferred_skills`, `key_responsibilities`, `experience_requirements`, and `education_requirements` (already cached on the job by content hash, so grading usually needs no extra extraction call). The extractor's loose `keywords` field is deliberately **excluded from grading** — it is ATS padding — but still drives the highlight colouring.

## How the score is computed

**The model is never asked for a percentage.** It judges one requirement at a time; the number is derived locally in `score_coverage`:

- weights: `required` = 2.0, everything else = 1.0
- credit: `covered` = 1.0, `partial` = 0.5, `missing` = 0.0
- `score = sum(weight × credit) / sum(weight) × 100`

Required requirements count double because missing the core stack is what actually loses the screen.

Two anti-inflation rules live in `_align_judgments`:

1. **A dropped judgment scores as `missing`, never as a smaller denominator.** Judgments are matched back onto *our* requirement list by text (falling back to position), each consumable once.
2. **`covered` with no quotable evidence is demoted to `partial`.** The evidence field exists so coverage cannot be asserted into existence.

Postings that yield more than `MAX_REQUIREMENTS` (30) are truncated, and `truncated: true` says so in the response rather than hiding it.

## Caching

The analysis is stored in the job's dynamic metadata as `jd_match: {key, analysis}`, where `key = sha256(normalized resume data + JD)`. So:

- re-opening the tab is free
- **editing the resume invalidates it automatically** (the key is content-derived, not id-derived)
- only one entry is kept per job — older resume versions are never read back
- `GET ...?refresh=true` forces a re-grade

The frontend gates the fetch on the tab actually being open (`useJdMatch(resumeId, enabled)`), so opening the builder does not spend a call.

## Improve match (gap closing)

The **IMPROVE MATCH** button asks the backend for the changes that would close every `missing` / `partial` requirement. It is a *targeted* pass, not a re-tailor: for each gap the model emits exactly one change, of exactly two kinds —

- `add_skill` on `additional.technicalSkills` — for a tool/technology/platform gap
- `append` on `workExperience[i].description` / `personalProjects[i].description` — for a responsibility/practice/scope gap

**Nothing is persisted by the endpoint.** It returns the proposed resume plus the change list; the client reviews them in `GapFixDialog` and saves through the ordinary `PATCH /resumes/{id}`. A rejected suggestion costs nothing.

Two safety layers apply to generated changes:

1. **`apply_diffs` gates** (reused from the tailoring pipeline) — a change targeting `personalInfo`, a company, job title, date, degree, or certification is *rejected*, not written. `rejected_count` reports how many. This is why the prompt's rules are not the only defence.
2. **`plain_ascii_deep`** (`services/text_normalize.py`) — models emit non-breaking hyphens and curly quotes (`Self‑studied`), which `ats_lint` itself flags as an ATS parseability problem. Generated text is normalised before it can reach the resume.

After a successful save the client explicitly calls `reanalyze()` — the cache is keyed on resume content, so a stale score would otherwise linger until the tab remounted.

## Key Files

| File | Purpose |
|------|---------|
| `apps/backend/app/services/jd_match.py` | Requirement building, scoring, judgment alignment, gap closing |
| `apps/backend/app/prompts/jd_match.py` | `JD_MATCH_PROMPT` (grading), `CLOSE_GAPS_PROMPT` (gap closing) |
| `apps/backend/app/services/text_normalize.py` | Shared typography normalisation (also used by career answers) |
| `apps/backend/app/routers/resumes.py` | `_resolve_resume_and_job`, `_get_or_analyze_jd_match`, both endpoints |
| `apps/frontend/hooks/use-jd-match.ts` | Owns fetch / refresh / gap-fix request state |
| `apps/frontend/components/builder/jd-gap-panel.tsx` | Score + requirement coverage list + actions (left panel) |
| `apps/frontend/components/builder/gap-fix-dialog.tsx` | Review gate before anything is saved |
| `apps/frontend/components/builder/jd-comparison-view.tsx` | Split JD/resume view; headline score + keyword hit rate |
| `apps/frontend/lib/utils/keyword-matcher.ts` | Browser-side highlighting (reading aid only) |

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /resumes/{resume_id}/job-description` | Fetch the JD used to tailor a resume |
| `GET /resumes/{resume_id}/jd-match?refresh=false` | Semantic match: `score`, `coverage[]`, `highlight_keywords[]`, `cached`, `truncated` |
| `POST /resumes/{resume_id}/close-gaps` | Propose (never save) changes closing the open requirements |

All three require a **tailored** resume (`parent_id` set) with an `improvements` record linking it to a job; otherwise 400. A posting with nothing gradable returns 422 rather than a meaningless 0%.

## Tests

| Suite | Covers |
|-------|--------|
| `apps/backend/tests/unit/test_jd_match.py` | Scoring weights, requirement construction, both anti-inflation rules, cache-key invalidation |
| `apps/backend/tests/unit/test_text_normalize.py` | Typography normalisation, incl. leaving accented names intact |
| `apps/backend/tests/integration/test_jd_match_api.py` | Cache hit/miss, `refresh`, resume-edit invalidation, gap closing not persisting, employer-targeting change rejected |
| `apps/frontend/tests/jd-gap-panel.test.tsx` | Score rounding, open-gap counting, disabled states, error/loading states |

> Integration tests must seed **both** `job_keywords` and `job_keywords_hash` (see `_seed_keywords`). Seeding only the keywords makes `_get_or_extract_job_keywords` distrust the cache and fall through to a live LLM call.
