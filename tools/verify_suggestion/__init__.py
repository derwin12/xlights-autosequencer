"""End-to-end verifier for show-improvement suggestions.

Given a suggestion number, slug, and "what changed / why" text, this tool:
  1. Regenerates the .xsq for the reference song with the current code state
  2. Renders the FSEQ via tools/render/ (Docker + Xvfb)
  3. Renders the MP4 via xlight-video
  4. Computes per-frame metrics (lit pixels, motion, color diversity, third activations)
  5. Builds a side-by-side comparison MP4 vs the frozen baseline

Output goes to docs/video-samples/. See run.py for the CLI.
"""
