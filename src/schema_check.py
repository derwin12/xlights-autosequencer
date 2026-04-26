"""Generalized stale-cache schema-version handling.

Versioned cache files (analyzer baselines, hierarchy results, library indices,
etc.) bump their ``schema_version`` field whenever the on-disk format changes.
Without a uniform check, each call site reinvents the wheel: some raise
inscrutable mismatch errors, some silently load partial data, some auto-migrate
on the fly. This module standardizes the response.

Three outcomes for any version comparison:

- **match** — caller proceeds with the loaded data.
- **older** — the cached file pre-dates the current code. Caller is expected to
  emit a warning *with a refresh-command hint* and either reject the data
  (return ``None``) or raise (when the data is gating something — e.g. a
  regression baseline). Never silently load partial data.
- **newer** — the cached file was written by a future version of the code.
  Loading it could mean reading fields that don't exist yet, so we raise.
  This is always an error, regardless of caller policy.

The refresh-command hint must be a real CLI command the user can copy-paste
to refresh the cache (e.g. ``xlight-evaluate snapshot-analyzer``). A warning
without a hint is exactly the inscrutable error we're trying to eliminate.
"""
from __future__ import annotations

import sys
from typing import Literal, Optional, Union

VersionStatus = Literal["match", "older", "newer"]


class SchemaFromFutureError(ValueError):
    """Raised when a cache file's schema version is newer than the running code.

    Inherits from ``ValueError`` so existing call sites that catch
    ``ValueError`` on schema-version handling continue to work.
    """


def compare_schema_version(
    loaded_version: Optional[Union[int, str]],
    expected_version: Union[int, str],
) -> VersionStatus:
    """Return ``"match"``, ``"older"``, or ``"newer"`` for a version comparison.

    A missing or ``None`` ``loaded_version`` is treated as older (older code
    that pre-dates the schema_version field at all).

    Versions must be the same type — either both ``int`` or both ``str`` (e.g.
    semver). Mixing types raises ``TypeError`` because comparison semantics are
    ambiguous (e.g. ``int(1) < "2.0.0"`` is meaningless).
    """
    if loaded_version is None:
        return "older"
    if type(loaded_version) is not type(expected_version):
        raise TypeError(
            f"Schema version type mismatch: loaded={type(loaded_version).__name__} "
            f"({loaded_version!r}) vs expected={type(expected_version).__name__} "
            f"({expected_version!r})"
        )
    if loaded_version == expected_version:
        return "match"
    if loaded_version < expected_version:  # type: ignore[operator]
        return "older"
    return "newer"


def stale_cache_warning(
    name: str,
    loaded_version: Optional[Union[int, str]],
    expected_version: Union[int, str],
    refresh_hint: str,
) -> str:
    """Build the canonical stderr warning string for an older-schema cache.

    Centralized so every call site phrases it the same way and always includes
    the refresh command. The ``name`` is a human-readable identifier of the
    cache (e.g. ``"analyzer baseline"``, ``"_hierarchy.json"``) so the user
    knows which file is stale.
    """
    return (
        f"WARNING: {name} schema {loaded_version!r} loaded; "
        f"current code expects {expected_version!r}. "
        f"To refresh, run: {refresh_hint}"
    )


def check_stale_cache(
    loaded_version: Optional[Union[int, str]],
    expected_version: Union[int, str],
    *,
    name: str,
    refresh_hint: str,
    on_older: Literal["warn", "raise"] = "warn",
    stream=None,
) -> VersionStatus:
    """Compare schema versions and act per ``on_older`` policy.

    Args:
        loaded_version: Schema version from the on-disk file (``None`` if absent).
        expected_version: Schema version the current code understands.
        name: Human-readable identifier of the cache, e.g. ``"analyzer baseline"``.
        refresh_hint: Exact CLI command the user can run to refresh the cache.
        on_older: ``"warn"`` emits a stderr message and returns ``"older"`` so the
            caller can decide to reject (return None) or auto-rebuild.
            ``"raise"`` raises ``ValueError`` with the warning text — appropriate
            for gating contexts (regression baselines) where stale data must be
            visible, not silently swapped out.
        stream: Optional file-like object for the warning. Defaults to
            ``sys.stderr``. Used by tests to capture output.

    Returns:
        The ``VersionStatus``. Callers receiving ``"older"`` under ``on_older="warn"``
        must reject the data (return None / start fresh) — never silently load it.

    Raises:
        SchemaFromFutureError: When ``loaded_version > expected_version``.
            Always raised — newer-than-code data is unsafe to load regardless
            of policy.
        ValueError: When ``on_older="raise"`` and the loaded version is older.
        TypeError: When ``loaded_version`` and ``expected_version`` are different
            types (e.g. int vs str).
    """
    status = compare_schema_version(loaded_version, expected_version)
    if status == "match":
        return status
    if status == "newer":
        raise SchemaFromFutureError(
            f"{name} schema {loaded_version!r} is newer than this code "
            f"(expected {expected_version!r}). Update the application before loading."
        )
    # status == "older"
    msg = stale_cache_warning(name, loaded_version, expected_version, refresh_hint)
    if on_older == "raise":
        raise ValueError(msg)
    print(msg, file=stream if stream is not None else sys.stderr)
    return status
