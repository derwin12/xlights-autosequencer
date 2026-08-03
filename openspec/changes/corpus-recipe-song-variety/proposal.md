# Proposal: song-seeded corpus-recipe variety (pilot: minitree)

## Why

User observation (2026-08-02): generated sequences are converging — different
songs "look pretty much the same" for a given prop family. Root cause traced
to how `CORPUS_RECIPES` (`src/generator/corpus_recipes.py`) turns mining data
into behavior: for every family without a `motion_rotation` pool, the
alt-effect decision is `(variation_seed // 2) % 2 == 1`, where
`variation_seed = config.variation_seed (per-song) + section_index`. Every
song's qualifying occurrences therefore alternate primary/alt in the exact
same lockstep parity pattern — occurrence 0 always primary, occurrence 1
always alt, occurrence 2 always primary, regardless of which song, which
audio hash, or what the real mined idiom for that specific song actually
looked like. The mechanism already varies effect choice *within* a song; it
has never varied *across* songs.

This was invisible until now because mining always reported one aggregate
winner per family and the recipe just encoded that winner — a single global
answer looks consistent by construction. Re-mining the corpus after adding 4
new songs (session 2026-08-02) surfaced a concrete case where this framing
breaks down: **minitree**. The original 12-song corpus showed SingleStrand
dominant (73%) with Shockwave a rare 3% alt-bounce — but all 4 new songs
independently show Shockwave *out-scoring* SingleStrand (54%, 54%, 38%, 59%
vs. 10%, 0%, 8%, 10%), pulling the 17-song aggregate to a near-tie (31%/29%).
This isn't measurement noise or a "which one is right" question — it's
confirmation that real vendor songs each commit to their own dominant look,
and averaging them into one fixed winner (or one fixed alternation pattern)
throws away exactly the variety that made the source material interesting.

## What Changes

Minitree only, as a pilot. If it reads well, the same mechanism generalizes
to other primary/alt families later (not in this change).

### New opt-in field: `PropFamilyRecipe.song_seeded_alt_share`

```python
song_seeded_alt_share: tuple[int, int] | None = None
```

A `(min, max)` range, out of a fixed 8-slot pool, for how many of a song's
qualifying occurrences use `alt_effect_name` instead of `effect_name`.
Default `None` → today's fixed `(variation_seed // 2) % 2` parity, so every
other family (arch, cane, snowflake, star, …) is bit-for-bit unaffected.

Minitree sets `song_seeded_alt_share=(2, 6)` — 25%-75% Shockwave share,
centered on the near-50/50 mined aggregate but with real per-song spread,
deliberately **not** allowed to reach 0/8 or 8/8: a recipe that always plays
one effect for an entire song is the exact monotony bug class already fixed
elsewhere (2026-07-28 bounce/reroll work, tier-layering-policy). Bounding
the range keeps every song showing *some* of both looks while letting the
dominant one differ song to song.

### Mechanism (`_place_corpus_recipe`, `src/generator/effect_placer.py`)

Reuses the exact shuffle pattern already shipped for megatree's mirror
overlay (`overlay_order = random.Random(f"mirror_overlay:{variation_seed}")
.sample(...)`, 2026-07-23) — same idea, corrected to key off a genuinely
per-song value instead of the per-section `variation_seed`:

```python
elif recipe.alt_effect_name is not None:
    if recipe.song_seeded_alt_share is not None and occurrence_index is not None:
        pool_size = 8
        alt_min, alt_max = recipe.song_seeded_alt_share
        rng = random.Random(f"song_alt_share:{song_seed}:{recipe.family}:{group.name}")
        alt_count = rng.randint(alt_min, alt_max)
        seq = [True] * alt_count + [False] * (pool_size - alt_count)
        rng.shuffle(seq)
        use_alt = seq[occurrence_index % pool_size]
    else:
        use_alt = (variation_seed // 2) % 2 == 1
    if use_alt:
        effect_name = recipe.alt_effect_name
        ...  # existing alt_rotation_effect_name / bounce logic, unchanged
```

