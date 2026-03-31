"""TDD tests for src/story/energy_arc.py — must FAIL before implementation."""
import pytest

from src.story.energy_arc import detect_energy_arc

# ---------------------------------------------------------------------------
# Valid arc shape labels
# ---------------------------------------------------------------------------

VALID_ARCS = {"ramp", "arch", "flat", "valley", "sawtooth", "bookend"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ramp(n: int = 20) -> list[float]:
    """Monotonically increasing sequence from 0 to 1."""
    return [i / (n - 1) for i in range(n)]


def _arch(n: int = 20) -> list[float]:
    """Rises to peak in the middle then falls back."""
    half = n // 2
    rise = [i / half for i in range(half)]
    fall = [1.0 - i / half for i in range(half)]
    return rise + fall


def _flat(n: int = 20, value: float = 0.5) -> list[float]:
    """Constant value — variance effectively 0."""
    return [value] * n


def _valley(n: int = 20) -> list[float]:
    """Falls to trough in the middle then rises back."""
    half = n // 2
    fall = [1.0 - i / half for i in range(half)]
    rise = [i / half for i in range(half)]
    return fall + rise


def _sawtooth(n: int = 16) -> list[float]:
    """Alternating high-low-high-low values."""
    return [1.0 if i % 2 == 0 else 0.1 for i in range(n)]


def _bookend(n: int = 20) -> list[float]:
    """High at both ends, low in the middle."""
    result = [0.9] * 3 + [0.1] * (n - 6) + [0.9] * 3
    return result


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_string(self):
        result = detect_energy_arc(_ramp())
        assert isinstance(result, str)

    def test_returns_valid_arc_label(self):
        """Return value must always be one of the 6 known arc shapes."""
        for curve in [_ramp(), _arch(), _flat(), _valley(), _sawtooth(), _bookend()]:
            result = detect_energy_arc(curve)
            assert result in VALID_ARCS, f"Unexpected arc label '{result}'"


# ---------------------------------------------------------------------------
# Ramp
# ---------------------------------------------------------------------------

class TestRamp:
    def test_monotonic_increase_is_ramp(self):
        assert detect_energy_arc(_ramp()) == "ramp"

    def test_ramp_with_minor_noise(self):
        """Small perturbations on an upward trend should still yield ramp."""
        curve = _ramp(20)
        # Add ±0.02 noise while keeping the overall trend
        noisy = [v + (0.01 if i % 2 == 0 else -0.01) for i, v in enumerate(curve)]
        assert detect_energy_arc(noisy) == "ramp"

    def test_steep_ramp(self):
        """A curve that jumps from 0 to 1 in two steps is a ramp."""
        assert detect_energy_arc([0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0]) == "ramp"


# ---------------------------------------------------------------------------
# Arch
# ---------------------------------------------------------------------------

class TestArch:
    def test_arch_shape(self):
        assert detect_energy_arc(_arch()) == "arch"

    def test_arch_asymmetric(self):
        """Arch with a slightly off-center peak still classifies as arch."""
        curve = [0.1, 0.3, 0.6, 0.9, 1.0, 0.8, 0.5, 0.2, 0.1]
        assert detect_energy_arc(curve) == "arch"


# ---------------------------------------------------------------------------
# Flat
# ---------------------------------------------------------------------------

class TestFlat:
    def test_constant_is_flat(self):
        assert detect_energy_arc(_flat()) == "flat"

    def test_near_flat_within_tolerance(self):
        """Values within ±0.05 of each other should be classified as flat."""
        curve = [0.5 + (0.04 if i % 3 == 0 else -0.03) for i in range(20)]
        assert detect_energy_arc(curve) == "flat"

    def test_empty_curve_returns_flat(self):
        """Empty input → default 'flat'."""
        assert detect_energy_arc([]) == "flat"

    def test_single_value_returns_flat(self):
        """Single-element curve → 'flat'."""
        assert detect_energy_arc([0.7]) == "flat"

    def test_two_values_same_returns_flat(self):
        assert detect_energy_arc([0.5, 0.5]) == "flat"


# ---------------------------------------------------------------------------
# Valley
# ---------------------------------------------------------------------------

class TestValley:
    def test_valley_shape(self):
        assert detect_energy_arc(_valley()) == "valley"

    def test_valley_pronounced_dip(self):
        """Pronounced drop in the middle with high bookends."""
        curve = [0.9, 0.8, 0.3, 0.1, 0.05, 0.2, 0.7, 0.9]
        assert detect_energy_arc(curve) == "valley"


# ---------------------------------------------------------------------------
# Sawtooth
# ---------------------------------------------------------------------------

class TestSawtooth:
    def test_alternating_is_sawtooth(self):
        assert detect_energy_arc(_sawtooth()) == "sawtooth"

    def test_sawtooth_triple_alternation(self):
        """Three or more up-down cycles classify as sawtooth."""
        curve = [0.9, 0.1, 0.9, 0.1, 0.9, 0.1, 0.9, 0.1]
        assert detect_energy_arc(curve) == "sawtooth"


# ---------------------------------------------------------------------------
# Bookend
# ---------------------------------------------------------------------------

class TestBookend:
    def test_bookend_shape(self):
        assert detect_energy_arc(_bookend()) == "bookend"

    def test_bookend_with_low_middle(self):
        """High-energy intro and outro with a sustained low middle."""
        curve = [0.85, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.8, 0.85]
        assert detect_energy_arc(curve) == "bookend"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_curve_same_result(self):
        """Calling detect_energy_arc twice with the same input yields the same output."""
        curve = _arch()
        assert detect_energy_arc(curve) == detect_energy_arc(curve)
