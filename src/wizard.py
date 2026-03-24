"""Interactive CLI wizard for configuring and launching xlight-analyze runs."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

__all__ = [
    "WizardConfig",
    "WizardRunner",
    "WhisperModelInfo",
    "whisper_model_list",
]


# ---------------------------------------------------------------------------
# WizardConfig — captures all user selections; maps to analyze_cmd kwargs
# ---------------------------------------------------------------------------

@dataclass
class WizardConfig:
    """All user selections from the interactive wizard (or defaults for non-interactive)."""

    audio_path: str
    cache_strategy: Literal["use_existing", "regenerate", "skip_write"] = "regenerate"
    algorithm_groups: set = field(default_factory=lambda: {"librosa", "vamp", "madmom"})
    use_stems: bool = True
    use_phonemes: bool = True
    whisper_model: str = "base"
    use_structure: bool = True
    use_genius: bool = True

    def to_analyze_kwargs(self) -> dict:
        """Map WizardConfig fields to analyze_cmd keyword arguments (FR-014)."""
        return {
            "use_stems": self.use_stems,
            "use_phonemes": self.use_phonemes,
            "phoneme_model": self.whisper_model,
            "use_structure": self.use_structure,
            "genius": self.use_genius,
            "no_cache": self.cache_strategy in ("regenerate", "skip_write"),
            "skip_cache_write": self.cache_strategy == "skip_write",
            "include_vamp": "vamp" in self.algorithm_groups,
            "include_madmom": "madmom" in self.algorithm_groups,
        }


# ---------------------------------------------------------------------------
# WhisperModelInfo + model list
# ---------------------------------------------------------------------------

@dataclass
class WhisperModelInfo:
    """Metadata about a single Whisper model variant."""

    name: str
    description: str
    approximate_size_mb: int
    is_cached: bool


def _whisper_model_cached(name: str) -> bool:
    """Return True if the model files exist in a known local cache location."""
    import os
    home = Path.home()
    # faster-whisper / huggingface_hub layout
    hf_cache = home / ".cache" / "huggingface" / "hub"
    # Original openai/whisper layout
    whisper_cache = home / ".cache" / "whisper"
    # Check either cache directory for any entry containing the model name
    for cache_dir in (hf_cache, whisper_cache):
        if cache_dir.exists():
            for entry in cache_dir.iterdir():
                if name in entry.name:
                    return True
    return False


def whisper_model_list() -> list[WhisperModelInfo]:
    """Return info for all supported Whisper model sizes."""
    specs = [
        ("tiny",    "fastest, ~2x realtime, lower accuracy",     75),
        ("base",    "fast, good for clear vocals (default)",     145),
        ("small",   "balanced speed/accuracy",                   461),
        ("medium",  "high accuracy, ~2x slower than small",     1500),
        ("large-v2","highest accuracy, slowest (~4x medium)",   2900),
    ]
    return [
        WhisperModelInfo(
            name=name,
            description=desc,
            approximate_size_mb=size_mb,
            is_cached=_whisper_model_cached(name),
        )
        for name, desc, size_mb in specs
    ]


# ---------------------------------------------------------------------------
# WizardRunner — interactive prompt flow
# ---------------------------------------------------------------------------

class WizardRunner:
    """Guides the user through analysis configuration with arrow-key menus.

    Usage::

        runner = WizardRunner(flags={"non_interactive": False, ...})
        config = runner.run(audio_path)  # None if user cancelled (exit 130)
    """

    def __init__(self, flags: dict | None = None) -> None:
        self._flags: dict = flags or {}

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self, audio_path: Path) -> WizardConfig | None:
        """Execute the wizard and return a WizardConfig, or None if cancelled."""
        config = WizardConfig(audio_path=str(audio_path))

        if not self._detect_tty():
            return self._non_interactive(config)

        try:
            # Step 1: cache
            result = self._step_cache(config, audio_path)
            if result is False:
                return None  # user cancelled
            if config.cache_strategy == "use_existing":
                return config  # short-circuit: no further steps needed

            # Step 2: scope
            result = self._step_scope(config)
            if result is False:
                return None

            # Step 3: Genius lyrics
            result = self._step_genius(config)
            if result is False:
                return None

            # Step 4: Whisper model (conditional)
            if config.use_phonemes:
                result = self._step_whisper_model(config)
                if result is False:
                    return None

            # Step 5: confirm
            if not self._step_confirm(config):
                return None

        except KeyboardInterrupt:
            return None  # clean exit (caller exits with code 130)

        return config

    # ── TTY detection ─────────────────────────────────────────────────────────

    def _detect_tty(self) -> bool:
        if self._flags.get("non_interactive"):
            return False
        return sys.stdin.isatty()

    # ── Non-interactive path ──────────────────────────────────────────────────

    def _non_interactive(self, config: WizardConfig) -> WizardConfig:
        print(
            "Non-interactive mode: using defaults. Use --help for flag options.",
            file=sys.stderr,
        )
        f = self._flags
        if "use_stems" in f:
            config.use_stems = f["use_stems"]
        if "use_phonemes" in f:
            config.use_phonemes = f["use_phonemes"]
        if "phoneme_model" in f and f["phoneme_model"]:
            config.whisper_model = f["phoneme_model"]
        if "use_structure" in f:
            config.use_structure = f["use_structure"]
        if "genius" in f:
            config.use_genius = f["genius"]
        # In non-interactive mode, disable Genius if no token is available
        import os
        if config.use_genius and not os.environ.get("GENIUS_API_TOKEN"):
            config.use_genius = False

        # Cache strategy from flags
        if f.get("use_cache"):
            config.cache_strategy = "use_existing"
        elif f.get("no_cache"):
            config.cache_strategy = "regenerate"
        elif f.get("skip_cache_write"):
            config.cache_strategy = "skip_write"

        # Algorithm groups
        groups: set[str] = {"librosa"}
        if f.get("include_vamp", True):
            groups.add("vamp")
        if f.get("include_madmom", True):
            groups.add("madmom")
        config.algorithm_groups = groups

        return config

    # ── Wizard steps ──────────────────────────────────────────────────────────

    def _step_cache(self, config: WizardConfig, audio_path: Path):
        """Show cache status and prompt for cache strategy."""
        import questionary
        from src.cache import CacheStatus

        status = CacheStatus.from_audio_path(audio_path)

        if status.exists and status.is_valid:
            age_min = (status.age_seconds or 0) // 60
            status_line = f"Cache found — {age_min} minutes ago, valid ({status.track_count} tracks)"
            choices = [
                questionary.Choice("Use existing cache  (skip re-analysis)", value="use_existing"),
                questionary.Choice("Regenerate cache", value="regenerate"),
                questionary.Choice("Skip cache for this run only", value="skip_write"),
            ]
        elif status.exists:
            status_line = "Cache found but stale (source file has changed)"
            choices = [
                questionary.Choice("Regenerate cache", value="regenerate"),
                questionary.Choice("Skip cache for this run only", value="skip_write"),
            ]
        else:
            status_line = "No cache found — analysis will run fresh"
            choices = [
                questionary.Choice("Save result to cache (default)", value="regenerate"),
                questionary.Choice("Skip cache for this run only", value="skip_write"),
            ]

        print(f"\n  {status_line}")
        answer = questionary.select(
            "Cache strategy:",
            choices=choices,
        ).ask()
        if answer is None:
            return False
        config.cache_strategy = answer
        return True

    def _step_scope(self, config: WizardConfig):
        """Choose analysis scope."""
        import questionary
        answer = questionary.select(
            "Analysis scope:",
            choices=[
                questionary.Choice("Full analysis  (all algorithms + stems + phonemes)", value="full"),
                questionary.Choice("Quick analysis  (librosa only, no stems)", value="quick"),
                questionary.Choice("Custom  (choose groups individually)", value="custom"),
            ],
        ).ask()
        if answer is None:
            return False
        if answer == "full":
            config.algorithm_groups = {"librosa", "vamp", "madmom"}
            config.use_stems = True
            config.use_phonemes = True
            config.use_structure = True
        elif answer == "quick":
            config.algorithm_groups = {"librosa"}
            config.use_stems = False
            config.use_phonemes = False
            config.use_structure = False
        else:
            return self._step_custom_groups(config)
        return True

    def _step_custom_groups(self, config: WizardConfig):
        """Custom algorithm group selection."""
        import questionary
        choices = [
            questionary.Choice("Librosa (always included)", value="librosa", checked=True),
            questionary.Choice("Vamp plugins", value="vamp", checked=True),
            questionary.Choice("Madmom", value="madmom", checked=True),
            questionary.Choice("Stem separation", value="stems", checked=True),
            questionary.Choice("Phoneme analysis (vocal transcription)", value="phonemes", checked=False),
        ]
        answer = questionary.checkbox("Select components:", choices=choices).ask()
        if answer is None:
            return False
        config.algorithm_groups = {g for g in ("librosa", "vamp", "madmom") if g in answer}
        config.algorithm_groups.add("librosa")  # always required
        config.use_stems = "stems" in answer
        config.use_phonemes = "phonemes" in answer
        return True

    def _step_genius(self, config: WizardConfig):
        """Ask whether to fetch lyrics from Genius; prompt for API token if missing."""
        import os
        import questionary

        token = os.environ.get("GENIUS_API_TOKEN", "")
        if token:
            status_line = "Genius API token found in environment"
        else:
            status_line = "No GENIUS_API_TOKEN found in environment"

        print(f"\n  {status_line}")
        answer = questionary.confirm(
            "Fetch lyrics and song structure from Genius?", default=True
        ).ask()
        if answer is None:
            return False

        if not answer:
            config.use_genius = False
            return True

        # Token missing — prompt for it
        if not token:
            token = questionary.text(
                "Paste your Genius API token (from genius.com/api-clients):"
            ).ask()
            if not token or not token.strip():
                print("  No token provided — skipping Genius.")
                config.use_genius = False
                return True
            token = token.strip()
            os.environ["GENIUS_API_TOKEN"] = token
            print("  Token set for this session.")

        config.use_genius = True
        return True

    def _step_whisper_model(self, config: WizardConfig):
        """Choose Whisper model size (only shown when phonemes enabled)."""
        import questionary
        models = whisper_model_list()
        choices = []
        for m in models:
            cached_badge = "  [cached locally]" if m.is_cached else ""
            label = f"{m.name:<10}  {m.description}{cached_badge}"
            choices.append(questionary.Choice(label, value=m.name))
        answer = questionary.select("Whisper model for vocal transcription:", choices=choices).ask()
        if answer is None:
            return False
        config.whisper_model = answer
        return True

    def _step_confirm(self, config: WizardConfig) -> bool:
        """Show summary and ask for confirmation."""
        import questionary
        stems_label = "yes" if config.use_stems else "no"
        phonemes_label = f"yes ({config.whisper_model})" if config.use_phonemes else "no"
        genius_label = "yes" if config.use_genius else "no"
        summary = (
            f"  Audio:     {config.audio_path}\n"
            f"  Cache:     {config.cache_strategy}\n"
            f"  Algorithms:{', '.join(sorted(config.algorithm_groups))}\n"
            f"  Stems:     {stems_label}\n"
            f"  Phonemes:  {phonemes_label}\n"
            f"  Genius:    {genius_label}"
        )
        print(summary)
        answer = questionary.confirm("Start analysis?").ask()
        return bool(answer)

