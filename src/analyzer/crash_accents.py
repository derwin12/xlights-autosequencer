"""Rare whole-house crash/transient detection (cymbal-stem isolation score).

Third design (2026-07-16). History, because this module has been wrong twice:

1. **v1 (2026-07-14)**: full-spectrum onset strength on the full mix.
   Failed both ways on its own target song (Dream On/Aerosmith): missed both
   known crashes and flagged the track's cold open — the quietest moment in
   the song — because transitioning out of near-silence produces the largest
   relative spectral-flux spike in the track.

2. **v2 (recalibration, 2026-07-14/15)**: treble-band (>=4000Hz) onset
   envelope on the full mix + a pre-transient RMS floor + a 6.0x ratio
   floor. Fixed the cold-open false positive, but bug-266 (2026-07-16)
   showed it never worked on the real generation audio: the 10s min-gap was
   applied inside ``find_peaks`` candidate-picking, so a stronger nearby
   peak (186.31s) suppressed the true crash (190.21s) before it was ever
   scored, and 5 unrelated moments cleared the "rare" floor — the "single
   6.17x standout" of its validation did not reproduce across rips. The
   full-mix treble band was the underlying problem: vocal sibilance and
   bright guitar compress the gap between "hero crash" and "loud moment".

3. **v3 (this design)**: isolation-scored envelope analysis on a
   **cymbal-isolated stem** (drumsep chained on the demucs drums stem — see
   src/analyzer/drum_stems.py). Validated 2026-07-16 on 6 user-confirmed
   Dream On crashes: all 6 rank top-6 with a clean score gap on a
   crash-isolated stem — including the 50.85s crash v2 formally accepted as
   undetectable — and 5/6 top-5 on a combined cymbals stem, while the outro's
   wall-of-continuous-cymbals moments (which swamped every full-mix
   formulation) score near zero. Two features carry the discrimination:

   - **isolation**: envelope peak height over the median cymbal-stem level
     in the preceding 8s. A hero crash erupts out of local cymbal-silence;
     a crash inside an already-crashing outro does not.
   - **wash area**: envelope area above the pre-crash background, bounded
     6s. A hero crash stays bright for seconds; ordinary hits are narrow.
     (Raw area alone was tested and rejected: with no isolation term it
     degenerates into "how loud is the loudest section".)

   Score = log1p(isolation) x log1p(wash_area / median wash_area). Kept
   from v2, verbatim: the full-mix pre-transient RMS floor — the cold-open
   false positive must stay dead. Changed from v2: the min-gap is enforced
   post-scoring (keep the higher-scored of any conflicting pair) and
   shrunk to 3s (the confirmed 122.0s/125.0s pair is 3s apart), and the
   cap is 6 (raised from 5 per user decision 2026-07-16; Dream On
   legitimately has 6 confirmed crashes). Known accepted miss: the 163.5s
   crash rides a tom fill and drumsep routes its energy to the toms/snare
   stems, so it never becomes a candidate on the platillos stem.

Rare by design: the absolute score floor means most songs emit zero marks.
No cymbals stem available -> the orchestrator emits no marks at all; for
this feature zero marks beats wrong marks.

Vocal-proximity exclusion is intentionally NOT applied here — it depends on
WhisperX word timing, which is a generator-side input
(``GenerationConfig.vocal_words``). See
``src/generator/effect_placer.py::_place_crash_accents``.

See openspec/changes/crash-stem-impact-score/design.html for the full
evidence table, and CLAUDE.md -> "Crash/Transient Detector" for background.
"""
from __future__ import annotations

import numpy as np

from src.analyzer.result import TimingMark

_HOP_LENGTH = 512
_N_FFT = 2048
# Even on a cymbals stem, restrict the envelope to >=4kHz: drumsep leaks
# some low/mid kit content into platillos, and the band cut restored the
# range-ranking on the locally-separated stem (5/6 confirmed crashes in the
# top 6 vs 4/6 full-band, validated 2026-07-16).
_TREBLE_FMIN_HZ = 4000.0
# Envelope smoothing (~35ms at 44.1kHz) so a crash wash reads as one lobe.
_SMOOTH_FRAMES = 3
# Candidate spacing for peak-picking. Deliberately SHORT — this is not the
# output rarity constraint (that is the score floor + cap). bug-266:
# applying 10s here suppressed the true crash behind a stronger neighbor
# before it was ever scored.
_CANDIDATE_GAP_S = 3.0
# Local background: median cymbal envelope over this window before the peak
# (with a small gap so the crash's own attack doesn't contaminate it).
_PRE_BG_WINDOW_S = 8.0
_PRE_BG_GAP_S = 0.3
# Wash integration bound.
_WASH_WINDOW_S = 6.0
# Absolute score floor. Calibrated on a 6-song local panel (2026-07-16,
# drumsep stems): Dream On's 6 confirmed crashes score 7.51-10.61 and its
# first non-confirmed candidate 6.17, so 7.0 keeps all confirmed marks with
# margin; across the panel it yields 6/3/2/1/0/0 marks (cymbal-heavy rock ->
# percussive country -> pop/chiptune), honoring rare-by-design without
# dropping validated ground truth. See the change dir's validation notes.
_SCORE_FLOOR = 7.0
# The 500ms of FULL MIX immediately before a candidate must average at least
# this fraction of the song's median full-mix RMS — kept verbatim from v2:
# excludes a transient that is really the transition out of near-silence
# (e.g. the track's own cold open).
_PRE_TRANSIENT_RMS_FLOOR_RATIO = 0.4
_PRE_TRANSIENT_WINDOW_MS = 500
# Minimum spacing between emitted marks, enforced post-scoring (the
# higher-scored of a conflicting pair wins). 3s, not 10s: Dream On's
# user-confirmed crashes at 122.0s and 125.0s are only 3s apart — a 10s gap
# would drop real ground truth.
_MIN_GAP_MS = 3_000
# Hard cap regardless of how many candidates clear the score floor
# (6 = the validated song's confirmed crash count; user decision 2026-07-16).
_MAX_MARKS = 6


