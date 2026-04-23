"""Boundary-source extraction and agreement clustering.

Given a hierarchy.json, pull boundary candidates from every available source
(QM segmenter, segmentino, stem entries, energy events, key changes, chord
density) and cluster them by temporal proximity. The resulting
``AgreementCluster`` objects carry a score = number of distinct sources
agreeing on that boundary, which serves as a confidence signal.

Moved here from ``scripts/boundary_confidence_map.py`` so that ``src/story/
builder.py`` and other consumers can use the same logic without shelling
out to a script.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Optional


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Boundary:
    """A single boundary candidate from one source."""
    time_ms: int
    source: str
    label: Optional[str] = None   # e.g. "chorus", "A", "qm_boundary"
    extra: dict = field(default_factory=dict)


@dataclass
class AgreementCluster:
    """A group of boundaries from different sources that agree within tolerance."""
    centre_ms: int
    members: list[Boundary]

    @property
    def sources(self) -> list[str]:
        """Distinct logical source types in this cluster (stem_entry:* collapsed to stem_entry)."""
        seen: set[str] = set()
        out: list[str] = []
        for m in self.members:
            s = m.source.split(":")[0]
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    @property
    def score(self) -> int:
        return len(self.sources)


# ── Source extractors ─────────────────────────────────────────────────────────

# Segmentino labels: single letters (A, B, C) or N-prefixed novelty markers.
_SEGMENTINO_LABEL_RE = re.compile(r"^[A-Z]$|^N\d+$")


def extract_segmentino(hier: dict) -> list[Boundary]:
    """Boundaries from segmentino (letter-labelled entries in hierarchy.sections)."""
    out: list[Boundary] = []
    for s in hier.get("sections", []):
        label = s.get("label", "")
        if _SEGMENTINO_LABEL_RE.match(label):
            out.append(Boundary(
                time_ms=int(s["time_ms"]),
                source="segmentino",
                label=label,
                extra={"duration_ms": s.get("duration_ms")},
            ))
    return out


def extract_qm_segmenter(hier: dict) -> list[Boundary]:
    """Boundaries from the QM segmenter (entries labelled 'qm_boundary')."""
    out: list[Boundary] = []
    for s in hier.get("sections", []):
        if s.get("label") == "qm_boundary":
            out.append(Boundary(
                time_ms=int(s["time_ms"]),
                source="qm_segmenter",
                label="qm",
            ))
    return out


def extract_key_changes(hier: dict) -> list[Boundary]:
    """Boundaries at each detected key change."""
    out: list[Boundary] = []
    kc = hier.get("key_changes")
    if isinstance(kc, dict):
        marks = kc.get("marks") or []
    elif isinstance(kc, list):
        marks = kc
    else:
        marks = []
    for m in marks:
        t = m.get("time_ms")
        if t is None:
            continue
        out.append(Boundary(
            time_ms=int(t),
            source="key_change",
            label=m.get("label") or m.get("key"),
        ))
    return out


def extract_energy_events(hier: dict) -> list[Boundary]:
    """Boundaries at energy impacts and drops."""
    out: list[Boundary] = []
    for e in hier.get("energy_impacts", []) or []:
        t = e.get("time_ms") or e.get("t_ms")
        if t is None:
            continue
        out.append(Boundary(
            time_ms=int(t),
            source="energy_impact",
            label="impact",
            extra={k: v for k, v in e.items() if k not in ("time_ms", "t_ms")},
        ))
    for e in hier.get("energy_drops", []) or []:
        t = e.get("time_ms") or e.get("t_ms")
        if t is None:
            continue
        out.append(Boundary(
            time_ms=int(t),
            source="energy_drop",
            label="drop",
            extra={k: v for k, v in e.items() if k not in ("time_ms", "t_ms")},
        ))
    return out


def extract_chord_density_spikes(
    hier: dict, bar_interval_ms: int, window_bars: int = 2,
) -> list[Boundary]:
    """
    Windows of high chord-change density — often coincide with section transitions.

    A rolling window counts chord changes per window; windows scoring above
    (median + 2*stdev) become candidate boundaries, anchored at window centre.
    """
    chord_track = hier.get("chords") or {}
    marks = chord_track.get("marks") or []
    if len(marks) < 4 or bar_interval_ms <= 0:
        return []

    window_ms = bar_interval_ms * window_bars
    times = [int(m["time_ms"]) for m in marks]
    labels = [m.get("label", "") for m in marks]

    changes = [
        t for i, (t, lbl) in enumerate(zip(times, labels))
        if lbl and lbl != "N" and (i == 0 or lbl != labels[i - 1])
    ]
    if len(changes) < 4:
        return []

    duration_ms = int(hier.get("duration_ms", changes[-1] + window_ms))
    step = max(bar_interval_ms // 2, 500)
    densities: list[tuple[int, int]] = []
    t = 0
    while t + window_ms <= duration_ms:
        count = sum(1 for c in changes if t <= c < t + window_ms)
        densities.append((t + window_ms // 2, count))
        t += step

    if not densities:
        return []

    counts = [d[1] for d in densities]
    if max(counts) < 2:
        return []
    med = statistics.median(counts)
    try:
        sd = statistics.pstdev(counts) or 1.0
    except statistics.StatisticsError:
        sd = 1.0
    threshold = med + 2 * sd

    out: list[Boundary] = []
    last_accepted: Optional[int] = None
    for centre, cnt in densities:
        if cnt >= threshold and cnt >= 2:
            if last_accepted is None or centre - last_accepted >= window_ms:
                out.append(Boundary(
                    time_ms=centre,
                    source="chord_density_spike",
                    label=f"{cnt}changes/{window_bars}bars",
                ))
                last_accepted = centre
    return out


def extract_stem_entry_events(
    hier: dict, min_silence_ms: int = 3000,
) -> list[Boundary]:
    """Per-stem "entry" moments: where a stem becomes active after silence."""
    out: list[Boundary] = []
    events = hier.get("events") or {}
    for stem, track in events.items():
        if stem == "full_mix":
            continue
        marks = track.get("marks") or []
        if len(marks) < 2:
            continue
        times = [int(m["time_ms"]) for m in marks]
        prev = times[0]
        if prev >= min_silence_ms:
            out.append(Boundary(
                time_ms=prev,
                source=f"stem_entry:{stem}",
                label="entry",
            ))
        for t in times[1:]:
            if t - prev >= min_silence_ms:
                out.append(Boundary(
                    time_ms=t,
                    source=f"stem_entry:{stem}",
                    label="entry",
                    extra={"silence_before_ms": t - prev},
                ))
            prev = t
    return out


# ── Clustering ────────────────────────────────────────────────────────────────

def cluster_boundaries(
    boundaries: list[Boundary], tolerance_ms: int,
) -> list[AgreementCluster]:
    """
    Single-linkage cluster: boundaries within *tolerance_ms* of the running
    cluster mean are merged. Output sorted by cluster centre time.
    """
    if not boundaries:
        return []
    sorted_b = sorted(boundaries, key=lambda b: b.time_ms)

    clusters: list[AgreementCluster] = []
    current = AgreementCluster(centre_ms=sorted_b[0].time_ms, members=[sorted_b[0]])
    running_sum = sorted_b[0].time_ms

    for b in sorted_b[1:]:
        mean = running_sum // len(current.members)
        if b.time_ms - mean <= tolerance_ms:
            current.members.append(b)
            running_sum += b.time_ms
            current.centre_ms = running_sum // len(current.members)
        else:
            clusters.append(current)
            current = AgreementCluster(centre_ms=b.time_ms, members=[b])
            running_sum = b.time_ms
    clusters.append(current)
    return clusters


# ── Convenience: one-call "build clusters from a hierarchy" ──────────────────

def build_clusters_for_hierarchy(
    hier: dict, bar_interval_ms: int, tolerance_ms: Optional[int] = None,
) -> list[AgreementCluster]:
    """
    Pull every source from *hier* and return agreement clusters.

    *tolerance_ms* defaults to *bar_interval_ms* (±1 bar).
    """
    if tolerance_ms is None:
        tolerance_ms = bar_interval_ms

    all_boundaries: list[Boundary] = []
    for fn in (extract_qm_segmenter,
               extract_segmentino,
               extract_stem_entry_events,
               extract_energy_events,
               extract_key_changes):
        try:
            all_boundaries.extend(fn(hier))
        except Exception:
            # Missing / malformed fields are tolerated — the source just
            # contributes nothing instead of taking down the whole pipeline.
            pass
    try:
        all_boundaries.extend(extract_chord_density_spikes(hier, bar_interval_ms))
    except Exception:
        pass

    return cluster_boundaries(all_boundaries, tolerance_ms)


def snap_to_cluster(
    time_ms: int,
    clusters: list[AgreementCluster],
    tolerance_ms: int,
    min_score: int = 3,
) -> tuple[int, int]:
    """
    Snap *time_ms* to the nearest cluster centre within *tolerance_ms*
    whose score >= *min_score*.

    Returns (snapped_time_ms, score_of_snapped_cluster). When no eligible
    cluster exists, returns (time_ms, 0) — input left untouched.
    """
    best: Optional[AgreementCluster] = None
    best_dist = tolerance_ms + 1
    for c in clusters:
        if c.score < min_score:
            continue
        dist = abs(c.centre_ms - time_ms)
        if dist <= tolerance_ms and dist < best_dist:
            best = c
            best_dist = dist

    if best is None:
        return time_ms, 0
    return best.centre_ms, best.score


def agreement_score_at(
    time_ms: int,
    clusters: list[AgreementCluster],
    tolerance_ms: int,
) -> int:
    """
    Return the agreement score of the nearest cluster to *time_ms* within
    *tolerance_ms* (number of distinct sources agreeing). 0 if no cluster
    is within tolerance.

    Unlike `snap_to_cluster`, this never modifies the input time — use it
    when you just want to *score* a boundary you've already committed to.
    """
    best_score = 0
    best_dist = tolerance_ms + 1
    for c in clusters:
        dist = abs(c.centre_ms - time_ms)
        if dist <= tolerance_ms and dist < best_dist:
            best_dist = dist
            best_score = c.score
    return best_score
