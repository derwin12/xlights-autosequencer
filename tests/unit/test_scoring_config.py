"""Unit tests for ScoringConfig loading, validation, and profile management."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.analyzer.scoring_config import (
    BUILTIN_CATEGORIES,
    CRITERIA_NAMES,
    DEFAULT_WEIGHTS,
    ScoringConfig,
    generate_default_toml,
    get_category_for_algorithm,
    list_profiles,
    load_profile,
    save_profile,
)


def _write_toml(content: str) -> Path:
    """Write TOML content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w")
    f.write(content)
    f.close()
    return Path(f.name)


# ── Default config ─────────────────────────────────────────────────────────────

class TestDefaultConfig:
    def test_default_weights_are_correct(self):
        cfg = ScoringConfig.default()
        assert cfg.weights == DEFAULT_WEIGHTS

    def test_default_diversity_settings(self):
        cfg = ScoringConfig.default()
        assert cfg.diversity_tolerance_ms == 50
        assert cfg.diversity_threshold == pytest.approx(0.90)

    def test_default_min_gap_threshold(self):
        cfg = ScoringConfig.default()
        assert cfg.min_gap_threshold_ms == 25

    def test_default_no_thresholds(self):
        cfg = ScoringConfig.default()
        assert cfg.thresholds == {}

    def test_default_no_category_overrides(self):
        cfg = ScoringConfig.default()
        assert cfg.category_overrides == {}


# ── TOML loading ───────────────────────────────────────────────────────────────

class TestTomlLoading:
    def test_loads_valid_config(self):
        path = _write_toml("[weights]\ndensity = 0.5\nregularity = 0.5\n")
        try:
            cfg = ScoringConfig.from_toml(path)
            assert cfg.weights["density"] == pytest.approx(0.5)
            assert cfg.weights["regularity"] == pytest.approx(0.5)
        finally:
            path.unlink()

    def test_missing_fields_use_defaults(self):
        path = _write_toml("[weights]\ndensity = 0.5\n")
        try:
            cfg = ScoringConfig.from_toml(path)
            assert cfg.weights["regularity"] == pytest.approx(DEFAULT_WEIGHTS["regularity"])
            assert cfg.diversity_tolerance_ms == 50
        finally:
            path.unlink()

    def test_loads_diversity_settings(self):
        path = _write_toml("[diversity]\ntolerance_ms = 100\nthreshold = 0.80\n")
        try:
            cfg = ScoringConfig.from_toml(path)
            assert cfg.diversity_tolerance_ms == 100
            assert cfg.diversity_threshold == pytest.approx(0.80)
        finally:
            path.unlink()

    def test_loads_min_gap_setting(self):
        path = _write_toml("[min_gap]\nthreshold_ms = 50\n")
        try:
            cfg = ScoringConfig.from_toml(path)
            assert cfg.min_gap_threshold_ms == 50
        finally:
            path.unlink()

    def test_loads_thresholds(self):
        path = _write_toml("[thresholds]\nmin_mark_count = 10.0\nmax_density = 5.0\n")
        try:
            cfg = ScoringConfig.from_toml(path)
            assert cfg.thresholds["min_mark_count"] == pytest.approx(10.0)
            assert cfg.thresholds["max_density"] == pytest.approx(5.0)
        finally:
            path.unlink()

    def test_loads_category_overrides(self):
        path = _write_toml("[categories.beats]\ndensity_min = 2.0\ndensity_max = 5.0\n")
        try:
            cfg = ScoringConfig.from_toml(path)
            assert "beats" in cfg.category_overrides
            assert cfg.category_overrides["beats"]["density_min"] == pytest.approx(2.0)
        finally:
            path.unlink()

    def test_category_override_applied_to_get_category(self):
        path = _write_toml("[categories.beats]\ndensity_min = 2.0\ndensity_max = 5.0\n")
        try:
            cfg = ScoringConfig.from_toml(path)
            cat = cfg.get_category("librosa_beats")
            assert cat.density_range[0] == pytest.approx(2.0)
            assert cat.density_range[1] == pytest.approx(5.0)
        finally:
            path.unlink()


# ── Validation errors ─────────────────────────────────────────────────────────

class TestValidationErrors:
    def test_negative_weight_raises(self):
        path = _write_toml("[weights]\ndensity = -0.5\n")
        try:
            with pytest.raises(ValueError, match="non-negative"):
                ScoringConfig.from_toml(path)
        finally:
            path.unlink()

    def test_all_zero_weights_raises(self):
        lines = "[weights]\n" + "\n".join(f"{c} = 0.0" for c in CRITERIA_NAMES)
        path = _write_toml(lines)
        try:
            with pytest.raises(ValueError, match="[Ss]um"):
                ScoringConfig.from_toml(path)
        finally:
            path.unlink()

    def test_unknown_criterion_raises(self):
        path = _write_toml("[weights]\nfakecriterion = 0.5\n")
        try:
            with pytest.raises(ValueError, match="Unknown scoring criterion"):
                ScoringConfig.from_toml(path)
        finally:
            path.unlink()

    def test_unknown_category_raises(self):
        path = _write_toml("[categories.fakecategory]\ndensity_min = 1.0\n")
        try:
            with pytest.raises(ValueError, match="Unknown scoring category"):
                ScoringConfig.from_toml(path)
        finally:
            path.unlink()

    def test_invalid_diversity_threshold_raises(self):
        path = _write_toml("[diversity]\nthreshold = 1.5\n")
        try:
            with pytest.raises(ValueError, match="diversity.threshold"):
                ScoringConfig.from_toml(path)
        finally:
            path.unlink()

    def test_zero_diversity_threshold_raises(self):
        path = _write_toml("[diversity]\nthreshold = 0.0\n")
        try:
            with pytest.raises(ValueError, match="diversity.threshold"):
                ScoringConfig.from_toml(path)
        finally:
            path.unlink()

    def test_zero_tolerance_ms_raises(self):
        path = _write_toml("[diversity]\ntolerance_ms = 0\n")
        try:
            with pytest.raises(ValueError, match="tolerance_ms"):
                ScoringConfig.from_toml(path)
        finally:
            path.unlink()


