"""Local product-analytics endpoints (self-hosted, PII-free)."""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.database import db
from app.schemas import AnalyticsSummaryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def analytics_summary(
    days: int | None = Query(
        None, ge=1, le=3650, description="Restrict to the last N days (default: all time)"
    ),
) -> AnalyticsSummaryResponse:
    """Return funnel counts (uploads → tailors → downloads) + per-event totals."""
    try:
        summary = await db.get_analytics_summary(days=days)
    except Exception as e:
        logger.error("Failed to load analytics summary: %s", e)
        raise HTTPException(
            status_code=500, detail="Failed to load analytics. Please try again."
        )
    return AnalyticsSummaryResponse(**summary)
