# Quickstart: 024-story-review-flyouts

**Date**: 2026-04-01

## Prerequisites

- Python 3.11+ with project dependencies installed (`pip install -e .` or `pip install -r requirements.txt`)
- A generated song story JSON file (run `xlight-analyze` on any MP3)
- For P2/P3 stories: feature 026-theme-editor must be implemented first

## Development Setup

```bash
# Start the review server with a song story
xlight-analyze review path/to/song_story.json

# Or upload via the web UI
xlight-analyze review
# Then open http://localhost:5173 and upload an MP3
```

## Files to Modify

### P1: Flyout Panel + Details/Moments Tabs

| File | Changes |
|------|---------|
| `src/review/static/story-review.html` | Replace `#sidebar` with `#flyout` structure; add tab bar; update CSS grid |
| `src/review/static/story-review.js` | Add flyout state; refactor `selectSection()`; add tab switching; add open/close handlers; canvas resize on flyout toggle |

### P2: Themes Tab + Drag-and-Drop (requires 026)

| File | Changes |
|------|---------|
| `src/review/static/story-review.html` | Add theme card styles, filter controls, drag-and-drop styles |
| `src/review/static/story-review.js` | Add `renderThemesTab()`; theme data fetching; drag-and-drop handlers; palette strip canvas rendering; theme filter state |

### P3: Recommendations + Bulk Actions (requires 026)

| File | Changes |
|------|---------|
| `src/review/static/story-review.js` | Add recommendation fetching; "Recommended" badge rendering; "Apply to Unassigned" handler |

## Testing

```bash
# Run existing tests (should not break)
pytest tests/ -v

# Manual testing checklist for P1:
# 1. Load a song story in the review UI
# 2. Click a section → flyout should slide in from right
# 3. Verify all detail fields appear (energy, tempo, texture, etc.)
# 4. Click "Moments" tab → moments list should appear
# 5. Dismiss/restore a moment → should persist
# 6. Click close button → flyout slides out, timeline fills full width
# 7. Click a section again → flyout opens to last active tab
# 8. Click a different section while flyout is open → content updates, no flicker
# 9. Resize browser → canvas and flyout should adjust
```

## Architecture Notes

- The review UI is a single HTML file with inline CSS and a single JS file — no build system
- Canvas rendering (timeline, stem tracks) must be re-triggered when flyout opens/closes because canvas width changes
- The `renderTimeline()` function uses `canvas.getBoundingClientRect().width` for all x-coordinate calculations, so it naturally adapts to width changes
- Theme data (P2) comes from endpoints provided by feature 026, not from local JSON files
