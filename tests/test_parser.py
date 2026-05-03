"""Tests for parser utilities."""

import pytest

from src.parser import truncate_for_context


class TestTruncateForContext:
    def test_short_text_unchanged(self):
        text = "short text"
        assert truncate_for_context(text, max_chars=100) == text

    def test_exactly_at_limit_unchanged(self):
        text = "a" * 12000
        assert truncate_for_context(text) == text

    def test_long_text_truncated(self):
        text = "a" * 13000
        result = truncate_for_context(text)
        assert "[...TRUNCATED FOR CONTEXT WINDOW...]" in result
        assert len(result) < 13000

    def test_cuts_at_newline_boundary(self):
        # Build text where a newline lands just before the cut point
        prefix = "line one\n"
        filler = "x" * (12000 - 200 - len(prefix) + 5)  # filler pushes past cut
        text = prefix + filler + "\n" + "z" * 500
        result = truncate_for_context(text)
        # The marker should appear and the result should not split mid-word
        assert "[...TRUNCATED FOR CONTEXT WINDOW...]" in result
        content = result.split("\n\n[...TRUNCATED")[0]
        assert not content.endswith("x" * 500)  # didn't cut in the middle of filler run

    def test_cuts_at_word_boundary_when_no_newline(self):
        # Single long line with spaces
        words = ("hello " * 3000).rstrip()
        result = truncate_for_context(words)
        content = result.split("\n\n[...TRUNCATED")[0]
        # Should end at a space boundary — last char before marker should be 'o'
        assert content[-1] == "o"  # last char of "hello"

    def test_custom_max_chars(self):
        text = "word " * 1000
        result = truncate_for_context(text, max_chars=500)
        assert len(result) < 700  # well under original
        assert "[...TRUNCATED FOR CONTEXT WINDOW...]" in result
