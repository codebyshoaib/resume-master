"""Shared text normalisation for LLM-generated copy.

Extracted from ``career.py`` when a second caller appeared: gap-closing bullets
land in the resume, and ``ats_lint`` flags non-ASCII bullet punctuation as an ATS
parseability problem — so the same typography the career answers strip must be
stripped there too. One table, one function, both callers.
"""

from typing import Any

# Typographic characters models emit freely but web form fields and ATS parsers
# mangle, and which read as machine-written when they survive.
_TYPOGRAPHY = {
    "—": "-",  # em dash
    "–": "-",  # en dash
    "‑": "-",  # non-breaking hyphen
    "‒": "-",  # figure dash
    "‘": "'",
    "’": "'",
    "‚": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    " ": " ",  # non-breaking space
    "​": "",  # zero-width space
}


def plain_ascii(text: str) -> str:
    """Replace typography that breaks paste-into-a-form with ASCII equivalents.

    Only substitutes known offenders; any other non-ASCII (accented names,
    non-Latin scripts for a non-English content language) is left intact.
    """
    for fancy, plain in _TYPOGRAPHY.items():
        text = text.replace(fancy, plain)
    return text


def plain_ascii_deep(value: Any) -> Any:
    """Apply :func:`plain_ascii` to every string inside a nested structure.

    Non-string leaves pass through untouched, so this is safe to run over a whole
    resume dict.
    """
    if isinstance(value, str):
        return plain_ascii(value)
    if isinstance(value, list):
        return [plain_ascii_deep(item) for item in value]
    if isinstance(value, dict):
        return {key: plain_ascii_deep(item) for key, item in value.items()}
    return value
