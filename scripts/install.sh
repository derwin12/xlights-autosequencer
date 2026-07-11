#!/usr/bin/env bash
# XLight AutoSequencer — full dependency installer
# Supports macOS (Homebrew) and Linux (Debian/Ubuntu apt)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; exit 1; }
step() { echo -e "\n${YELLOW}▶ $*${NC}"; }

# ── Detect OS ──────────────────────────────────────────────────────────────────
OS="$(uname -s)"
if [[ "$OS" == "Darwin" ]]; then
  PLATFORM="macos"
  VAMP_DIR="$HOME/Library/Audio/Plug-Ins/Vamp"
  LIB_EXT="dylib"
elif [[ "$OS" == "Linux" ]]; then
  PLATFORM="linux"
  VAMP_DIR="/usr/local/lib/vamp"
  LIB_EXT="so"
else
  fail "Unsupported OS: $OS"
fi

echo ""
echo "XLight AutoSequencer — Installer"
echo "Platform: $PLATFORM"
echo ""

# ── 1. System dependencies ─────────────────────────────────────────────────────
step "System dependencies"

if [[ "$PLATFORM" == "macos" ]]; then
  if ! command -v brew &>/dev/null; then
    fail "Homebrew not found. Install from https://brew.sh then re-run."
  fi
  for pkg in ffmpeg python@3.11 node; do
    if brew list "$pkg" &>/dev/null 2>&1; then
      ok "$pkg already installed"
    else
      echo "  Installing $pkg..."
      brew install "$pkg"
    fi
  done
  PYTHON311="$(brew --prefix python@3.11)/bin/python3.11"
  PYTHON_MAIN="python3"
else
  # Linux (Debian/Ubuntu)
  if ! command -v ffmpeg &>/dev/null; then
    echo "  Installing ffmpeg..."
    sudo apt-get install -y ffmpeg
  else
    ok "ffmpeg already installed"
  fi
  if ! command -v npm &>/dev/null; then
    echo "  Installing Node.js/npm..."
    sudo apt-get install -y nodejs npm
  else
    ok "Node.js/npm already installed"
  fi
  # Find a Python 3.11 or 3.12 for .venv-vamp (needs numpy<2 / madmom compat)
  PYTHON311=""
  for py in python3.11 python3.12 python3.10; do
    if command -v "$py" &>/dev/null; then
      PYTHON311="$(command -v "$py")"
      ok "Found $py at $PYTHON311"
      break
    fi
  done
  if [[ -z "$PYTHON311" ]]; then
    echo "  Installing python3.11..."
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
    PYTHON311="$(command -v python3.11)"
  fi
  PYTHON_MAIN="python3"
fi

# ── 2. Vamp plugins (via Vamp Plugin Pack v2.0) ────────────────────────────────
# All required plugins are bundled in the official pack. Individual plugin
# hosts (code.soundsoftware.ac.uk) are offline; GitHub is the only source.
# Pack: https://github.com/vamp-plugins/vamp-plugin-pack/releases/tag/v2.0
step "Vamp plugins → $VAMP_DIR"

mkdir -p "$VAMP_DIR"

