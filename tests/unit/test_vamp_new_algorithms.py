"""Tests for new Vamp algorithm wrappers — T015.

These tests verify that each new algorithm wrapper:
1. Has the correct plugin_key
2. Has preferred_stem and depends_on set
3. Inherits from Algorithm base class
4. Can be instantiated without errors
"""
from __future__ import annotations

import pytest

from src.analyzer.algorithms.base import Algorithm


class TestAubioAlgorithms:
    def test_aubio_onset_inherits_algorithm(self):
        from src.analyzer.algorithms.vamp_aubio import AubioOnsetAlgorithm
        algo = AubioOnsetAlgorithm()
        assert isinstance(algo, Algorithm)

    def test_aubio_onset_plugin_key(self):
        from src.analyzer.algorithms.vamp_aubio import AubioOnsetAlgorithm
        assert AubioOnsetAlgorithm.plugin_key == "vamp-aubio:aubioonset"

    def test_aubio_onset_has_depends_on(self):
        from src.analyzer.algorithms.vamp_aubio import AubioOnsetAlgorithm
        assert hasattr(AubioOnsetAlgorithm, "depends_on")
        assert len(AubioOnsetAlgorithm.depends_on) > 0

    def test_aubio_tempo_plugin_key(self):
        from src.analyzer.algorithms.vamp_aubio import AubioTempoAlgorithm
        assert AubioTempoAlgorithm.plugin_key == "vamp-aubio:aubiotempo"

    def test_aubio_notes_plugin_key(self):
        from src.analyzer.algorithms.vamp_aubio import AubioNotesAlgorithm
        assert AubioNotesAlgorithm.plugin_key == "vamp-aubio:aubionotes"


class TestBBCAlgorithms:
    def test_bbc_energy_inherits_algorithm(self):
        from src.analyzer.algorithms.vamp_bbc import BBCEnergyAlgorithm
        assert isinstance(BBCEnergyAlgorithm(), Algorithm)

    def test_bbc_energy_plugin_key(self):
        from src.analyzer.algorithms.vamp_bbc import BBCEnergyAlgorithm
        assert BBCEnergyAlgorithm.plugin_key == "bbc-vamp-plugins:bbc-energy"

    def test_bbc_energy_element_type(self):
        from src.analyzer.algorithms.vamp_bbc import BBCEnergyAlgorithm
        assert BBCEnergyAlgorithm.element_type == "value_curve"

    def test_bbc_spectral_flux_plugin_key(self):
        from src.analyzer.algorithms.vamp_bbc import BBCSpectralFluxAlgorithm
        assert BBCSpectralFluxAlgorithm.plugin_key == "bbc-vamp-plugins:bbc-spectral-flux"

    def test_bbc_peaks_plugin_key(self):
        from src.analyzer.algorithms.vamp_bbc import BBCPeaksAlgorithm
        assert BBCPeaksAlgorithm.plugin_key == "bbc-vamp-plugins:bbc-peaks"

    def test_bbc_rhythm_plugin_key(self):
        from src.analyzer.algorithms.vamp_bbc import BBCRhythmAlgorithm
        assert BBCRhythmAlgorithm.plugin_key == "bbc-vamp-plugins:bbc-rhythm"

    def test_bbc_rhythm_is_timing(self):
        from src.analyzer.algorithms.vamp_bbc import BBCRhythmAlgorithm
        assert BBCRhythmAlgorithm.element_type == "onset"  # timing marks, not value curve


class TestSegmentinoAlgorithm:
    def test_inherits_algorithm(self):
        from src.analyzer.algorithms.vamp_segmentation import SegmentinoAlgorithm
        assert isinstance(SegmentinoAlgorithm(), Algorithm)

    def test_plugin_key(self):
        from src.analyzer.algorithms.vamp_segmentation import SegmentinoAlgorithm
        assert SegmentinoAlgorithm.plugin_key == "segmentino:segmentino"

    def test_element_type(self):
        from src.analyzer.algorithms.vamp_segmentation import SegmentinoAlgorithm
        assert SegmentinoAlgorithm.element_type == "structure"


class TestExtraAlgorithms:
    def test_qm_key_plugin_key(self):
        from src.analyzer.algorithms.vamp_extra import QMKeyAlgorithm
        assert QMKeyAlgorithm.plugin_key == "qm-vamp-plugins:qm-keydetector"

    def test_qm_transcription_plugin_key(self):
        from src.analyzer.algorithms.vamp_extra import QMTranscriptionAlgorithm
        assert QMTranscriptionAlgorithm.plugin_key == "qm-vamp-plugins:qm-transcription"

    def test_silvet_notes_plugin_key(self):
        from src.analyzer.algorithms.vamp_extra import SilvetNotesAlgorithm
        assert SilvetNotesAlgorithm.plugin_key == "silvet:silvet"

    def test_percussion_onsets_plugin_key(self):
        from src.analyzer.algorithms.vamp_extra import PercussionOnsetsAlgorithm
        assert PercussionOnsetsAlgorithm.plugin_key == "vamp-example-plugins:percussiononsets"

    def test_percussion_onsets_preferred_stem(self):
        from src.analyzer.algorithms.vamp_extra import PercussionOnsetsAlgorithm
        assert PercussionOnsetsAlgorithm.preferred_stem == "drums"

    def test_amplitude_follower_plugin_key(self):
        from src.analyzer.algorithms.vamp_extra import AmplitudeFollowerAlgorithm
        assert AmplitudeFollowerAlgorithm.plugin_key == "vamp-example-plugins:amplitudefollower"

    def test_amplitude_follower_is_value_curve(self):
        from src.analyzer.algorithms.vamp_extra import AmplitudeFollowerAlgorithm
        assert AmplitudeFollowerAlgorithm.element_type == "value_curve"

    def test_tempogram_plugin_key(self):
        from src.analyzer.algorithms.vamp_extra import TempogramAlgorithm
        assert TempogramAlgorithm.plugin_key == "tempogram:tempogram"

    def test_tempogram_is_value_curve(self):
        from src.analyzer.algorithms.vamp_extra import TempogramAlgorithm
        assert TempogramAlgorithm.element_type == "value_curve"

    def test_all_extra_have_depends_on(self):
        from src.analyzer.algorithms.vamp_extra import (
            QMKeyAlgorithm, QMTranscriptionAlgorithm, SilvetNotesAlgorithm,
            PercussionOnsetsAlgorithm, AmplitudeFollowerAlgorithm, TempogramAlgorithm,
        )
        for cls in [QMKeyAlgorithm, QMTranscriptionAlgorithm, SilvetNotesAlgorithm,
                     PercussionOnsetsAlgorithm, AmplitudeFollowerAlgorithm, TempogramAlgorithm]:
            assert hasattr(cls, "depends_on"), f"{cls.__name__} missing depends_on"
            assert len(cls.depends_on) > 0, f"{cls.__name__} has empty depends_on"
