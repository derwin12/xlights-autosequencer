"""CLI entry point for xlight-analyze.

This package splits the CLI into submodules by command group.  The ``cli``
Click group is defined here and each submodule registers its commands by
importing this group.  All submodules are imported at the bottom of this
file so that commands are registered before ``cli`` is invoked.

``src.cli:cli`` remains the entry-point callable.
"""
from __future__ import annotations

import sys

import click


@click.group()
def cli() -> None:
    """xlight-analyze — generate xLights timing tracks from audio."""


def main() -> None:
    # Windows defaults stdout/stderr to cp1252 unless the console is UTF-8,
    # which crashes on unicode glyphs (✓/✗) used throughout CLI output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    cli()


# Import submodules to register commands on ``cli``.
# Core modules that have been fully extracted:
from src.cli import (  # noqa: E402, F401
    analyze,
    library,
    review,
    scoring,
)

# Remaining commands imported from the legacy monolith.  Imported AFTER
# ``library`` so that extras' "skip if already registered" rule keeps the
# legacy top-level ``library`` command from clobbering the new group.
from src.cli import extras  # noqa: E402, F401

# Re-export variant test-support overrides so that
# ``import src.cli as cli_module; cli_module._variant_library_override``
# keeps working for existing tests.
try:
    from src.cli_old import (  # noqa: E402, F401
        _variant_library_override,
        _variant_effect_library_override,
        _variant_custom_dir_override,
    )
except ImportError:
    _variant_library_override = None
    _variant_effect_library_override = None
    _variant_custom_dir_override = None
