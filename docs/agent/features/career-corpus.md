# Career Corpus Feature

> **One store for the career material a resume is a projection of, plus grounded answers to application-form questions.**

Spec: [`docs/specs/career-corpus-spec.md`](../../specs/career-corpus-spec.md) · Task history: [`tasks/todo.md`](../../../tasks/todo.md)

## Status

| Phase | What | State |
|-------|------|-------|
| 1 | Career documents: store, upload/paste, edit, mute, delete + `/career` UI | **Shipped** |
| 2 | Context assembly + grounded form answers with citations | **Shipped** |
| 3 | Curated facts (LLM extraction → user approval) | Specified, not built |
| 4 | Ladder assessment against a pasted rubric, with history | Specified, not built |
| 5 | Tailoring reads the corpus | Specified, not built — **blocked**, see below |

Phases 3–5 are deliberately unplanned. Phases 1–2 are independently useful and
touch no existing behavior, so the corpus can be judged with real data before
committing to the expensive half.

## Overview

`/career` holds **career documents** — performance reviews, brag docs, project
write-ups, pasted notes, a company career ladder. Those documents plus the
master resume form the **corpus**, which is assembled into one prompt block and
used to answer application-form questions ("describe a time you led a project
without formal authority") in the user's own words, with citations.

## Architecture decision: no retrieval, no vector store

**There is no RAG here, on purpose.** Retrieval exists to solve *corpus larger
than the context window*. At the size this feature targets (under ~50 pages,
~25k tokens) that problem does not exist, and top-k retrieval would make output
*worse*: choosing which achievements answer a question is a **breadth** problem,
whereas retrieval optimises for precision on a narrow query and would silently
drop the one relevant item — no error, just a weaker answer.

The whole corpus goes into one prompt. `build_career_context` has a `max_chars`
guard that is a **budget check, not a strategy**; `truncated` is surfaced through
`GET /career/context/stats` so it is observable.

**Upgrade path, in order, only when the previous step measurably fails:**
SQLite **FTS5** (already have SQLite, ~30 lines, no new dep) → `sqlite-vec` →
an external vector store. `truncated` coming back true in normal use is the
trigger for step one. Do not pre-build any of it.

A standalone RAG app (DocuRag: LangGraph + Groq + ChromaDB + sentence-transformers
+ cross-encoder + PostgreSQL + Docker Compose) was evaluated and rejected: a
second service and ~2GB of torch wheels beside a local-first SQLite app, buying
retrieval quality that is not needed.

## The master resume is projected, never copied

The master resume stays in `resumes` with its existing
`ux_resumes_single_master` invariant and Builder flow. It is **not** copied into
`career_documents`. `build_career_context` reads it live and renders it as a
virtual source.

Consequences, and why this is not a shortcut:

- **No sync mechanism, because there is nothing to sync.** Two editable copies
  would need conflict resolution for "both changed since last sync".
- **No drift.** The context is current by construction.
- Writing markdown back into the master would mean re-running
  `parse_resume_to_json`, which could degrade the `processed_data` that ATS
  scoring and tailoring both read (`restore_dates_from_markdown` exists because
  that rebuild is lossy).

`_master_resume_text` prefers `processed_data` over `content` /
`original_markdown`: the builder overwrites `content` with JSON on save, and
`original_markdown` is a snapshot of the original upload, so both can lag behind
edits.

In the UI it renders as a pinned, read-only row labelled "linked — edit in
Builder", with an include/exclude toggle that is a display preference, not a copy.

## Citations

`POST /career/answer` returns `used_sources` — the verification surface. It is
how the user confirms the answer quoted a real job rather than a plausible one.

- `source_id` + `kind` (`master_resume` | `document` | `fact`) is the **source
  type**, which is what the client needs to resolve a citation. It is *not* the
  document's own kind (`review` / `brag` / `ladder`); that lives in `detail` and
  reaches the prompt so the model can weigh a review above a loose note.
  Conflating the two makes citations unresolvable.
- **Ids the model invents are dropped server-side** before reaching the client.
  An id that resolves to nothing looks *verified*, which is worse than no
  citation at all. The number dropped is logged.
- An answer with empty `used_sources` and non-empty `gaps` is a valid, useful
  response, and the UI flags it explicitly rather than rendering it identically
  to a sourced answer.
- An **empty corpus returns 422 and the model is never called.** An ungrounded
  answer is worse than no answer.

## Answer quality: what the prompt has to fight

`app/prompts/career.py` carries rules that exist because real output failed
without them. Each is pinned by a regression test in
`tests/service/test_career_service.py`.

| Failure seen in real output | Rule |
|---|---|
| *"as it is listed among my technical skills in my resume"* | Never mention sources, or describe where something is written down |
| The gap argued against the candidate inside the answer body | Caveats live in `gaps` only, never in `answer` |
| `full‑stack` with U+2011, curly quotes | `_plain_ascii()` normalises typography that web form fields mangle; known offenders only, so accented names survive |
| A skills line + an unrelated employer became *"I used GraphQL at DTS to replace over-fetching REST endpoints"* | A technology appearing **only** in a skills list is not experience and may not be attached to any employer, project, or outcome |
| *"share your experience and understanding of the concepts"* answered with a CV summary | **Claims about you** stay grounded; **general technical knowledge** is explicitly exempt and must be explained. See below |

### Grounded biography, free explanation

The single most important distinction in the prompt:

- **Claims about you** — employers, titles, dates, what you built, what you
  measured — are strictly limited to the corpus. This is where fabrication is
  dangerous.
- **General technical knowledge** — what a technology is, how it works,
  trade-offs, common pitfalls — is public knowledge, *not* a claim about the
  candidate's career. It is exempt from grounding and must be explained properly.

Grounding everything was the original bug: it left the model no material except
resume lines, so a question asking for conceptual understanding could only be
answered by reciting the CV. A test asserts the biography guards survived the
exemption, so widening what may be *explained* cannot quietly widen what may be
*claimed*.

`CRITICAL_TRUTHFULNESS_RULES` from `prompts/templates.py` is deliberately **not**
reused: those rules govern *editing a resume* ("do not remove existing skills",
"copy date ranges exactly") and several are meaningless for a free-text answer.

## Data Model

`career_documents` — `document_id`, `title`, `kind`, `content`, `filename`,
`include_in_context`, `created_at`, `updated_at`. Append-mostly. Included in
`reset_database` (it is user data, so a full reset that left it behind would be
a bug). Cleared with the rest of the document tables; `api_keys` is preserved.

No `metadata_json` escape hatch, unlike `Job`: that exists because JD-pipeline
fields are genuinely dynamic, whereas this shape is stable and an escape hatch
invites unversioned sludge. **Known cost:** `create_all` cannot add columns to
an existing table, so a field added later needs a hand-written idempotent
`ALTER` in `db_engine.init_models_sync` (the `interview_prep` precedent).

Phase 3 adds `career_facts`, Phase 4 `ladder_assessments`. New *tables* are free
— `create_all` creates them on fresh and existing databases alike.

## API

All under `/api/v1/career`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/documents` | List, oldest first, bodies truncated to `PREVIEW_CHARS` |
| `GET` | `/documents/{id}` | One document with its full body |
| `POST` | `/documents` | Create from pasted text |
| `POST` | `/documents/upload` | Multipart; extracted via the shared upload helper |
| `PATCH` | `/documents/{id}` | Edit title/kind/content/`include_in_context`; empty body is a no-op |
| `DELETE` | `/documents/{id}` | 204, or 404 so retries are honest |
| `POST` | `/answer` | `{question, tone?, max_words?}` → `{answer, used_sources[], gaps[], truncated}` |
| `GET` | `/context/stats` | Corpus size + `truncated`, so emptiness is visible |

Only `GET /documents/{id}` ships a full body — rendering the list never
transfers the whole corpus.

## Uploads

`app/routers/_uploads.py::read_and_extract` is shared with the resume upload:
content-type allowlist (400), size cap (413), empty file (400), parse failure
(422, logged), and **empty extracted text (422)** for image-only/scanned files.
It lives in the router layer because no service in this codebase raises
`HTTPException`.

Career documents use a wider allowlist (`text/plain`, `text/markdown`) and a
higher cap than resumes; both pass their own values.

**Known ceiling — no OCR.** MarkItDown does not OCR, so a scanned PDF extracts
to nothing and returns the 422. If that becomes common, the upgrade is a vision
pass through the already-configured LiteLLM router, not a `tesseract` dependency.

## Phase 5 is blocked on a design decision

Tailoring currently validates output against the **master resume**, and
`CRITICAL_TRUTHFULNESS_RULES` exists to stop fabrication. Once tailoring can pull
from a corpus, legitimately-sourced content will trip that check as if it were
invented. Two wrong fixes: loosen the check (raises fabrication risk, which is
the app's stated guardrail) or leave it (the feature cannot work).

Intended fix: **the corpus becomes the truth set**, a superset of the master
resume, and alignment validates against corpus-derived facts. This must be
designed before Phase 5 starts. Phase 5 is the only phase that can break
something already working, and its gate includes: *with an empty corpus,
tailoring output must be byte-identical to today*.

## Known gaps

- **The five non-English locale sets for `career.*` are machine-authored** and
  want native review.
- **No test covers real LLM output.** Prompt construction and citation
  validation are verified against a stub; answer *quality* has only been checked
  by hand.
- `DEFAULT_MAX_CHARS = 120_000` is a guess pending measurement against a real
  corpus.
- Answers are only as good as what is in the store. A corpus of one resume
  produces generic answers; `GET /context/stats` exists so that is visible
  rather than silent.

## Testing

| Layer | File |
|-------|------|
| unit | `tests/unit/test_career_context.py` — assembly, live master projection, mute, injection scrub, truncation |
| unit | `tests/unit/test_career_helpers.py` — filename→title |
| unit | `tests/unit/test_database.py::TestCareerDocumentCrud` |
| service | `tests/service/test_career_service.py` — citation stripping, voice, list-only-skill guard, explain-vs-recite |
| integration | `tests/integration/test_career_api.py` — CRUD, upload guards, `/answer`, `/context/stats` |
| frontend | `tests/career-documents.test.tsx`, `tests/career-answer.test.tsx`, `tests/api-career.test.ts` |

Citation validation is **mutation-verified**: trusting the model's ids instead of
checking them fails exactly four tests.

> `tests/conftest.py::isolated_db` discovers every module binding the `db`
> singleton via `pkgutil` over `app.routers.*` and `app.services.*`. It used to
> keep a hand-written list, which let `app.services.career` point at the
> developer's real database in tests. Do not replace it with a list.
