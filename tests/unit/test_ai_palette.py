"""Tests for src.review.ai_palette (local Ollama palette suggestion).

All network calls are mocked — see openspec/changes/theme-ai-palette-suggest
for why suggest_palette() must return None (never raise) on every failure
mode: connection refused, timeout, malformed JSON, wrong item count,
invalid hex format.
"""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

from src.review.ai_palette import suggest_palette

_ARGS = dict(
    title="Believer", artist="Imagine Dragons", genre="rock", occasion="general",
    ollama_host="http://localhost:11434", ollama_model="qwen3:8b",
)


def _mock_response(response_text: str) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"response": response_text}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


class TestSuggestPalette:
    def test_valid_response_returns_uppercased_palette(self) -> None:
        with patch("urllib.request.urlopen", return_value=_mock_response(
            '["#ff6b6b", "#ffd6a8", "#88b04b", "#4ecdc4"]',
        )):
            result = suggest_palette(**_ARGS)
        assert result == ["#FF6B6B", "#FFD6A8", "#88B04B", "#4ECDC4"]

    def test_connection_refused_returns_none(self) -> None:
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            assert suggest_palette(**_ARGS) is None

    def test_timeout_returns_none(self) -> None:
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            assert suggest_palette(**_ARGS) is None

    def test_malformed_outer_json_returns_none(self) -> None:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert suggest_palette(**_ARGS) is None

    def test_malformed_inner_response_json_returns_none(self) -> None:
        with patch("urllib.request.urlopen", return_value=_mock_response("not a json array")):
            assert suggest_palette(**_ARGS) is None

    def test_wrong_item_count_returns_none(self) -> None:
        with patch("urllib.request.urlopen", return_value=_mock_response(
            '["#FF6B6B", "#FFD6A8"]',
        )):
            assert suggest_palette(**_ARGS) is None

    def test_invalid_hex_format_returns_none(self) -> None:
        with patch("urllib.request.urlopen", return_value=_mock_response(
            '["red", "#FFD6A8", "#88B04B", "#4ECDC4"]',
        )):
            assert suggest_palette(**_ARGS) is None

    def test_wrapper_object_instead_of_bare_array_returns_none(self) -> None:
        # Session finding (2026-08-02): format:"json" alone sometimes wraps
        # the array in an object ({"colors": [...]}). The JSON-schema format
        # this module uses should prevent that, but if a future model
        # ignores the schema, a wrapper object must not be silently
        # accepted as a valid palette.
        with patch("urllib.request.urlopen", return_value=_mock_response(
            '{"colors": ["#FF6B6B", "#FFD6A8", "#88B04B", "#4ECDC4"]}',
        )):
            assert suggest_palette(**_ARGS) is None

    def test_missing_response_field_returns_none(self) -> None:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert suggest_palette(**_ARGS) is None
