"""Entry point used by PyInstaller when the backend runs as a Tauri sidecar.

Binds Flask to an OS-chosen free port on 127.0.0.1, prints the port to
stdout for the Rust launcher to read (see contracts/sidecar-handshake.md),
then starts the existing Flask app.

This module is deliberately thin — all application logic still lives in
`src.review.server.create_app()`. Dev mode continues to use the existing
`src.review.cli` entry and binds to a fixed port as before.
"""
from __future__ import annotations

import argparse
import importlib
import socket
import sys

from src.review.server import create_app


HANDSHAKE_PREFIX = "XLIGHT_BACKEND_PORT="


def _pick_free_port() -> int:
    """Bind/release a socket on 127.0.0.1:0 to get an OS-assigned port.

    A small race window exists between release and Flask's rebind; on
    localhost it is in practice nil, and no production deployment uses
    this entry point — only local sidecars do.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _self_test() -> int:
    """Import every module that must survive PyInstaller bundling.

    Used by `tests/packaging/test_bundle_imports.py` to verify the
    onedir bundle contains every runtime dependency.
    """
    modules = [
        "numpy",
        "scipy",
        "soundfile",
        "librosa",
        "flask",
        "src.analyzer.audio",
        "src.analyzer.runner",
        "src.analyzer.stems",
        "src.analyzer.capabilities",
        "src.review.server",
        "src.packaging.bundled_mode",
        "src.packaging.stems_paths",
        "src.packaging.models_paths",
    ]
    optional_modules = [
        "madmom",
        "madmom.ml.nn.layers",
        "madmom.audio.comb_filters",
        "vamp",
        "demucs",
        "demucs.pretrained",
        "torch",
    ]

    failed: list[tuple[str, str]] = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as exc:  # pragma: no cover - diagnostic only
            failed.append((name, repr(exc)))

    from src.analyzer.capabilities import patch_madmom_compat
    patch_madmom_compat()

    optional_missing: list[tuple[str, str]] = []
    for name in optional_modules:
        try:
            importlib.import_module(name)
        except Exception as exc:
            optional_missing.append((name, repr(exc)))

    if failed:
        print("SELF-TEST FAILED:", file=sys.stderr)
        for name, err in failed:
            print(f"  {name}: {err}", file=sys.stderr)
        return 1

    if optional_missing:
        print("SELF-TEST optional modules missing (non-fatal):", file=sys.stderr)
        for name, err in optional_missing:
            print(f"  {name}: {err}", file=sys.stderr)

    print("SELF-TEST OK")
    return 0


def _force_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 regardless of the OS locale.

    PYTHONIOENCODING=utf-8 (set by the Rust launcher when spawning this
    sidecar) does not reliably apply to a PyInstaller-frozen executable's
    piped stdout/stderr -- confirmed live: the analyzer's checkmark/x-mark
    capability status line (src/analyzer/orchestrator.py) still crashed
    with UnicodeEncodeError under the Windows cp1252 codec even with that
    env var set. Reconfigure directly in-process instead, which is not
    subject to whatever bootloader-level stream setup ignores the env var.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def main() -> int:
    _force_utf8_streams()

    parser = argparse.ArgumentParser(prog="xlight-backend")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Import every required module and exit 0/1. Used for bundle verification.",
    )
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    port = _pick_free_port()
    # Hand the port off to the Tauri launcher before anything else can
    # flood stdout. PYTHONUNBUFFERED=1 is set by the launcher so this
    # flush is immediate; we still flush explicitly for safety.
    print(f"{HANDSHAKE_PREFIX}{port}", flush=True)

    app = create_app()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
