---
description: Adversarial review of the current branch's diff against main. Catches regressions, intent drift, hacky fixes, and engineering-principle violations.
---

## User Input

```text
$ARGUMENTS
```

Optional argument — a ref to diff against (default: `main`). Use to review against a different base branch.

## Preflight

1. Run `git branch --show-current`. If the result is `main` or `master`, STOP and tell the user: "Create a feature branch first — `/review-diff` is a merge gate, not something to run on main."
2. Determine the base ref:
   - If `$ARGUMENTS` is non-empty, use it.
   - Else use `main`.
3. Run `git rev-list --count <base>..HEAD`. If 0, STOP with "No commits ahead of `<base>` — nothing to review."
4. Collect the diff:
   - `git diff <base>...HEAD` (full diff)
   - `git diff --stat <base>...HEAD` (file counts)
   - `git log <base>..HEAD --pretty=format:"%h %s%n%b"` (commit messages + bodies)

## Review Passes

Apply the adversarial passes from `.wolf/OPENWOLF.md` → **Code Review Discipline**. Be suspicious, not agreeable. Cite `file:line` for every finding. Do not summarize — enumerate.

### 1. Intent conformance

- Restate the goal in one sentence (from the most recent commit message subject, or the `specs/` entry if the branch name matches `NNN-slug`).
- For each hunk: advances the goal? If not → **SCOPE DRIFT**.
- Anything in the goal not addressed by the diff? → **INCOMPLETE**.
- Did the implementation silently diverge from the plan? → **APPROACH DRIFT**.

### 2. Regression surface

For each modified public symbol (module-level function, class method, CLI command/arg, JSON/XML schema field):

- Grep callers across `src/` and `tests/`.
- Flag callers not updated → **BROKEN CALLER**.
- If no tests exist for the pre-change behavior → **UNCOVERED CHANGE**.

For shared-infrastructure modules (`src/generator/`, `src/analyzer/`, `src/story/`, `src/themes/`, `src/effects/`): list which features share the module and confirm their tests still pass. Flag untested dependents → **CROSS-FEATURE RISK**.

### 3. Root-cause discipline

For every bug fix commit: the commit body MUST include a one-line root cause ("X happens because Y"). Missing → **UNDIAGNOSED FIX**.

Grep the diff for these patterns and flag each occurrence:

| Pattern | Flag |
|---|---|
| `try:` block with `except ... : pass` / `return None` / `return []` / bare log | **SWALLOWED ERROR** |
| New `if X == "specific_value"` or `if name in {...}` guards on bug-fix commits | **INSTANCE-ONLY FIX** |
| Numeric literal changes with no test, no comment on why | **UNJUSTIFIED TUNING** |
| Hard-coded entries added to dicts/maps to work around bad data | **HARD-CODED PATCH** |
| Comments matching `(?i)(hack|workaround|temporary|todo.*fix|fixme)` | **ADMITTED BAND-AID** |
| Output sanitization/post-processing that implies upstream produced bad data | **FIX IN WRONG LAYER** |
| `var = None` or default-on-exception that hides broken state downstream | **DEFENSIVE MASK** |

Bug fix with no test that would have failed before → **NO REGRESSION TEST**.

### 4. Engineering-principle check (CLAUDE.md rules applied to the diff)

- Dead code (commented-out blocks, unused imports/functions, `# removed` markers) → **DEAD CODE**
- New helpers/classes/params used once → **SPECULATIVE ABSTRACTION**
- Unrelated refactors not required by the task → **DRIVE-BY REFACTOR**
- Comments explaining WHAT instead of WHY → **NOISE COMMENT**
- Backcompat shims / feature flags not asked for → **UNREQUESTED SHIM**

### 5. Test discipline

- New feature files with no matching test → **UNTESTED FEATURE**
- Tests that re-assert the implementation (tautological) → **USELESS TEST**
- Happy-path-only coverage on error-prone changes → **HAPPY-PATH ONLY**

## Output Format

```markdown
## Adversarial Review: <branch name>

**Goal:** <one-sentence restatement>
**Base:** <base ref>  **Commits ahead:** N  **Files touched:** M

### CRITICAL (blocks merge)
- [CATEGORY] path/to/file.py:42 — concrete issue; why it blocks merge

### HIGH (fix before merge unless justified in reply)
- ...

### MEDIUM
- ...

### LOW
- ...

### Intent check
- Goal: ...
- Diff match: ...
- Unaddressed from goal: ...
- Out-of-scope in diff: ...

### Regression surface
- Modified public symbols: ...
- Broken callers: ...
- Uncovered changes: ...
- Cross-feature risks: ...

### Recommended actions
1. ...
2. ...
```

## Rules

- Cite `file:line` for every finding. No generic feedback.
- Enumerate — do not summarize. 20 concrete findings beats 3 vague ones.
- Prefer false positives over false negatives. The point is to catch what slips through.
- Do not modify any files. This command is read-only.
- Severity bar: CRITICAL = breaks prod or breaks previously-passing tests. HIGH = regression risk, scope drift, undiagnosed fix. MEDIUM = principle violation, test gap. LOW = style, naming, minor cleanup.
- If nothing is wrong, say so briefly with the coverage statistics. Do not invent issues.

## Context

$ARGUMENTS
