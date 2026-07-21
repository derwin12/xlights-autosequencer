"""Tests for src.analyzer.vocal_diarization.

The acceptance-gate math (_label_utterances) and utterance grouping
(_group_utterances) are pure functions, tested directly without needing
torch/speechbrain installed. diarize_words' "never raises" contract is
tested by forcing _diarize to fail.
"""
from __future__ import annotations

import src.analyzer.vocal_diarization as vocal_diarization
from src.analyzer.vocal_diarization import (
    _group_utterances,
    _label_utterances,
    diarize_words,
)


def _word(label, start_ms, end_ms):
    return {"label": label, "start_ms": start_ms, "end_ms": end_ms}


class TestGroupUtterances:
    def test_merges_close_words_and_splits_on_gap(self):
        words = [_word("A", 0, 200), _word("B", 300, 500), _word("C", 5000, 5300)]
        utterances = _group_utterances(words)
        assert len(utterances) == 2
        assert [w["label"] for w in utterances[0]] == ["A", "B"]
        assert [w["label"] for w in utterances[1]] == ["C"]

    def test_single_utterance_when_no_gap(self):
        words = [_word("A", 0, 200), _word("B", 300, 500)]
        assert len(_group_utterances(words)) == 1


class TestLabelUtterances:
    def _utt(self, start_ms, end_ms):
        return [_word("W", start_ms, end_ms)]

    def test_confident_second_voice_accepted(self):
        # Majority (label 0): 20s across 4 utterances. Minority (label 1):
        # 10s across 3 utterances -- clears both thresholds.
        utterances = [
            self._utt(0, 5000), self._utt(6000, 11000),
            self._utt(12000, 17000), self._utt(18000, 23000),
            self._utt(30000, 33500), self._utt(34000, 37500), self._utt(38000, 41500),
        ]
        labels = [0, 0, 0, 0, 1, 1, 1]
        word_speaker = _label_utterances(utterances, labels)
        lead_ids = {id(utterances[i][0]) for i in range(4)}
        backup_ids = {id(utterances[i][0]) for i in range(4, 7)}
        assert all(word_speaker[i] == 0 for i in lead_ids)
        assert all(word_speaker[i] == 1 for i in backup_ids)

    def test_single_short_misfire_rejected_as_noise(self):
        # Mirrors the real false positives hit in manual testing: one
        # 0.4-1.3s utterance clustered apart from everything else.
        utterances = [
            self._utt(0, 5000), self._utt(6000, 11000), self._utt(12000, 17000),
            self._utt(20000, 20400),
        ]
        labels = [0, 0, 0, 1]
        word_speaker = _label_utterances(utterances, labels)
        assert set(word_speaker.values()) == {0}

    def test_minority_label_normalized_to_speaker_1_regardless_of_raw_label(self):
        # Raw cluster label "0" is actually the minority here -- output
        # must still normalize majority->speaker 0.
        utterances = [
            self._utt(0, 10000), self._utt(11000, 21000), self._utt(22000, 32000),
            self._utt(40000, 40500),
        ]
        labels = [1, 1, 1, 0]
        word_speaker = _label_utterances(utterances, labels)
        assert set(word_speaker.values()) == {0}  # minority (raw label 0) rejected: too short


class TestDiarizeWordsNeverRaises:
    def test_empty_words_returned_as_is(self):
        assert diarize_words("vocals.wav", []) == []

    def test_diarization_failure_falls_back_to_speaker_zero(self, monkeypatch):
        def _boom(vocals_path, words):
            raise ImportError("speechbrain not installed")

        monkeypatch.setattr(vocal_diarization, "_diarize", _boom)
        words = [_word("HELLO", 0, 400), _word("WORLD", 500, 900)]
        result = diarize_words("vocals.wav", words)
        assert all(w["speaker"] == 0 for w in result)
        assert [w["label"] for w in result] == ["HELLO", "WORLD"]

    def test_does_not_mutate_input(self, monkeypatch):
        monkeypatch.setattr(
            vocal_diarization, "_diarize",
            lambda vocals_path, words: [{**w, "speaker": 0} for w in words],
        )
        words = [_word("HELLO", 0, 400)]
        diarize_words("vocals.wav", words)
        assert "speaker" not in words[0]
