# Spec — Career Corpus ("career ladder RAG")

Status: **Phases 1–2 shipped. Phases 3–5 specified, not built.**
Owner: Shoaib · Confidence: high on the data layer, medium on the tailoring integration (see Risks).

| Phase | Deliverable | State |
|-------|-------------|-------|
| 1 | Career documents + `/career` UI | **Shipped** |
| 2 | Context assembly + grounded `/answer` with citations | **Shipped** |
| 3 | Curated facts (LLM extraction → approval) | Not built |
| 4 | Ladder assessment + history | Not built |
| 5 | Tailoring reads the corpus | Not built — **blocked on Risk 1** |

What shipped, what it cost, and what real output forced to change afterwards is
recorded in [`docs/agent/features/career-corpus.md`](../agent/features/career-corpus.md)
(the living feature doc) and [`tasks/todo.md`](../../tasks/todo.md) (per-task
history). This spec is the original reasoning; read the feature doc for current
behaviour.

**Phases 3–5 are deliberately unplanned.** Phases 1–2 are independently useful
and touch no existing behaviour, so the premise can be judged against real
documents before committing to the expensive half. Phase 5 in particular must not
start until Risk 1 below is designed — it is the only phase that can break
something already working.

---

## Objective

Make the user's career history a first-class store in Resume-Matcher, so that everything downstream (JD tailoring, application-form answers, cover letters, interview prep, level progression) reads from one curated source of truth instead of from a single markdown blob in `Resume.content`.

**Who:** a single user running the app locally (the existing deployment model — SQLite in `apps/backend/data/`).

**Five capabilities, in build order:**

1. **Career store + editing UI** — upload/paste career documents (resumes, performance reviews, brag docs, project write-ups, ladder rubrics), view and edit them.
2. **Form-question answering** — paste "Describe a time you led a cross-functional project" → grounded answer, with citations back to the source material used.
3. **Curated facts** — LLM extracts atomic achievements/roles/skills/stories from documents; user approves or edits them. These are what tailoring selects over.
4. **Ladder assessment** — paste your company's levelling rubric as a document; get a competency-by-competency assessment with evidence and gaps.
5. **Tailoring integration** — `improver.py` selects from the approved fact set instead of only rewriting the master resume.

**Success looks like:** a JD goes in and the tailored resume surfaces an achievement that *was not in the master resume* but was in the corpus — sourced, not invented.

---

## Architecture decision: no RAG, no vector store

**Rejected: DocuRag** (`github.com/hammad-sarfraz-1/DocuRag`). It is a standalone FastAPI app — LangGraph + Groq + ChromaDB + sentence-transformers + rank-bm25 + a cross-encoder reranker + **PostgreSQL** + Docker Compose — explicitly not an importable library. Adopting it means running a second service, adding Postgres alongside SQLite, and pulling ~2GB of torch wheels into a local-first single-user app. Cost is entirely infrastructural; the retrieval quality it buys is not needed (below).

**Rejected: retrieval in any form, for now.** The corpus is under ~50 pages (~25k tokens). Every model this app targets takes 200k+. Retrieval exists to solve *corpus > context window*; that problem does not exist here.

More importantly, retrieval would make output **worse**. Resume tailoring is a *breadth* problem — the model must see all achievements to select the best subset for a JD. Top-k retrieval optimizes for precision on a narrow query: it would return five backend-heavy chunks and silently drop the one leadership bullet that the JD's "mentors junior engineers" line needed. The failure is invisible — no error, just a quieter resume.

**Chosen: stuffed context.** One assembled markdown block containing the whole corpus, passed into the prompt.

**Upgrade path (do not pre-build):** if the corpus outgrows the window or per-call cost becomes the binding constraint → SQLite **FTS5** (already have SQLite, ~30 lines, zero new deps) → `sqlite-vec` → only then an external vector store. Record the trigger, not the code.

**New Python dependencies: zero.** See Document Parsing below — the extraction layer already exists and is already hardened.

---

## Document Parsing (PDF / DOCX / TXT)

