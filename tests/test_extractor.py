"""Tests for extractor JSON-recovery utilities."""

import pytest

from src.extractor import _extract_first_json_object, _strip_code_fences


# --------------------------------------------------------------------------- #
#  _strip_code_fences                                                         #
# --------------------------------------------------------------------------- #
class TestStripCodeFences:
    def test_plain_json_unchanged(self):
        s = '{"a": 1}'
        assert _strip_code_fences(s) == s

    def test_json_fence(self):
        s = '```json\n{"a": 1}\n```'
        assert _strip_code_fences(s) == '{"a": 1}'

    def test_bare_fence(self):
        s = '```\n{"a": 1}\n```'
        assert _strip_code_fences(s) == '{"a": 1}'

    def test_whitespace_around_fence(self):
        s = '  ```json\n{"a": 1}\n```  '
        assert _strip_code_fences(s) == '{"a": 1}'

    def test_no_closing_fence_unchanged(self):
        s = '```json\n{"a": 1}'
        # no closing fence → returned as-is (stripped)
        result = _strip_code_fences(s)
        assert "```json" in result  # fence not stripped because no closing ```


# --------------------------------------------------------------------------- #
#  _extract_first_json_object                                                 #
# --------------------------------------------------------------------------- #
class TestExtractFirstJsonObject:
    def test_plain_object(self):
        assert _extract_first_json_object('{"a": 1}') == '{"a": 1}'

    def test_object_with_trailing_text(self):
        s = '{"a": 1} some commentary here'
        assert _extract_first_json_object(s) == '{"a": 1}'

    def test_object_with_leading_text(self):
        s = 'Here is the result: {"a": 1}'
        assert _extract_first_json_object(s) == '{"a": 1}'

    def test_nested_objects(self):
        s = '{"a": {"b": 2}, "c": 3}'
        assert _extract_first_json_object(s) == '{"a": {"b": 2}, "c": 3}'

    def test_brace_in_string_value(self):
        s = '{"a": "has { brace"}'
        assert _extract_first_json_object(s) == '{"a": "has { brace"}'

    def test_escaped_quote_in_string(self):
        s = r'{"a": "say \"hi\""}'
        assert _extract_first_json_object(s) == r'{"a": "say \"hi\""}'

    def test_no_json_returns_none(self):
        assert _extract_first_json_object("no json here") is None

    def test_empty_object(self):
        assert _extract_first_json_object("{}") == "{}"

    def test_only_first_object_returned(self):
        s = '{"a": 1} {"b": 2}'
        assert _extract_first_json_object(s) == '{"a": 1}'
