"""Unit tests for the career router's pure helpers.

``_title_from_filename`` is tested here rather than through the upload endpoint
because a filename-less multipart part is not reachable via FastAPI: an empty
``filename`` makes the part a plain form field, which is rejected before the
router runs. Asserting the fallback over HTTP would pass for the wrong reason.
"""

from app.routers.career import _title_from_filename


class TestTitleFromFilename:
    def test_strips_extension(self):
        assert _title_from_filename("2024 review.pdf") == "2024 review"

    def test_strips_directory_components(self):
        assert _title_from_filename("some/path/brag doc.docx") == "brag doc"

    def test_keeps_dots_inside_the_stem(self):
        assert _title_from_filename("q1.2024.notes.txt") == "q1.2024.notes"

    def test_handles_no_extension(self):
        assert _title_from_filename("README") == "README"

    def test_falls_back_when_missing(self):
        # ``title`` is non-nullable and an untitled row is unusable in the list.
        assert _title_from_filename(None) == "Untitled document"
        assert _title_from_filename("") == "Untitled document"

    def test_falls_back_when_stem_is_only_whitespace(self):
        assert _title_from_filename("   .pdf") == "Untitled document"

    def test_falls_back_for_dotfile_with_empty_stem(self):
        assert _title_from_filename(".pdf") == "Untitled document"
