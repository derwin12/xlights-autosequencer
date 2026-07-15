# STATUS — xlight-autosequencer

> Single source of truth for resuming work. Read this FIRST when starting a session.
> Update this file at the end of every work phase so the next `/clear` resumes in 1 read.
> Last updated: 2026-07-15

---

## ✅ Done

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

**Goal:** none queued — next work starts fresh from whatever the user brings.

### Open decisions
- **Fast-follow explicitly scoped by the user (2026-07-15):** wire `image_suggestions`/`image_topics` into generation — when a `_place_picture_effects` placement's time window overlaps a lyric-matched word, prefer that matched image over the random library rotation, falling back to random otherwise. Not yet implemented (round 1 was advisory-only by explicit choice).
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
