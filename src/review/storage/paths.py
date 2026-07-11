import os
from pathlib import Path


def _state_home() -> Path:
    override = os.environ.get("XLIGHT_STATE_HOME")
    if override:
        return Path(override)
    return Path.home() / ".xlight"


def library_root() -> Path:
    return _state_home() / "library"


def library_json_path() -> Path:
    return library_root() / "library.json"


def song_session_path(song_id: str) -> Path:
    return library_root() / "songs" / song_id / "session.json"


def layout_xml_path(layout_id: str) -> Path:
    return _state_home() / "layouts" / f"{layout_id}.xml"
