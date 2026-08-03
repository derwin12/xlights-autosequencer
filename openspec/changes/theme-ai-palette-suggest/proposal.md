# Proposal: AI-suggested palette in the custom theme editor

## Why

Custom themes already exist end-to-end: `POST/PUT /api/v1/themes` persist
`palette`/`accent_palette` to `~/.xlight/custom_themes/*.json`, and
`Theme.tsx`'s `EditDialog` already has working textareas for typing hex
codes by hand. What's missing is a starting point when none of the 21
built-in themes' colors fit a specific song — today that means typing hex
codes from scratch with no song-aware assistance.

This session validated (2026-08-02, manual testing against the user's local
Ollama instance) that a small local model, called with the right technique,
can reliably produce a usable starting palette:

- **`format: "json"` alone is unreliable** — `qwen3:8b` returned valid-but-
  inconsistently-shaped JSON (`{"colors": [...]}`, `{"colorPalette": ...}`,
  `{"$colorPalette": ...}`, malformed duplicate keys, and once a literal
  echoed JSON Schema instead of data).
- **`format: <JSON Schema>` (Ollama's structured-output mode) fixed this
  completely** — 10/10 calls across 2 runs × 5 songs returned a clean, bare
  4-item hex array, 1.2–3.6s per call, zero malformed output, zero timeouts.
- Longer, guideline-heavy prompts made output *worse* (degenerate repetition,
  broken JSON) — the short, direct prompt performed better on an 8B model.
- Two other local models were ruled out: `llamusic/llamusic:3b` (despite
  being music-specialized, unreliable JSON even with schema constraints
  untested — not worth pursuing given `qwen3:8b`'s clean results) and
  `gpt-oss:20b` (too slow — 13GB reasoning model, timed out or only emitted
  its reasoning preamble, never a final answer, even with `think: false`).
- Quality caveat, set expectations accordingly: outputs lean on a handful of
  go-to colors (`#FFD700` gold, `#8A2BE2` purple show up across most genres)
  rather than deeply differentiating every song. It's a decent **starting
  point**, not a finished, always-novel palette — which is exactly why this
  belongs in the existing manual editor (human reviews/adjusts/saves) rather
  than an unattended generation-pipeline decision.

## What Changes

### Backend

**New module `src/review/ai_palette.py`**:

```python
def suggest_palette(
    title: str, artist: str, genre: str, occasion: str,
    ollama_host: str, ollama_model: str, timeout_s: float = 10.0,
) -> list[str] | None:
    ...
```

Uses stdlib `urllib.request` (no new dependency — consistent with the
project's general dependency-minimalism). Builds the validated short prompt,
calls `POST {ollama_host}/api/generate` with the JSON Schema `format`
(array, exactly 4 items, `^#[0-9A-Fa-f]{6}$` pattern), `stream: false`.
Validates the response defensively even though schema-constrained (a
different/future model might not honor it): exactly 4 items, each matching
the hex pattern. Returns `None` on **any** failure — connection refused,
timeout, malformed JSON, wrong shape — never raises. Every failure mode is
unit-testable by mocking `urllib.request.urlopen`.

**New settings keys** (`src/settings.py`'s existing flat
`~/.xlight/settings.json` store, no schema version needed): `ollama_host`
(default `"http://localhost:11434"`), `ollama_model` (default `"qwen3:8b"`).
No new settings UI screen in v1 — edited by hand in the JSON file for now;
a settings screen is a separate, unrelated scope.

**New endpoint** in `src/review/api/v1/themes.py`:

```
POST /api/v1/songs/<song_id>/theme-suggest-palette
```

Looks up the song's `title`/`artist` via `load_library()` (same pattern
`export.py` already uses), reads `genre`/`occasion` from the request body
(the values currently being edited in the dialog, not necessarily the
song's saved genre — the user may be actively changing them), calls
`suggest_palette()`. Returns `{"palette": [...]}` (200) on success or
`{"error": {"code": "ai_unavailable", "message": "..."}}` (200, not a 4xx —
this is an expected, non-exceptional outcome the frontend should handle
gracefully, not treat as a request error) on any failure.

### Frontend

**`Theme.tsx`**: new `suggesting: boolean` field on `EditState`; new
`handleSuggestPalette()` in the `Theme` component (has `song.song_id` in
scope) that POSTs to the new endpoint with the dialog's current
`mood`/`occasion`/`genre` values, and on success replaces `state.palette`
(not `accent_palette` — v1 scope is the main palette only, matching what
was actually validated). On failure, sets `state.error` to a clear message
("AI suggestion unavailable — check Ollama is running") without closing
the dialog or discarding any manual edits already made.

**`EditDialog`**: new "✨ Suggest with AI" button above the Palette
textarea, calling a new `onSuggest` prop, disabled + labeled "Suggesting…"
while in flight (mirrors the existing `saving`/"Saving…" pattern already
on the Save button).

## Alternatives considered

- **Auto-apply during generation** (the originally-scoped idea, before this
  session's pivot) — rejected: requires a whole new fallback-on-failure
  design inside `build_plan()`/`GenerationConfig`, breaks full pipeline
  determinism when enabled, and the validated output quality (decent but
  same-y across genres) isn't strong enough to trust unattended. The
  existing manual editor is a better fit: human always reviews before
  saving.
- **Suggest `accent_palette` too** — deferred: only the 4-color main
  palette prompt was actually validated this session; extending the same
  technique to accent colors is a small follow-up, not bundled here to keep
  this change's tested surface matching its shipped surface.
- **`format: "json"` (string) instead of a JSON Schema** — rejected per the
  session's own findings above: proven unreliable (inconsistent wrapper
  keys, occasional garbage) versus the schema-constrained mode's 10/10
  clean results.
- **A dedicated settings screen for `ollama_host`/`ollama_model`** —
  deferred: no existing settings-screen infrastructure in the review UI to
  build on; hand-editing `settings.json` is sufficient for v1 and avoids
  scope creep into unrelated UI work.

## Files touched

| File | Change |
|---|---|
| `src/review/ai_palette.py` | new — `suggest_palette()` |
| `src/settings.py` | modified — no code change needed (existing `load_settings`/`save_settings` already handle arbitrary keys); documented here as the settings store used |
| `src/review/api/v1/themes.py` | modified — new `POST /songs/<song_id>/theme-suggest-palette` route |
| `src/review/frontend/src/screens/Theme.tsx` | modified — `EditState.suggesting`, `handleSuggestPalette()`, new button in `EditDialog` |
| `tests/unit/test_ai_palette.py` | new — mocked `urlopen`: valid response, malformed JSON, wrong item count, invalid hex pattern, timeout, connection error — all return `None` except the valid case |
| `tests/review/test_api_themes.py` (or equivalent) | modified/new — endpoint returns palette on success, graceful error shape on `suggest_palette()` returning `None`, song-not-found case |
| `openspec/changes/theme-ai-palette-suggest/` (this dir) | new — design artifacts |

## Regression surface

- **`src/settings.py`** — no code changes; two new keys used by convention
  only (the module already accepts arbitrary dict keys). No existing caller
  reads/writes these keys, so no collision risk.
- **`src/review/api/v1/themes.py`** — new route, additive. Existing
  `GET/POST/PUT /themes` routes untouched.
- **`Theme.tsx`** — `EditState` gains one field (`suggesting: boolean`);
  every existing `setEditState({...})` call that doesn't mention it keeps
  working (TypeScript will flag any call site the compiler considers
  incomplete, giving a compile-time check for free). `EditDialog`'s prop
  list gains `onSuggest`; single render site (line ~554) updated.

## Prerequisite / open item: network reachability by deployment mode

This feature has two real deployment targets, with different confidence
levels:

- **Tauri `.exe` (the real end-user deployment)** — checked
  `packaging/tauri/src-tauri/tauri.conf.json`: `"security": {"csp": null}`,
  no Content Security Policy restricting outbound `fetch()` calls from the
  WebView. The bundled backend is a PyInstaller sidecar running as a native
  Windows process on the *same machine* as the user's Ollama install —
  exactly the native-host-to-native-host path this session's live testing
  already exercised successfully. **High confidence this works**, though
  not yet verified end-to-end against the actual compiled `.exe` + sidecar
  (only the config was inspected, not a real packaged run). This is the
  path that actually matters for users — treat as the primary target.
- **Docker (`xlight-dev` devcontainer, dev-only)** — CLAUDE.md documents
  the review server as normally running **inside** this container for
  development, whose `.devcontainer/init-firewall.sh` is a default-deny
  egress allowlist (domains resolved to IPs via `ipset`, not raw
  hostnames). `host.docker.internal` is a Docker-internal address, not a
  resolvable public domain, so it doesn't fit the existing allowlist
  mechanism as-is — this call would likely fail silently (falling back to
  the graceful "AI suggestion unavailable" error path, not crashing
  anything) when developing/testing inside the container. **This is a
  developer-experience gap, not a user-facing blocker** — end users get the
  `.exe`, not the devcontainer. Worth fixing (allowlist the Docker bridge
  gateway IP, or a documented workaround) so contributors can iterate on
  this feature comfortably, but it does not gate shipping the feature
  itself.

## Validation

1. Unit: `tests/unit/test_ai_palette.py` (all failure modes mocked, no real
   network calls in the test suite); endpoint tests with `suggest_palette`
   monkeypatched.
2. Manual, native host (primary target): click "Suggest with AI" in a
   running review server against the real local Ollama instance, confirm
   the palette textarea populates, confirm graceful error display when
   Ollama is stopped.
3. Manual, packaged `.exe` (before considering this "done" for real users):
   repeat step 2 against an actual built `.exe` + PyInstaller sidecar, not
   just the dev server — confirms the config-level analysis above
   (`csp: null`, native sidecar-to-native-Ollama) holds in the real
   packaged artifact.
4. Dev-convenience only, not a ship blocker: check whether the
   `xlight-dev` devcontainer's firewall needs an allowlist fix so
   contributors developing this feature inside the container don't hit a
   silent "AI suggestion unavailable" every time.
