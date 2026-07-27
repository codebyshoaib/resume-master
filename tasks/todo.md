# Todo — Career Corpus, Phases 1–2

Plan: [`tasks/plan.md`](plan.md) · Spec: [`docs/specs/career-corpus-spec.md`](../docs/specs/career-corpus-spec.md)
Status: **Phases 1–2 complete.** Gates 1 and 2 passed; Phases 3–5 remain specified but unplanned.

Every task: type hints on all Python functions, details logged server-side + generic client messages, Swiss International Style on UI, nothing committed unless asked.

---

## Phase 1 — Career documents

- [x] **T1 — Shared upload validation** ✅
  - Done: `routers/_uploads.py` exports `read_and_extract(file, *, allowed_types, allowed_label, max_bytes) -> tuple[str, int]` covering type (400), oversize (413), empty (400), parse failure (422, logged), zero extracted text (422, scanned-document message). `resumes.py::upload_resume` delegates to it; `ALLOWED_TYPES` / `MAX_FILE_SIZE` kept as aliases for existing importers.
  - Returns `(text, raw_byte_size)` — the byte count is needed for the `resume_uploaded` analytics event and differs from the extracted-text length for PDF/DOCX.
  - Verified: `uv run pytest` → **540 passed**. The suite caught a real regression mid-refactor (`size_bytes` referencing a deleted local), which is the anti-theater evidence for this task.
  - Gate note: four `@patch` targets moved from `app.routers.resumes.parse_document` to `app.routers._uploads.parse_document` (`test_upload_api.py` ×2, `test_analytics_api.py`, `test_pipeline_e2e.py`). **No assertion changed.** Leaving them stale was the unsafe option — the mock would have stopped intercepting and `test_maps_parse_failure_to_422` would have passed for the wrong reason.
  - Rule refined for future tasks: an **assertion** change means stop and reconsider; a **mock-target** change is expected when code moves modules.
  - Files: `app/routers/_uploads.py` (new), `app/routers/resumes.py`, 3 test files (patch targets only)

- [x] **T2 — `CareerDocument` model + facade** ✅
  - Done: `CareerDocument` in `models.py` (`document_id`, `title`, `kind`, `content`, `filename`, `include_in_context`, timestamps). Facade: `create/get/list/update/delete_career_document` + `_career_document_to_dict`, following the `Resume`/`Application` precedent.
  - `list_career_documents(kind=None, *, included_only=False)` — `included_only` is the corpus-assembly view; the management UI wants every row.
  - `update_career_document` rejects `document_id` / `created_at` as immutable and warns on unknown keys, rather than the `update_resume` behaviour of silently allowing any attribute that happens to exist.
  - **Added to `reset_database`** — career documents are user data, so a "reset all data" that left them behind would be the same bug as leaving orphaned tracker cards.
  - Decided **against** a `metadata_json` escape hatch. `Job` has one because JD-pipeline fields are genuinely dynamic; this shape is stable, and an escape hatch invites unversioned sludge. Accepting the known cost: a future column needs one idempotent ALTER in `init_models_sync`.
  - Verified: 10 new tests in `tests/unit/test_database.py`; full suite **550 passed**. Anti-theater confirmed by mutation — dropping the `included_only` filter and the reset truncation failed exactly the two tests targeting them, and only those.
  - Files: `app/models.py`, `app/database.py`, `tests/unit/test_database.py`

- [x] **T3 — Document schemas** ✅
  - Done: `schemas/career.py` — `CareerDocumentKind` enum, `CareerDocumentCreate/Update`, `CareerDocumentSummary` (list view, body truncated to `PREVIEW_CHARS=400`) / `CareerDocumentResponse` (full body) / `CareerDocumentListResponse`. Exported from `schemas/__init__.py`.
  - Also landed the Phase-2 citation contract early so it never needs changing: `CareerSourceKind` (`master_resume` | `document` | `fact`), `CareerSourceRef`, `CareerContextStats`. `fact` is declared now and used in Phase 3.
  - `CareerDocumentUpdate` fields are all optional (empty PATCH = no-op) but `title`/`content` reject empty strings when supplied — blanking them would leave an unusable row.
  - Files: `app/schemas/career.py` (new), `app/schemas/__init__.py`

