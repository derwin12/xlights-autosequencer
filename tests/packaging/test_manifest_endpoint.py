"""T075 — /api/v1/manifest returns dev stub in dev, real manifest when bundled."""
from __future__ import annotations

import pytest

from src.review.server import create_app


@pytest.fixture()
def client_dev(tmp_path, monkeypatch):
    monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("XLIGHT_PACKAGED", raising=False)
    app = create_app(testing=True)
    app.config["TESTING"] = True
    yield app.test_client()


def test_dev_mode_returns_stub(client_dev):
    resp = client_dev.get("/api/v1/manifest")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["app_version"] == "dev"
    assert body["is_bundled"] is False


def test_dev_mode_reports_backend_commit_and_start_time(client_dev):
    """The dev stub carries the running checkout's git commit and the
    process start time so the UI can flag a stale backend server."""
    import re
    from datetime import datetime

    body = client_dev.get("/api/v1/manifest").get_json()
    # Tests run from a git checkout, so a commit must resolve.
    assert re.fullmatch(r"[0-9a-f]{7,}(-dirty)?", body["backend_commit"])
    # ISO-8601, parseable.
    datetime.fromisoformat(body["backend_started_at"])


def test_dev_mode_reports_repo_head_commit_for_staleness_check(client_dev):
    """repo_head_commit is read fresh per-request (unlike backend_commit,
    cached once at process start), so the UI can detect when code has
    been committed since this process launched and show a "restart
    needed" warning (user request, 2026-07-18)."""
    import re

    body = client_dev.get("/api/v1/manifest").get_json()
    assert re.fullmatch(r"[0-9a-f]{7,}(-dirty)?", body["repo_head_commit"])


def test_dev_mode_reports_origin_main_commit(client_dev):
    """origin_main_commit lets the UI detect 'haven't pulled yet', distinct
    from repo_head_commit vs backend_commit ('pulled but not restarted').
    Tests run from a real git checkout with a remote, so this should
    resolve to a real short SHA (or None if genuinely offline)."""
    import re

    body = client_dev.get("/api/v1/manifest").get_json()
    assert "origin_main_commit" in body
    if body["origin_main_commit"] is not None:
        assert re.fullmatch(r"[0-9a-f]{7}", body["origin_main_commit"])


def test_origin_main_commit_failure_returns_none_not_error(monkeypatch):
    """A failed `git fetch` (offline, no remote, etc.) must not break the
    manifest endpoint -- it should just omit the value."""
    import subprocess as subprocess_module

    import src.review.api.v1.manifest as manifest_module

    manifest_module._origin_main_commit_cache = None
    manifest_module._origin_ahead_cache = None
    manifest_module._origin_main_checked_at = 0.0

    def _raise(*args, **kwargs):
        raise subprocess_module.SubprocessError("network unreachable")

    monkeypatch.setattr(manifest_module.subprocess, "run", _raise)
    assert manifest_module._origin_main_commit() is None
    assert manifest_module._origin_ahead_of_head() is None


def test_origin_main_commit_is_cached_within_ttl(monkeypatch):
    """The remote check costs a network round-trip -- it must not run on
    every manifest request within the TTL window."""
    import src.review.api.v1.manifest as manifest_module

    manifest_module._origin_main_commit_cache = "abc1234"
    manifest_module._origin_ahead_cache = False
    manifest_module._origin_main_checked_at = manifest_module.time.monotonic()

    call_count = 0

    def _fail_if_called(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise AssertionError("git fetch should not run again within the TTL")

    monkeypatch.setattr(manifest_module.subprocess, "run", _fail_if_called)
    assert manifest_module._origin_main_commit() == "abc1234"
    assert manifest_module._origin_ahead_of_head() is False
    assert call_count == 0


def test_origin_ahead_of_head_true_when_origin_has_new_commits(monkeypatch):
    """`git rev-list --count HEAD..FETCH_HEAD` > 0 means origin/main has
    commits this checkout's HEAD doesn't -- a pull would bring in something new."""
    import subprocess as subprocess_module

    import src.review.api.v1.manifest as manifest_module

    manifest_module._origin_main_commit_cache = None
    manifest_module._origin_ahead_cache = None
    manifest_module._origin_main_checked_at = 0.0

    def _fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "fetch"]:
            return subprocess_module.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--short"]:
            return subprocess_module.CompletedProcess(cmd, 0, stdout="bbb2222\n", stderr="")
        if cmd[:3] == ["git", "rev-list", "--count"]:
            return subprocess_module.CompletedProcess(cmd, 0, stdout="3\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(manifest_module.subprocess, "run", _fake_run)
    assert manifest_module._origin_main_commit() == "bbb2222"
    assert manifest_module._origin_ahead_of_head() is True


def test_origin_ahead_of_head_false_when_head_has_unpushed_commits(monkeypatch):
    """Regression for the false-positive 'update available' banner: HEAD
    committed locally but not yet pushed also produces a different SHA from
    origin/main, but rev-list --count reports 0 commits reachable from
    FETCH_HEAD that aren't already reachable from HEAD, so this must be
    False, not True."""
    import subprocess as subprocess_module

    import src.review.api.v1.manifest as manifest_module

    manifest_module._origin_main_commit_cache = None
    manifest_module._origin_ahead_cache = None
    manifest_module._origin_main_checked_at = 0.0

    def _fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "fetch"]:
            return subprocess_module.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--short"]:
            return subprocess_module.CompletedProcess(cmd, 0, stdout="aaa1111\n", stderr="")
        if cmd[:3] == ["git", "rev-list", "--count"]:
            return subprocess_module.CompletedProcess(cmd, 0, stdout="0\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(manifest_module.subprocess, "run", _fake_run)
    assert manifest_module._origin_main_commit() == "aaa1111"
    assert manifest_module._origin_ahead_of_head() is False


def test_origin_ahead_of_head_false_when_commits_are_equal(monkeypatch):
    """origin/main and HEAD pointing at the same commit must not be reported
    as 'origin ahead' -- 0 commits reachable from FETCH_HEAD that aren't
    already reachable from HEAD."""
    import subprocess as subprocess_module

    import src.review.api.v1.manifest as manifest_module

    manifest_module._origin_main_commit_cache = None
    manifest_module._origin_ahead_cache = None
    manifest_module._origin_main_checked_at = 0.0

    def _fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "fetch"]:
            return subprocess_module.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--short"]:
            return subprocess_module.CompletedProcess(cmd, 0, stdout="ccc3333\n", stderr="")
        if cmd[:3] == ["git", "rev-list", "--count"]:
            return subprocess_module.CompletedProcess(cmd, 0, stdout="0\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(manifest_module.subprocess, "run", _fake_run)
    assert manifest_module._origin_main_commit() == "ccc3333"
    assert manifest_module._origin_ahead_of_head() is False


def test_bundled_stub_when_manifest_file_absent(monkeypatch, tmp_path):
    # Simulate bundled mode but without the manifest file on disk — the
    # endpoint must fall back to the dev stub (shape-compatible) rather
    # than crashing.
    monkeypatch.setenv("XLIGHT_PACKAGED", "1")
    monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
    app = create_app(testing=True)
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.get("/api/v1/manifest")
        assert resp.status_code == 200
        body = resp.get_json()
        # sys._MEIPASS not set in this test env → get_manifest() returns None → stub path.
        assert body["app_version"] == "dev"
