# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-25

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

- **Adversarial review is expected.** Code review should be suspicious, not agreeable. Cite `file:line`, flag concrete findings, rank by severity (CRITICAL / HIGH / MEDIUM / LOW). No generic feedback.
- **Root cause first, always.** For any bug fix, state the root cause in one sentence ("X happens because Y") before proposing the change. Fix at the layer where the cause lives, not downstream of it.
- **Keep changes scoped.** Do exactly what was asked — nothing more, nothing less. No "while I was in here" refactors, no speculative abstractions, no preemptive cleanup.
- **Branches required.** Never work directly on `main`/`master`. Every new task gets a new branch (`fix/`, `feat/`, `refactor/`, `chore/`). See Branch Discipline in OPENWOLF.md.
- **No hacks.** No `# HACK`, no `# TODO: fix properly later`, no workaround comments, no try/except-pass, no hard-coded special cases to mask bad data. If the right fix is too large for scope, say so — don't ship a band-aid.

## Key Learnings

- **Project:** xlight-autosequencer — MP3 → xLights sequence generator pipeline. Python 3.11+, vamp/librosa/madmom analysis, Flask review UI, click CLI.
- **Review surface:** OPENWOLF.md now carries Branch Discipline and Code Review Discipline sections. `/review-diff` slash command runs the adversarial review against `git diff main...HEAD`.
- **Shared-infrastructure modules** (touching any of these requires cross-feature regression check and the full design-first gate — size is NOT a safe proxy for risk here): `src/analyzer/` (86 importers), `src/effects/` (54), `src/generator/` (44), `src/review/` (32), `src/themes/` (38). Measured 2026-04-24 by grepping callers outside each module.
- **Design-First Gate** (CLAUDE.md → "Design-First Gate" section): for any change beyond a single-file bug fix < ~30 lines with a stated root cause and no shared-module touch, produce a written design (OpenSpec change or inline plan) covering goal, approach, files touched, alternatives considered, regression surface (with grepped callers), and historical echoes from `.wolf/buglog.json` + cerebrum Do-Not-Repeat. Wait for user approval before editing project files. Use `/pre-mortem <change>` to stress-test the design before implementation. If the user says "just do it" — comply and note the override in the session summary.
- **Acceptance gate** (`xlight-evaluate gate`): unified pre-merge check covering analyzer + generator + UI suites. Exit codes (priority order, highest wins): `8` infra-failure (Playwright missing, corpus download failed, unknown error), `4` no-baseline (run `xlight-evaluate snapshot-analyzer` first), `6` regression detected, `0` pass. Modes: full (`gate`, all 5 fixtures + 5 UI flows, ~3-5 min), quick (`gate --quick`, 1 fixture + content UI flow only, ~90s), skip-ui (`gate --skip-ui`, no Playwright needed). The full analyzer suite requires the `.venv-vamp` sidecar (madmom + vamp); without it, the content UI flow auto-skips. **CI runs only the cheap tier** — unit tests, existing generator check, UI smoke flows (no content). The full gate is a **local pre-PR** step; install + runtime cost makes it impractical on fresh CI runners.
- **Validator confidence-write convention** (`src/analyzer/validator.py`): when a downstream pass populates `TimingMark.confidence` before `validate_hierarchy` runs (e.g. `selector.annotate_agreement_confidence` for L2 / L3 agreement), the validator must guard its own assignment with `if mark.confidence is None: mark.confidence = track_score`. Otherwise the bulk per-mark write at the end of each level's block silently clobbers the upstream value. Track-level scalars are still surfaced via `report['<level>']['score']`. This pattern applies to L1 / L4 / L0 marks too if a future change pre-populates them — same `if confidence is None` guard.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- [2026-04-19] Shipped changes that broke previously-working behavior because modified public symbols weren't audited for callers. Before finishing any diff, grep callers of every modified public function/method/CLI arg/schema field across `src/` and `tests/` and update or verify each one.
- [2026-04-19] Applied symptom fixes instead of root-cause fixes — swallowed exceptions with try/except-pass, added input-specific guard clauses, tuned magic numbers with no explanation, hard-coded special cases, post-processed bad output downstream. Always name the root cause first and fix it where it originates.
- [2026-04-19] Did more or less than what was asked — scope drift from unrelated refactors, or incomplete work that missed stated sub-requirements. Always restate the goal in one sentence before coding and verify every hunk of the diff advances that sentence.
- [2026-04-19] Committed work directly to `main` or bundled unrelated changes on an existing feature branch. Every new task starts with `git checkout -b <type>/<slug>` off `main`.
- [2026-04-25] Marked failing tests `pytest.mark.xfail` / `pytest.mark.skip` / CI `--ignore` instead of fixing them. Quarantine is a band-aid that decays into permanent dead code. When a test fails: fix the test, fix the code, or delete the test with a written rationale. The only acceptable quarantine is one paired with a `docs/known-broken-tests.md` entry stating diagnosis, remediation plan, and why it can't be fixed now.
- [2026-04-25] Patched `src.cli._variant_library_override` (the re-export) when consumers read `src.cli_old._variant_library_override` (the canonical). Re-exports do not propagate runtime mutations. Always patch the module the consumer imports from — find it by grepping where the symbol is *read*, not where it's *defined*.
- [2026-04-25] Tests inherited state from prior runs because module-level dicts (`_runs`, `_jobs`, `_library`) accumulate across test invocations. Any fixture that exercises a module holding state at module scope must reset that state explicitly before yielding the app/client.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- [2026-04-19] Added adversarial review discipline to OpenWolf (OPENWOLF.md sections + `/review-diff` command). Chosen over editing built-in `review`/`security-review` skills because those live outside the repo and can't be versioned; chosen over tightening `/speckit.analyze` because the pain is post-implementation (diffs, regressions) not pre-implementation (spec quality).
