# STATUS — xlight-autosequencer

> Single source of truth for resuming work. Read this FIRST when starting a session.
> Update this file at the end of every work phase so the next `/clear` resumes in 1 read.
> Last updated: 2026-07-16

---

## ✅ Done

- **Moving Head (DMX fixture) support — v1 white wash, CONFIRMED WORKING in real xLights (2026-07-16, branch `feat/moving-head-effects`).**
  User opened the generated `.xsq` in real xLights against their actual MH-1..MH-4 fixtures (configured as `DmxColorAbilityWheel`, color-wheel type) and confirmed all 3 test segments render white correctly. Two real bugs were caught and fixed via this real-hardware testing loop (both root-caused by reading the actual xLights source at `H:\XlightsSourceDir\xLights`, not guesswork): (1) the `Dimmer:` command is a value-curve point list, not an opaque encoding — the original vendor-sample-derived guess was a flat curve at 0% (permanently off); (2) a color-wheel fixture only recognizes a commanded hue within ~3.6° of one of its own configured wheel-slot hues (`DmxColorAbilityWheel::GetDMXWheelValue`), so arbitrary theme-derived colors were fundamentally unreliable — per user request, the placement now always sends a fixed white `Wheel:` command (not `Color:`) plus `AutoShutter: true` (only meaningful on the Wheel path) instead of deriving a color per section. See the git log on this branch for the full incremental history (4 commits, each with source-code-verified root cause).
  Investigated two real vendor `.xsqz` examples (unzipped to scratch, never referenced in code/docs) to reverse-engineer the actual model/effect shape: fixtures are `DisplayAs="DmxMovingHeadAdv"` models wrapped in a plain `modelGroup`, driven exclusively by xLights' native "Moving Head" effect, whose real state lives in a per-fixture `E_TEXTCTRL_MH{n}_Settings` mini-DSL (`Color:`/`Dimmer:`/`Pan:`/`Tilt:`/... commands) rather than the flat slider schema every other effect uses. Confirmed the exact format (including a `&comma;` escape required for literal commas inside that DSL — the outer settings string is itself comma-delimited) against the xLights wiki's `Effect-MovingHead` page via the `xlights` MCP server.
  Shipped: (1) `src/grouper/layout.py::find_moving_head_groups()` detects a layout's moving-head modelGroup; (2) `src/grouper/grouper.py::generate_groups()` excludes moving-head props from every generic tier at one choke point — root cause: without this, `01_BASE_All` and an auto-familied `06_PROP_MH` would receive ordinary RGB effects, which for Pan/Tilt channels means snapping a real physical fixture to garbage positions; (3) new `src/generator/moving_head.py::place_moving_head_effects()` — a song-scoped pass (same pattern as vocal/video/crash effects) placing one static per-section color-wash "Moving Head" effect (theme/anchor color, dimmer full-on, no motion) per moving-head group; (4) wired through `GenerationConfig.moving_head_effects` (default True), `SequencePlan.moving_head_effects`, and `xsq_writer.write_xsq`'s existing song-scoped merge point. No changes needed to `_serialize_effect_params` — the generic flat-dict serializer already handles hand-built parameter strings correctly once commas are pre-escaped.
  Verified via a synthetic 2-head test fixture (`tests/fixtures/grouper/moving_head_layout.xml`, not derived from vendor content) exercised both through targeted unit tests (`test_moving_head.py`, `test_grouper_layout.py::TestFindMovingHeadGroups`, `test_grouper_groups.py::TestMovingHeadExclusion`) and a direct `write_xsq` smoke run whose output was hand-inspected — settings string matches the real vendor shape exactly, including the `&comma;` escaping. Full suite run: no new regressions (34 pre-existing failures on `main`, confirmed via `git stash` before/after comparison, are all unrelated — devcontainer path-resolution tests, section_profiler, duration_scaling — not touched by this change).
  **Deliberately deferred for a fast-follow**: Pan/Tilt motion (the embedded `Tilt VC: Active=TRUE|...` value-curve syntax observed in the vendor files), fan-out/grouping choreography across multiple heads, beat-synced shutter-strobe accents (seen as short ~300ms individual-model bursts in both vendor examples). This v1 intentionally ships the lowest-risk-to-get-wrong slice (static color, no motion) so it can be validated against real hardware before adding movement.

