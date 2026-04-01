# Quickstart: Theme Editor

**Feature**: 026-theme-editor | **Date**: 2026-04-01

## Prerequisites

Same as the existing project — no new system dependencies:

```bash
pip install vamp librosa madmom click pytest flask
brew install ffmpeg  # macOS
```

## Running the Theme Editor

The theme editor is served by the existing Flask review server. Launch it without any song file:

```bash
# Start the server (no analysis file needed for theme editor)
xlight-analyze review

# Or start with a specific port
xlight-analyze review --port 5173
```

Then navigate to: **http://localhost:5173/themes**

### Deep linking

- Open a specific theme: `http://localhost:5173/themes?theme=Inferno`
- Open in edit mode: `http://localhost:5173/themes?theme=Inferno&mode=edit`

## Development

### Backend (Flask API)

New files to create:
- `src/themes/writer.py` — Custom theme file I/O (save, delete, rename)
- `src/review/theme_routes.py` — Flask blueprint with theme CRUD endpoints

Modified files:
- `src/review/server.py` — Register `theme_bp` blueprint, add `/themes` HTML route

### Frontend (Vanilla JS)

New files to create:
- `src/review/static/theme-editor.html` — Editor HTML shell
- `src/review/static/theme-editor.js` — Editor SPA logic
- `src/review/static/theme-editor.css` — Editor styles

Modified files:
- `src/review/static/story-review.js` — Add theme name deep links (open in new tab)

### Tests

```bash
# Run theme writer tests
pytest tests/unit/test_theme_writer.py -v

# Run theme API route tests
pytest tests/unit/test_theme_routes.py -v

# Run all tests
pytest tests/ -v
```

## Custom Theme Storage

Custom themes are stored as individual JSON files:

```
~/.xlight/custom_themes/
├── my-cool-theme.json
├── winter-wonderland.json
└── inferno.json          # Override of built-in "Inferno"
```

The directory is created automatically on the first save.

## Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/themes` | Theme editor HTML page |
| GET | `/themes/api/list` | All themes with metadata |
| GET | `/themes/api/effects` | Available effects and parameters |
| POST | `/themes/api/save` | Create/update a custom theme |
| POST | `/themes/api/delete` | Delete a custom theme |
| POST | `/themes/api/restore` | Restore built-in theme defaults |
| POST | `/themes/api/validate` | Validate without saving |

See [contracts/theme-api.md](contracts/theme-api.md) for full request/response schemas.
