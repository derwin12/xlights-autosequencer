# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-19

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
- **Shared-infrastructure modules** (touching any of these requires cross-feature regression check): `src/generator/`, `src/analyzer/`, `src/story/`, `src/themes/`, `src/effects/`.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- [2026-04-19] Shipped changes that broke previously-working behavior because modified public symbols weren't audited for callers. Before finishing any diff, grep callers of every modified public function/method/CLI arg/schema field across `src/` and `tests/` and update or verify each one.
- [2026-04-19] Applied symptom fixes instead of root-cause fixes — swallowed exceptions with try/except-pass, added input-specific guard clauses, tuned magic numbers with no explanation, hard-coded special cases, post-processed bad output downstream. Always name the root cause first and fix it where it originates.
- [2026-04-19] Did more or less than what was asked — scope drift from unrelated refactors, or incomplete work that missed stated sub-requirements. Always restate the goal in one sentence before coding and verify every hunk of the diff advances that sentence.
- [2026-04-19] Committed work directly to `main` or bundled unrelated changes on an existing feature branch. Every new task starts with `git checkout -b <type>/<slug>` off `main`.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- [2026-04-19] Added adversarial review discipline to OpenWolf (OPENWOLF.md sections + `/review-diff` command). Chosen over editing built-in `review`/`security-review` skills because those live outside the repo and can't be versioned; chosen over tightening `/speckit.analyze` because the pain is post-implementation (diffs, regressions) not pre-implementation (spec quality).
