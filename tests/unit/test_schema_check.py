"""Unit tests for src/schema_check.py — generalized stale-cache helper."""
from __future__ import annotations

import io
import json

import pytest

from src.schema_check import (
    SchemaFromFutureError,
    check_stale_cache,
    compare_schema_version,
    stale_cache_warning,
)


# ---------------------------------------------------------------------------
# compare_schema_version
# ---------------------------------------------------------------------------

def test_compare_match_int() -> None:
    assert compare_schema_version(2, 2) == "match"


def test_compare_older_int() -> None:
    assert compare_schema_version(1, 2) == "older"


def test_compare_newer_int() -> None:
    assert compare_schema_version(3, 2) == "newer"


def test_compare_match_string_semver() -> None:
    assert compare_schema_version("1.0.0", "1.0.0") == "match"


def test_compare_missing_version_is_older() -> None:
    """A None version (field absent) is treated as older than any expected version."""
    assert compare_schema_version(None, 1) == "older"


def test_compare_type_mismatch_raises() -> None:
    with pytest.raises(TypeError, match="type mismatch"):
        compare_schema_version(1, "2.0.0")


# ---------------------------------------------------------------------------
# stale_cache_warning — message format
# ---------------------------------------------------------------------------

def test_warning_includes_refresh_hint() -> None:
    msg = stale_cache_warning("widget cache", 1, 2, "do-the-thing")
    assert "widget cache" in msg
    assert "1" in msg and "2" in msg
    assert "do-the-thing" in msg
    assert msg.startswith("WARNING:")


# ---------------------------------------------------------------------------
# check_stale_cache — three paths
# ---------------------------------------------------------------------------

def test_check_match_returns_match() -> None:
    """On version match the helper returns 'match' and emits nothing."""
    stream = io.StringIO()
    status = check_stale_cache(
        2, 2, name="thing", refresh_hint="run-cmd", stream=stream
    )
    assert status == "match"
    assert stream.getvalue() == ""


def test_check_older_warns_to_stream() -> None:
    """on_older='warn' writes to stderr (or supplied stream) with refresh hint."""
    stream = io.StringIO()
    status = check_stale_cache(
        1, 2,
        name="widget cache",
        refresh_hint="xlight-refresh widgets",
        on_older="warn",
        stream=stream,
    )
    assert status == "older"
    output = stream.getvalue()
    assert "WARNING" in output
    assert "widget cache" in output
    assert "xlight-refresh widgets" in output


def test_check_older_raise_mode() -> None:
    """on_older='raise' raises ValueError with the refresh hint in the message."""
    with pytest.raises(ValueError, match="xlight-refresh widgets"):
        check_stale_cache(
            1, 2,
            name="widget cache",
            refresh_hint="xlight-refresh widgets",
            on_older="raise",
        )


def test_check_newer_always_raises() -> None:
    """A schema_version greater than expected is always an error."""
    with pytest.raises(SchemaFromFutureError, match="newer than this code"):
        check_stale_cache(
            5, 2,
            name="widget cache",
            refresh_hint="upgrade-app",
            on_older="warn",  # irrelevant for newer-version path
        )


def test_schema_from_future_is_value_error() -> None:
    """SchemaFromFutureError must inherit from ValueError so existing
    ValueError-catching callers continue to work."""
    assert issubclass(SchemaFromFutureError, ValueError)


def test_check_newer_raises_in_raise_mode_too() -> None:
    """Even when on_older='raise', newer-version still raises the future-data error."""
    with pytest.raises(SchemaFromFutureError):
        check_stale_cache(
            5, 2,
            name="thing",
            refresh_hint="upgrade",
            on_older="raise",
        )


# ---------------------------------------------------------------------------
# Integration: existing analyzer-baseline path still raises ValueError
# (so snapshot_analyzer's catch-and-rebuild logic keeps working)
# ---------------------------------------------------------------------------

def test_analyzer_baseline_load_older_raises_value_error(tmp_path) -> None:
    """Loading an older-schema baseline must raise ValueError so the existing
    snapshot_analyzer catch-and-rebuild path in src/cli/evaluate.py still
    triggers the auto-rebuild."""
    from src.evaluation.analyzer_baseline import load, SCHEMA_VERSION

    # Build an older-schema baseline file.
    path = tmp_path / "old_baseline.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION - 1, "fixtures": {}}))

    with pytest.raises(ValueError) as exc_info:
        load(path)

    # The new helper-driven message must contain the refresh command.
    assert "snapshot-analyzer" in str(exc_info.value)


def test_analyzer_baseline_load_newer_raises_future_error(tmp_path) -> None:
    """Newer-than-code baseline raises SchemaFromFutureError (a ValueError subclass)."""
    from src.evaluation.analyzer_baseline import load, SCHEMA_VERSION

    path = tmp_path / "future_baseline.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION + 1, "fixtures": {}}))

    with pytest.raises(SchemaFromFutureError):
        load(path)


def test_generator_baseline_older_raises_typed_schema_error(tmp_path) -> None:
    """src/evaluation/baseline.py preserves its typed BaselineSchemaError so
    callers that catch the typed exception keep working."""
    from src.evaluation.baseline import (
        BaselineSchemaError,
        SCHEMA_VERSION,
        load_baseline,
    )

    path = tmp_path / "old.json"
    path.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION + 100,  # newer-than-code path
        "generator_commit": "x",
        "generated_at": "2026-01-01T00:00:00Z",
        "entries": {},
    }))

    with pytest.raises(BaselineSchemaError):
        load_baseline(path)