- **Crash-accent detector v3 — crash-stem impact score (2026-07-16, bugs 265/266 fixed).**
  User reported the 3:10 Dream On crash never appeared in any generated .xsq. Two root
  causes found and fixed: (1) `SCHEMA_VERSION` was never bumped when `crash_accents`
  was added, so pre-feature hierarchy caches silently skipped placement (bug-265) —
  now 2.1.0, and six hard-coded `== "2.0.0"` readers were converted to
  `src/analyzer/result.py::is_hierarchy_schema()` (accepts any 2.x); (2) the v2
  detector's 10s min-gap inside `find_peaks` suppressed the true crash behind a
  stronger neighbor before scoring (bug-266). v3 detector: drumsep cymbal separation
  chained on the demucs drums stem (new `src/analyzer/drum_stems.py`, checkpoint
  auto-downloads to `~/.xlight/models/drumsep/49469ca8.th`, torch>=2.6 needs
  `safe_globals([HDemucs])`), isolation x wash-area score on the >=4kHz platillos
  band, floor 7.0, 3s post-scoring min-gap, cap 6 (user raised from 5). Validated:
  5/6 user-confirmed Dream On crashes detected (163.5s rides a tom fill drumsep
  routes to toms/snare — accepted miss); 6-song panel yields 6/3/2/1/0/0 marks.
  End-to-end verified: generated .xsq has 6 Shockwaves on `01_BASE_All_FADES` incl.
  190.15s, clear of the end-of-song fade. Marks also export as a `crash_accents`
  .xtiming layer. Design: `openspec/changes/crash-stem-impact-score/`.
  **Note for next session:** all hierarchy caches re-analyze on next use (intended);
  first analysis per song now also runs drumsep (~70s CPU, cached as
  `.stems/<md5>/drums_cymbals.mp3`). Remaining task 7: run the full
  `xlight-evaluate gate` analyzer tier + `snapshot-analyzer` in the devcontainer.

- **Lyric-matched images wired into Pictures placement (bug-209/214 fast-follow, 2026-07-15).** `image_catalog.suggest_images_for_words()` now returns a `stored_path` key per suggestion (additive, existing `analysis.py`/`Pictures.tsx` consumers unaffected). `effect_placer._place_picture_effects()` gained an optional `word_image_matches` param: when a per-prop segment's time window overlaps a lyric-matched word, that word's image is used for the segment instead of the seeded rotation pick (earliest-starting match wins on overlap ties; falls back to rotation otherwise). `plan.py`'s 5e block computes `suggest_images_for_words(config.vocal_words)` once and passes it through. Added `logger.info` summary (`N/M segments lyric-matched`) plus per-override `logger.debug` lines for validation. 8 new tests in `test_picture_effects.py`, 406 generator-suite tests pass, no regressions.
- **Pictures effect support shipped and hardened (bug-209 → bug-213 → bug-214).** `effect_placer._place_picture_effects()` places Pictures effects song-scoped (like `_place_video_effect`), cycling eligible props through an image library in 20s segments across the song, seeded by `variation_seed`+prop name so props don't sync to the same image. New `GenerationConfig.picture_effects` flag (default True); new `SequencePlan.picture_effects` field. Three corrections landed the same day:
  1. **bug-213**: verified the real filename attribute against 87 real placements across 5 reference `.xsqz` packages — it's `E_TEXTCTRL_Pictures_Filename`, not the originally-shipped `E_FILEPICKER_Pictures_Filename` (would have silently shown no image in real xLights). Also narrowed eligibility from broad `prop_suitability` to **Matrix display type or Mega Tree name match only**, per user request — the corpus showed every other prop family just repeated one shared decorative image.
  2. **bug-214 (architecture change)**: discovered the `xlight-dev` container has **no mount at all** to the user's real show folder (`docker inspect` confirmed only the repo workspace bind) — a host-scanned `Images/` directory can never work from inside the container. Replaced the whole image-source model: images are now **uploaded through the UI** into a container-local **global** library (`~/.xlight/library/images/`, keyed by `tag`, mirroring `import_video.py`'s pattern) via new `POST/GET /api/v1/images`. `image_catalog.py` rewritten around the library; new `find_unmatched_topics()` surfaces lyric words with no library match. New dedicated **Pictures wizard screen** (`Pictures.tsx`, between Theme and Export) shows unmatched topics with an upload control plus already-matched suggestions. `xsq_writer.py` gained the same copy-and-rewrite-to-bare-filename treatment already used for the Video effect, since library paths are container-internal.
  595 tests pass, frontend build clean. `docs/xlights-effect-params.md` annotated with the bug-213 correction (its scraped metadata still shows the wrong `E_CUSTOM_Pictures_FilenameBlock`).
