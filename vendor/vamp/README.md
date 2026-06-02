# Vendored Vamp plugins

Prebuilt, **self-contained** Vamp plugin binaries committed to the repo so that
real Vamp analysis works in ephemeral containers (Claude Code web sessions, CI
runners) without a compile step or a network download.

The canonical build-from-source recipe lives in `.devcontainer/Dockerfile`
(the "Build Vamp plugins from source" block). These vendored binaries are the
output of that same recipe, captured here so a fresh container that does *not*
run the Dockerfile (e.g. the web execution environment) still gets working
plugins by pointing `VAMP_PATH` at the directory for its platform.

## Layout

```
vendor/vamp/<platform>/<plugin>.{so,cat,n3}
```

| platform        | target                                  |
|-----------------|-----------------------------------------|
| `linux-x86_64`  | Linux glibc, x86-64                      |

## What's vendored

| plugin             | provides                                          | used by                                  |
|--------------------|---------------------------------------------------|------------------------------------------|
| `segmentino`       | L1 song structure (repetition labels A/B/C)       | `src/analyzer/orchestrator.py`, `src/story/` |
| `nnls-chroma`      | `chordino` chords + `nnls-chroma` chroma          | `src/analyzer/algorithms/vamp_harmony.py`|
| `qm-vamp-plugins`  | segmenter, bar/beat, key, onset, tempo, transcription | `vamp_structure.py`, `vamp_beats.py`, `vamp_onsets.py` |
| `bbc-vamp-plugins` | energy, rhythm, spectral-flux curves              | `vamp_bbc.py`                            |
| `beatroot-vamp`    | beat tracking                                     | `vamp_beats.py`                          |
| `pyin`             | pitch / note events (melody)                      | `vamp_pitch.py`                          |
| `vamp-aubio`       | onset, tempo, note detection                      | `vamp_aubio.py`                          |

This is the complete required panel (see `scripts/start.sh`). All seven `.so`
files are linked to be **self-contained** — `ldd` shows only
`libstdc++`/`libm`/`libgcc_s`/`libc`(/`libpthread`), so no apt packages are
required at runtime:

- The Vamp SDK is baked in statically (`libvamp-sdk.a`, or the SDK's
  `PluginAdapter.o`/`RealTime.o`/`FFT.o` linked directly).
- `qm-vamp-plugins` statically links `libqm-dsp.a` (which bundles its own
  clapack/cblas — no system LAPACK/BLAS needed).
- `segmentino` uses header-only armadillo (no LAPACK runtime dep).
- `vamp-aubio` statically links `libaubio.a` **and** `libfftw3f.a`, dropping
  Ubuntu libaubio's heavy ffmpeg/sndfile transitive chain entirely.

## Activating

`src/analyzer/capabilities.py` discovers plugins via `VAMP_PATH` and the
standard system dirs. To use the vendored set in a session:

```bash
export VAMP_PATH="$PWD/vendor/vamp/linux-x86_64"
```

`scripts/install.sh` copies the vendored binaries for the current platform
into `$VAMP_DIR` automatically (offline fast path) before attempting any
network download.

## Rebuild recipe (linux-x86_64)

The canonical recipe is `.devcontainer/Dockerfile` ("Building Vamp plugins from
source"). The notes below capture the self-contained-link variants used here.

System packages: `build-essential`, `libboost-dev` (build-time, for
nnls-chroma's / pyin's `<boost/*>`), `libaubio-dev`, `libfftw3-dev`,
`libsamplerate0-dev` (for vamp-aubio), `vamp-plugin-sdk`.

Shared deps built once, reused by all plugins (clone from the c4dm GitHub
mirrors): the Vamp SDK — compile `src/vamp-sdk/{PluginAdapter,RealTime,FFT}.cpp`
to `.o` and archive the rest into `libvamp-sdk.a` — and `qm-dsp`
(`make -f build/linux/Makefile.linux64` with the `-msse*` flags stripped for
portability). Let `$SDK` be the SDK clone and
`$ADAPTERS="$SDK/src/vamp-sdk/{PluginAdapter,RealTime,FFT}.o"`.

```bash
# nnls-chroma (chordino + chroma) — static SDK link
git clone --depth 1 https://github.com/c4dm/nnls-chroma && cd nnls-chroma
make -f Makefile.linux VAMP_SDK_DIR=/usr/include \
  CXXFLAGS="-O3 -ffast-math -I/usr/include -fPIC" \
  LDFLAGS="-shared -Wl,-soname=nnls-chroma.so \
           /usr/lib/x86_64-linux-gnu/libvamp-sdk.a -Wl,--version-script=vamp-plugin.map"

# segmentino (L1 sections) — bundles armadillo (in its repo) + qm-dsp
git clone --depth 1 https://github.com/c4dm/segmentino && cd segmentino
for d in qm-dsp vamp-plugin-sdk nnls-chroma; do git clone --depth 1 https://github.com/c4dm/$d; done
touch .repoint.point   # deps placed manually; skip the repoint fetch step
make -f Makefile.linux

# qm-vamp-plugins (segmenter/bar-beat/key/onset/tempo/transcription)
git clone --depth 1 https://github.com/c4dm/qm-vamp-plugins && cd qm-vamp-plugins
mkdir -p lib && ln -sf $QMDSP lib/qm-dsp && ln -sf $SDK lib/vamp-plugin-sdk
sed 's/-msse -msse2 -mfpmath=sse//' build/linux/Makefile.linux64 > /tmp/mk && make -f /tmp/mk

# bbc-vamp-plugins (energy/rhythm/spectral-flux) — needs $SDK/libvamp-sdk.a
git clone --depth 1 https://github.com/bbc/bbc-vamp-plugins && cd bbc-vamp-plugins
make -f Makefile.linux VAMP_SDK_DIR=$SDK

# beatroot-vamp — relink with adapter objects to bake in the SDK
git clone --depth 1 https://github.com/c4dm/beatroot-vamp && cd beatroot-vamp
make -f Makefile.linux VAMP_SDK_DIR=$SDK
g++ -o beatroot-vamp.so *.o $ADAPTERS -shared -Wl,--version-script=vamp-plugin.map

# pyin (pitch/notes) — system boost + adapter objects
git clone --depth 1 https://github.com/c4dm/pyin && cd pyin
make -f Makefile.linux64 plugin CFLAGS="-O3 -fPIC -I/usr/include -I$SDK" \
  PLUGIN_LDFLAGS="-shared -Wl,--version-script=vamp-plugin.map $ADAPTERS"

# vamp-aubio — static libaubio.a + static libfftw3f.a → drops the ffmpeg chain
git clone --depth 1 https://github.com/aubio/vamp-aubio-plugins && cd vamp-aubio-plugins
g++ -shared -fPIC -O3 -o vamp-aubio.so -I$SDK plugins/*.cpp libmain.cpp $ADAPTERS \
  -Wl,--version-script=vamp-plugin.map \
  /usr/lib/x86_64-linux-gnu/libaubio.a /usr/lib/x86_64-linux-gnu/libfftw3f.a -lsamplerate -lm
```

Verify with the project's own detector:

```bash
VAMP_PATH="$PWD/vendor/vamp/linux-x86_64" .venv-vamp/bin/python -c \
  "import vamp; print(vamp.list_plugins())"
```
