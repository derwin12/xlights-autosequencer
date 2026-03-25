"""Stem quality inspection and intelligent sweep config generation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


_STEM_NAMES = ["drums", "bass", "vocals", "guitar", "piano", "other"]

# Which stems each algorithm family works best on.
# Key = algorithm name, value = ordered list of preferred stems (best first).
_STEM_AFFINITY: dict[str, list[str]] = {
    "qm_beats":          ["drums", "bass", "full_mix"],
    "qm_bars":           ["drums", "bass", "full_mix"],
    "beatroot_beats":    ["drums", "full_mix", "bass"],
    "qm_onsets_hfc":     ["drums", "full_mix", "guitar"],
    "qm_onsets_complex": ["drums", "guitar", "full_mix"],
    "qm_onsets_phase":   ["bass", "vocals", "full_mix"],
    "qm_segmenter":      ["full_mix"],
    "qm_tempo":          ["full_mix", "drums"],
    "pyin_notes":        ["vocals", "guitar", "piano", "full_mix"],
    "pyin_pitch":        ["vocals", "guitar", "piano", "full_mix"],
    "chordino":          ["guitar", "piano", "full_mix"],
    "nnls_chroma":       ["guitar", "piano", "full_mix"],
}


# ── Per-stem metrics ──────────────────────────────────────────────────────────

@dataclass
class StemMetrics:
    name: str
    rms: float                  # root-mean-square energy
    peak: float                 # peak absolute sample value
    crest_db: float             # 20·log10(peak/rms) — higher = more transient
    coverage: float             # fraction of frames above noise floor (0–1)
    spectral_centroid_hz: float # mean spectral centroid
    verdict: str                # "keep" | "review" | "skip"
    reason: str                 # human-readable explanation

    @property
    def rms_db(self) -> float:
        return 20.0 * np.log10(max(self.rms, 1e-9))

    @property
    def is_rhythmic(self) -> bool:
        """High crest factor → transient-rich → good for beat/onset detection."""
        return self.crest_db >= 15.0

    @property
    def is_tonal(self) -> bool:
        """High spectral centroid, lower crest → harmonic content."""
        return self.spectral_centroid_hz >= 1500 and self.crest_db < 20.0


def _compute_metrics(name: str, y: np.ndarray, sr: int) -> StemMetrics:
    import librosa

    hop = 512
    rms = float(np.sqrt(np.mean(y ** 2)))
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    crest_db = float(20.0 * np.log10(peak / rms)) if rms > 1e-8 else 0.0

    frame_rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    coverage = float(np.mean(frame_rms > 0.01))

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
    spectral_centroid_hz = float(np.mean(centroid))

    if rms < 0.005 or coverage < 0.12:
        verdict = "skip"
        reason = (
            f"nearly silent (RMS {rms:.4f})" if rms < 0.005
            else f"sparse — only {coverage * 100:.0f}% active"
        )
    elif coverage < 0.40:
        verdict = "review"
        reason = f"intermittent content ({coverage * 100:.0f}% active, crest {crest_db:.1f} dB)"
    else:
        verdict = "keep"
        reason = f"{coverage * 100:.0f}% active, crest {crest_db:.1f} dB, centroid {spectral_centroid_hz:.0f} Hz"

    return StemMetrics(
        name=name,
        rms=rms,
        peak=peak,
        crest_db=crest_db,
        coverage=coverage,
        spectral_centroid_hz=spectral_centroid_hz,
        verdict=verdict,
        reason=reason,
    )


def inspect_stems(
    audio_path: str,
    stem_dir: Optional[Path] = None,
) -> list[StemMetrics]:
    """
    Analyse all available stems for *audio_path* and return per-stem metrics.

    Always includes full_mix as the first entry.
    Looks for stems in <audio_dir>/stems/ or <audio_dir>/.stems/ unless
    *stem_dir* is specified explicitly.
    """
    import librosa

    audio_path_p = Path(audio_path)

    if stem_dir is None:
        for candidate in [
            audio_path_p.parent / "stems",
            audio_path_p.parent / ".stems",
            audio_path_p.parent / audio_path_p.stem / "stems",   # song folder convention
            audio_path_p.parent / audio_path_p.stem / ".stems",
        ]:
            if candidate.exists() and any(candidate.glob("*.mp3")):
                stem_dir = candidate
                break

    results: list[StemMetrics] = []

    # full_mix first
    y, sr = librosa.load(str(audio_path_p), mono=True)
    results.append(_compute_metrics("full_mix", y, sr))

    if stem_dir and stem_dir.exists():
        for name in _STEM_NAMES:
            stem_file = stem_dir / f"{name}.mp3"
            if stem_file.exists():
                try:
                    y_stem, sr_stem = librosa.load(str(stem_file), mono=True)
                    results.append(_compute_metrics(name, y_stem, sr_stem))
                except Exception:
                    pass

    return results


# ── Interactive stem selection ────────────────────────────────────────────────

def interactive_review(
    metrics: list[StemMetrics],
    auto_accept: bool = False,
) -> "StemSelection":
    """
    Present each stem's verdict and allow the user to accept or override it.

    Returns a StemSelection capturing the final keep/skip decision per stem
    and any stems where the user overrode the automatic verdict.
    """
    from src.analyzer.result import StemSelection

    stems: dict[str, str] = {}
    overrides: list[str] = []

    for m in metrics:
        auto_verdict = m.verdict
        # Normalise REVIEW → keep by default (user prompted to confirm)
        default_verdict = "keep" if auto_verdict in ("keep", "review") else "skip"

        if auto_accept:
            stems[m.name] = default_verdict
            continue

        _print_stem_row(m)

        choice = input(f"  [{m.verdict.upper()}] [K]eep  [S]kip  [Enter=accept]: ").strip().lower()
        if choice == "k":
            chosen = "keep"
        elif choice == "s":
            chosen = "skip"
        else:
            chosen = default_verdict

        if chosen != default_verdict:
            overrides.append(m.name)
        stems[m.name] = chosen

    # All-SKIP fallback
    fallback_to_mix = False
    if not any(v == "keep" for v in stems.values()):
        print("\nWARNING: All stems were skipped. Falling back to full mix.")
        stems["full_mix"] = "keep"
        fallback_to_mix = True

    return StemSelection(stems=stems, overrides=overrides, fallback_to_mix=fallback_to_mix)


def _print_stem_row(m: StemMetrics) -> None:
    verdict_label = m.verdict.upper()
    print(
        f"\n  {m.name:<10} {verdict_label:<6}  "
        f"RMS: {m.rms_db:+.1f} dB  Coverage: {m.coverage * 100:.0f}%"
    )
    print(f"             {m.reason}")


# ── Sweep config generation ───────────────────────────────────────────────────

def generate_sweep_configs(
    audio_path: str,
    stem_metrics: list[StemMetrics],
    algorithms: Optional[list[str]] = None,
) -> tuple[list[dict], float]:
    """
    Generate sweep config dicts for each algorithm with intelligently derived
    parameter ranges.

    Returns (configs, estimated_bpm) where configs is a list of dicts each
    containing the JSON-ready sweep config plus a ``_meta`` key with rationale.

    The ``_meta`` key is ignored by SweepConfig.from_file() but useful for
    understanding why the values were chosen.
    """
    import librosa

    y, sr = librosa.load(str(audio_path), mono=True)
    tempo_arr, beats = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo_arr)[0])
    bpm = max(55.0, min(220.0, bpm))

    # Beat stability: low std/mean ratio = confident tempo = good candidate for constraintempo=1
    if len(beats) > 2:
        intervals = np.diff(librosa.frames_to_time(beats, sr=sr))
        tempo_cv = float(np.std(intervals) / (np.mean(intervals) + 1e-9))
    else:
        tempo_cv = 1.0  # uncertain

    stem_map = {m.name: m for m in stem_metrics}
    # Include "review" stems in sweep — the sweep is the right place to evaluate them.
    # Only hard-exclude "skip" stems (nearly silent / too sparse to be useful).
    keep_stems = {m.name for m in stem_metrics if m.verdict in ("keep", "review")}
    keep_stems.add("full_mix")

    all_algorithms = list(_STEM_AFFINITY.keys())
    targets = algorithms if algorithms else all_algorithms

    configs: list[dict] = []
    for alg in targets:
        cfg = _make_config(alg, bpm, tempo_cv, keep_stems, stem_map)
        if cfg is not None:
            configs.append(cfg)

    return configs, bpm


def _preferred_stems_for(
    algorithm: str,
    keep_stems: set[str],
    stem_map: dict[str, StemMetrics],
) -> list[str]:
    """
    Return stems to include in the sweep config for *algorithm*.

    Takes the algorithm's affinity list, keeps only "keep" stems, ensures
    full_mix is always available as a fallback, caps at 3 stems to avoid
    combinatorial explosion.
    """
    affinity = _STEM_AFFINITY.get(algorithm, ["full_mix"])
    selected = [s for s in affinity if s in keep_stems]
    if not selected:
        selected = ["full_mix"]
    return selected[:3]


def _sensitivity_range(stems: list[str], stem_map: dict[str, StemMetrics]) -> list[int]:
    """
    Derive a 4-point sensitivity sweep range from per-stem RMS.

    Quieter stems need higher sensitivity to detect subtle events.
    Louder stems can use lower sensitivity without missing events.

    Typical RMS range: 0.005 (quiet) to 0.15 (loud).
    Maps to sensitivity: 80 (quiet) down to 25 (loud).
    Formula keeps values in [15, 90] at multiples of 5.
    """
    rms_values = [stem_map[s].rms for s in stems if s in stem_map]
    avg_rms = float(np.mean(rms_values)) if rms_values else 0.05

    # Convert to dB then to sensitivity (loud → low, quiet → high)
    rms_db = 20.0 * np.log10(max(avg_rms, 1e-9))
    # rms_db typically −26 dB (loud) to −46 dB (quiet), centred around −35
    base = int(round((-rms_db - 10) / 2)) * 5
    base = max(20, min(70, base))

    candidates = sorted({
        max(10, base - 15),
        base,
        min(85, base + 15),
        min(90, base + 30),
    })
    return candidates


def _bpm_sweep(bpm: float) -> list[int]:
    """
    Three BPM values to sweep around the estimate.

    0.8× handles cases where librosa detected double-time.
    1.0× is the direct estimate.
    1.25× handles cases where librosa detected half-time.
    """
    return sorted({
        max(40, round(bpm * 0.8)),
        round(bpm),
        min(240, round(bpm * 1.25)),
    })


def _make_config(
    algorithm: str,
    bpm: float,
    tempo_cv: float,
    keep_stems: set[str],
    stem_map: dict[str, StemMetrics],
) -> Optional[dict]:
    stems = _preferred_stems_for(algorithm, keep_stems, stem_map)

    # ── Beat / bar trackers ───────────────────────────────────────────────────
    if algorithm in ("qm_beats", "qm_bars", "beatroot_beats"):
        bpm_vals = _bpm_sweep(bpm)
        rationale_parts = [
            f"inputtempo sweeps {bpm_vals} around estimated BPM {bpm:.0f}",
            f"(0.8× / 1.0× / 1.25× to catch half/double-time errors)",
        ]
        sweep: dict = {"inputtempo": bpm_vals}
        fixed: dict = {}

        if algorithm != "beatroot_beats":
            # constraintempo=1 is only reliable when tempo is stable
            if tempo_cv < 0.12:
                fixed["constraintempo"] = 1
                rationale_parts.append(
                    f"tempo CV={tempo_cv:.3f} is stable → constraintempo fixed to 1"
                )
            else:
                sweep["constraintempo"] = [0, 1]
                rationale_parts.append(
                    f"tempo CV={tempo_cv:.3f} is variable → sweeping constraintempo"
                )

        return {
            "algorithm": algorithm,
            "stems": stems,
            "sweep": sweep,
            "fixed": fixed,
            "_meta": {
                "estimated_bpm": round(bpm, 1),
                "tempo_cv": round(tempo_cv, 3),
                "selected_stems": stems,
                "rationale": "; ".join(rationale_parts),
            },
        }

    # ── Onset detectors ───────────────────────────────────────────────────────
    if algorithm in ("qm_onsets_hfc", "qm_onsets_complex", "qm_onsets_phase"):
        dftype_map = {
            "qm_onsets_hfc": 0,
            "qm_onsets_complex": 3,
            "qm_onsets_phase": 2,
        }
        dftype = dftype_map[algorithm]
        dftype_names = {0: "HFC", 1: "SpecDiff", 2: "Phase", 3: "Complex"}

        sens_vals = _sensitivity_range(stems, stem_map)
        rms_values = [stem_map[s].rms for s in stems if s in stem_map]
        avg_rms = float(np.mean(rms_values)) if rms_values else 0.05

        return {
            "algorithm": algorithm,
            "stems": stems,
            "sweep": {"sensitivity": sens_vals},
            "fixed": {"dftype": dftype},
            "_meta": {
                "estimated_bpm": round(bpm, 1),
                "selected_stems": stems,
                "avg_stem_rms": round(avg_rms, 4),
                "dftype": f"{dftype} ({dftype_names[dftype]})",
                "rationale": (
                    f"sensitivity sweeps {sens_vals} derived from avg stem RMS "
                    f"{avg_rms:.4f} ({20 * np.log10(max(avg_rms, 1e-9)):.1f} dB); "
                    f"dftype={dftype} ({dftype_names[dftype]}) fixed"
                ),
            },
        }

    # ── Algorithms with no sweep params: single-pass on best stem ─────────────
    return {
        "algorithm": algorithm,
        "stems": stems,
        "sweep": {},
        "fixed": {},
        "_meta": {
            "selected_stems": stems,
            "rationale": "no tunable parameters; stem selection only",
        },
    }
