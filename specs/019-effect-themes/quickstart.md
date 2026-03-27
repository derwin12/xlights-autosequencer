# Quickstart: Effect Themes

**Date**: 2026-03-26
**Branch**: `019-effect-themes`

---

## What This Is

A JSON catalog of 21+ composite "looks" — each theme stacks multiple xLights effects with color palettes and blend modes to create a specific visual mood. Tagged by mood, occasion, and genre for downstream selection.

---

## Using the Library in Code

```python
from src.themes.library import load_theme_library

# Load themes (auto-loads effect library for validation)
themes = load_theme_library()

# Look up a theme
inferno = themes.get("Inferno")
print(inferno.mood)        # "aggressive"
print(inferno.occasion)    # "general"
print(inferno.palette)     # ["#FF4400", "#FF8800", "#FFCC00", "#FFFFFF"]
print(len(inferno.layers)) # 3 (Fire + Morph + Shockwave)

# Query by tags
christmas = themes.by_occasion("christmas")
aggressive_rock = themes.query(mood="aggressive", genre="rock")
```

---

## Customizing a Theme

1. Find the theme in `src/themes/builtin_themes.json`
2. Copy its JSON block to `~/.xlight/custom_themes/Inferno.json`
3. Edit layers, palette, or tags
4. Next load picks up the override