Nothing new is needed. `app/services/parser.py:119` — `parse_document(content: bytes, filename: str) -> str` — wraps **MarkItDown** (`markitdown[docx]==0.1.4` + `pdfminer.six`, both already installed) and covers PDF, DOC, DOCX, XLSX, PPTX, HTML, TXT. It is already live at `routers/resumes.py:756`.

DocuRag's extraction layer used the same class of library; its actual contribution was chunk → embed → Chroma → BM25 → rerank, which is the part this spec rejects. Parsing was never the dependency's value.

The existing resume-upload path is already hardened — content-type allowlist (400), 4MB cap (413), empty file (400), parse failure (422, logged), and **empty extracted text (422 with a scanned-document message)**. Career upload must not reimplement any of it.

**Change:** extract that validation into `app/routers/_uploads.py` as one parameterized helper:

```python
async def read_and_extract(
    file: UploadFile,
    *,
    allowed_types: frozenset[str],
    max_bytes: int,
) -> str:
    """Validate an upload and extract it to markdown.

    Raises HTTPException with client-safe messages; details are logged.
    """
```

- Lives in the **router** layer, not `services/` — no service in this repo raises `HTTPException` (verified: zero hits under `app/services/`), and that layering stays intact.
- Parameterized because the callers legitimately differ: resumes keep `RESUME_TYPES` / 4MB; career documents also accept `text/plain` and `text/markdown` at a higher cap.
- `resumes.py` is refactored onto it in the same change — one code path, both callers. Pure extraction, guarded by the existing upload integration tests.

**Known ceiling — no OCR.** MarkItDown does not OCR, so image-only/scanned PDFs extract to nothing and return the existing 422. That is correct behavior, not a defect, and DocuRag would not have changed it. If scanned documents turn out to be common in the real corpus, the upgrade is a vision-model pass through the LiteLLM router already configured (no new dependency) rather than adding `tesseract`. Out of scope until a real file fails.

---

## Tech Stack

Unchanged from the repo. FastAPI + Python 3.13, SQLAlchemy 2.0 async / aiosqlite, LiteLLM (`app/llm.py::complete_json`), Next.js 16 + React 19 + Tailwind v4.

---

## Commands

```bash
# Backend
cd apps/backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
uv run pytest                                  # must stay green

# Frontend
cd apps/frontend
npm install
npm run dev
npm run test
npm run lint
npm run format
npm run build
```

---

## Project Structure

New files only; everything follows the placement of the most recently added table (`Application`), which is the live convention.

```
apps/backend/app/
├── models.py                    → EDIT: add CareerDocument, CareerFact, LadderAssessment
├── database.py                  → EDIT: facade methods, mirroring the Application precedent
├── schemas/career.py            → NEW: Pydantic request/response models
├── services/career.py           → NEW: context assembly, fact extraction, answering, ladder
├── prompts/career.py            → NEW: extraction / answer / ladder prompt templates
├── routers/career.py            → NEW: /api/v1/career/*  (register in main.py)
├── routers/_uploads.py          → NEW: shared upload validation + extraction
├── routers/resumes.py           → EDIT: upload path refactored onto _uploads.py
└── services/improver.py         → EDIT (Phase 5 only): accept career context

apps/backend/tests/
├── unit/test_career_context.py       → context assembly, token budget, redaction
├── service/test_career_service.py    → extraction + answering with mocked LLM
└── integration/test_career_router.py → CRUD + answer endpoint via httpx ASGI

apps/frontend/
├── app/(default)/career/page.tsx     → NEW: Documents | Facts | Answer | Ladder
├── components/career/                → NEW: doc list, fact editor, answer panel
└── lib/api/career.ts                 → NEW: typed client (mirrors lib/api/tracker.ts)
```

---

## Data Model

Three tables. New tables are created by the existing `Base.metadata.create_all` bootstrap in `db_engine.py` — no migration script needed. *(Verify at implementation time that the bootstrap runs on startup for a fresh DB.)*

