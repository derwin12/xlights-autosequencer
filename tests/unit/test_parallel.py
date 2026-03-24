"""Tests for PipelineStep, DependencyGraph, and dependency declarations."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# T006: PipelineStep.is_ready() — must fail until PipelineStep exists
# ---------------------------------------------------------------------------

class TestPipelineStep:
    """PipelineStep dataclass and state transitions."""

    def _make_step(self, name="test", depends_on=None):
        from src.analyzer.parallel import PipelineStep, PipelineStepStatus
        return PipelineStep(
            name=name,
            phase="analysis",
            depends_on=depends_on or [],
        )

    def test_initial_status_is_pending(self):
        from src.analyzer.parallel import PipelineStepStatus
        step = self._make_step()
        assert step.status == PipelineStepStatus.PENDING

    def test_is_ready_no_dependencies(self):
        step = self._make_step(depends_on=[])
        assert step.is_ready(set()) is True

    def test_is_ready_unsatisfied_dependency(self):
        step = self._make_step(depends_on=["audio_load"])
        assert step.is_ready(set()) is False
        assert step.is_ready({"other"}) is False

    def test_is_ready_satisfied_dependency(self):
        step = self._make_step(depends_on=["audio_load"])
        assert step.is_ready({"audio_load"}) is True

    def test_is_ready_multiple_dependencies(self):
        step = self._make_step(depends_on=["audio_load", "stem_separation"])
        assert step.is_ready({"audio_load"}) is False
        assert step.is_ready({"audio_load", "stem_separation"}) is True

    def test_status_transitions(self):
        from src.analyzer.parallel import PipelineStepStatus
        step = self._make_step()
        assert step.status == PipelineStepStatus.PENDING
        step.status = PipelineStepStatus.RUNNING
        assert step.status == PipelineStepStatus.RUNNING
        step.status = PipelineStepStatus.DONE
        assert step.status == PipelineStepStatus.DONE

    def test_failed_status(self):
        from src.analyzer.parallel import PipelineStepStatus
        step = self._make_step()
        step.status = PipelineStepStatus.FAILED
        step.error = "something went wrong"
        assert step.status == PipelineStepStatus.FAILED
        assert step.error == "something went wrong"

    def test_skipped_status(self):
        from src.analyzer.parallel import PipelineStepStatus
        step = self._make_step()
        step.status = PipelineStepStatus.SKIPPED
        assert step.status == PipelineStepStatus.SKIPPED


# ---------------------------------------------------------------------------
# T026: DependencyGraph.topological_sort() — must fail until DependencyGraph exists
# ---------------------------------------------------------------------------

class TestDependencyGraph:
    """DependencyGraph topological sort and cascade failure behavior."""

    def _make_steps(self, spec):
        """spec is list of (name, depends_on) tuples."""
        from src.analyzer.parallel import PipelineStep
        return [PipelineStep(name=n, phase="analysis", depends_on=d) for n, d in spec]

    def test_no_dependencies_single_layer(self):
        from src.analyzer.parallel import DependencyGraph
        steps = self._make_steps([("a", []), ("b", []), ("c", [])])
        graph = DependencyGraph(steps)
        layers = graph.topological_sort()
        assert len(layers) == 1
        names = {s.name for s in layers[0]}
        assert names == {"a", "b", "c"}

    def test_chain_three_layers(self):
        from src.analyzer.parallel import DependencyGraph
        steps = self._make_steps([("a", []), ("b", ["a"]), ("c", ["b"])])
        graph = DependencyGraph(steps)
        layers = graph.topological_sort()
        assert len(layers) == 3
        assert layers[0][0].name == "a"
        assert layers[1][0].name == "b"
        assert layers[2][0].name == "c"

    def test_diamond_parallel_middle(self):
        from src.analyzer.parallel import DependencyGraph
        # A -> B, A -> C, B -> D, C -> D
        steps = self._make_steps([
            ("A", []),
            ("B", ["A"]),
            ("C", ["A"]),
            ("D", ["B", "C"]),
        ])
        graph = DependencyGraph(steps)
        layers = graph.topological_sort()
        assert len(layers) == 3
        assert layers[0][0].name == "A"
        middle_names = {s.name for s in layers[1]}
        assert middle_names == {"B", "C"}
        assert layers[2][0].name == "D"

    def test_cycle_raises_value_error(self):
        from src.analyzer.parallel import DependencyGraph
        steps = self._make_steps([("a", ["b"]), ("b", ["a"])])
        with pytest.raises(ValueError, match="cycle"):
            DependencyGraph(steps).topological_sort()

    def test_failed_step_skips_dependents(self):
        from src.analyzer.parallel import DependencyGraph, PipelineStepStatus
        steps = self._make_steps([
            ("stem_separation", []),
            ("drums_algo", ["stem_separation"]),
            ("vocals_algo", ["stem_separation"]),
        ])
        graph = DependencyGraph(steps)
        # Simulate stem_separation failing
        steps[0].status = PipelineStepStatus.FAILED
        layers = graph.topological_sort()
        # After failure is propagated, dependents should be skipped
        graph.propagate_failure(steps[0])
        assert steps[1].status == PipelineStepStatus.SKIPPED
        assert steps[2].status == PipelineStepStatus.SKIPPED
        assert "stem_separation" in steps[1].error
        assert "stem_separation" in steps[2].error


# ---------------------------------------------------------------------------
# T033: depends_on declarations must match preferred_stem for all algorithms
# ---------------------------------------------------------------------------

class TestAlgorithmDependsOn:
    """All algorithms must declare consistent depends_on (tested in T036/T033)."""

    def test_all_algorithms_have_depends_on(self):
        from src.analyzer.runner import default_algorithms
        for algo in default_algorithms(include_vamp=False, include_madmom=False):
            assert hasattr(algo, "depends_on"), (
                f"Algorithm {algo.name} is missing depends_on class attribute"
            )
            assert isinstance(algo.depends_on, list), (
                f"Algorithm {algo.name}.depends_on must be a list"
            )
            assert len(algo.depends_on) > 0, (
                f"Algorithm {algo.name}.depends_on must not be empty"
            )

    def test_stem_algorithms_declare_stem_separation(self):
        from src.analyzer.runner import default_algorithms
        for algo in default_algorithms(include_vamp=False, include_madmom=False):
            if algo.preferred_stem != "full_mix":
                assert algo.depends_on == ["stem_separation"], (
                    f"Algorithm {algo.name} has preferred_stem={algo.preferred_stem!r} "
                    f"but depends_on={algo.depends_on!r}; expected ['stem_separation']"
                )

    def test_full_mix_algorithms_declare_audio_load(self):
        from src.analyzer.runner import default_algorithms
        for algo in default_algorithms(include_vamp=False, include_madmom=False):
            if algo.preferred_stem == "full_mix":
                assert algo.depends_on == ["audio_load"], (
                    f"Algorithm {algo.name} has preferred_stem='full_mix' "
                    f"but depends_on={algo.depends_on!r}; expected ['audio_load']"
                )