- Fixed three user-reported whole-house rendering bugs, all confirmed against a real exported `.xsq` before fixing (bug-206, bug-207, bug-208): (1) `01_BASE_All` composite layers could stack the identical effect on itself simultaneously ("shader on top of shader") — `_place_whole_house_composite` (`src/generator/effect_placer.py`) now rotates through 5 distinct effect names instead of indexing a flat pool with duplicate runs; (2) fade in/out values could exceed the duration of the placement they were on (503/789 fades in the sample file exceeded 25% of their own effect's length) — `_serialize_effect_params` (`src/generator/xsq_writer.py`) now caps `fade_in_ms`/`fade_out_ms` to 25% of the placement's own `end_ms - start_ms` at write time, guarding every fade producer at one point; (3) `08_HERO_Mega_Topper` was double-sequenced — the raw "Mega Topper" model got 48 direct drum-hit accents on top of the HERO group's own 594 placements because `_place_drum_accents`'s group-coverage skip only checked tier-6 PROP groups, not tier-8 HERO. Widened to `g.tier in (6, 8)`. Full generator/transitions/xsq_writer/beat-accents test suites green (390+ passed, no regressions).
- Arch prop-family recipe: chorus alternates Single Strand/Shockwave, bridge alternates to Spirals, chase direction + chase-size (Color_Mix1) rotate per section occurrence — merged to `main`.
- Same direction/size rotation extended to cane/horizontal/vertical (minitree deliberately excluded — its data stays fixed to Right-Left).
- Fixed stale `video_path` on re-import in `src/review/api/v1/import_video.py` (always adopts the latest drop, not just the first).
- Added `Shader` effect (scoped to Plasma Emitter.fs) + 3 variants, and a new energy-gated whole-house composite mechanism (`AccentPolicy.whole_house_layers`, `_place_whole_house_composite` in `effect_placer.py`) that stacks extra layers on `01_BASE_All`, mined from the corpus's "All" group idiom.
- Installed the real `openwolf` CLI (`npm install -g openwolf`), ran `openwolf init` — it auto-wired unrequested Codex integration (removed) and silently deleted the Branch Discipline / Code Review Discipline sections from OPENWOLF.md plus inserted an unsolicited "Astryx" framework recommendation into reframe-frameworks.md (both restored/removed). `.claude/settings.json` hook registration now real. Note: live hooks auto-write noisy "auto-detected" entries to `.wolf/buglog.json`/`anatomy.md` on every Read/Edit — currently just `git checkout`-ing those away each time; worth revisiting whether to disable that specific hook behavior.
- **Recovered all genuinely-missing work from branches ≤2 days old** (per user's cutoff): cherry-picked icicle recipe, mega-topper recipe + topper→hero promotion, star recipe, corpus-paired-hero pairing + always-fade-out, matrix motion rotation (4 looks), and the `mine_arch_corpus.py` tool script from `fix/spirals-textctrl-movement` / `feat/arch-sequencing-corpus-miner`. Deliberately dropped: the old All-group recipe (superseded by today's whole-house composite — removed `all_group`/`_SHOCKWAVE_ALL`/`_PINWHEEL_ALL`/`burst_volley` + related dead code), and several already-redundant commits (textctrl migrations, a devcontainer doc already present differently). Deleted all now-fully-accounted-for local branches (remotes untouched as backup).
- Full test suite green throughout (2916 passed at last full run).

---

## 🚀 Next phase

**Goal:** Test the Moving Head v1 branch (`feat/moving-head-effects`) against real hardware/xLights, then decide on motion follow-up.

### Open decisions
- **Moving Head v1 ready to merge** — confirmed working against real xLights + real hardware fixture config. Not yet merged to `main`; ask the user whether to merge `feat/moving-head-effects` now or keep iterating on the branch first.
- **Moving Head fast-follow candidates** (deliberately out of v1 scope): Pan/Tilt motion via the embedded `Tilt VC: Active=TRUE|Id=...|Type=Ramp|...` value-curve syntax; per-head fan-out (`PanOffset`/`TiltOffset`/`Groupings` > 1) for multi-head formations; short beat-synced shutter-strobe accents on individual heads (observed as ~300ms bursts in both vendor examples, separate from the group-level wash). Each adds real risk (wrong DMX values on real hardware) and should get its own smaller design/test pass rather than being bundled together. Given v1 was color-wheel type, motion follow-ups should re-verify against `MovingHeadEffect.cpp`'s actual Pan/Tilt VC parsing before implementing, same discipline as this round.
- **Multi-layer offset Pictures placement** — user noted (2026-07-15) the reference corpus sometimes places Pictures on multiple overlapping/offset layers for a deliberate parallax look (confirmed: layer distribution varies a lot per song — Darlene Love 100% layer 1, Hockey Song spread across layers 1-6). Not implemented; current placement is always a single layer per prop.
- **Deleting/managing uploaded library images** — `POST`/`GET /api/v1/images` exist; no `DELETE` endpoint or management UI yet. Fine for now (library only grows), but worth adding if the list gets unwieldy.
- Whether to add folder-name/theme-mood matching for image selection (explicitly deferred — user chose "flat pool" for round 1, now moot since the source is an upload library, not a scanned folder).
- Whether to re-mine/redo the All-group idiom later as an enhancement on top of today's whole-house composite (volley pacing, color-cycling backbone) — deferred, not decided.
- Whether to investigate/disable the openwolf hook that auto-generates noisy "auto-detected" buglog.json entries and drastically rewrites anatomy.md on every Read/Edit.
- **`06_PROP_Horizontal_Lines` investigation closed as a non-issue** (2026-07-15): user reported the group "including way more than it should" on `F:\ShowFolderAI\xlights_rgbeffects.xml`; re-running the classifier against that file reproduced the same 12-member list (Windows Top 1-3, Matrix Top-1/2, Pergola Top x4, Garage Top x3) already present in the file, and the user confirmed via the UI it looks fine — no code change made. **Real finding surfaced along the way, still open**: that layout carries three separate group definitions with byte-identical 12-member lists — the vendor's original `"Horizontal Lines"` (aliased `06_prop_horizontal_lines`), plus our own `03_TYPE_Horizontal` and `06_PROP_Horizontal_Lines`. Worth a follow-up: check whether `group-layout`'s generation should detect/skip re-creating a tier-6 group when a vendor group with the same alias/membership already exists, to avoid three groups rendering the same lines redundantly.

---

## 📁 Active architecture

- **Stack:** Python 3.11+ (analyzer/generator/CLI), Flask + React/Vite review UI, click CLI. See CLAUDE.md for the full stack list.
- **Key modules:** `src/generator/corpus_recipes.py` (mined prop-family idioms) + `src/generator/effect_placer.py` (placement engine, `_place_corpus_recipe`, `_place_whole_house_composite`) + `src/generator/plan.py` (orchestrates `build_plan`, computes `AccentPolicy` gates once per section).
- **Patterns:** corpus-mined presets always cite the actual mined stat in a comment (see `_SHOCKWAVE_BURST`, `_SPIRALS_ARCH_BRIDGE`, etc.); accent passes (`drum_hits`/`impact`/`whole_house_layers`) run as a second pass in `build_plan` AFTER `place_effects`, not inside it — any isolation test re-running `place_effects` alone must disable all of them via `GenerationConfig`.

---

## ⚠️ External blockers (don't block coding)

- The devcontainer's `xlight-review` server does NOT hot-reload backend Python changes — must be killed/restarted after every commit (see CLAUDE.md → "Restarting the dev review server after a commit"). Always check the UI's `api <commit>` version banner before concluding a fix "didn't work."
- Mined corpus extracts (`docs/*_sequencing_corpus/`) must never be pushed to GitHub (purchased reference sequences) — gitignored on `main`.

---

## 🔧 Useful commands

```bash
# Restart the devcontainer review server (Git Bash needs MSYS_NO_PATHCONV=1)
MSYS_NO_PATHCONV=1 docker exec xlight-dev pkill -f xlight-review
MSYS_NO_PATHCONV=1 docker exec -d xlight-dev /usr/bin/python3 /home/node/.local/bin/xlight-review --dev --host 0.0.0.0 --port 5000

# Run the generator/effects test suites
python -m pytest tests/unit/test_generator/ tests/unit/test_effects_library.py tests/unit/test_variant_library.py -q

# Full suite (excludes vamp/madmom-only suites not installed on this host)
python -m pytest tests/ -q --ignore=tests/microscope
```

---

## 📚 References (read IF needed)

- `.wolf/cerebrum.md` — User Preferences + Do-Not-Repeat + Decision Log
- `.wolf/anatomy.md` — token-efficient file index
- `.wolf/buglog.json` — known bugs + fixes