**`career_documents`** — raw source, append-mostly.

| Column | Type | Notes |
|---|---|---|
| `document_id` | str PK | uuid |
| `title` | str | user-editable |
| `kind` | str | `resume` \| `review` \| `brag` \| `project` \| `jd` \| `ladder` \| `other` |
| `content` | Text | extracted markdown/plain text |
| `filename` | str? | null when pasted |
| `include_in_context` | bool | default true; lets the user mute a doc without deleting it |
| `created_at` / `updated_at` | str | ISO, matching existing convention |

**`career_facts`** — curated atomic records; the unit tailoring selects over.

| Column | Type | Notes |
|---|---|---|
| `fact_id` | str PK | uuid |
| `type` | str | `achievement` \| `role` \| `skill` \| `story` \| `education` |
| `title` | str | one-line label |
| `body` | Text | the claim, in the user's words |
| `metrics` | JSON? | `[{"label": "latency", "value": "-40%"}]` — kept structured so tailoring can restate without inventing numbers |
| `tags` | JSON | free-text tags for selection |
| `org` | str? | employer/project |
| `start_date` / `end_date` | str? | ISO or `YYYY-MM`; null = ongoing |
| `source_document_id` | str? | provenance; null = hand-entered |
| `status` | str | `draft` (LLM-proposed) \| `approved` \| `archived` |
| `created_at` / `updated_at` | str | |

**`ladder_assessments`** — derived artifact, one row per run.

| Column | Type | Notes |
|---|---|---|
| `assessment_id` | str PK | |
| `rubric_document_id` | str | FK-ish to a `kind='ladder'` document |
| `current_level` | str? | where you are, per this run |
| `target_level` | str? | e.g. `Senior` — free text, comes from the rubric |
| `result` | JSON | `[{competency, verdict, evidence_source_ids[], gap}]` |
| `created_at` | str | |

**Progress tracking needs no extra table.** One row per assessment run plus `created_at` *is* the history — ordered rows give the timeline, and the newest row is "where I am now". A separate profile table storing current/target would only duplicate what the latest row already says, and then drift from it.

**Deliberate simplification:** the ladder rubric has no schema. It is just a document of `kind='ladder'`, and the assessment is an LLM pass over (rubric text + approved facts). Every company's ladder is shaped differently; modelling competency hierarchies would be a schema we rewrite on first contact with a real rubric.

### The master resume is projected, never copied

The existing master resume (`resumes` where `is_master = 1`) stays exactly as it is today — same table, same `ux_resumes_single_master` invariant, same Builder flow. It is **not** copied into `career_documents`.

Instead, `build_career_context()` reads it live and renders it as a virtual source. Consequences:

- **No sync mechanism, because there is nothing to sync.** Two editable copies would require conflict resolution for "both changed since last sync", and there is no safe answer.
- **No drift.** The context is current by construction.
- **No risk to structured data.** Writing markdown back into the master would mean re-running `parse_resume_to_json` and could silently degrade `processed_data`, which ATS scoring and tailoring both read. `restore_dates_from_markdown` exists precisely because that rebuild is lossy.
- **UI:** shown as a pinned, read-only entry — *"Master résumé — linked, edit in Builder"* — with the same include/exclude toggle as real documents. The toggle is a user preference, not a copy.

If it ever needs to be editable from the career page, that is a deliberate feature with its own spec — not something inherited from a sync bug.

Sources feeding the context block: the live master resume, `career_documents` where `include_in_context`, and (from Phase 3) `career_facts` where `status='approved'`. `ladder_assessments` is output, never input.

---

## Context Assembly

One function, one reader of the corpus:

```python
@dataclass(frozen=True)
class CareerSource:
    """A citable unit of the corpus."""

    source_id: str
    kind: str  # "master_resume" | "document" | "fact"
    title: str


async def build_career_context(
    *,
    include_drafts: bool = False,
    max_chars: int = 120_000,
) -> tuple[str, list[CareerSource], bool]:
    """Render the career corpus as a markdown block for prompt injection.

    Returns (context_markdown, sources, truncated). Facts render first when
    they exist (curated, highest signal); the master resume and documents
    follow as background. Truncation drops documents before facts, oldest
    first, and is logged — a silently truncated corpus reads as a complete one.
    """
```

