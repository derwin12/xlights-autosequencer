# Quickstart: Value Curves Integration

**Feature**: 032-value-curves-integration

## Prerequisites

- Python 3.11+ with project dependencies installed (`pip install -e ".[all]"`)
- At least one analyzed song (with `_hierarchy.json`)
- xLights layout file (`xlights_rgbeffects.xml`)

## Generate a sequence with value curves

```bash
source .venv/bin/activate

# Generate with all value curves (default)
xlight-analyze generate song.mp3 ~/xLights/xlights_rgbeffects.xml

# Generate with brightness curves only
xlight-analyze generate song.mp3 ~/xLights/xlights_rgbeffects.xml --curves brightness

# Generate without value curves (static, for comparison)
xlight-analyze generate song.mp3 ~/xLights/xlights_rgbeffects.xml --curves none
```

## Verify in xLights

1. Open the generated `.xsq` file in xLights
2. Click on any effect placement on the timeline
3. Open the effect settings panel
4. Click on a parameter (e.g., brightness/transparency)
5. The value curve icon should be active (not flat line)
6. Click the value curve icon to see the control points
7. Play the sequence — brightness should visually pulse with the music

## Test with your songs

Good test songs for each curve type:

| Curve type | What to look for | Good test songs |
|-----------|-----------------|-----------------|
| Brightness | Quiet sections dim, loud sections bright | Songs with clear verse/chorus dynamic range |
| Speed | Build sections accelerate, drops peak | EDM, rock with crescendos |
| Color | Subtle saturation shifts with energy | Any song; chord accents visible on pop/rock with clear harmony |

## Run tests

```bash
# Existing value curve unit tests
pytest tests/unit/test_generator/test_value_curves.py -v

# All generator tests
pytest tests/unit/test_generator/ -v

# Integration test (after implementation)
pytest tests/integration/test_generate_with_curves.py -v
```

## Key files to understand

| File | What it does |
|------|-------------|
| `src/generator/plan.py:151` | The activation point — currently disabled with Phase 1 comment |
| `src/generator/value_curves.py` | Core algorithm: extract analysis data, apply curve shapes, downsample |
| `src/generator/models.py` | `EffectPlacement.value_curves` field, `GenerationConfig.curves_mode` (new) |
| `src/generator/xsq_writer.py:417` | Encodes curves into xLights inline format |
| `src/effects/builtin_effects.json` | 33 effects with `analysis_mappings` defining what maps where |
| `src/cli.py:1748` | `generate` command — add `--curves` flag here |