# ── Category mapping ──────────────────────────────────────────────────────────

class TestCategoryMapping:
    def test_known_algorithm_maps_to_correct_category(self):
        cat = get_category_for_algorithm("librosa_beats")
        assert cat.name == "beats"

    def test_segment_algorithm_maps_to_segments(self):
        cat = get_category_for_algorithm("qm_segments")
        assert cat.name == "segments"

    def test_unknown_algorithm_falls_back_to_general(self):
        cat = get_category_for_algorithm("some_unknown_algo")
        assert cat.name == "general"

    def test_all_builtin_categories_have_valid_ranges(self):
        for name, cat in BUILTIN_CATEGORIES.items():
            assert cat.density_range[0] <= cat.density_range[1]
            assert cat.regularity_range[0] <= cat.regularity_range[1]
            assert cat.mark_count_range[0] <= cat.mark_count_range[1]
            assert cat.coverage_range[0] <= cat.coverage_range[1]


# ── Default TOML generation ────────────────────────────────────────────────────

class TestDefaultTomlGeneration:
    def test_generates_valid_toml(self):
        import tomllib
        content = generate_default_toml()
        # Strip comment lines for tomllib parsing
        lines = [l for l in content.splitlines() if not l.startswith("#")]
        cleaned = "\n".join(lines)
        parsed = tomllib.loads(cleaned)
        assert "weights" in parsed

    def test_contains_all_criteria(self):
        content = generate_default_toml()
        for crit in CRITERIA_NAMES:
            assert crit in content

    def test_contains_section_headers(self):
        content = generate_default_toml()
        assert "[weights]" in content
        assert "[diversity]" in content
        assert "[min_gap]" in content


# ── Profile management ────────────────────────────────────────────────────────

class TestProfileManagement:
    def test_save_and_load_profile(self, tmp_path, monkeypatch):
        # Patch the project profile dir to use tmp_path
        import src.analyzer.scoring_config as sc_mod
        monkeypatch.setattr(sc_mod, "_project_profile_dir", lambda: tmp_path / ".scoring")

        source = tmp_path / "my_config.toml"
        source.write_text("[weights]\ndensity = 0.5\nregularity = 0.5\n")

        saved_path = save_profile("test_profile", source, scope="project")
        assert saved_path.exists()

        loaded = load_profile("test_profile")
        assert loaded.weights["density"] == pytest.approx(0.5)

    def test_load_nonexistent_profile_raises(self, tmp_path, monkeypatch):
        import src.analyzer.scoring_config as sc_mod
        monkeypatch.setattr(sc_mod, "_project_profile_dir", lambda: tmp_path / ".scoring")
        monkeypatch.setattr(sc_mod, "_USER_PROFILE_DIR", tmp_path / "user_profiles")

        with pytest.raises(FileNotFoundError):
            load_profile("does_not_exist")

    def test_list_profiles_includes_saved(self, tmp_path, monkeypatch):
        import src.analyzer.scoring_config as sc_mod
        proj_dir = tmp_path / ".scoring"
        proj_dir.mkdir()
        monkeypatch.setattr(sc_mod, "_project_profile_dir", lambda: proj_dir)
        monkeypatch.setattr(sc_mod, "_USER_PROFILE_DIR", tmp_path / "user_profiles")

        (proj_dir / "ambient.toml").write_text("[weights]\ndensity = 0.1\n")
        (proj_dir / "fast_edm.toml").write_text("[weights]\ndensity = 0.5\n")

        profiles = list_profiles()
        names = [p["name"] for p in profiles]
        assert "ambient" in names
        assert "fast_edm" in names

    def test_project_profile_overrides_user_profile(self, tmp_path, monkeypatch):
        import src.analyzer.scoring_config as sc_mod
        proj_dir = tmp_path / ".scoring"
        proj_dir.mkdir()
        user_dir = tmp_path / "user_profiles"
        user_dir.mkdir()
        monkeypatch.setattr(sc_mod, "_project_profile_dir", lambda: proj_dir)
        monkeypatch.setattr(sc_mod, "_USER_PROFILE_DIR", user_dir)

        # User profile has density 0.1, project profile has density 0.9
        (user_dir / "myprofile.toml").write_text("[weights]\ndensity = 0.1\n")
        (proj_dir / "myprofile.toml").write_text("[weights]\ndensity = 0.9\n")

        loaded = load_profile("myprofile")
        assert loaded.weights["density"] == pytest.approx(0.9)