**Citations are `source_id` + `kind`, not `fact_id`.** This matters: Phase 2 ships before facts exist, so the only citable sources are documents and the master resume. Keeping the citation contract generic means Phase 3 adds `kind="fact"` without changing the `/answer` response shape or the frontend that renders it. One schema, no rewrite.

Rules:

- **Facts before documents**, once facts exist. Facts are curated and short; documents are background.
- **Every source renders with its `source_id`** in the prompt — that is what makes citation and verification possible at all.
- **`max_chars` is a guard, not a strategy.** At the stated corpus size it should never trigger. If it starts triggering regularly, that is the signal to build FTS5 — log it loudly enough to notice, and surface `truncated` through `/context/stats`.
- **Reuse `_sanitize_user_input` from `improver.py`** on all corpus text. The corpus is user-authored, but it now flows into every prompt in the app, which is a wider injection surface than a single resume upload was.

---

## API

All under `/api/v1/career`, registered in `main.py` alongside the existing routers.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/documents` | list (metadata + content preview) |
| `POST` | `/documents` | create from paste (`{title, kind, content}`) |
| `POST` | `/documents/upload` | multipart; extracts via `parse_document` |
| `PATCH` | `/documents/{id}` | edit title/kind/content/`include_in_context` |
| `DELETE` | `/documents/{id}` | |
| `GET` | `/facts` | list, filterable by `type` / `status` |
| `POST` | `/facts` | hand-create |
| `PATCH` | `/facts/{id}` | edit / approve (`status`) |
| `DELETE` | `/facts/{id}` | |
| `POST` | `/documents/{id}/extract` | LLM → draft facts for review. Idempotency: skips near-duplicate bodies against existing facts. |
| `POST` | `/answer` | `{question, tone?, max_words?}` → `{answer, used_sources[], gaps[]}` |
| `POST` | `/ladder/assess` | `{rubric_document_id, current_level?, target_level?}` → assessment |
| `GET` | `/ladder/assessments` | history, newest first — powers the progress timeline |
| `GET` | `/context/stats` | `{source_count, document_count, fact_count, approx_chars, truncated}` — powers the tailor-page indicator |

**`/answer` returns citations, always.** `used_sources` is the verification surface: it is how you confirm the model quoted a real job rather than a plausible one. An answer with empty `used_sources` and non-empty `gaps` is a valid, useful response ("I have no evidence for this — here's what's missing"). Ids the model invents are dropped server-side, never rendered.

---

## Code Style

Match the surrounding code. Concretely, from `routers/applications.py` and `services/improver.py`:

```python
async def answer_career_question(
    question: str,
    *,
    tone: str | None = None,
    max_words: int = 250,
) -> CareerAnswer:
    """Answer an application-form question from the career corpus.

    Grounded: the model may only assert claims traceable to a supplied fact.
    Unsupported claims are returned in ``gaps`` rather than asserted.
    """
    context, sources, _truncated = await build_career_context()
    if not sources:
        raise HTTPException(
            status_code=422, detail="No career material available. Add a document first."
        )

    try:
        data = await complete_json(
            CAREER_ANSWER_PROMPT.format(
                context=context,
                question=_sanitize_user_input(question),
                tone=tone or "professional, first-person, concrete",
                max_words=max_words,
            ),
            schema_type="career_answer",
        )
    except Exception as e:
        logger.error(f"Career answer failed: {e}")
        raise HTTPException(status_code=500, detail="Could not generate an answer. Please try again.")

    # Drop hallucinated citations rather than surfacing ids that resolve to nothing.
    by_id = {s.source_id: s for s in sources}
    used = [by_id[sid] for sid in data.get("used_source_ids", []) if sid in by_id]
    return CareerAnswer(answer=data["answer"], used_sources=used, gaps=data.get("gaps", []))