- [x] **T4 — Document endpoints** ✅
  - Done: `GET/POST/PATCH/DELETE /api/v1/career/documents`, `GET /documents/{id}`, `POST /documents/upload`. Registered in `routers/__init__.py` + `main.py`. Upload delegates entirely to `read_and_extract` — zero duplicated validation.
  - List returns truncated previews + `char_count`; only `GET /documents/{id}` ships the full body, so rendering the list never transfers the whole corpus.
  - Upload derives the title from the filename stem (`_title_from_filename`), falling back to "Untitled document" since `title` is non-nullable.
  - Files: `app/routers/career.py` (new), `app/routers/__init__.py`, `app/main.py`

- [x] **T5 — Backend tests (Phase 1 gate)** ✅
  - Done: 20 integration tests (`tests/integration/test_career_api.py`) over real isolated SQLite + 7 unit tests (`tests/unit/test_career_helpers.py`). Full suite **577 passed**.
  - **`conftest.py::isolated_db` needed `"career"` added to its router list** — without it `app.routers.career.db` kept pointing at the global singleton and tests would have written to the developer's real database.
  - One planned test was **deleted rather than made to pass**: a filename-less upload is unreachable through FastAPI (an empty multipart `filename` becomes a plain form field, rejected before the router runs), so asserting the fallback over HTTP would have passed for the wrong reason. `_title_from_filename` is unit-tested directly instead.
  - Files: `tests/integration/test_career_api.py` (new), `tests/unit/test_career_helpers.py` (new), `tests/conftest.py`

> **GATE 1 (backend) — PASSED.** Verified with **no mocks** against real extraction: a real `python-docx` DOCX and a real Chromium-rendered PDF both upload, extract with metrics intact (`40%`, `80%` preserved), edit, mute, and delete. Script: `scratchpad/e2e_career.py`.

- [x] **T6 — Frontend API client** ✅
  - Done: `lib/api/career.ts` — typed CRUD + multipart upload, mirroring `lib/api/tracker.ts`.
  - **Moved `extractDetail` + `asJson` from `tracker.ts` into `client.ts`** and repointed `tracker.ts` at them, rather than duplicating 30 lines of FastAPI error-detail parsing that would drift. `tests/api-tracker.test.ts` passed unchanged after the move.
  - Upload uses raw `fetch` (not `apiFetch`) deliberately: `FormData` must set its own multipart boundary, so no `Content-Type` header is sent. A test asserts `options.headers` is undefined.
  - Files: `apps/frontend/lib/api/career.ts` (new), `lib/api/client.ts`, `lib/api/tracker.ts`

- [x] **T7 — Career page + Documents UI** ✅
  - Done: `/career` — list with kind filter, upload, paste/edit dialog, include-in-corpus toggle (optimistic, re-syncs on failure), delete behind `ConfirmDialog`. Corpus summary counts **only** included documents. Swiss style throughout; textarea stops `Enter` propagation.
  - Master résumé renders as a **pinned read-only row** (`Lock` icon, "linked — edit in Builder", link to `/builder`) with no content editor and no delete control. Hidden entirely when no master exists.
  - Nav entry added to `swiss-grid.tsx` footer next to the tracker link.
  - **i18n: `career.*` + `nav.careerCorpus` added to all 6 locales** (en, es, fr, ja, pt-BR, zh). Parity is build-breaking, so this was not optional. The 5 non-English sets are mine and would benefit from native review.
  - Note: `apps/frontend/CLAUDE.md` says 5 locales — stale, `fr` was added since. `i18n/config.ts` is the authority.
  - Files: `app/(default)/career/page.tsx`, `components/career/career-documents.tsx`, `components/career/document-editor-dialog.tsx` (all new), `components/home/swiss-grid.tsx`, `messages/*.json` ×6

- [x] **T8 — Frontend tests** ✅
  - Done: 11 component tests + 10 API-client tests. Full frontend suite **211 passed**, `npm run lint` clean, `tsc` clean, `npm run build` succeeds with `/career` prerendered.
  - `t` is mocked to echo its key (suite convention), with params appended as JSON so the corpus-summary maths is still pinned — a muted document must contribute neither to the count nor the char total.
  - Master-résumé invariants are covered explicitly: links to `/builder`, no delete control, absent when no master exists.
  - Used `fireEvent` rather than adding `@testing-library/user-event` — not installed, and not worth a dependency.
  - Files: `tests/career-documents.test.tsx`, `tests/api-career.test.ts` (both new)

