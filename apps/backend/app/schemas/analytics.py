"""Pydantic response models for the local analytics summary endpoint."""

from pydantic import BaseModel, Field


class AnalyticsFunnel(BaseModel):
    """Core product funnel: uploads → tailors → downloads."""

    uploads: int = Field(..., description="resume_uploaded event count")
    tailors: int = Field(..., description="tailor_completed event count")
    downloads: int = Field(..., description="resume_pdf_downloaded event count")


class AnalyticsSummaryResponse(BaseModel):
    """Aggregated, PII-free product-analytics summary over an optional window."""

    funnel: AnalyticsFunnel
    event_totals: dict[str, int] = Field(
        default_factory=dict, description="Per-event-name totals in the window"
    )
    total_events: int = Field(..., description="Sum of all event totals in the window")
    days: int | None = Field(
        default=None, description="Day window applied (None = all time)"
    )
