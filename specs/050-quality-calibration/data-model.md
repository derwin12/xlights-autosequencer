# Phase 1 Data Model: Quality Calibration Harness

All entities are Python `@dataclass`es in `src/evaluation/models.py` unless marked otherwise. Persisted entities have a JSON schema; in-memory-only entities do not.

## Manifest entry

Persisted in `tests/golden/pro_reference/manifest.json` as a list under key `entries`.

```json
{
  "song_id": "light-of-christmas",
  "pro_id": "xatw",
  "xsq_path": "/home/node/xlights/baseline-sequences/Light Of Christmas XATW.xsq",
  "mp3_path": "/home/node/xlights/baseline-sequences/02 - Light Of Christmas [feat. Owl City].mp3",
  "audio_hash": "md5:3f4b…",
  "tags": ["christmas", "pop", "vocal-heavy"],
  "notes_ref": "notes/light-of-christmas.md",
  "master_may_differ": false
}
```

**Validation**:
- `song_id`, `pro_id` — lowercase-slug (`[a-z0-9-]+`), non-empty.
- `(song_id, pro_id)` must be unique across manifest (composite key, FR-004 / research §7).
- `xsq_path` must exist and be readable; file must end in `.xsq` or `.xsqz`.
- `mp3_path` may be missing at runtime — the corpus loader flags it as a corpus-side skip (FR-015).
- `audio_hash` — string `"md5:<32-hex-chars>"`; compared against fresh hash of on-disk `mp3_path` (FR-002). Mismatch logs a warning; entry is still measured.
- `tags` — free-form strings for human filtering; no semantic validation.
- `notes_ref` — relative path from manifest directory; existence is warned on but not enforced.
- `master_may_differ` — boolean; when true, beat- and section-dependent metrics are tagged `reliability=reduced` in the report for this entry (FR-003).

## Placement

In-memory only. Output of `src.evaluation.xsq_reader.parse()`.

```python
@dataclass(frozen=True)
class Placement:
    start_ms: int
    end_ms: int
    effect_type: str         # e.g. "Marquee", "Plasma", or "Unknown"
    model_name: str          # from <Element name="...">
    palette_colors: tuple[str, ...]  # active hex colors from referenced palette, order preserved
    layer_index: int         # position of <EffectLayer> within the <Element>
```

**Validation**:
- `start_ms < end_ms`, both non-negative integers (xLights stores these as int ms).
- `effect_type` — canonical token from research §2; "Unknown" allowed.
- `palette_colors` — tuple of `"#RRGGBB"` strings; may be empty if the referenced palette has no `C_CHECKBOX_Palette<n>=1` entries.
- `layer_index` — zero-indexed; tracked so multi-layer stacks are distinguishable.

## SequenceSummary

In-memory only. Returned by `parse()`; consumed by every metric.

```python
@dataclass(frozen=True)
class SequenceSummary:
    song_id: str              # corpus-side identity
    source_label: str         # "pro:<pro_id>" or "ours"
    duration_ms: int          # from <sequenceDuration>
    placements: tuple[Placement, ...]
    model_names: tuple[str, ...]         # all <Element name> values in file order
    inferred_prop_types: dict[str, str]  # model_name -> prop-type guess from name heuristic
```

**Prop-type heuristic** (research §2 outcome, same rules for pro and ours): match model names case-insensitively against substring tokens — `arch`, `tree`, `star`, `candy`, `matrix`, `snowflake`, `deer`, `house`, `mega`, `outline`; unmatched → `"Unknown"`. Heuristic lives in `xsq_reader.py` so it applies identically to both sides.

## MetricValue

Persisted inside each `Report` entry.

```json
{
  "name": "placements_per_minute",
  "kind": "scalar",
  "value": 42.3,
  "payload": null,
  "reliability": "ok"
}
```

- `kind ∈ {"scalar", "distribution", "per_section", "structured"}` — determines how the value is rendered and compared.
- `value` — primary numeric (always present for scalar; for distributions, the scalar comparison metric such as JS divergence).
- `payload` — additional structured data (e.g. for `palette_top5_colors`: the list of `[color, share]` pairs; for `per_section_palette_diversity`: the per-section array).
- `reliability ∈ {"ok", "reduced"}` — set to `reduced` when `master_may_differ=true` and the metric depends on audio alignment (FR-003).

## MetricDefinition

Python object only, in `src/evaluation/metrics/__init__.py` registry.

```python
@dataclass(frozen=True)
class MetricDefinition:
    name: str
    kind: MetricKind                  # enum matching MetricValue.kind
    gated: bool                       # True = counted by regression gate
    tolerance: MetricTolerance | None # None → use default
    compute: Callable[..., MetricValue]
    pro_comparable: bool              # False for ours-only metrics
```