# Offline fast path: copy any self-contained binaries vendored in the repo for
# this platform before falling back to a network download. See vendor/vamp/README.md.
if [[ "$PLATFORM" == "linux" ]]; then
  VENDOR_DIR="$REPO_ROOT/vendor/vamp/linux-$(uname -m)"
  if [[ -d "$VENDOR_DIR" ]] && ls "$VENDOR_DIR"/*.so &>/dev/null 2>&1; then
    cp "$VENDOR_DIR"/*.so "$VENDOR_DIR"/*.cat "$VENDOR_DIR"/*.n3 "$VAMP_DIR/" 2>/dev/null || true
    ok "Copied vendored Vamp plugins from $VENDOR_DIR"
  fi
fi

REQUIRED_PLUGINS="qm-vamp-plugins segmentino bbc-vamp-plugins beatroot-vamp pyin nnls-chroma vamp-aubio"
MISSING=""
for p in $REQUIRED_PLUGINS; do
  ls "$VAMP_DIR/${p}."* &>/dev/null 2>&1 || MISSING="$MISSING $p"
done

if [[ -z "$MISSING" ]]; then
  ok "All Vamp plugins already installed"
else
  echo "  Missing:$MISSING"
  echo "  Downloading Vamp Plugin Pack v2.0..."

  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT

  if [[ "$PLATFORM" == "macos" ]]; then
    # ── macOS: mount the DMG, run the Qt IFW installer headlessly ────────────
    # The DMG contains a Qt Installer Framework app, not loose plugin files.
    # We mount it, locate the installer app bundle, run it headlessly with
    # --root to extract plugins to a temp dir, then copy .dylib/.cat/.n3 files.
    DMG_URL="https://github.com/vamp-plugins/vamp-plugin-pack/releases/download/v2.0/Vamp.Plugin.Pack.Installer-2.0.dmg"
    DMG="$TMP_DIR/vamp-pack.dmg"
    curl -sSL --progress-bar "$DMG_URL" -o "$DMG"

    echo "  Mounting disk image..."
    # Remove quarantine attribute that macOS adds to curl-downloaded files
    xattr -rd com.apple.quarantine "$DMG" 2>/dev/null || true
    # Use -plist output so Python can reliably extract the mount point
    PLIST_OUT="$TMP_DIR/hdiutil-attach.plist"
    if ! hdiutil attach "$DMG" -nobrowse -plist > "$PLIST_OUT" 2>&1; then
      warn "hdiutil attach failed. Error output:"
      cat "$PLIST_OUT" >&2
      warn "Run manually to finish installation:"
      warn "  open \"$DMG\""
      warn "  Then copy the .dylib files to: $VAMP_DIR"
    else
      MOUNT_POINT="$(python3 -c "
import plistlib, sys
with open('$PLIST_OUT', 'rb') as f:
    d = plistlib.load(f)
points = [e.get('mount-point','') for e in d.get('system-entities',[]) if e.get('mount-point','')]
print(points[-1] if points else '')
" 2>/dev/null)"

      if [[ -z "$MOUNT_POINT" ]] || [[ ! -d "$MOUNT_POINT" ]]; then
        warn "Could not determine mount point from DMG."
        warn "Run manually to finish installation:"
        warn "  open \"$DMG\""
        warn "  Then copy the .dylib files to: $VAMP_DIR"
      else
        echo "  Mounted at: $MOUNT_POINT"

        # Find the Qt IFW installer executable inside the .app bundle on the DMG
        INSTALLER_APP="$(find "$MOUNT_POINT" -maxdepth 1 -name "*.app" | head -1)"
        if [[ -z "$INSTALLER_APP" ]]; then
          warn "No installer .app found on DMG."
          hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null || true
        else
          # The executable lives at Contents/MacOS/<AppName>
          INSTALLER_BIN="$(find "$INSTALLER_APP/Contents/MacOS" -maxdepth 1 -type f | head -1)"
          xattr -rd com.apple.quarantine "$INSTALLER_APP" 2>/dev/null || true
          INSTALL_ROOT="$TMP_DIR/pack-root"

          echo "  Running installer headlessly (this may take a minute)..."
          if "$INSTALLER_BIN" --root "$INSTALL_ROOT" --accept-licenses \
                              --default-answer --confirm-command install 2>/dev/null; then
            count=0
            while IFS= read -r -d '' f; do
              cp "$f" "$VAMP_DIR/"
              count=$((count + 1))
            done < <(find "$INSTALL_ROOT" \( -name "*.dylib" -o -name "*.cat" -o -name "*.n3" \) -print0)
            ok "Installed $count plugin files from pack"
          else
            warn "Headless installer failed (may need a display). Run manually:"
            warn "  open \"$DMG\""
            warn "  Then install to: $VAMP_DIR"
          fi

          hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null || true
        fi
      fi
    fi

  else
    # ── Linux: run the Qt self-extracting installer headlessly ───────────────
    INSTALLER_URL="https://github.com/vamp-plugins/vamp-plugin-pack/releases/download/v2.0/vamp-plugin-pack-installer-2.0"
    INSTALLER="$TMP_DIR/vamp-pack-installer"
    curl -sSL --progress-bar "$INSTALLER_URL" -o "$INSTALLER"
    chmod +x "$INSTALLER"

    # Qt Installer Framework supports --root + --accept-licenses for headless install
    INSTALL_ROOT="$TMP_DIR/pack-root"
    if "$INSTALLER" --root "$INSTALL_ROOT" --accept-licenses --default-answer \
                    --confirm-command install 2>/dev/null; then
      count=0
      while IFS= read -r -d '' f; do
        sudo cp "$f" "$VAMP_DIR/"
        count=$((count + 1))
      done < <(find "$INSTALL_ROOT" \( -name "*.so" -o -name "*.cat" -o -name "*.n3" \) -print0)
      ok "Installed $count plugin files from pack"
    else
      # Fallback: try apt for the plugins it carries
      echo "  Qt installer requires a display — trying apt instead..."
      sudo apt-get install -y --quiet \
        vamp-plugin-sdk vamp-examples \
        libvamp-sdk2 2>/dev/null || true
      # vamp-aubio via apt
      sudo apt-get install -y --quiet vamp-aubio-plugins 2>/dev/null || true
      warn "Some plugins (segmentino, qm-vamp, beatroot, pyin, nnls-chroma) require"
      warn "the Vamp Plugin Pack installer. Download and run manually:"
      warn "  $INSTALLER_URL"
      warn "Or install with a display: xvfb-run $INSTALLER"
    fi
  fi
fi

# Final count
plugin_count=$(find "$VAMP_DIR" -name "*.${LIB_EXT}" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$plugin_count" -eq 0 ]]; then
  warn "No Vamp plugins found in $VAMP_DIR"
  warn "Download the pack manually: https://github.com/vamp-plugins/vamp-plugin-pack/releases/tag/v2.0"
else
  ok "$plugin_count Vamp plugin libraries present"
fi

# ── 3. Set VAMP_PATH persistently ─────────────────────────────────────────────
step "VAMP_PATH environment variable"

if [[ "$PLATFORM" == "linux" ]]; then
  VAMP_ENV_LINE="VAMP_PATH=\"$VAMP_DIR\""
  if grep -qF "VAMP_PATH" /etc/environment 2>/dev/null; then
    ok "VAMP_PATH already in /etc/environment"
  else
    echo "$VAMP_ENV_LINE" | sudo tee -a /etc/environment > /dev/null
    ok "Added VAMP_PATH to /etc/environment"
  fi
fi

# Also write to a local env file used by start.sh
ENV_FILE="$REPO_ROOT/.env"
if grep -qF "VAMP_PATH" "$ENV_FILE" 2>/dev/null; then
  ok "VAMP_PATH already in .env"
else
  echo "export VAMP_PATH=\"$VAMP_DIR\"" >> "$ENV_FILE"
  ok "Added VAMP_PATH to .env"
fi

# ── 4. Main Python venv ────────────────────────────────────────────────────────
step "Main Python virtualenv (venv/)"

if [[ ! -d "$REPO_ROOT/venv" ]]; then
  $PYTHON_MAIN -m venv "$REPO_ROOT/venv"
  ok "Created venv/"
else
  ok "venv/ already exists"
fi

# shellcheck source=/dev/null
source "$REPO_ROOT/venv/bin/activate"

echo "  Installing main package and dependencies..."
pip install --quiet --upgrade pip
# Always re-install in editable mode to pick up branch changes and clear stale bytecode
find "$REPO_ROOT/src" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
pip install --quiet --force-reinstall --no-deps -e "$REPO_ROOT"
pip install --quiet -e "$REPO_ROOT"
ok "Main package installed"

# ── 5. .venv-vamp (Python ≤3.12, numpy<2 for madmom/vamp ABI) ─────────────────
step ".venv-vamp virtualenv (madmom + vamp Python bindings)"

if [[ ! -d "$REPO_ROOT/.venv-vamp" ]]; then
  "$PYTHON311" -m venv "$REPO_ROOT/.venv-vamp"
  ok "Created .venv-vamp/"
else
  ok ".venv-vamp/ already exists"
fi

VAMP_PYTHON="$REPO_ROOT/.venv-vamp/bin/python"

# Recreate venv if missing or built with wrong Python version (needs <=3.12 for madmom/vamp ABI)
VAMP_PY_VERSION=""
if [[ -f "$VAMP_PYTHON" ]]; then
  VAMP_PY_VERSION="$("$VAMP_PYTHON" -c 'import sys; print(sys.version_info.major*100+sys.version_info.minor)' 2>/dev/null || echo 0)"
fi
if [[ ! -f "$VAMP_PYTHON" ]] || [[ "$VAMP_PY_VERSION" -gt 312 ]] || [[ "$VAMP_PY_VERSION" -lt 309 ]]; then
  echo "  .venv-vamp missing or wrong Python version (got $VAMP_PY_VERSION, need 3.9–3.12) — recreating..."
  rm -rf "$REPO_ROOT/.venv-vamp"
  "$PYTHON311" -m venv "$REPO_ROOT/.venv-vamp"
fi

# Check if already set up
if "$VAMP_PYTHON" -c "import vamp, madmom" &>/dev/null 2>&1; then
  ok "vamp + madmom already installed in .venv-vamp"
else
  echo "  Installing numpy<2 into .venv-vamp..."
  "$VAMP_PYTHON" -m pip install --quiet --upgrade pip
  "$VAMP_PYTHON" -m pip install --quiet "numpy>=1.24,<2"
  echo "  Installing build prerequisites (Cython)..."
  "$VAMP_PYTHON" -m pip install --quiet "Cython<3"
  echo "  Installing vamp (no build isolation)..."
  "$VAMP_PYTHON" -m pip install --quiet --no-build-isolation vamp
  echo "  Installing madmom (no build isolation)..."
  "$VAMP_PYTHON" -m pip install --quiet --no-build-isolation \
    "madmom @ git+https://github.com/CPJKU/madmom.git"
  echo "  Installing demucs..."
  "$VAMP_PYTHON" -m pip install --quiet demucs
  "$VAMP_PYTHON" -m pip install --quiet -e "$REPO_ROOT"
  ok "vamp + madmom installed in .venv-vamp"
fi

# WhisperX and syncedlyrics — checked separately so they install even if
# vamp/madmom were already present from a previous run.
if "$VAMP_PYTHON" -c "import whisperx" &>/dev/null 2>&1; then
  ok "whisperx already installed in .venv-vamp"
else
  echo "  Installing whisperx (lyric alignment)..."
  "$VAMP_PYTHON" -m pip install --quiet whisperx
  # whisperx may pull in numpy>=2 which breaks vamp/madmom compiled extensions.
  # Force numpy back to <2 after whisperx is installed.
  echo "  Restoring numpy<2 (vamp/madmom ABI compatibility)..."
  "$VAMP_PYTHON" -m pip install --quiet "numpy>=1.24,<2"
  ok "whisperx installed in .venv-vamp"
fi

if "$VAMP_PYTHON" -c "import syncedlyrics" &>/dev/null 2>&1; then
  ok "syncedlyrics already installed in .venv-vamp"
else
  echo "  Installing syncedlyrics (lyric-anchored boundary refinement)..."
  "$VAMP_PYTHON" -m pip install --quiet syncedlyrics
  ok "syncedlyrics installed in .venv-vamp"
fi

# ── 6. Frontend build (review UI) ─────────────────────────────────────────────
step "Frontend build (src/review/frontend/)"

if ! command -v npm &>/dev/null; then
  fail "npm not found. Install Node.js (https://nodejs.org) then re-run."
fi

(
  cd "$REPO_ROOT/src/review/frontend"
  echo "  Installing frontend dependencies..."
  npm install --silent
  echo "  Building frontend bundle..."
  npm run build --silent
)
ok "Frontend built to src/review/frontend/dist/ (git-ignored — rebuild after pulling frontend changes)"

# ── 7. Verify ─────────────────────────────────────────────────────────────────
step "Verifying capabilities"

export VAMP_PATH="$VAMP_DIR"

# vamp/madmom/demucs live in .venv-vamp — verify from there
"$REPO_ROOT/.venv-vamp/bin/python" -c "
import sys, os
os.environ['VAMP_PATH'] = '$VAMP_DIR'
sys.path.insert(0, '$REPO_ROOT')
from src.analyzer.capabilities import detect_capabilities
caps = detect_capabilities()
labels = {
    'vamp':      'Vamp plugins (segmentino, QM, BBC, pYIN…)',
    'madmom':    'madmom beat tracking',
    'demucs':    'Demucs stem separation',
    'essentia':  'Essentia (optional)',
    'whisperx':  'WhisperX phonemes (optional)',
}
all_good = True
for k, label in labels.items():
    v = caps.get(k, False)
    icon = '✓' if v else ('⚠' if k in ('essentia','whisperx') else '✗')
    if not v and k not in ('essentia','whisperx'):
        all_good = False
    print(f'  {icon} {label}')
if not all_good:
    sys.exit(1)
"

echo ""
echo -e "${GREEN}Installation complete.${NC}"
echo "Run ./scripts/start.sh to launch the UI."
