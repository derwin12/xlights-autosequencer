#!/usr/bin/env python3
"""Pre-review for the tier-layering-policy iteration loop.

Diffs a baseline `.xsq` against a treatment `.xsq` and emits a markdown
report covering:

  * One-line verdict (PASS / FAIL — reason)
  * Per-tier placement counts (baseline vs treatment, delta)
  * Distinct base effects used per tier (treatment)
  * Tier-1 sanity check — flags placements using base effects commonly
    associated with bold output (Color Wash, Bars, Single Strand,
    Marquee). These can be valid background variants if parameters are
    tuned, but a *high* count of them on tier 1 means the affinity
    routing didn't bias toward background-tagged variants.

The pre-review is informational. It always exits 0; the reader decides
whether to do a visual review based on the verdict line. See
``openspec/changes/tier-layering-policy/design.md`` for the iteration
plan that uses this.

Usage:
    python3 scripts/pre_review_tier_layering.py \\
        ~/xlights/Cher__baseline.xsq \\
        ~/xlights/Cher__treatment.xsq \\
        > treatment-notes-Cher.md
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


# Base effects commonly associated with bold output. Not a hard
# filter — the variant library has background-tagged variants of
# Color Wash and Bars — but a high tier-1 count of these effects
# is a signal that the affinity routing isn't doing its job.
_BOLD_BASE_EFFECTS: frozenset[str] = frozenset({
    "Color Wash", "Bars", "Single Strand", "Marquee", "Strobe", "On",
})

# Tiers we expect treatment to populate that baseline doesn't.
# Source of truth: the design.md mood→active-tier-set table.
_TARGET_NEW_TIERS: frozenset[int] = frozenset({1, 2, 4})


@dataclass(frozen=True)
class Placement:
    tier: int
    base_effect: str
    start_ms: int
    end_ms: int


def _tier_from_element_name(name: str) -> int | None:
    """Extract the tier prefix from a synthesised group name like
    ``06_PROP_Arch`` → ``6``. Returns None for non-tier-prefixed
    elements (timing tracks, status displays)."""
    if len(name) < 2 or not name[:2].isdigit():
        return None
    return int(name[:2])


def _parse_xsq(path: Path) -> list[Placement]:
    """Walk the .xsq's ElementEffects tree and produce a flat list of
    placements with the tier extracted."""
    tree = ET.parse(path)
    root = tree.getroot()
    ee = root.find("ElementEffects")
    if ee is None:
        return []
    out: list[Placement] = []
    for elem in ee.findall("Element"):
        name = elem.attrib.get("name", "")
        tier = _tier_from_element_name(name)
        if tier is None:
            continue
        for layer in elem.findall("EffectLayer"):
            for effect in layer.findall("Effect"):
                base = effect.attrib.get("name", "")
                try:
                    s = int(effect.attrib.get("startTime", "0"))
                    e = int(effect.attrib.get("endTime", "0"))
                except ValueError:
                    s = e = 0
                out.append(Placement(tier=tier, base_effect=base, start_ms=s, end_ms=e))
    return out


def _per_tier_counts(placements: list[Placement]) -> Counter[int]:
    return Counter(p.tier for p in placements)


def _per_tier_effects(placements: list[Placement]) -> dict[int, Counter[str]]:
    out: dict[int, Counter[str]] = {}
    for p in placements:
        out.setdefault(p.tier, Counter())[p.base_effect] += 1
    return out


def _verdict(
    baseline_counts: Counter[int],
    treatment_counts: Counter[int],
    treatment_effects: dict[int, Counter[str]],
) -> tuple[str, str]:
    """Return (status, reason). status is "PASS" or "FAIL"."""
    newly_active = {
        t for t in _TARGET_NEW_TIERS
        if treatment_counts.get(t, 0) > 0 and baseline_counts.get(t, 0) == 0
    }
    still_zero = _TARGET_NEW_TIERS - newly_active - {
        t for t in _TARGET_NEW_TIERS if baseline_counts.get(t, 0) > 0
    }

    # Regression: any tier that had placements in baseline now has zero.
    regressed = [
        t for t, n in baseline_counts.items()
        if n > 0 and treatment_counts.get(t, 0) == 0
    ]

    if regressed:
        return ("FAIL", f"tiers regressed to zero placements: {sorted(regressed)}")
    if not newly_active:
        return (
            "FAIL",
            "no new tier activation — treatment activates the same tiers as baseline. "
            "Expected tiers 1, 2, or 4 to gain placements.",
        )
    if still_zero == _TARGET_NEW_TIERS:
        return ("FAIL", "tiers 1/2/4 all still zero in treatment")

    # Soft signal: high bold-effect count on tier 1.
    tier1_effects = treatment_effects.get(1, Counter())
    tier1_total = sum(tier1_effects.values())
    bold_count = sum(c for e, c in tier1_effects.items() if e in _BOLD_BASE_EFFECTS)
    if tier1_total > 0 and bold_count / tier1_total > 0.5:
        return (
            "FAIL",
            f"tier 1 dominated by bold effects ({bold_count}/{tier1_total} = "
            f"{bold_count / tier1_total:.0%}); affinity routing not biasing toward background",
        )

    return ("PASS", f"new tiers activated: {sorted(newly_active)}")


def _markdown(
    baseline_path: Path,
    treatment_path: Path,
    baseline: list[Placement],
    treatment: list[Placement],
) -> str:
    bc = _per_tier_counts(baseline)
    tc = _per_tier_counts(treatment)
    te = _per_tier_effects(treatment)
    status, reason = _verdict(bc, tc, te)

    lines: list[str] = [
        f"# Pre-review: {treatment_path.name}",
        "",
        f"**Baseline:** `{baseline_path}`  ({len(baseline)} placements)",
        f"**Treatment:** `{treatment_path}`  ({len(treatment)} placements)",
        "",
        f"**Verdict: {status}** — {reason}",
        "",
        "## Tier placement counts",
        "",
        "| Tier | Baseline | Treatment | Δ |",
        "|------|---------:|----------:|--:|",
    ]
    all_tiers = sorted(set(bc) | set(tc))
    for t in all_tiers:
        b, c = bc.get(t, 0), tc.get(t, 0)
        lines.append(f"| {t:02d}   | {b}        | {c}         | {c - b:+d} |")
    if not all_tiers:
        lines.append("| (none) | | | |")

    lines += ["", "## Distinct base effects per tier (treatment)", ""]
    if not te:
        lines.append("_No tier-prefixed placements in treatment._")
    else:
        for t in sorted(te):
            counts = te[t]
            entries = ", ".join(f"{e} ({n})" for e, n in counts.most_common())
            lines.append(f"- **Tier {t:02d}** ({sum(counts.values())} placements, "
                         f"{len(counts)} distinct effects): {entries}")

    # Tier-1 bold-effect signal
    t1 = te.get(1, Counter())
    t1_bold = {e: n for e, n in t1.items() if e in _BOLD_BASE_EFFECTS}
    if t1:
        lines += [
            "",
            "## Tier-1 sanity check",
            "",
            f"- Total tier-1 placements: **{sum(t1.values())}**",
            f"- Tier-1 effects flagged as commonly-bold: "
            f"**{sum(t1_bold.values())}** ({list(t1_bold)})",
            f"- Bold-effect fraction: **"
            f"{(sum(t1_bold.values()) / sum(t1.values()) if t1 else 0):.0%}**",
        ]

    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"Usage: {argv[0]} <baseline.xsq> <treatment.xsq>", file=sys.stderr)
        return 2
    baseline_path = Path(argv[1])
    treatment_path = Path(argv[2])
    if not baseline_path.is_file():
        print(f"Not a file: {baseline_path}", file=sys.stderr)
        return 2
    if not treatment_path.is_file():
        print(f"Not a file: {treatment_path}", file=sys.stderr)
        return 2

    baseline = _parse_xsq(baseline_path)
    treatment = _parse_xsq(treatment_path)
    print(_markdown(baseline_path, treatment_path, baseline, treatment))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