```

Conventions: type hints on every function (non-negotiable per CLAUDE.md); detailed log server-side + generic client message; `copy.deepcopy()` for mutable defaults; textareas get the `Enter` → `stopPropagation` handler; frontend follows Swiss International Style (`rounded-none`, 1px black borders, hard shadows, `#F0F0E8` canvas, serif headers / sans body / mono metadata).

---

## Testing Strategy

pytest (`unit` / `service` / `integration`) + vitest. Default suites make **no** real network or LLM calls.

| Level | Test |
|---|---|
| unit | `build_career_context` includes every source's `source_id`, honours `include_in_context=false`, renders facts before docs once facts exist, drops docs-before-facts on truncation and sets `truncated` |
| unit | the live master resume appears as a `kind="master_resume"` source; editing the master changes the context on the next call with no sync step |
| unit | injection patterns in document content are redacted before reaching the prompt |
| service | `answer_career_question` with a mocked LLM: fabricated `used_source_ids` are stripped from the response |
| service | extraction on a fixture document yields `status='draft'` facts; re-running does not duplicate |
| integration | full CRUD on documents and facts via httpx ASGI; `PATCH status='approved'` moves a fact into the context block |
| integration | `read_and_extract` rejects a disallowed content type (400), an oversize file (413), and a zero-text extraction (422) — and the existing resume-upload tests still pass after the refactor |
| integration | `/answer` with an empty corpus returns 422, not a hallucinated answer |
| integration | **(Phase 4)** two assessment runs return in newest-first order from `/ladder/assessments` |
| integration | **(Phase 5)** tailoring with a corpus containing a fact absent from the master resume surfaces that fact — and tailoring with an empty corpus produces byte-identical output to today |
| frontend | fact editor round-trips an edit; answer panel renders citations |

The Phase 5 empty-corpus-identical test is the regression guard that keeps this feature from degrading existing tailoring.

---

## Boundaries

**Always:**
- `uv run pytest` + `npm run test` + `npm run lint` + `npm run format` before any commit.
- Type hints on every Python function.
- Log details server-side, return generic messages to clients.
- Every generated career claim traceable to a `fact_id`.
- New behavior covered by a test that fails when the behavior breaks.

**Ask first:**
- Any new Python or npm dependency (the whole point of this design is that there are none).
- Touching `improver.py` / `refiner.py` truthfulness logic (Phase 5 — see Risks).
- Changing existing tables or the `database.py` facade contract.
- Anything that sends corpus content to a service other than the configured LLM provider.

**Never:**
- Add a vector store, embedding model, or second service without the FTS5 step failing first, measurably.
- Commit secrets, or the local `data/*.db`.
- Remove or disable existing tests.
- Modify `.github/workflows/`, CI config, or Docker build behavior.

---

## Risks

**1. Truthfulness guardrail collision — highest risk, Phase 5.** `refiner.py` currently validates tailored output against the **master resume**; `CRITICAL_TRUTHFULNESS_RULES` exists to stop fabrication. Introducing a corpus means legitimately-sourced content will trip that check as if it were invented. Two wrong fixes: loosen the check (fabrication risk goes up, which is the app's stated guardrail — "zero fabricated skills") or leave it (the feature can't work). Correct fix: **the corpus becomes the truth set**, a superset of the master resume, and alignment validates against corpus-derived facts. This must be designed before Phase 5 starts, not during it.

**2. Curation debt.** Facts only help if they exist. LLM extraction produces drafts; if approving them is tedious, the corpus stays empty and every downstream feature degrades to today's behavior. Mitigation: bulk-approve in the UI, and the `/context/stats` indicator on the tailor page so an empty corpus is visible rather than silent.

**3. Prompt-injection surface widens.** Corpus text flows into every LLM call in the app, not just one upload path. Mitigated by routing all corpus text through the existing sanitizer, but worth a second look at Phase 5.

