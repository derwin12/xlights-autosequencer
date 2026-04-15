# Research: Pipeline Decision-Ordering Refactor (048)

## 1. Current `place_effects` call graph (pre-refactor)

Single entry point today:

```
src/generator/plan.py:184  build_plan()
  └─ place_effects(assignment, groups, effect_library, hierarchy,
                   tiers=tiers_arg,               # from config.tier_selection gate
                   variant_library=variant_library,
                   rotation_plan=rotation_plan,
                   section_index=idx,
                   working_set=section_working_set,
                   focused_vocabulary=config.focused_vocabulary,
                   palette_restraint=config.palette_restraint,
                   duration_scaling=config.duration_scaling,
                   bpm=hierarchy.estimated_bpm)

src/generator/plan.py:443  regenerate_sections()
  └─ place_effects(assignment, groups, effect_library, hierarchy,
                   tiers=tiers_arg,
                   variant_library=variant_library,
                   rotation_plan=rotation_plan,
                   section_index=idx,
                   palette_restraint=getattr(config, "palette_restraint", True),
                   duration_scaling=getattr(config, "duration_scaling", True),
                   bpm=hierarchy.estimated_bpm)
                   # Note: focused_vocabulary and working_set NOT passed here — divergence
```

The two sites pass overlapping-but-not-identical kwarg sets. That divergence is the
exact reason FR-023 mandates migrating both to a single `SectionAssignment`-driven call.

## 2. Decision points currently inside per-tier / per-layer loops

Every item below is a decision re-computed each time `place_effects` runs, with inputs
that are section-level (not layer-level or tier-level). Each is pulled into the
precompute pass.

| Decision | Where today | Inputs | Frequency | Destination on assignment |
|----------|-------------|--------|-----------|---------------------------|
| Active tiers | `effect_placer.py:557-560` (only when `tiers` arg is None) | `section`, `section_index`, `hierarchy` | once per section | `assignment.active_tiers` |
| Palette trim target | `effect_placer.py:601-602` inside `for tier in selected` loop | `section.energy_score`, `tier` | once per (section, tier) | `assignment.palette_target[tier]` |
| Duration target | threaded as `bpm` + `duration_scaling` flag into `_place_effect_on_group` | `hierarchy.estimated_bpm`, `section.energy_score` | once per section | `assignment.duration_target` |
| Working-set selection toggle | `effect_placer.py:661` (`if focused_vocabulary and working_set…`) | `config.focused_vocabulary`, per-theme working_set | once per section | `assignment.working_set` (None ⇒ disabled) |
| Drum-accent gate | `plan.py:199` (`if config.beat_accent_effects:`) plus implicit section-energy / drum-event presence check inside `_place_drum_accents` | `config.beat_accent_effects`, `section.energy_score`, `hierarchy.events["drums"]` | once per section | `assignment.accent_policy.drum_hits` |
| Impact-accent gate | `effect_placer.py:1821-1828` (energy + duration + role) | `config.beat_accent_effects`, `section.energy_score`, duration, role | once per section | `assignment.accent_policy.impact` |
| Section index plumbing | passed as explicit `section_index=` kwarg | position in `assignments` list | once per section | `assignment.section_index` |

### Not moved upstream (intentionally)

| Decision | Reason it stays inside placement |
|----------|----------------------------------|
| `_DRUM_HIT_ENERGY_GATE` per-hit sample | Per-hit, not per-section. Sampling `energy_curves["drums"]` at each hit's `time_ms`. Per-hit data cannot be precomputed to a single section-level boolean. |
| Rotation plan lookups by (section_index, group.name) | Already a read off an externally-built plan. The refactor removes only the kwarg `section_index` — the rotation plan itself remains the source of truth. |
| Chord/tension curves (`build_tension_curve`) | Already built once per `place_effects` invocation from `hierarchy.chords`. Moving it upstream would save nothing. |
| Background/accent palette derivation (`_darken_palette_hsl`, `_lighten_palette`) | Pure functions of `theme.palette`; no section input. Cost is negligible and they're not on the Brief. |

## 3. Canonical-XML tooling decision

**Chosen**: `xml.etree.ElementTree.canonicalize(xml_data=..., strip_text=True)` — Python
stdlib since 3.8, C14N 2.0 compliant.

**Why**: `xsq_writer.py` already imports `xml.etree.ElementTree`. C14N 2.0 guarantees
lexicographic attribute ordering and configurable whitespace stripping — exactly the
two properties FR-031 requires. Zero new dependency.

