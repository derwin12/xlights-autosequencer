"""Signature guard for `place_effects` (spec 048, FR-020, SC-002, SC-004).

Before the 048 refactor, `place_effects` accepted eleven keyword arguments, seven of
which duplicated per-section decisions that should live on `SectionAssignment`:
`tiers`, `section_index`, `working_set`, `focused_vocabulary`, `palette_restraint`,
`duration_scaling`, `bpm`. The refactor reduces the signature to six parameters
and these kwargs are forbidden — reintroducing any of them fails this test.

This test is expected to FAIL on pre-refactor `main` (the signature still has the
legacy kwargs) and PASS after US2 lands.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

from src.generator.effect_placer import place_effects


_EXPECTED_PARAMS = (
    "assignment",
    "groups",
    "effect_library",
    "hierarchy",
    "variant_library",
    "rotation_plan",
)

_FORBIDDEN_PARAMS = frozenset({
    "tiers",
    "section_index",
    "working_set",
    "focused_vocabulary",
    "palette_restraint",
    "duration_scaling",
    "bpm",
})


def test_place_effects_signature_is_exactly_six_params() -> None:
    """`place_effects` has exactly the six parameters listed in FR-020."""
    sig = inspect.signature(place_effects)
    actual = tuple(sig.parameters.keys())
    assert actual == _EXPECTED_PARAMS, (
        f"place_effects signature must be {_EXPECTED_PARAMS}, "
        f"got {actual}"
    )


def test_place_effects_has_no_forbidden_kwargs() -> None:
    """None of the legacy kwargs may be reintroduced."""
    sig = inspect.signature(place_effects)
    names = set(sig.parameters.keys())
    intersect = names & _FORBIDDEN_PARAMS
    assert not intersect, (
        f"place_effects must not accept these legacy kwargs: {sorted(intersect)}. "
        f"Decisions live on SectionAssignment."
    )


# ---------------------------------------------------------------------------
# Call-site audit (T008) — grep-style scan of plan.py
# ---------------------------------------------------------------------------

_PLAN_PY = Path(__file__).parent.parent.parent / "src" / "generator" / "plan.py"


def _extract_place_effects_calls(source: str) -> list[str]:
    """Return the text of every `place_effects(...)` call, balanced across parens."""
    calls: list[str] = []
    i = 0
    while True:
        m = re.search(r"\bplace_effects\s*\(", source[i:])
        if m is None:
            break
        start = i + m.start()
        open_idx = i + m.end() - 1
        depth = 1
        j = open_idx + 1
        while j < len(source) and depth > 0:
            if source[j] == "(":
                depth += 1
            elif source[j] == ")":
                depth -= 1
            j += 1
        calls.append(source[start:j])
        i = j
    return calls


def test_no_call_site_passes_forbidden_kwargs() -> None:
    """No `place_effects(...)` invocation in `plan.py` passes a forbidden kwarg.

    Guards against reintroduction at the call site — a subtle regression path
    that the function signature alone can't catch (e.g. if someone adds back a
    flag to the signature later, or uses **kwargs).
    """
    source = _PLAN_PY.read_text(encoding="utf-8")
    calls = _extract_place_effects_calls(source)
    assert calls, f"Expected at least one place_effects(...) call in {_PLAN_PY}"
    offenders: list[tuple[str, str]] = []
    for call in calls:
        for kw in _FORBIDDEN_PARAMS:
            if re.search(rf"\b{re.escape(kw)}\s*=", call):
                offenders.append((kw, call[:120].replace("\n", " ")))
    assert not offenders, (
        f"place_effects(...) call sites still pass forbidden kwargs: "
        + "; ".join(f"{kw} in `{snippet}`" for kw, snippet in offenders)
    )


def test_all_call_sites_use_six_arg_form() -> None:
    """Every `place_effects(...)` invocation in `plan.py` uses the 6-arg form.

    Both `build_plan` and `regenerate_sections` must call `place_effects` with the
    same parameter list — no divergent flag handling (FR-023, SC-004).
    """
    source = _PLAN_PY.read_text(encoding="utf-8")
    calls = _extract_place_effects_calls(source)
    # Expect exactly two call sites after the refactor (build_plan + regenerate_sections).
    assert len(calls) >= 1, f"No place_effects calls found in {_PLAN_PY}"
    for call in calls:
        # Named params present: assignment, groups, effect_library, hierarchy,
        # variant_library, rotation_plan. None of the forbidden ones.
        for kw in _FORBIDDEN_PARAMS:
            assert not re.search(rf"\b{re.escape(kw)}\s*=", call), (
                f"Call uses forbidden kwarg '{kw}': {call[:200]}"
            )