**4. Per-call token cost rises** for tailoring (corpus is added to every call). At ~25k tokens this is acceptable. LiteLLM supports provider prompt caching, which would cut repeat cost substantially — but the app is deliberately multi-provider and caching support is provider-dependent, so treat it as an optimization to measure, not a design assumption.

**5. Scope.** Five phases is a lot. Phases 1–2 are independently useful and ship without touching any existing code path. If momentum dies after Phase 2, the feature is still net-positive. Phases 4–5 are where it gets expensive.

---

## Build Order

Sequenced so the first usable thing ships fastest. Phase 3 comes *after* answering, because at this corpus size `/answer` works fine off raw documents — facts exist to make *tailoring* selection good, which is Phase 5's dependency, not Phase 2's.

| Phase | Deliverable | Touches existing code? | Gate |
|---|---|---|---|
| 1 | `career_documents` + CRUD + upload + Documents UI + `_uploads.py` | Only the `resumes.py` upload refactor | Upload a PDF, see extracted text, edit it; resume upload unchanged |
| 2 | `build_career_context` + `/answer` + Answer UI | No | Paste a real form question, get a grounded answer with citations |
| 3 | `career_facts` + extraction + approve flow + Facts UI | No | Extract from a review doc, approve 5 facts, see context stats change |
| 4 | `/ladder/assess` + history + Ladder UI | No | Paste a real rubric, get per-competency gaps with evidence; two runs form a timeline |
| 5 | Tailoring reads the corpus | **Yes — `improver.py`, `refiner.py`** | Corpus-only achievement appears in tailored output; empty corpus → identical output to today |

Each phase is its own review gate. Phase 5 requires the Risk 1 design settled first.

**Only Phases 1–2 are planned** (`tasks/plan.md`, `tasks/todo.md`). Phases 3–5 remain specified but deliberately unplanned: once there are real documents in the store and real form-question answers to judge, the plan for them will be based on evidence rather than assumption.

---

## Success Criteria

- [ ] A PDF performance review uploads, extracts, and is editable in the UI.
- [ ] Pasting an application-form question returns an answer that cites the sources it used, and fabricated ids never reach the client.
- [ ] With an empty corpus, `/answer` returns 422 — never an ungrounded answer.
- [ ] Editing the master resume in the Builder changes the career context immediately, with no sync action and no duplicated copy.
- [ ] LLM-extracted facts land as `draft` and require explicit approval; re-extraction does not duplicate.
- [ ] A pasted ladder rubric produces per-competency verdicts with evidence and named gaps, and two runs form a visible timeline.
- [ ] Tailoring surfaces a corpus-only achievement for a matching JD.
- [ ] **With an empty corpus, tailoring output is identical to pre-change behavior** (regression guard).
- [ ] Zero new Python or npm dependencies. Zero new services.
- [ ] `uv run pytest`, `npm run test`, `npm run lint` all green.

---

## Decisions Made

- **Master resume: projected live, never copied, no sync.** Two editable copies would need conflict resolution and could corrupt `processed_data` via a lossy re-parse. Not copying removes the problem instead of solving it. *(Reversible — making it editable from the career page is a later, deliberate feature.)*
- **Ladder: progress tracked**, via ordered `ladder_assessments` rows. No separate profile table; the newest row is the current state.
- **Citations: `source_id` + `kind`**, generic from the start, so Phase 3 adds facts without changing the `/answer` contract.
- **Planning scope: Phases 1–2 only.** Phases 3–5 stay specified but unplanned until there is real data in the store.

## Open Questions

1. **Fact granularity for tailoring.** Does `improver.py` receive facts as structured JSON (better selection, harder prompt) or rendered markdown (simpler, reuses the existing prompt shape)? Leaning markdown. — *decide before Phase 5, not now.*
2. **`max_chars: 120_000`** is a guess. Replace it with a measured number once Phase 1 has real documents in it.
3. **Career-page upload cap.** Resumes are capped at 4MB. Career documents should be higher, but how high? Deferred until a real file gets rejected — the 413 message makes the limit obvious when it bites.
