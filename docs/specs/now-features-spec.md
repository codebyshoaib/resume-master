# Spec — NOW features (Resume Master)

Owner: product-lead · Status: ready to build · Confidence: high (first-principles + category benchmarks: Jobscan, Teal, Rezi)

Three independent bets, each built in its own git worktree. They overlap on `apps/backend/app/routers/resumes.py` and the frontend tailor surface — expect merge conflicts at integration time.

**North Star:** interview callbacks per user (lagging). **Activation:** first tailored resume downloaded. **Value moment:** seeing the match score jump for a specific job. **Guardrail (all three):** zero fabricated skills — the existing master-alignment checks in `refiner.py` must remain the source of truth; no feature may incentivize keyword-stuffing that fabricates.

Conventions (all features): Python type hints on every function; log details server-side, generic client messages; frontend follows the Swiss International Style (`docs/portable/swiss-design-system/`); `npm run lint` + `npm run format` clean; new behavior covered by a deterministic test. Leave changes unstaged.

---

## Feature 1 — Before → After ATS match (hero loop)

**Problem.** Tailoring is a black box. `compute_ats_score` (`app/services/ats.py`) already returns `overall_score`, `sub_scores`, `missing_keywords`, `injectable_keywords`, `recommendations`, but it's only produced *inside* the improve-preview response (`resumes.py::_build_ats_score`) — there's no baseline "before" number and no visible delta. The user never sees the win.

**Outcome.** Turn tailoring into a visible `62 → 89` result → activation + repeat use. This is Jobscan's entire paid value prop.

**Scope (in).**
- **Backend:** new endpoint `POST /api/v1/resumes/{id}/ats-score` with body `{ "job_id": <int> }` that computes the ATS score for the **current, untailored** resume against a job **without** running the LLM tailoring pipeline. Reuse: load the resume's `processed_data`, load/extract the job's keywords (`extract_job_keywords` is cached on the job by content hash — reuse the cache, don't force a new LLM call if cached), compute keyword match + missing/injectable via existing `refiner`/`ats` helpers, return the existing `ATSScore` schema. Fast and cheap (no tailoring LLM call).
- **Frontend (tailor page, `app/(default)/tailor` + components):** on JD selection, call the score-only endpoint to show the **baseline** score; after tailoring completes (existing flow already returns the after-score), render **before → after** with the numeric delta, the sub-score bars, and **missing-keyword chips**. Chips are display-only in this MVP.

**Scope (out / future).** One-click "inject this keyword" from a chip; historical score tracking over versions.

**User stories / acceptance criteria.**
- As a user, when I pick a JD I see my current resume's match score before tailoring. → endpoint returns a valid `ATSScore` for an untailored resume+job with no tailoring LLM call.
- After tailoring I see before, after, and the delta. → tailor page renders all three.
- Missing keywords render as chips. → chips present, sourced from the score payload.
- **Test:** deterministic backend test that the score-only endpoint returns a score for a seeded resume+job and does **not** invoke the tailoring pipeline (mock/assert LLM tailor not called; keyword extraction may be stubbed/cached).

**Technical notes.** Don't duplicate scoring logic — reuse `compute_ats_score`. Keep the `ATSScore` Pydantic schema shared. Handle: resume has no `processed_data` (return 422 with generic message), job not found (404).

---

## Feature 2 — ATS parseability linter

**Problem.** A high keyword score ≠ an ATS-parseable resume. Real auto-rejections come from *content/structure* problems, not keywords.

**Outcome.** Fewer silent rejections; delivers the literal "proper ATS resume" promise. Differentiator vs pure-keyword tools.

**Scope (in).**
- **Backend:** new pure service `app/services/ats_lint.py` → `lint_resume(resume: dict) -> list[LintFinding]` where `LintFinding = {code: str, severity: "error"|"warn"|"info", message: str, fix: str, path: str|None}`. Checks (operate on the parsed `ResumeData` JSON — deterministic, no LLM):
  - Missing contact email and/or phone (error).
  - Date ranges missing months where the resume elsewhere has months (warn) — reuse date conventions from `parser.py`.
  - Missing core sections: work experience, skills, education (warn each).
  - Empty/whitespace or non-descriptive `customSections` keys/titles (warn).
  - Summary absent or absurd length (<40 or >600 chars) (info/warn).
  - Bullets containing em dash `—` or other non-ASCII punctuation that some parsers mangle (warn) — note the output PDF is already single-column/no-tables, so **certify the rendered output as ATS-safe** and focus lint on parsed content.
  - Over-long bullets (> ~240 chars) (info).
- **Endpoint:** `GET /api/v1/resumes/{id}/ats-lint` → `{ findings: [...], summary: { errors, warnings, infos } }`.
- **Frontend:** a checklist panel on the resume view/builder listing findings grouped by severity, each with its `fix` hint. Swiss style — hard borders, mono metadata, alert colors from the token set (`#DC2626` error, `#F97316` warn).

**Scope (out / future).** Layout linting of arbitrary uploaded PDFs (you already normalize on parse); LLM-based phrasing critique (that's the buzzword scrub's job).

**Acceptance criteria.**
- `lint_resume` is pure, fully type-hinted, deterministic.
- Endpoint returns findings + summary for a seeded resume; 404 on missing resume.
- Frontend renders the checklist with severity colors and fix hints.
- **Test:** one unit test per check (a resume that trips it and one that doesn't) — each test must fail if its check regresses.

---

## Feature 3 — Instrumentation (the meta-bet)

**Problem.** Zero visibility → every future product bet is a guess.

**Outcome.** Evidence for the Next/Later gates in the roadmap. This is a means, not a user feature.

**Scope (in) — local-first, no external dependency (self-hosted tool).**
- **Backend:** new SQLAlchemy model `AnalyticsEvent(id, event_name: str, properties: JSON, created_at: datetime)` in `models.py` (tables auto-created on startup — match existing pattern). An `app/services/analytics.py::emit_event(name: str, properties: dict) -> None` helper that is **fire-and-forget and never raises or blocks the request** (wrap in try/except, log-and-swallow). Instrument these call sites:
  - `resume_uploaded`, `tailor_started`, `tailor_completed` (props: `before_score`, `after_score`, `delta` when available), `resume_pdf_downloaded`, `cover_letter_generated`, `application_created`.
- **Endpoint:** `GET /api/v1/analytics/summary` → funnel counts (`uploads → tailors → downloads`) + event totals over an optional `?days=N` window.
- **Guardrail — privacy:** events store **no PII and no resume content** — ids and numeric metrics only. Local SQLite only; nothing leaves the machine.

**Scope (out / future).** External analytics (PostHog/GA), per-user segmentation, a rich dashboard UI (a minimal read-only funnel view is fine but optional for this pass).

**Acceptance criteria.**
- `emit_event` writes a row and **never propagates an exception** (test: patch the DB to throw → caller still succeeds).
- Key events emitted at the listed call sites.
- `/analytics/summary` returns correct funnel counts for seeded events.
- **Test:** emit writes a row; summary aggregates a seeded set correctly; emit swallows DB errors.