def detect_crash_accents(
    cymbals: np.ndarray,
    cymbals_sample_rate: int,
    full_mix: np.ndarray,
    full_mix_sample_rate: int,
) -> list[TimingMark]:
    """Return up to ``_MAX_MARKS`` rare, isolated cymbal-crash transients.

    *cymbals* is a cymbal-isolated mono stem (drum_stems.separate_cymbals);
    *full_mix* is the original song audio, used only for the cold-open
    pre-transient RMS guard.
    """
    if cymbals.size == 0 or full_mix.size == 0:
        return []

    import librosa
    from scipy.signal import find_peaks

    stft = np.abs(librosa.stft(cymbals, n_fft=_N_FFT, hop_length=_HOP_LENGTH))
    freqs = librosa.fft_frequencies(sr=cymbals_sample_rate, n_fft=_N_FFT)
    env = stft[freqs >= _TREBLE_FMIN_HZ, :].sum(axis=0)
    if env.size == 0 or float(env.max()) <= 0.0:
        return []
    kernel = np.ones(_SMOOTH_FRAMES) / _SMOOTH_FRAMES
    env = np.convolve(env, kernel, mode="same")

    frames_per_s = cymbals_sample_rate / _HOP_LENGTH
    env_floor = float(np.median(env))
    height_floor = max(env_floor * 3.0, float(np.percentile(env, 90)))
    if height_floor <= 0.0:
        return []

    # Two-tier peak picking. The LOW bar collects every ordinary hit — its
    # wash areas form the normalization distribution, so a song with a
    # single hero crash doesn't end up normalized against itself (median of
    # one == its own area == score zero). Only HIGH-bar peaks are scored as
    # crash candidates.
    dist_indices, _ = find_peaks(
        env,
        distance=max(1, int(_CANDIDATE_GAP_S * frames_per_s)),
        height=env_floor,
    )
    if dist_indices.size == 0:
        return []
    peak_indices = dist_indices[env[dist_indices] >= height_floor]
    if peak_indices.size == 0:
        return []

    mix_rms = librosa.feature.rms(y=full_mix, hop_length=_HOP_LENGTH)[0]
    mix_median_rms = float(np.median(mix_rms))
    if mix_median_rms <= 0.0:
        return []
    mix_frames_per_s = full_mix_sample_rate / _HOP_LENGTH
    mix_lead_frames = max(1, int(_PRE_TRANSIENT_WINDOW_MS / 1000 * mix_frames_per_s))

    pre_bg_frames = int(_PRE_BG_WINDOW_S * frames_per_s)
    pre_gap_frames = int(_PRE_BG_GAP_S * frames_per_s)
    wash_frames = int(_WASH_WINDOW_S * frames_per_s)

    def _wash_area(p: int, pre_bg: float) -> float:
        area = 0.0
        for j in range(p, min(len(env), p + wash_frames)):
            v = float(env[j]) - pre_bg
            if v <= 0.0:
                break
            area += v
        return area

    def _pre_background(p: int) -> float:
        pre = env[max(0, p - pre_bg_frames):max(1, p - pre_gap_frames)]
        return float(np.median(pre)) if pre.size else env_floor

    # Normalization distribution: wash areas of every ordinary peak.
    all_areas = np.array([_wash_area(p, _pre_background(p)) for p in dist_indices])
    positive = all_areas[all_areas > 0]
    if positive.size == 0:
        return []
    median_area = float(np.median(positive))

    # Score the strong candidates.
    candidates: list[tuple[float, float, float]] = []  # (time_s, isolation, area)
    for p in peak_indices:
        time_s = p * _HOP_LENGTH / cymbals_sample_rate

        pre_bg = _pre_background(p)
        isolation = float(env[p]) / (pre_bg + env_floor * 0.1 + 1e-9)
        area = _wash_area(p, pre_bg)

        # Cold-open guard on the full mix.
        mix_frame = int(time_s * mix_frames_per_s)
        pre_mix = mix_rms[max(0, mix_frame - mix_lead_frames):mix_frame]
        pre_mix_mean = float(pre_mix.mean()) if pre_mix.size else 0.0
        if pre_mix_mean / mix_median_rms < _PRE_TRANSIENT_RMS_FLOOR_RATIO:
            continue

        candidates.append((time_s, isolation, area))

    if not candidates:
        return []

    scored = sorted(
        ((float(np.log1p(iso) * np.log1p(area / median_area)), t)
         for t, iso, area in candidates),
        reverse=True,
    )

    # Post-scoring selection: score floor, then greedy min-gap, then cap.
    accepted_ms: list[int] = []
    for score, time_s in scored:
        if score < _SCORE_FLOOR:
            break
        time_ms = int(round(time_s * 1000))
        if any(abs(time_ms - a) < _MIN_GAP_MS for a in accepted_ms):
            continue
        accepted_ms.append(time_ms)
        if len(accepted_ms) >= _MAX_MARKS:
            break

    accepted_ms.sort()
    return [TimingMark(time_ms=t, confidence=None, label="crash")
            for t in accepted_ms]
