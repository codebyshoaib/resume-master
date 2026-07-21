"""Local-first product analytics (self-hosted only — no external dependency).

``emit_event`` is **fire-and-forget**: it records a lightweight, PII-free event
for product visibility and must NEVER raise or break the request that triggered
it. All datastore work is wrapped in try/except and log-and-swallowed on failure.

Privacy invariant: events carry ids and numeric metrics ONLY — never resume
content, names, emails, or job-description text. Everything stays in the local
SQLite database; nothing leaves the machine.
"""

import logging
from typing import Any

import app.database as _database

logger = logging.getLogger(__name__)


async def emit_event(name: str, properties: dict[str, Any] | None = None) -> None:
    """Record a product-analytics event; never raises.

    Resolves the global ``db`` at call time (via the module) so test harnesses
    that swap the singleton are honoured. Any failure is logged and swallowed —
    analytics is never allowed to break the calling request.
    """
    try:
        await _database.db.record_analytics_event(name, properties or {})
    except Exception as e:  # noqa: BLE001 - analytics must never break a request
        # ponytail: log-and-swallow by design; visibility is best-effort.
        logger.warning("Failed to emit analytics event %r: %s", name, e)
