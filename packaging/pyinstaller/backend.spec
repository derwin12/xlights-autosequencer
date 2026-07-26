# PyInstaller spec for the XLight backend sidecar.
#
# Builds a Windows onedir executable consumed by Tauri as an externalBin
# sidecar. The executable must be renamed to `backend-x86_64-pc-windows-msvc`
# by `packaging/scripts/build-backend.ps1` before Tauri will accept it.
#
# Targets one arch at a time (pass --target-arch to pyinstaller CLI).

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

REPO_ROOT = Path(SPECPATH).resolve().parent.parent  # packaging/pyinstaller/ -> repo root

# ── Collect heavy native stacks ─────────────────────────────────────────
# collect_all returns (datas, binaries, hiddenimports). We aggregate.
datas = []
binaries = []
hiddenimports = []

for pkg in ["madmom", "librosa", "soundfile", "demucs"]:
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        # Optional deps: skip if not installed on this build machine.
        continue
    datas += d
    binaries += b
    hiddenimports += h

# Torch is deliberately NOT collected here via collect_all("torch") --
# collect_all() internally calls copy_metadata() too, which bundles torch's
# dist-info directory whole (including its deeply-nested third-party license
# text, which exceeds Windows' MAX_PATH). PyInstaller auto-applies the custom
# hook-torch.py in packaging/pyinstaller/hooks/ whenever torch appears in the
# module graph (e.g. via demucs above), which already collects everything
# collect_all("torch") would -- submodules, dynamic libs, data files -- while
# filtering that metadata tree down to individual files and excluding the
# offending subtree. Calling collect_all("torch") here duplicated that same
# unfiltered whole-directory copy back in, undoing the hook's fix.

# ── Application data — builtin JSON catalogs ────────────────────────────
datas += [
    (str(REPO_ROOT / "src/effects/builtin_effects.json"), "src/effects"),
    (str(REPO_ROOT / "src/themes/builtin_themes.json"), "src/themes"),
    # The one, fixed layout — never uploaded/replaced per-user (see
    # src/paths.py::get_committed_layout_xml_path/get_committed_networks_xml_path).
    # Destination "layout" matches _repo_root()'s sys._MEIPASS resolution
    # when frozen.
    (str(REPO_ROOT / "layout/xlights_rgbeffects.xml"), "layout"),
    (str(REPO_ROOT / "layout/xlights_networks.xml"), "layout"),
]
# Variant builtins folder (feature 033)
variants_root = REPO_ROOT / "src/variants/builtins"
if variants_root.is_dir():
    datas += [(str(p), str(p.parent.relative_to(REPO_ROOT))) for p in variants_root.glob("*.json")]

# ── Hidden imports known to be missed by auto-detection ─────────────────
hiddenimports += [
    "madmom.ml.nn.layers",
    "madmom.audio.comb_filters",
    "librosa.util.exceptions",
    "scipy.sparse.csgraph._validation",
    "sklearn.utils._cython_blas",
    "demucs.pretrained",
    "demucs.apply",
    "torch._C",
    "torch.jit",
    "pkg_resources.py2_warn",
]

# src.analyzer.algorithms.registry loads every algorithm module via
# importlib.import_module(module_path) with module_path as a runtime string
# from a list, not a literal `import` statement -- invisible to PyInstaller's
# static bytecode analysis, so none of librosa_beats.py, madmom_beat.py, the
# vamp_*.py modules, etc. were ever bundled (bug found 2026-07-25: every
# algorithm silently failed to import in the frozen exe, algo_map ended up
# empty, and _build_algorithm_list's _add() calls returned False with no
# warning printed anywhere -- the packaged app produced zero beat/bar/onset
# tracks for every song regardless of capabilities, and the story builder
# collapsed every song into one flat "intro" section). collect_submodules
# walks the real package directory at build time and lists every .py file
# under it, so future new algorithm files are covered automatically instead
# of needing a hand-maintained list here.
hiddenimports += collect_submodules("src.analyzer.algorithms")


a = Analysis(
    [str(REPO_ROOT / "src/review/bundled_entrypoint.py")],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(REPO_ROOT / "packaging/pyinstaller/hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Keep the bundle lean — we don't use any GUI toolkit.
        "tkinter",
        "matplotlib",
        # Torch CUDA / ROCm subpackages.
        "torch.cuda",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="backend",  # renamed to backend-x86_64-pc-windows-msvc by build script
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX breaks codesigning
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # set via pyinstaller --target-arch flag
    codesign_identity=None,  # signing done post-build by sign-backend.sh
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="backend",
)
