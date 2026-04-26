# tools/render — headless xLights renderer

xLights' macOS App Store build is sandboxed and **cannot run `-r` headlessly**:
during render it tries to `CVDisplayLinkCreateWithCGDisplays` on a display the
sandbox doesn't expose, hits "Fatal exception occurred", and pops a modal
dialog that hangs the process. There is no non-sandboxed macOS build.

The official Linux AppImage IS unsandboxed. So we run xLights inside a
linux/amd64 container under Xvfb with software OpenGL (Mesa llvmpipe).
That produces real FSEQ output (~3s render for a 96s song under emulation).

## One-time setup

```bash
brew install squashfs                # for unsquashfs
./build.sh                           # downloads + extracts AppImage, builds image
```

The AppImage (~98 MB) and extracted tree are gitignored; rerunning `build.sh`
skips the download/extract steps if the cached files are present.

## Render a sequence

```bash
docker run --rm --platform linux/amd64 \
    -v ~/xlights:/work \
    xlights-render \
    /work "/work/My Song.xsq"
```

The bind-mounted show directory must contain:
- the `.xsq` file you're rendering
- the matching `.mp3` (or other audio)
- `xlights_rgbeffects.xml` (model layout)
- `xlights_networks.xml` (controller channel mapping)

The FSEQ lands next to the `.xsq` on the host filesystem.

## Notes

- Rosetta emulation on Apple Silicon runs the renderer at ~1× realtime; native
  amd64 runs ~10×.
- llvmpipe (software OpenGL) is good enough for the render pipeline — no GPU
  passthrough needed.