> **GATE 1 — PASSED (backend + frontend).**
> Backend: **577 passed**. Frontend: **211 passed**, lint clean, tsc clean, production build green.
> Real-extraction check with no mocks: DOCX + Chromium-rendered PDF both upload with metrics intact, edit, mute, delete (`scratchpad/e2e_career.py`).
> Resume upload behaviour unchanged — its own integration tests pass with assertions untouched.
> Side note: `npm run format` also reformatted `apps/frontend/CLAUDE.md` (pre-existing prettier drift, unrelated) — **reverted** to keep the diff focused.

---

## Phase 2 — Context assembly + form answering

- [x] **T9 — `build_career_context`** ✅
  - Done: `services/career.py`. Returns `(context_markdown, sources, truncated)`. Master resume projected **live** from `resumes` (never copied); muted documents excluded; every `source_id` rendered into the prompt; all corpus text through the tailoring pipeline's sanitiser.
  - Prefers `processed_data` over `content`/`original_markdown` for the master: the builder overwrites `content` with JSON and `original_markdown` is a snapshot of the upload, so both can lag behind edits.
  - Truncation drops documents oldest-first, **never the master resume**, and logs a warning naming FTS5 as the fix.
  - **Design bug caught by a test:** I had set `CareerSource.kind` to the *document's* kind (`review`/`brag`), which collides with the source-type taxonomy the client needs to resolve a citation (`master_resume`/`document`/`fact`). Split into `kind` + `detail`; `detail` still reaches the prompt so the model can weigh a performance review above a loose note.
  - Files: `app/services/career.py` (new), `tests/unit/test_career_context.py` (new, 16 tests)

- [x] **T10 — Answer prompt** ✅
  - Done: `prompts/career.py::CAREER_ANSWER_PROMPT`. Seven grounding rules; requires `used_source_ids`; routes unsupported material to `gaps`; takes `{output_language}` per repo convention.
  - **Deviated from the spec:** did *not* reuse `CRITICAL_TRUTHFULNESS_RULES`. Those govern editing a resume ("do not remove existing skills", "copy date ranges exactly") and several are meaningless for a free-text answer. Wrote task-appropriate rules with the same intent instead.
  - Files: `app/prompts/career.py` (new)

- [x] **T11 — `answer_career_question`** ✅
  - Done: strips citation ids not present in the assembled corpus, dedupes them, logs how many were dropped. Empty corpus raises before the model is called at all. Blank answer is an error, not an empty success.
  - Verified anti-theater by mutation: trusting the model's ids instead of validating them fails exactly 4 tests.
  - Files: `app/services/career.py`, `tests/service/test_career_service.py` (new, 11 tests)

- [x] **T12 — Answer endpoints** ✅
  - Done: `POST /career/answer` → `{answer, used_sources[], gaps[], truncated}`; `GET /career/context/stats`. Empty corpus → 422 with a fixable message; LLM failure → 500 with the detail logged, never leaked.
  - **Second `isolated_db` escape, fixed at the root:** `services/career.py` also binds `db`, and conftest only patched routers. Replaced the hand-written module list with `pkgutil` discovery over `app.routers.*` + `app.services.*`, so no future module can silently bind the developer's real database in tests.
  - Files: `app/routers/career.py`, `app/schemas/career.py`, `tests/integration/test_career_api.py`, `tests/conftest.py`

- [x] **T13 — Answer UI** ✅
  - Done: `components/career/career-answer.tsx` — question textarea, tone, word limit, answer with copy button, citations as chips, gaps block, truncation warning. Empty corpus disables asking and says why rather than firing a request that can only 422.
  - An answer with **zero citations renders an explicit warning** ("treat this answer with suspicion") instead of looking identical to a sourced one.
  - Page now holds `sourceCount` and refreshes it whenever the documents panel changes the corpus.
  - `career.answer.*` added to all 6 locales.
  - Files: `components/career/career-answer.tsx` (new), `app/(default)/career/page.tsx`, `components/career/career-documents.tsx`, `lib/api/career.ts`, `messages/*.json` ×6

- [x] **T14 — Frontend test** ✅
  - Done: 9 tests. Covers uncited-answer warning, gaps rendering, truncation warning, payload shape, blank tone omitted, error surfacing, and empty-corpus blocking.
  - Files: `tests/career-answer.test.tsx` (new)

> **GATE 2 — PASSED.**
> Backend **613 passed**; frontend **220 passed**; lint clean, tsc clean, production build green.
> End-to-end with only the LLM stubbed (`scratchpad/e2e_answer.py`): real corpus assembled from a master resume + documents, muted document excluded from the prompt, grounding rules and citable ids present, a **fabricated citation id dropped** before reaching the client, gaps preserved, and an empty corpus returning 422 without the model being called.
