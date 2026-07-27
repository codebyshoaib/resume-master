"""Pydantic schemas for the career corpus.

See ``docs/specs/career-corpus-spec.md``. Phase 1 covers career documents; the
citation types are shaped for facts to join later without changing the contract.
"""

from enum import Enum

from pydantic import BaseModel, Field


class CareerDocumentKind(str, Enum):
    """What a document is, which drives how the corpus weighs it."""

    resume = "resume"
    review = "review"
    brag = "brag"
    project = "project"
    jd = "jd"
    ladder = "ladder"
    other = "other"


# How much document body the list endpoint returns. The management UI shows a
# snippet per row; the full text is fetched only when a document is opened.
PREVIEW_CHARS = 400


class CareerDocumentCreate(BaseModel):
    """Create a document from pasted text."""

    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    kind: CareerDocumentKind = CareerDocumentKind.other


class CareerDocumentUpdate(BaseModel):
    """Patch a document. Omitted fields are left untouched.

    Every field is optional, so an empty body is a no-op rather than an error —
    but ``title`` and ``content`` reject empty strings when they *are* supplied,
    because clearing them would leave an unusable row.
    """

    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, min_length=1)
    kind: CareerDocumentKind | None = None
    include_in_context: bool | None = None


class CareerDocumentSummary(BaseModel):
    """A document as it appears in the list view (body truncated)."""

    document_id: str
    title: str
    kind: str
    filename: str | None = None
    include_in_context: bool
    preview: str
    char_count: int
    created_at: str
    updated_at: str


class CareerDocumentResponse(CareerDocumentSummary):
    """A single document with its full body."""

    content: str


class CareerDocumentListResponse(BaseModel):
    documents: list[CareerDocumentSummary]


class CareerSourceKind(str, Enum):
    """Where a citable piece of the corpus came from.

    ``master_resume`` is projected live from the ``resumes`` table rather than
    stored in the corpus, so it is a distinct kind rather than a document.
    ``fact`` arrives in Phase 3 and needs no contract change.
    """

    master_resume = "master_resume"
    document = "document"
    fact = "fact"


class CareerSourceRef(BaseModel):
    """A citation the client can resolve back to something the user can read."""

    source_id: str
    kind: CareerSourceKind
    title: str


class CareerContextStats(BaseModel):
    """Corpus size, so an empty corpus is visible rather than silently degrading."""

    source_count: int
    document_count: int
    fact_count: int
    approx_chars: int
    truncated: bool


class CareerAnswerRequest(BaseModel):
    """An application-form question to answer from the corpus."""

    question: str = Field(min_length=1, max_length=4000)
    tone: str | None = Field(default=None, max_length=200)
    max_words: int = Field(default=250, ge=30, le=1000)


class CareerAnswerResponse(BaseModel):
    """A grounded answer plus the evidence behind it.

    ``used_sources`` is the verification surface: it is how the user confirms the
    answer quoted a real job rather than a plausible one. Ids the model invents
    are dropped server-side and never appear here.

    An answer with empty ``used_sources`` and non-empty ``gaps`` is a valid,
    useful response — "I have no evidence for this, here is what's missing".
    """

    answer: str
    used_sources: list[CareerSourceRef]
    gaps: list[str]
    truncated: bool