`song_seed` is new: a pure per-song value recovered at the call site as
`assignment.variation_seed - assignment.section_index` (no new field on
`SectionAssignment` needed — `variation_seed = base + section_index` is
already the documented formula, so subtracting the known `section_index`
recovers the song-constant base). This is the correction referenced above:
the existing mirror-overlay shuffle keys off the raw per-section
`variation_seed`, so in a real song with multiple qualifying sections it
silently reshuffles every time `variation_seed` changes rather than staying
stable for the song — not touched by this change, but explicitly not
copied into the new mechanism, since keeping one shuffle order stable for
the whole song (not per-section) is the entire point here.

Only `_place_corpus_recipe`'s signature and the 4 call sites in
`effect_placer.py` need the new `song_seed` argument; everything downstream
of `effect_name` being set (bounce, `alt_rotation_effect_name`'s 1-in-3
Color Wash override, palette, direction rotation) is untouched — this
patches *which occurrences* pick the alt effect, not what happens once one
does.

## Alternatives considered

- **Fully replace minitree's primary/alt with a `motion_rotation` pool**
  (the mechanism megatree/matrix already use) — rejected for this pilot:
  `motion_rotation`'s per-beat-block bounce reroll (2026-07-28, "shockwaves
  don't seem to change... between ~50s and 1:55s") is wired specifically to
  the `effect_name == recipe.alt_effect_name` branch, not to
  `motion_rotation`. Switching would silently drop that fix for minitree's
  Shockwave occurrences and reintroduce the same long-occurrence-freezing
  bug for a different reason. The `song_seeded_alt_share` approach keeps the
  existing alt-effect_name plumbing (and its bounce fix) completely intact
  and only changes the *selection* condition.
- **Unweighted independent per-occurrence coin flip** (50/50 every time, no
  per-song bias) — rejected: doesn't match the real data. Actual songs don't
  alternate randomly occurrence-to-occurrence: they commit to a dominant
  look (Magic: 0% SingleStrand; the original 12-song corpus: 73%
  SingleStrand) with occasional variation. A per-song bias reproduces that
  shape; an unbiased coin flip would just be a differently-random version of
  the same "every song looks statistically identical" problem.
- **Unbounded per-song share (0-8 out of 8)** — rejected: would let a song
  land on the alt effect 0 or 8 times out of 8, i.e. the literal monotony
  bug this whole conversation started from. `(2, 6)` guarantees both looks
  appear in every song while letting the ratio vary.
- **Apply this to all primary/alt families in one change** — rejected per
  explicit user direction to pilot on minitree first, since it's the family
  with concrete new data showing the problem, before generalizing.

## Files touched

| File | Change |
|---|---|
| `src/generator/corpus_recipes.py` | modified — new `song_seeded_alt_share` field on `PropFamilyRecipe` (default `None`); minitree recipe sets `song_seeded_alt_share=(2, 6)` |
| `src/generator/effect_placer.py` | modified — `_place_corpus_recipe` gains `song_seed: int = 0` param; new branch in the alt-effect-name `elif`; the 4 call sites (~1210, ~1379, ~1460, ~1592) pass `song_seed=assignment.variation_seed - assignment.section_index` |
| `tests/unit/test_generator/test_corpus_recipes.py` | modified — new tests: different songs (varying `song_seed`) produce different alt-shares for minitree; share always within [2,6]/8; every other family's existing parity tests (`test_minitree_alternate_is_shockwave_burst`, `test_minitree_bounce_occurrence_implodes`) updated to pin `song_seed` explicitly since the selection condition changed; non-minitree families' existing tests unaffected (field defaults to `None`) |
| `docs/segment-classification-changelog.md` | not touched — no segment/classification change |

## Regression surface

- **`PropFamilyRecipe`** — new field, default `None`. Grep: only constructed
  in `src/generator/corpus_recipes.py`'s `CORPUS_RECIPES` tuple; no other
  constructors in `src/` or `tests/`. Every family except minitree keeps the
  field at `None` → old codepath, bit-for-bit unchanged.
