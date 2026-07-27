"""Packaging helpers for running xLightsAI inside the bundled Windows app.

These modules are imported by the existing backend when `XLIGHT_PACKAGED=1`
is set in the environment (the Tauri launcher sets it). They are also safe
to import in dev mode — `is_bundled()` returns False and the helpers fall
back to existing behavior.
"""
