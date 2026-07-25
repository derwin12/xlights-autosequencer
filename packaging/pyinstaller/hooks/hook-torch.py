"""PyInstaller hook: torch (CPU-only).

Collect everything except CUDA/ROCm subpackages which we do not ship.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

# NOTE: deliberately not using collect_all("torch") -- it internally calls
# copy_metadata() too and appends its unfiltered whole-directory result to
# datas, which the filtered copy_metadata expansion below can't undo since
# it only appends. Call collect_all's other three steps individually instead.
datas = collect_data_files("torch", include_py_files=True)
binaries = collect_dynamic_libs("torch")
hiddenimports = collect_submodules("torch")

hiddenimports = [m for m in hiddenimports if "cuda" not in m.lower() and "rocm" not in m.lower()]
hiddenimports += [
    "torch._C",
    "torch.jit",
    "torch.nn.functional",
]

# copy_metadata("torch") returns one (whole-directory-src, dest) tuple, which
# PyInstaller recurses internally at build time -- filtering that returned
# list does nothing, since there's nothing to filter. torch's
# dist-info/licenses/third_party tree nests vendored C++ license text
# (kineto/dynolog/prometheus-cpp/civetweb/...) deep enough that several
# paths exceed Windows' 260-char MAX_PATH when bundled as-is; NSIS's
# makensis fails to open them. Expand the directory into individual file
# entries ourselves so the third_party subtree can actually be dropped --
# legal text only, not runtime-required; torch's own top-level LICENSE is
# unaffected.
for src, dest in copy_metadata("torch"):
    src_path = Path(src)
    if not src_path.is_dir():
        datas.append((src, dest))
        continue
    for file_path in src_path.rglob("*"):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(src_path)
        if "licenses/third_party" in rel.as_posix():
            continue
        rel_dir = rel.parent.as_posix()
        file_dest = dest if rel_dir == "." else f"{dest}/{rel_dir}"
        datas.append((str(file_path), file_dest))
