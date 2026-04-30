"""Tests for ``_PROP_TYPE_TOKENS`` extension (§1.5 of OpenSpec
``visual-quality-microscope``).

Two new tokens (``radial`` and ``vertical``) were added to align the
inference vocabulary with the catalog's
``{matrix, outline, arch, vertical, tree, radial}``. The change is
purely additive: every model name that resolved to a specific prop
type before the change must resolve to the same type after.
"""
from __future__ import annotations

from src.evaluation.xsq_reader import _infer_prop_type


# ── New tokens ─────────────────────────────────────────────────────────────

def test_radial_spinner_infers_radial() -> None:
    assert _infer_prop_type("RadialSpinner") == "radial"


def test_radial_burst_infers_radial() -> None:
    assert _infer_prop_type("RadialBurst") == "radial"


def test_vertical_left_line_infers_vertical() -> None:
    assert _infer_prop_type("VerticalLeftLine") == "vertical"


def test_outline_roof_left_infers_outline() -> None:
    assert _infer_prop_type("OutlineRoofLeft") == "outline"


# ── Existing matches must still resolve ────────────────────────────────────

def test_matrix_center_still_infers_matrix() -> None:
    assert _infer_prop_type("MatrixCenter") == "matrix"


def test_mega_tree_still_infers_tree() -> None:
    """Pre-existing behaviour: ``MegaTree`` matches ``tree`` first
    because ``tree`` precedes ``mega`` in the token list. The
    additive change must NOT alter this — reordering is out of scope."""
    assert _infer_prop_type("MegaTree") == "tree"


def test_arch_left_still_infers_arch() -> None:
    assert _infer_prop_type("ArchLeft") == "arch"


def test_tree_left_still_infers_tree() -> None:
    assert _infer_prop_type("TreeLeft") == "tree"


def test_unknown_model_still_returns_unknown() -> None:
    assert _infer_prop_type("WhateverThing") == "Unknown"
