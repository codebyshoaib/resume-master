# Plan — Career Corpus, Phases 1–2

Spec: [`docs/specs/career-corpus-spec.md`](../docs/specs/career-corpus-spec.md) · Status: **awaiting approval**
Scope: Phase 1 (career documents + editing UI) and Phase 2 (context assembly + form-question answering). Phases 3–5 are specified but deliberately unplanned.

**What ships at the end of this plan:** upload or paste your career documents, see and edit them, then paste an application-form question and get an answer grounded in that material with citations you can check.

---

## Dependency graph

```
T1 _uploads.py (+ refactor resumes.py)
      │
      ├──────────────┐
      ▼              │
T2 CareerDocument    │
   model + facade    │
      │              │
      ▼              ▼
T3 schemas ────► T4 router: documents CRUD + upload
                      │
                      ├──► T5 backend tests (Phase 1 gate)
                      │
                      ▼
                 T6 api client ──► T7 Career page + Documents UI ──► T8 frontend tests
                                              │
        ══════════════ PHASE 1 GATE ══════════╧══════════════
                                              │
                                              ▼
                 T9 build_career_context (+ live master projection)
                      │
                      ▼
                 T10 answer prompt ──► T11 answer_career_question
                                              │
                                              ▼
                                    T12 /answer + /context/stats
                                              │
                                              ▼
                                    T13 Answer UI + citations ──► T14 frontend test
                                              │
        ══════════════ PHASE 2 GATE ══════════╯
```

**Sequential by necessity:** T1→T4 (router needs the helper), T2→T9 (context needs documents to exist), T9→T11 (answering needs context), T11→T12→T13.

**Parallelisable:** T3 alongside T1/T2. T6 can start once T3 lands (the schemas are the contract). T10 can be drafted any time after T9's signature is fixed.

---

## Phase 1 — Career documents

Goal: a real place to put career material, with nothing AI-powered yet. Deliberately boring; it is the foundation every later phase reads from.

### T1 — Shared upload validation

Extract the hardened upload path from `routers/resumes.py:729-770` into `routers/_uploads.py` as `read_and_extract(file, *, allowed_types, max_bytes)`, then refactor `upload_resume` onto it.

Router layer, not `services/` — no service in this repo raises `HTTPException`, and that layering stays. Parameterized because career documents need a wider allowlist (`text/plain`, `text/markdown`) and a higher cap than a 4MB resume.

**Risk:** this is the one task that touches a working, user-facing path. Mitigated by it being a pure extraction with existing integration tests as the guard — run them before and after and diff nothing.

### T2 — `CareerDocument` model + facade

Add the model to `models.py` and facade methods to `database.py`, following the `Application` precedent end-to-end (it is the most recently added table, so it is the live convention).

**Bootstrap: verified, no work needed.** `create_all` does not run at startup — it runs lazily from `Database._ensure_initialized()` (`database.py:83`) on first session access, guarded by `_initialized`. Models are registered on `Base` at import time (`db_engine.py` imports `Base` from `app.models`, so `db = Database()` at `database.py:828` cannot exist before the metadata is complete). Probed empirically: a new table is created on a **fresh** DB and on an **existing** one, idempotently, with existing rows intact. `career_documents` needs no migration script.

**The real constraint — get the columns right the first time.** `create_all` silently ignores *new columns on existing tables* (confirmed by probe; this is why `db_engine.py:70` hand-writes `ALTER TABLE resumes ADD COLUMN interview_prep`). Adding a column after Phase 1 ships means a hand-written idempotent ALTER in `init_models_sync`, not a model edit. So:

- Review the `career_documents` columns properly before writing them — this is not a "we'll add fields later" situation.
- Keep genuinely uncertain fields inside **JSON columns**, which extend without an ALTER. `career_facts.metrics` and `.tags` are already JSON for this reason.
- New *tables* remain free (Phase 3's `career_facts`, Phase 4's `ladder_assessments` need no migration).

### T3 — Document schemas

`schemas/career.py`: create/update/response models for documents. Export from `schemas/__init__.py` per existing pattern.

### T4 — Document endpoints

`routers/career.py` with `GET/POST/PATCH/DELETE /documents` and `POST /documents/upload`, registered in `main.py` alongside the other routers. Upload calls `read_and_extract` from T1 — no duplicated validation.

### T5 — Backend tests (Phase 1 gate)

