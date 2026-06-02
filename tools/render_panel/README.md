# tools/render_panel — repeatable visual-render harness

One command takes a song + your xLights layout all the way to a **contact
sheet of the actual rendered light show**, using the repo's own generator
and headless xLights. This is the visual feedback loop: change generator
code, re-render, look at the result — no desk, no Mac, no Docker.

```
song.mp3 ──generate──▶ .xsq ──xLights -r──▶ .fseq ──src.video──▶ .mp4 ──ffmpeg──▶ contact_sheet.jpg
            (repo generator)   (headless)       (ortho+bloom)        (stills tiled)
```

Unlike `tools/render/` (a Docker image wrapping the Linux xLights AppImage
so it can run on a Mac), this runs xLights **directly** in any Linux amd64
environment — including a Claude Code container. The container *is* the
unsandboxed Linux box the Docker image was emulating.

## One-time system deps

The harness needs Xvfb, a software-GL stack, and ffmpeg:

```bash
apt-get install -y xvfb ffmpeg libgl1 libosmesa6 libgtk-3-0 \
    libsdl2-2.0-0 libwebkit2gtk-4.1-0 libegl1 libgles2 squashfs-tools
```

Then fetch xLights itself (downloads ~98 MB, extracts under
`tools/render/xlights/`, both gitignored):

```bash
python -m tools.render_panel.run setup
```

## Render one song

```bash
python -m tools.render_panel.run render \
    --song path/to/song.mp3 \
    --layout ~/xlights/xlights_rgbeffects.xml \
    --networks ~/xlights/xlights_networks.xml \
    --story  path/to/song_story.json     # optional, see note below
```

Writes `render-out/<slug>/`: the `.xsq`, `.mp4`, extracted frames, and
`<slug>_contact_sheet.jpg`. Prints a JSON summary including the model
**placement count** — `0` means the generator produced an unlit
timing-only sequence (see note).

## Committed fixture — the standing visual loop

A ready-to-run panel lives at `tests/fixtures/render_panel/`:

- `xlights_rgbeffects.xml` — a real 81-prop show layout.
- `xlights_networks.xml` — sanitized (placeholder IPs, generic machine name);
  channel structure preserved so rendering is faithful.
- `maple_leaf_rag_story.json`, `nostalgic_piano_story.json` — librosa-derived
  sections with song-normalized energy, so the generator places effects
  without the vamp segmenter.
- `manifest.json` — wires the above to the two CC0 songs.

Run it in any session (songs are gitignored — fetch them first):

```bash
python -m tests.validation.download_fixtures              # fetch CC0 mp3s
python -m tools.render_panel.run setup                    # fetch xLights (once)
python -m tools.render_panel.run panel \
    --manifest tests/fixtures/render_panel/manifest.json
```

That's the repeatable feedback loop: change generator code → run the panel →
look at `render-out/panel_contact_sheet.jpg`.

## Render a panel

```bash
python -m tools.render_panel.run panel --manifest panel.json
```

`panel.json` (relative paths resolve against the manifest's directory):

```json
{
  "layout":   "xlights_rgbeffects.xml",
  "networks": "xlights_networks.xml",
  "songs": [
    {"song": "maple_leaf_rag.mp3", "story": "maple_story.json"},
    {"song": "space_ambience.mp3"}
  ]
}
```

Renders each song and tiles every song's mid-frame into
`render-out/panel_contact_sheet.jpg`, plus `panel_results.json`. Songs that
rendered unlit (0 placements) are listed at the end.

## Note: the `--story` flag and unlit sequences

The generator places effects **per section**. Section detection comes from
the vamp QM segmenter; with a librosa-only analysis environment (no vamp),
analysis finds 0 sections, so the generator emits a timing-only `.xsq` with
**no effects on any model** — the render comes out black. The harness warns
when this happens (`0 model placements`).

To get a lit render in a librosa-only environment, pass a `--story` JSON
that supplies the section boundaries and roles (the same schema the review
UI writes as `<song>_story.json`). With vamp/madmom installed, real
sections drive placement and `--story` is unnecessary.

> The silent-empty-sequence behavior itself (generator should fall back to
> a single whole-song section instead of emitting nothing) is a generator
> bug tracked separately — this harness only surfaces it, it doesn't fix it.

## Notes / limits

- The MP4 renderer is an **approximation** (orthographic projection +
  bloom), good for "is this section lit / what's the palette / does motion
  change" — not a pixel-accurate simulation of your physical display.
- Each `panel` song uses its own Xvfb display (`:80+i`); `render` uses
  `:89`. The harness starts and tears down Xvfb itself.
- Artifacts under `render-out/` are scratch — gitignore or delete them.