**Default tolerance** (research §5, spec FR-017 clarification):
- `MetricTolerance(kind="relative", value=0.10)` — 10% relative delta — applied when a metric definition has `tolerance=None`.
- Metrics override per their natural scale. Initial overrides:
  - `placements_per_minute`: 15% relative.
  - `beat_alignment_pct`: absolute ±3 percentage points.
  - `tier_utilization`: absolute ±0.05 on fractions.
  - All others: default 10% relative.
- Tolerances are immutable values declared alongside the metric; changing one is a code change reviewed in PR.

**Registered metrics (v0)**:

| Name | Kind | Gated | Pro-comparable |
|---|---|---|---|
| `placements_per_minute` | scalar | ✅ | ✅ |
| `palette_top5_colors` | structured | ✅ | ✅ |
| `effect_type_histogram` | distribution | ✅ | ✅ |
| `beat_alignment_pct` | scalar | ✅ | ✅ |
| `density_energy_correlation` | scalar | ✅ | ✅ |
| `per_section_palette_diversity` | per_section | ✅ | ✅ |
| `section_transition_delta` | per_section | ✅ | ✅ |
| `tier_utilization` | per_section | ✅ | ❌ |
| `theme_assignment_consistency` | scalar | ✅ | ❌ |

(`unknown_effect_fraction` is not a standalone registered metric — it's a companion field on the `effect_type_histogram` MetricValue payload; see spec FR-009 / research §8.)

## Report

Persisted to `tests/golden/reports/<iso>.json` on every `compare` run.

```json
{
  "schema_version": 1,
  "generated_at": "2026-04-15T14:33:12Z",
  "generator_commit": "abc123…",
  "corpus_manifest_hash": "md5:…",
  "entries": [
    {
      "song_id": "light-of-christmas",
      "pro_entries": [
        { "pro_id": "xatw", "metrics": [ MetricValue, ... ] },
        { "pro_id": "bill-jenkins", "metrics": [ ... ] },
        { "pro_id": "jeremy-poling", "metrics": [ ... ] }
      ],
      "ours": { "metrics": [ MetricValue, ... ] },
      "intra_pro_variance": {
        "placements_per_minute": { "min": 38.0, "max": 44.1, "range": 6.1 },
        ...
      },
      "skips": []
    },
    {
      "song_id": "uptown-funk",
      "pro_entries": [],
      "ours": null,
      "skips": [
        { "pro_id": "*", "reason": "mp3_missing", "category": "corpus-side" }
      ]
    }
  ],
  "cross_song_trends": [
    {
      "metric": "palette_top5_colors",
      "direction": "ours>pro",
      "songs_agreeing": 5,
      "songs_total": 6,
      "consistent_gap": true
    }
  ],
  "summary": {
    "songs_measured": 5,
    "songs_skipped_corpus_side": 1,
    "songs_skipped_our_side": 0,
    "ci_status": "pass"
  }
}
```

**Validation**:
- `schema_version` — integer; v0 is `1`. Baseline files carry the same schema version; a version mismatch between baseline and current run triggers a hard error with migration guidance (research §5 + the edge case: "first-ever run with no baseline committed").
- `intra_pro_variance` present only for songs with ≥ 2 pro entries (FR-013).
- `cross_song_trends` — computed only over metrics that have at least one per-song comparison, using the 80% consistency threshold (research §10).
- `ci_status ∈ {"pass", "fail-regression", "fail-generator-error", "fail-no-baseline"}` — mirrors exit codes of the `check` subcommand.
- `skips[].category ∈ {"corpus-side", "our-side"}` — per spec FR-015 clarification.

## Baseline

Persisted in `tests/golden/baseline.json`. Structurally identical to `Report.entries[*].ours.metrics` but keyed by `song_id`:

```json
{
  "schema_version": 1,
  "generator_commit": "abc123…",
  "generated_at": "2026-04-15T14:33:12Z",
  "entries": {
    "light-of-christmas": { "metrics": [ MetricValue, ... ] },
    "danger-zone": { "metrics": [ ... ] }
  }
}
```

**Regression gate comparison** (FR-016, FR-017):
1. For each `song_id` in baseline AND current run, walk `metrics` by name.
2. For each `gated` metric, compare `current.value` vs `baseline.value` using the metric's declared tolerance.
3. Any violation → CI failure with the list of `(song_id, metric_name, baseline, current, delta, tolerance)` tuples.
4. Songs present in baseline but not in current run (or vice versa) → CI failure with reason `baseline_song_count_mismatch` unless `baseline.json` was modified in the same commit as the failing run.

## Manifest note file

Plain Markdown under `tests/golden/pro_reference/notes/<song-id>.md`. No schema; free-form. Referenced by `notes_ref` in manifest entries. Typical content: genre, why selected, what the pro did well, any caveats (master mismatch, unusual layout).
