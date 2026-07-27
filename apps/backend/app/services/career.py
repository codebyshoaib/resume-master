"""Career corpus assembly and grounded question answering.

Phase 2 of ``docs/specs/career-corpus-spec.md``.

The whole corpus is passed to the model in one prompt — there is no retrieval
layer, deliberately. At the target size (under ~50 pages) retrieval solves no
problem, and top-k retrieval would actively hurt: selecting which achievements
fit a question needs *breadth*, whereas retrieval optimises for precision on a
narrow query and would silently drop the one relevant item.

If ``truncated`` starts coming back true in normal use, that is the signal to
add SQLite FTS5 — not a reason to raise ``max_chars`` indefinitely.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config_cache import get_content_language
from app.database import db
from app.llm import complete_json
from app.prompts import get_language_name
from app.prompts.career import build_career_answer_prompt

# The corpus now flows into every prompt that reads it, which is a wider
# injection surface than a single resume upload was. Reusing the tailoring
# pipeline's sanitiser rather than writing a second one that can drift.
from app.services.improver import _sanitize_user_input as sanitize_user_input
from app.services.text_normalize import plain_ascii

logger = logging.getLogger(__name__)

# Budget guard, not a retrieval strategy. Should never fire at the corpus size
# this feature targets; see the module docstring for what it means if it does.
DEFAULT_MAX_CHARS = 120_000


@dataclass(frozen=True)
class CareerSource:
    """A citable unit of the corpus.

    ``source_id`` is what the model must cite and what the client resolves back
    to something the user can read.

    ``kind`` is the *source type* — ``master_resume`` | ``document`` | ``fact``
    (the last from Phase 3) — which is what the client needs to resolve a
    citation. It is deliberately **not** the document's own kind: ``review`` /
    ``brag`` / ``ladder`` is a separate taxonomy and lives in ``detail``.
    Conflating the two makes citations unresolvable.
    """

    source_id: str
    kind: str
    title: str
    detail: str | None = None


def _master_resume_text(resume: dict[str, Any]) -> str:
    """Render the master resume as prompt text.

    Prefers ``processed_data`` because it reflects the *current* resume: the
    builder overwrites ``content`` with JSON on save, and ``original_markdown``
    is a snapshot of the original upload, so both can lag behind edits.
    """
    processed = resume.get("processed_data")
    if processed:
        return json.dumps(processed, ensure_ascii=False)
    content = resume.get("content") or ""
    if content.strip():
        return content
    return resume.get("original_markdown") or ""


# The answer gets pasted into someone else's textarea, so typography models emit
# freely is normalised before it ever reaches the client. The table is shared with
# the gap-closing path, which writes into the resume itself (see text_normalize).
_plain_ascii = plain_ascii


def _render(source: CareerSource, body: str) -> str:
    """Render one source as a citable prompt block.

    ``detail`` (the document's own kind) is included because it tells the model
    how much weight the source carries — a performance review is stronger
    evidence than a loose note.
    """
    label = source.detail or source.kind
    return f"### SOURCE {source.source_id} — {source.title} ({label})\n{body.strip()}\n"


async def build_career_context(
    *, max_chars: int = DEFAULT_MAX_CHARS
) -> tuple[str, list[CareerSource], bool]:
    """Assemble the career corpus into one markdown block for prompt injection.

    Returns ``(context_markdown, sources, truncated)``.

    The master resume is read **live** from the ``resumes`` table and rendered as
    a virtual source; it is never copied into the corpus, so there is nothing to
    keep in sync. Documents the user has muted are excluded.

    Truncation drops documents oldest-first and never the master resume, and is
    logged — a silently truncated corpus reads as a complete one.
    """
    blocks: list[str] = []
    sources: list[CareerSource] = []
    used = 0
    truncated = False

    master = await db.get_master_resume()
    if master:
        text = _master_resume_text(master)
        if text.strip():
            source = CareerSource(
                source_id=master["resume_id"], kind="master_resume", title="Master resume"
            )
            block = _render(source, sanitize_user_input(text))
            blocks.append(block)
            sources.append(source)
            used += len(block)

    documents = await db.list_career_documents(included_only=True)
    for doc in documents:
        body = (doc.get("content") or "").strip()
        if not body:
            continue
        source = CareerSource(
            source_id=doc["document_id"],
            kind="document",
            title=doc["title"],
            detail=doc["kind"],
        )
        block = _render(source, sanitize_user_input(body))
        if used + len(block) > max_chars:
            truncated = True
            logger.warning(
                "Career context truncated at %d/%d chars; dropping %r and any later "
                "documents. Consider adding FTS5 retrieval.",
                used,
                max_chars,
                doc["title"],
            )
            break
        blocks.append(block)
        sources.append(source)
        used += len(block)

    return "\n".join(blocks), sources, truncated


async def context_stats(*, max_chars: int = DEFAULT_MAX_CHARS) -> dict[str, Any]:
    """Corpus size, so an empty corpus is visible rather than silently degrading."""
    context, sources, truncated = await build_career_context(max_chars=max_chars)
    return {
        "source_count": len(sources),
        "document_count": sum(1 for s in sources if s.kind == "document"),
        # Facts arrive in Phase 3; reported now so the client contract is stable.
        "fact_count": 0,
        "approx_chars": len(context),
        "truncated": truncated,
    }


async def answer_career_question(
    question: str,
    *,
    tone: str | None = None,
    max_words: int = 250,
) -> dict[str, Any]:
    """Answer an application-form question from the career corpus.

    Grounded: the model may only assert claims traceable to a supplied source.
    Anything it cannot support belongs in ``gaps`` rather than in the answer.

    Returns ``{"answer", "used_sources", "gaps", "truncated"}``.

    Raises:
        ValueError: when the corpus is empty. An ungrounded answer would be
            worse than no answer, so this is not something to paper over with a
            generic response.
    """
    context, sources, truncated = await build_career_context()
    if not sources:
        raise ValueError("empty_corpus")

    prompt = build_career_answer_prompt(
        context=context,
        question=sanitize_user_input(question),
        tone=tone or "direct, first-person, specific; the way you would talk, not write",
        max_words=max_words,
        output_language=get_language_name(get_content_language()),
    )
    data = await complete_json(prompt, schema_type="career_answer", max_tokens=2048)

    answer = _plain_ascii(str(data.get("answer") or "").strip())
    if not answer:
        raise RuntimeError("model returned no answer text")

    # Drop citations the model invented. An id that resolves to nothing is worse
    # than no citation at all, because it looks verified.
    by_id = {s.source_id: s for s in sources}
    raw_ids = data.get("used_source_ids") or []
    seen: set[str] = set()
    used_sources: list[dict[str, str]] = []
    for raw in raw_ids:
        source_id = str(raw)
        if source_id in by_id and source_id not in seen:
            seen.add(source_id)
            source = by_id[source_id]
            used_sources.append(
                {"source_id": source.source_id, "kind": source.kind, "title": source.title}
            )
    dropped = len(raw_ids) - len(used_sources)
    if dropped > 0:
        logger.warning("Dropped %d unresolvable citation(s) from a career answer", dropped)

    gaps = [str(g) for g in (data.get("gaps") or []) if str(g).strip()]
    return {
        "answer": answer,
        "used_sources": used_sources,
        "gaps": gaps,
        "truncated": truncated,
    }
