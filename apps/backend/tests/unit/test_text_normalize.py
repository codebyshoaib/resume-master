"""Typography normalisation shared by career answers and gap-closing bullets.

The concrete bug: a gap-closing bullet came back as "Self‑studied C# and
ASP.NET" with a non-breaking hyphen, which ``ats_lint`` flags as non-ASCII bullet
punctuation. Prompt rules do not enforce this, so the normaliser does.
"""

from app.services.text_normalize import plain_ascii, plain_ascii_deep


class TestPlainAscii:
    def test_replaces_non_breaking_hyphen(self):
        assert plain_ascii("Self‑studied C#") == "Self-studied C#"

    def test_replaces_dashes_quotes_and_ellipsis(self):
        assert plain_ascii("a—b–c") == "a-b-c"
        assert plain_ascii("‘x’ “y”") == "'x' \"y\""
        assert plain_ascii("wait…") == "wait..."

    def test_replaces_invisible_whitespace(self):
        assert plain_ascii("a b") == "a b"
        assert plain_ascii("a​b") == "ab"

    def test_leaves_legitimate_non_ascii_intact(self):
        """Accented names and non-Latin scripts must survive for other locales."""
        assert plain_ascii("Björn") == "Björn"
        assert plain_ascii("求聘") == "求聘"

    def test_ascii_passes_through_unchanged(self):
        assert plain_ascii("plain text - already fine") == "plain text - already fine"


class TestPlainAsciiDeep:
    def test_normalizes_strings_nested_in_a_diff_payload(self):
        payload = {
            "changes": [
                {
                    "path": "workExperience[0].description",
                    "value": "Self‑studied ASP.NET",
                    "reason": "closes the gap — suggested addition",
                    "original": None,
                }
            ],
            "strategy_notes": "used “quotes”",
        }
        cleaned = plain_ascii_deep(payload)
        assert cleaned["changes"][0]["value"] == "Self-studied ASP.NET"
        assert cleaned["changes"][0]["reason"] == "closes the gap - suggested addition"
        assert cleaned["strategy_notes"] == 'used "quotes"'

    def test_preserves_non_string_leaves(self):
        assert plain_ascii_deep({"a": None, "b": 3, "c": True, "d": ["x—y"]}) == {
            "a": None,
            "b": 3,
            "c": True,
            "d": ["x-y"],
        }