Integration: full document CRUD via httpx ASGI; upload rejects bad content type (400), oversize (413), zero-extracted-text (422). Plus: the existing resume-upload tests still pass unchanged after T1.

### T6 — Frontend API client

`lib/api/career.ts`, mirroring `lib/api/tracker.ts`.

### T7 — Career page + Documents UI

`app/(default)/career/page.tsx` with a Documents section: list, upload, paste, edit title/kind/content, include/exclude toggle, delete.

The master resume renders as a **pinned read-only entry** — *"Master résumé — linked, edit in Builder"* — with an include/exclude toggle but no editable content. That toggle is a display preference; there is no copy of the resume anywhere.

Swiss International Style throughout. Textareas get the `Enter` → `stopPropagation` handler.

### T8 — Frontend tests

Document list renders; edit round-trips; the master-resume entry is not editable.

> **PHASE 1 GATE:** upload a real PDF performance review, see extracted text, edit it, save. Resume upload still works identically. `uv run pytest`, `npm run test`, `npm run lint` green.

---

## Phase 2 — Context assembly + form answering

Goal: the feature you actually wanted first. Works off documents alone — facts (Phase 3) exist to improve *tailoring*, not answering.

### T9 — `build_career_context`

`services/career.py`. Returns `(context_markdown, sources, truncated)`.

Three things this must get right:

1. **Project the master resume live** from `resumes` where `is_master = 1`, as a `kind="master_resume"` source. Never copy it. This is what makes "no sync" work.
2. **Render every source with its `source_id`** — citation is impossible otherwise.
3. **Sanitize all corpus text** through `_sanitize_user_input` from `improver.py`. This text now flows into every prompt in the app, a wider injection surface than a single resume upload was.

`max_chars` is a guard, not a strategy. It should never fire at this corpus size; if it starts firing, that is the FTS5 signal and it must be loud, not silent.

### T10 — Answer prompt

`prompts/career.py::CAREER_ANSWER_PROMPT`. Must instruct: only assert claims traceable to a supplied source, return `used_source_ids`, and put anything unsupported in `gaps` rather than asserting it. Reuse `CRITICAL_TRUTHFULNESS_RULES`.

### T11 — `answer_career_question`

Calls `complete_json`. **Drops citation ids the model invents** before they reach the client — an id that resolves to nothing is worse than no citation, because it looks verified. Empty corpus → 422, never an ungrounded answer.

### T12 — Endpoints

`POST /answer`, `GET /context/stats`. Stats powers the tailor-page indicator so an empty corpus is visible rather than silently degrading later phases.

### T13 — Answer UI

Question textarea → answer, with citations rendered as clickable chips linking to the source document, and gaps shown as a distinct block. The citations are the whole point: they are how you confirm the model quoted a real job.

### T14 — Frontend test

Answer renders; citations render; a fabricated id is not rendered.

> **PHASE 2 GATE:** paste a real application-form question, get a usable answer citing real sources. Empty corpus returns 422. All suites green.

---

## Risks

| Risk | Mitigation |
|---|---|
| **T1 breaks resume upload** — the only existing user-facing path touched | Pure extraction; existing integration tests run before and after. If they change behavior at all, revert and duplicate instead. |
| ~~`create_all` does not bootstrap fresh DBs~~ | **Resolved** — probed: new tables auto-create on fresh and existing DBs. No migration needed. |
| A `career_documents` column is wrong or missing after Phase 1 ships | `create_all` will not add it — costs a hand-written ALTER. Scrutinise the schema in T2; put uncertain fields in JSON columns. |
| Answers read plausible but are subtly invented | Citations are mandatory and server-validated; `gaps` is a first-class output. An honest "no evidence" beats a confident fabrication. |
| Corpus widens the prompt-injection surface | Sanitize in T9, at the single chokepoint every consumer reads through. |
| Curation never happens, corpus stays empty | `/context/stats` on the tailor page makes emptiness visible. Phase 2 needs no curation at all — only documents. |

## Out of scope

Facts, extraction, ladder, tailoring integration (Phases 3–5). No vector store, no embeddings, no FTS5. No new Python or npm dependencies — if a task seems to need one, stop and raise it.

## Definition of done

`uv run pytest` + `npm run test` + `npm run lint` + `npm run format` green · type hints on every Python function · Swiss style on all new UI · both phase gates demonstrated with a real document and a real question · zero new dependencies · nothing committed unless asked.
