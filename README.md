# xlight-autosequencer

Analyzes MP3 files and generates timing tracks (beats, onsets, chords, stems, phonemes) for use with xLights LED sequencing software.

---

## Prerequisites

### 1. Python 3.11 or 3.12

Install from [python.org](https://www.python.org/downloads/) or via Homebrew:

```bash
brew install python@3.12
```

> **macOS Python.org installer only:** After installing, run the SSL certificate fix once or network-dependent features (demucs model downloads) will fail with SSL errors:
> ```bash
> open "/Applications/Python 3.12/Install Certificates.command"
> ```
> Adjust the version number to match your install.

### 2. ffmpeg

Required for MP3 loading and stem export:

```bash
brew install ffmpeg
```

### 3. Vamp Plugins (optional, recommended)

Vamp plugins provide ~14 high-quality timing tracks. Without them you still get librosa and madmom tracks.

1. Download the following plugin packs from [vamp-plugins.org](https://vamp-plugins.org/pack.html):
   - **QM Vamp Plugins** — bar/beat tracking, onset detection, segmentation
   - **BeatRoot** — beat tracking
   - **pYIN** — pitch and note detection
   - **NNLS Chroma / Chordino** — chord detection
   - **Silvet** — note transcription

2. Copy the `.dylib` files to:
   ```
   ~/Library/Audio/Plug-Ins/Vamp/
   ```
   Create the folder if it doesn't exist.

3. Install the Python Vamp host:
   ```bash
   pip install vamp
   ```

### 4. Vamp + madmom venv (optional, for full track count)

The Vamp Python bindings (`vampyhost`) and `madmom` were compiled against NumPy 1.x and cannot run in the same environment as `whisperx` (which requires NumPy ≥ 2). The solution is a separate virtual environment used only for those algorithms.

```bash
python3.12 -m venv .venv-vamp
source .venv-vamp/bin/activate
pip install "numpy<2" vamp madmom librosa soundfile
deactivate
```

When `.venv-vamp/bin/python` exists, the analyzer automatically routes Vamp and madmom algorithms through it as a subprocess. Without it, those ~14 tracks are silently skipped and only librosa tracks are produced.

### 5. whisperx (optional, for phoneme/lyric analysis)

whisperx transcribes vocals and generates word/phoneme timing tracks. It requires a specific install sequence because of PyTorch dependencies:

```bash
# Install PyTorch first (CPU-only, stable)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Then install whisperx
pip install whisperx

# nltk cmudict data (downloaded automatically on first run, or manually):
python -c "import nltk; nltk.download('cmudict')"
```

> **Note:** You may see a warning about `torchcodec` not being installed correctly. This is harmless — whisperx loads audio a different way and the warning can be ignored.

> **First phoneme run:** whisperx downloads the Whisper model (~145 MB for `base`, up to ~3 GB for `large-v2`) and a wav2vec2 alignment model on first use. These are cached in `~/.cache/` and only download once.

---

## Installation

```bash
git clone <repo>
cd xlight-autosequencer
python3.12 -m venv .venv
source .venv/bin/activate

# Core dependencies
pip install -e .
pip install librosa madmom click flask demucs

# Vamp (if you installed the plugin packs above)
pip install vamp

# whisperx (if you want phoneme analysis — see Prerequisites section above)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install whisperx
```

---

## Running the Review UI

```bash
source .venv/bin/activate
xlight-analyze review
```

Opens a browser at `http://localhost:5173`. From here you can:

- **Song Library** — view previously analyzed songs, click to reopen any analysis
- **Analyze New File** — drag-and-drop or browse for an MP3, choose options, click Analyze
- **Timeline** — visualize timing tracks, play audio, select tracks, export
- **Phonemes** — view word/phoneme timing synchronized with lyrics and audio

### Analysis options

| Option | Description |
|--------|-------------|
| Vamp plugins | ~14 additional tracks via QM/BeatRoot/pYIN/Chordino. Requires Vamp plugin packs installed. |
| madmom | ~2 tracks via RNN beat tracking (slower but high quality). |
| Stem separation (demucs) | Separates audio into drums/bass/vocals/guitar/piano/other. First run downloads ~200 MB model and takes 2–5 min on CPU; subsequent runs use the stem cache. |
| Phonemes (whisperx) | Transcribes vocals and generates word/phoneme timing. Requires stem separation. Requires `whisperx` installed. |

---

## CLI Usage

```bash
source .venv/bin/activate

# Analyze a file (beats, onsets, chords — no stems)
xlight-analyze analyze song.mp3

# With stem separation (routes algorithms to their best stem)
xlight-analyze analyze song.mp3 --stems

# With phoneme analysis (implies --stems, generates .xtiming + .lyrics.txt)
xlight-analyze analyze song.mp3 --phonemes

# Better phoneme timing accuracy (tradeoff: slower, larger model download)
xlight-analyze analyze song.mp3 --phonemes --phoneme-model small
xlight-analyze analyze song.mp3 --phonemes --phoneme-model large-v2

# Re-run phonemes only (skip algorithm cache, use edited lyrics file)
xlight-analyze analyze song.mp3 --phonemes --lyrics song.lyrics.txt --no-cache

# View track quality scores for an existing analysis
xlight-analyze summary song_analysis.json

# Open the review UI (no upload page — jumps straight to timeline)
xlight-analyze review song_analysis.json
```

### Phoneme model sizes

| Model | Download size | Notes |
|-------|--------------|-------|
| `tiny` | ~75 MB | Fastest, least accurate |
| `base` | ~145 MB | Default |
| `small` | ~466 MB | Good balance for most songs |
| `medium` | ~1.5 GB | High accuracy |
| `large-v2` | ~3 GB | Best accuracy, slowest |

### Improving phoneme timing

If the word timing doesn't match the song well:

1. Run analysis with `--phonemes` — this auto-generates a `song.lyrics.txt` file next to the MP3.
2. Open the lyrics file and correct any mis-transcribed words.
3. Re-run with your corrected lyrics and a larger model:
   ```bash
   xlight-analyze analyze song.mp3 --phonemes --phoneme-model small --lyrics song.lyrics.txt --no-cache
   ```
   The lyrics file won't be overwritten on re-runs so your edits are safe.

---

## Output files

All files for a song are saved under `./songs/<song_name>/`:

```
songs/
└── My_Song/
    ├── My_Song.mp3              <- uploaded or analyzed file
    ├── My_Song_analysis.json    <- full analysis result (cached by MD5)
    ├── My_Song.xtiming          <- xLights timing file (phonemes)
    ├── My_Song.lyrics.txt       <- auto-transcribed lyrics (edit and rerun)
    └── stems/
        ├── drums.mp3
        ├── bass.mp3
        ├── vocals.mp3
        ├── guitar.mp3
        ├── piano.mp3
        ├── other.mp3
        └── manifest.json
```

Analyzed songs are also registered in `~/.xlight/library.json` for the library view.

---

## Known Issues & Workarounds

### `SSLCertVerificationError` during demucs model download
Run the Install Certificates command for your Python version (see Prerequisites above). This is only needed for Python.org installs — Homebrew Python includes certs automatically.

### `No module named 'demucs.api'`
The `demucs.api` high-level module does not exist in demucs 4.0.1. The code uses `demucs.pretrained` and `demucs.apply` directly. Ensure you are on demucs ≥ 4.0.1:
```bash
pip install -U demucs
```

### `TorchCodec is required` warning
A harmless warning from pyannote (a whisperx dependency) at import time. The pipeline uses `librosa` and `whisperx.load_audio()` for audio loading and doesn't require torchcodec.

### `FileNotFoundError: ffmpeg` during stem separation
The server may not inherit your shell `PATH`. The code checks `/opt/homebrew/bin/ffmpeg` (Apple Silicon) and `/usr/local/bin/ffmpeg` (Intel) as fallbacks. If ffmpeg is installed somewhere else, add it to your PATH before starting the server:
```bash
export PATH="/your/ffmpeg/location:$PATH"
xlight-analyze review
```

### Stem separation is slow on first run
Demucs (`htdemucs_6s`) runs on CPU by default and takes 2–5 minutes for a typical song. Results are cached in `songs/<name>/stems/` — subsequent runs are instant.

### whisperx alignment model download fails
whisperx downloads a wav2vec2 alignment model from Hugging Face on first use. If this fails with an auth error, you may need a Hugging Face token:
```bash
pip install huggingface_hub
huggingface-cli login
```

---

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

---

## Project Structure

```
src/
├── analyzer/
│   ├── audio.py              # MP3 loading
│   ├── result.py             # Data classes
│   ├── runner.py             # Orchestrates algorithm runs
│   ├── scorer.py             # Quality scoring
│   ├── stems.py              # Demucs stem separation + cache
│   ├── phonemes.py           # WhisperX phoneme analysis
│   ├── xtiming.py            # xLights .xtiming XML writer
│   └── algorithms/           # Individual algorithm implementations
├── cache.py                  # MD5-keyed analysis result cache
├── library.py                # ~/.xlight/library.json song index
├── export.py                 # JSON serialization
├── cli.py                    # Click CLI entry point
└── review/
    ├── server.py             # Flask app
    └── static/               # Browser UI (vanilla JS + Canvas)
```
