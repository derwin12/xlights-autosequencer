"""Speaker-embedding-based vocal diarization — lead vs. featured/backup singer.

Runs on the demucs vocals stem (already isolated for word/phoneme alignment
by ``src.analyzer.phoneme_align``). Groups WhisperX word marks into
contiguous utterances, embeds each utterance with a pretrained
speaker-verification model (speechbrain ECAPA-TDNN), and clusters into two
voices via cosine-distance agglomerative clustering.

A second voice is only accepted when it clears a minimum total duration AND
utterance count. Validated by hand against three real clips (2026-07-21): a
genuine duet (Natalie Grant feat. Bart Millard) held together as one
coherent, multi-utterance cluster spanning ~30s; two single-singer clips
produced only single 0.4-1.3s misfires, which the threshold rejects as
clustering noise rather than a real second singer. Below the threshold,
every word is tagged speaker 0 (i.e. a no-op).

Never raises: returns the input words tagged speaker=0 if
speechbrain/torch/sklearn aren't importable, or if diarization fails for any
other reason — callers can always rely on a "speaker" key being present.
"""
from __future__ import annotations

from src.log import get_logger

log = get_logger("xlight.vocal_diarization")

_UTTERANCE_GAP_MS = 800
_MIN_SECOND_SPEAKER_SECONDS = 8.0
_MIN_SECOND_SPEAKER_UTTERANCES = 3


def diarize_words(vocals_path: str, words: list[dict]) -> list[dict]:
    """Tag each word mark with a ``speaker`` key (0 = lead, 1 = backup).

    ``words`` are the ``{"label", "start_ms", "end_ms"}`` dicts produced by
    :func:`src.analyzer.phoneme_align.align_words_and_phonemes`. Returns a
    new list; the input is not mutated.
    """
    if not words:
        return words
    try:
        return _diarize(vocals_path, words)
    except Exception as exc:  # noqa: BLE001
        log.warning("vocal diarization skipped: %s", exc, exc_info=True)
        return [{**w, "speaker": 0} for w in words]


def _group_utterances(words: list[dict]) -> list[list[dict]]:
    utterances: list[list[dict]] = [[words[0]]]
    for w in words[1:]:
        if w["start_ms"] - utterances[-1][-1]["end_ms"] > _UTTERANCE_GAP_MS:
            utterances.append([w])
        else:
            utterances[-1].append(w)
    return utterances


def _label_utterances(valid_utterances: list[list[dict]], labels: list[int]) -> dict[int, int]:
    """Apply the majority/minority acceptance gate to raw cluster labels.

    Returns a ``{id(word): speaker}`` map (0=lead, 1=backup) for every word
    in an utterance that survives the gate. Speaker 0 is always normalized
    to the majority (by total duration) cluster, speaker 1 to the minority
    — regardless of the clustering's own arbitrary raw label numbering. The
    minority cluster is only accepted as a real second voice when it clears
    both ``_MIN_SECOND_SPEAKER_SECONDS`` and ``_MIN_SECOND_SPEAKER_UTTERANCES``;
    otherwise every word maps to speaker 0 (a no-op).

    Pulled out of ``_diarize`` so the acceptance-gate math is unit-testable
    without importing torch/speechbrain.
    """
    counts = {0: 0, 1: 0}
    durations = {0: 0.0, 1: 0.0}
    for utt, label in zip(valid_utterances, labels):
        counts[int(label)] += 1
        durations[int(label)] += (utt[-1]["end_ms"] - utt[0]["start_ms"]) / 1000.0

    majority_label = 0 if durations[0] >= durations[1] else 1
    minority_label = 1 - majority_label

    word_speaker: dict[int, int] = {}
    if (durations[minority_label] < _MIN_SECOND_SPEAKER_SECONDS
            or counts[minority_label] < _MIN_SECOND_SPEAKER_UTTERANCES):
        for utt in valid_utterances:
            for w in utt:
                word_speaker[id(w)] = 0
        return word_speaker

    for utt, label in zip(valid_utterances, labels):
        normalized = 0 if int(label) == majority_label else 1
        for w in utt:
            word_speaker[id(w)] = normalized
    return word_speaker


def _diarize(vocals_path: str, words: list[dict]) -> list[dict]:
    import numpy as np
    import torch
    import torchaudio
    from sklearn.cluster import AgglomerativeClustering
    from speechbrain.inference.speaker import EncoderClassifier

    utterances = _group_utterances(words)
    if len(utterances) < 2:
        return [{**w, "speaker": 0} for w in words]

    wav, sr = torchaudio.load(vocals_path)
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    if sr != 16000:
        wav = torchaudio.functional.resample(wav, sr, 16000)
        sr = 16000

    classifier = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="pretrained_models/spkrec-ecapa-voxceleb",
        run_opts={"device": "cpu"},
    )

    embeddings = []
    valid_utterances = []
    for utt in utterances:
        start_s = utt[0]["start_ms"] / 1000.0
        end_s = utt[-1]["end_ms"] / 1000.0
        if end_s - start_s < 0.3:
            continue
        seg = wav[:, int(start_s * sr):int(end_s * sr)]
        with torch.no_grad():
            emb = classifier.encode_batch(seg).squeeze().numpy()
        embeddings.append(emb)
        valid_utterances.append(utt)

    if len(valid_utterances) < 2:
        return [{**w, "speaker": 0} for w in words]

    stacked = np.stack(embeddings)
    normed = stacked / np.linalg.norm(stacked, axis=1, keepdims=True)
    clustering = AgglomerativeClustering(n_clusters=2, metric="cosine", linkage="average")
    labels = clustering.fit_predict(normed)

    word_speaker = _label_utterances(valid_utterances, labels)
    return [{**w, "speaker": word_speaker.get(id(w), 0)} for w in words]