- **`_place_corpus_recipe`** — private, called only from the 4 sites in
  `effect_placer.py` inside `place_effects`; all 4 updated together. Grep of
  `tests/`: no test calls it with a bare positional-arg list that would
  break from an added keyword-only param (existing tests use keyword args
  per the `_place()` test helper — checked `test_corpus_recipes.py`'s
  `_place()` wrapper, single call site, updated once).
- **Existing minitree tests** (`test_minitree_alternate_is_shockwave_burst`,
  `test_minitree_bounce_occurrence_implodes`, the occurrence-rotation test
  at line ~1349) currently assert Shockwave fires on `corpus_occurrence=1`
  under the OLD parity rule — these will need a fixed `song_seed` pinned
  (e.g. one that happens to land occurrence 1 on the alt effect) rather than
  relying on bare parity, since parity is no longer minitree's selection
  rule. Flagged explicitly so this isn't missed during implementation.
- **Golden/microscope baselines** — minitree output changes by design
  (that's the point). `xlight-evaluate microscope panel` must be re-run,
  reviewed, and baselines re-promoted only after `microscope sensitivity`
  passes, per the CLAUDE.md promotion rule.
- **Mined corpus docs** (`docs/minitree_sequencing_corpus/`) are gitignored,
  local-only, unaffected by this code change either way.

## Historical echoes (`.wolf/buglog.json`, `.wolf/cerebrum.md` Do-Not-Repeat)

- **2026-07-28 Shockwave bounce reroll** (`_SHOCKWAVE_BOUNCE_REROLL_BEATS`
  cerebrum entry) — a single long occurrence must keep varying, not freeze
  on one look for its whole span. Explicitly preserved: this change only
  touches which occurrences select `alt_effect_name` in the first place, not
  the per-beat-block reroll that already runs once they do (see "Alternatives
  considered" for why `motion_rotation` was rejected specifically to avoid
  losing this).
- **bug-182 / cerebrum "variation_seed is the global section index"** — raw
  section-index parity aliases with regular section strides and can lock one
  branch in for a whole song. This proposal's `song_seed` is deliberately
  the *song-constant* component (base, with `section_index` subtracted back
  out), not the raw per-section `variation_seed`, specifically to avoid this
  failure family recurring in a new form.
- **2026-07-23 mirror-overlay shuffle** (`mirror_overlay_rotation`,
  `overlay_order = random.Random(f"mirror_overlay:{variation_seed}")
  .sample(...)`) — direct precedent for "shuffle a pool's walk order per
  song instead of always starting at slot 0," reused here. Noted deviation:
  that existing mechanism keys off the raw per-section `variation_seed`
  rather than a song-constant value, so it likely reshuffles across a real
  song's multiple qualifying sections rather than staying stable for the
  whole song — **not** in scope to fix here (out of scope, pre-existing,
  unrelated family), but explicitly not copied into this new mechanism.
- **tier-layering-policy / "one effect the whole song" incidents** — the
  general pattern of "a recipe collapsing to a single look for an entire
  song reads as broken" recurs across several past fixes (arch direction
  rotation bug-197, Single Strand render-style freeze, Shockwave bounce
  reroll). The `(2, 6)`-of-8 bound is a direct application of that lesson:
  never let a per-song draw reach the 0-variety extremes.
- No matching entries found for `song_seeded_alt_share` or
  cross-song-variety regressions beyond the above; stated explicitly per the
  gate.

## Validation

1. Unit: new song-seed-variety tests (different `song_seed` values produce
   different but bounded alt-shares); updated parity-dependent minitree
   tests; full `pytest tests/unit/test_generator -v`.
2. Regenerate several of the new corpus songs (Believer, Magic, Sounding
   Joy, Uptown Funk — now available locally) plus a couple of the original
   12-song-corpus songs, and confirm in each `.xsq`: minitree's
   Shockwave-vs-SingleStrand ratio visibly differs song to song, and no
   single song shows 100% one effect.
3. `xlight-evaluate microscope panel` against current baselines; expect
   minitree-related variety metrics to move — review the diff, re-run
   `microscope sensitivity`, re-promote only after it passes.