**Alternatives rejected**:

| Alternative | Reason rejected |
|-------------|-----------------|
| `lxml.etree.c14n` | No `lxml` in the project today (`python -c "import lxml"` fails). Adding lxml for one CI gate is gratuitous. |
| Hand-rolled attribute sort + whitespace normaliser | Reinvents C14N. Introduces our own edge cases around namespace handling, CDATA, comments. |
| Byte-for-byte `.xsq` diff | Spec clarification explicitly rejected this: ET serialiser attribute order and EOL drift would make the gate noisy. |
| Plan-JSON diff instead of XML | Spec clarification chose XML. Plan-JSON doesn't round-trip through the XSQ writer's normalisation (fade scaling, frame alignment), so JSON parity ≠ output parity. |

**Usage pattern in the CI test**:

```python
from xml.etree.ElementTree import canonicalize

def _canon(xsq_path: Path) -> str:
    return canonicalize(xml_data=xsq_path.read_text(encoding="utf-8"),
                        strip_text=True)

def test_default_fixture_canonical_equality():
    generated = generate_sequence(DEFAULT_CONFIG)
    golden = FIXTURE_DIR / "default.xsq"
    assert _canon(generated) == _canon(golden)
```

## 4. `SectionAssignment.palette_target` shape

From spec clarification (2026-04-14): **per-tier mapping**, one entry per tier in
`active_tiers`.

**Rationale**:

- A single integer (e.g. `palette_target: int = 3`) collapses the per-tier cap table
  (`_TIER_PALETTE_CAP`, line 154 of `effect_placer.py`) — tier 8 allows 6 colours,
  tier 4 caps at 3. A scalar cannot represent both in one field.
- A function/closure (`palette_target: Callable[[int], int]`) blocks JSON serialisation,
  which the Brief UI needs.
- A dict `{tier: count}` is the minimal shape that (a) JSON-serialises for the Brief,
  (b) supports per-tier override from spec 047 (e.g. "2 colours on tier 5, 4 on tier 8"),
  (c) is a plain field read from `place_effects` (no helper call).

**Population** in the precompute pass: call `restrain_palette` once per tier in
`active_tiers` with a *dummy 6-colour palette*, take `len(...)` of the returned list —
that integer is the target count for that tier at that section's energy. Storing the
count rather than the trimmed palette itself keeps the actual palette selection
(per-tier theme vs accent vs background) exactly where it lives today inside
`place_effects`; we only hoist the *decision of how many*, not *which specific colours*.

## 5. Accent-policy boundary

Spec FR-013 lists three per-section gates today baked into accent helpers:

| Gate | Today's location | Moves to `build_plan`? |
|------|------------------|------------------------|
| `config.beat_accent_effects` flag | `plan.py:199` | YES — combined into policy |
| `section.energy_score >= 60` (drum) | implicit in today's helper (today it runs unconditionally; energy is checked via per-hit curve only — the >=60 threshold is a *new* explicit gate the spec surfaces, drawn from the section-level expectation that accents should not fire on low-energy sections. Today the per-hit 15/100 gate absorbs this implicitly on quiet sections.) | YES |
| drum-event-track presence | `effect_placer.py:1685-1691` | YES — `hierarchy.events.get("drums") is not None` |
| `section.energy_score > 80` (impact) | `effect_placer.py:1821` | YES |
| `section.end_ms - start_ms >= 4000ms` (impact) | `effect_placer.py:1823` | YES |
| role in `_IMPACT_QUALIFYING_ROLES` | `effect_placer.py:1827` | YES |

The per-hit drum energy sample (`_DRUM_HIT_ENERGY_GATE`, `_sample_energy_curve`) stays
inside `_place_drum_accents` — it is per-hit, not per-section (see §2).

## 6. Golden fixture capture procedure

Before applying any refactor diff:

1. Check out `main` at the exact commit preceding the refactor.
2. Run `pytest tests/integration/test_generator_equivalence.py::capture_goldens`
   (a one-shot `@pytest.mark.capture_only` helper that writes the current output
   into `tests/fixtures/xsq/048_golden/{default,no_focus,no_tier_selection,no_accents}.xsq`).
3. Commit the captured goldens on the refactor branch as the first commit.
4. Apply the refactor. Re-run the test suite without the `capture_only` marker —
   the goldens are now read-only expectations.

This keeps the capture step explicit and auditable; the goldens are versioned with
the refactor rather than regenerated silently.
