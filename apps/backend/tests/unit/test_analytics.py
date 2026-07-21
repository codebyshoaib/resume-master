"""Unit tests for local-first analytics: the emit_event service + summary DB.

Covers the fire-and-forget contract (writes a row; NEVER propagates a DB error)
and the funnel/window aggregation in ``Database.get_analytics_summary``.
"""

import pytest
from sqlalchemy import select

import app.database as database_module
from app.database import Database
from app.models import AnalyticsEvent
from app.services.analytics import emit_event


@pytest.fixture
async def temp_db(tmp_path, monkeypatch):
    """Real temp-file DB, also installed as the global singleton the service uses."""
    database = Database(db_path=tmp_path / "analytics.db")
    monkeypatch.setattr(database_module, "db", database)
    yield database
    await database.close()


class _BoomDB:
    """Stand-in whose event write always fails."""

    async def record_analytics_event(self, *args, **kwargs) -> None:
        raise RuntimeError("database unavailable")


class TestEmitEvent:
    async def test_writes_a_row(self, temp_db):
        await emit_event("resume_uploaded", {"resume_id": "r1", "size_bytes": 123})

        summary = await temp_db.get_analytics_summary()
        assert summary["event_totals"].get("resume_uploaded") == 1
        assert summary["total_events"] == 1

    async def test_emit_without_properties_writes_empty_dict(self, temp_db):
        await emit_event("tailor_started")

        async with temp_db._session() as session:
            rows = (await session.execute(select(AnalyticsEvent))).scalars().all()
        assert len(rows) == 1
        assert rows[0].properties == {}

    async def test_never_raises_when_db_fails(self, monkeypatch):
        # A failing datastore must be swallowed — emit_event returns None quietly.
        monkeypatch.setattr(database_module, "db", _BoomDB())
        assert await emit_event("tailor_started", {"x": 1}) is None

    async def test_caller_still_succeeds_when_emit_fails(self, monkeypatch):
        monkeypatch.setattr(database_module, "db", _BoomDB())

        async def caller() -> str:
            await emit_event("resume_uploaded", {"resume_id": "r1"})
            return "request-completed"

        assert await caller() == "request-completed"


class TestAnalyticsSummary:
    async def test_funnel_and_totals(self, temp_db):
        for _ in range(3):
            await temp_db.record_analytics_event("resume_uploaded", {})
        for _ in range(2):
            await temp_db.record_analytics_event("tailor_completed", {"delta": 5.0})
        await temp_db.record_analytics_event("resume_pdf_downloaded", {})
        await temp_db.record_analytics_event("tailor_started", {})

        summary = await temp_db.get_analytics_summary()
        assert summary["funnel"] == {"uploads": 3, "tailors": 2, "downloads": 1}
        assert summary["event_totals"]["tailor_started"] == 1
        assert summary["total_events"] == 7
        assert summary["days"] is None

    async def test_empty_db_is_all_zero(self, temp_db):
        summary = await temp_db.get_analytics_summary()
        assert summary["funnel"] == {"uploads": 0, "tailors": 0, "downloads": 0}
        assert summary["total_events"] == 0

    async def test_days_window_excludes_old_events(self, temp_db):
        # Seed one stale event (well outside any window) directly.
        async with temp_db._session() as session:
            session.add(
                AnalyticsEvent(
                    event_name="resume_uploaded",
                    properties={},
                    created_at="2000-01-01T00:00:00+00:00",
                )
            )
            await session.commit()
        await temp_db.record_analytics_event("resume_uploaded", {})  # "now"

        assert (await temp_db.get_analytics_summary())["funnel"]["uploads"] == 2
        windowed = await temp_db.get_analytics_summary(days=7)
        assert windowed["funnel"]["uploads"] == 1
        assert windowed["days"] == 7


class TestTailorCompletedProperties:
    """The tailor_completed prop-builder is evaluated as an argument, outside
    emit_event's swallow boundary — so it must never raise into the request."""

    def test_never_raises_on_bad_response(self):
        import types

        from app.routers.resumes import _tailor_completed_properties

        class _BoomData:
            @property
            def refinement_stats(self):
                raise ValueError("boom")

            @property
            def ats_score(self):
                raise ValueError("boom")

        request = types.SimpleNamespace(resume_id="r1", job_id="j1")
        response = types.SimpleNamespace(data=_BoomData())

        # Must return the base ids without propagating the exception.
        props = _tailor_completed_properties(request, response)
        assert props == {"resume_id": "r1", "job_id": "j1"}
