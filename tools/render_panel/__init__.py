"""Repeatable visual-render harness.

Generates sequences with the repo's own generator, renders them through
headless xLights to MP4, and tiles frames into a contact sheet. Runs
entirely in a Linux amd64 environment (no macOS, no Docker-in-Docker) —
the same machinery the ``tools/render/`` Docker image provided, called
directly. See README.md.
"""
