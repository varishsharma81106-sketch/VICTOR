"""
Tests for DoD #8: StatisticsKernel + core.py wiring + CLI compute commands.

Run with:  pytest victor/tests/test_statistics_kernel.py -v
"""
import json
import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from victor.kernels import StatisticsKernel, ComputedResult, KERNEL_VERSION
from victor.models import NodeType, EdgeType, EpistemicStatus


# ═══════════════════════════════════════════════════════════════════════════════
#  StatisticsKernel Unit Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatisticsKernelCompute:
    """Test StatisticsKernel.compute() with various inputs."""

    def test_basic_five_values(self):
        """Standard case: 5 values produce correct mean, variance, std, CI."""
        k = StatisticsKernel()
        r = k.compute([1.0, 2.0, 3.0, 4.0, 5.0], input_node_ids=["n1", "n2", "n3", "n4", "n5"])
        assert r.kernel == "statistics"
        assert r.kernel_version == KERNEL_VERSION
        assert r.inputs == ["n1", "n2", "n3", "n4", "n5"]
        assert r.outputs["n"] == 5.0
        assert r.outputs["mean"] == 3.0
        # Sample variance: sum((x-3)^2) / 4 = 10/4 = 2.5
        assert abs(r.outputs["variance"] - 2.5) < 1e-6
        assert abs(r.outputs["std"] - math.sqrt(2.5)) < 1e-6
        # CI at 95%: 3 ± 1.96 * sqrt(2.5/5)
        se = math.sqrt(2.5 / 5)
        expected_ci_low = 3.0 - 1.96 * se
        expected_ci_high = 3.0 + 1.96 * se
        assert abs(r.outputs["ci_low"] - expected_ci_low) < 1e-4
        assert abs(r.outputs["ci_high"] - expected_ci_high) < 1e-4
        assert r.uncertainty is not None
        assert "se" in r.uncertainty
        assert r.reproducibility_hash  # non-empty

    def test_single_value(self):
        """n=1: variance and std should be 0."""
        k = StatisticsKernel()
        r = k.compute([42.0])
        assert r.outputs["mean"] == 42.0
        assert r.outputs["variance"] == 0.0
        assert r.outputs["std"] == 0.0
        assert r.outputs["n"] == 1.0

    def test_empty_raises(self):
        """Empty values list must raise ValueError."""
        k = StatisticsKernel()
        with pytest.raises(ValueError, match="at least one value"):
            k.compute([])

    def test_custom_confidence_level(self):
        """90% CI uses z=1.645, not 1.96."""
        k = StatisticsKernel()
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        r_95 = k.compute(values, confidence_level=0.95)
        r_90 = k.compute(values, confidence_level=0.90)
        # 90% CI should be narrower than 95%
        width_95 = r_95.outputs["ci_high"] - r_95.outputs["ci_low"]
        width_90 = r_90.outputs["ci_high"] - r_90.outputs["ci_low"]
        assert width_90 < width_95

    def test_reproducibility_hash_deterministic(self):
        """Same inputs → same hash."""
        k = StatisticsKernel()
        r1 = k.compute([1.0, 2.0, 3.0], input_node_ids=["a", "b", "c"])
        r2 = k.compute([1.0, 2.0, 3.0], input_node_ids=["a", "b", "c"])
        assert r1.reproducibility_hash == r2.reproducibility_hash

    def test_reproducibility_hash_changes_with_inputs(self):
        """Different input node IDs → different hash (same values)."""
        k = StatisticsKernel()
        r1 = k.compute([1.0, 2.0, 3.0], input_node_ids=["a", "b", "c"])
        r2 = k.compute([1.0, 2.0, 3.0], input_node_ids=["x", "y", "z"])
        assert r1.reproducibility_hash != r2.reproducibility_hash

    def test_no_input_node_ids(self):
        """When input_node_ids is None, generates raw: tags."""
        k = StatisticsKernel()
        r = k.compute([10.0, 20.0])
        assert r.inputs == ["raw:value:0", "raw:value:1"]

    def test_small_n_notes_approximation(self):
        """n<30 should have a note about approximate CI."""
        k = StatisticsKernel()
        r = k.compute([1.0, 2.0, 3.0])
        assert "approximate" in r.notes.lower()

    def test_large_n_no_approximation_note(self):
        """n>=30 should NOT have the approximate CI note."""
        k = StatisticsKernel()
        values = list(range(1, 31))  # n=30
        r = k.compute(values)
        assert "approximate" not in r.notes.lower()


class TestStatisticsKernelEffectSize:
    """Test StatisticsKernel.effect_size()."""

    def test_basic_cohens_d(self):
        """Two clearly different groups should produce a large Cohen's d."""
        k = StatisticsKernel()
        group_a = [1.0, 1.1, 0.9, 1.0, 1.1]
        group_b = [5.0, 5.1, 4.9, 5.0, 5.1]
        r = k.effect_size(group_a, group_b)
        assert r.kernel == "statistics.effect_size"
        assert "cohens_d" in r.outputs
        assert abs(r.outputs["cohens_d"]) > 2.0  # Very large effect
        assert r.outputs["magnitude"] == "large"

    def test_identical_groups(self):
        """Identical groups → Cohen's d ≈ 0, magnitude = negligible."""
        k = StatisticsKernel()
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        r = k.effect_size(values, values)
        assert abs(r.outputs["cohens_d"]) < 0.01
        assert r.outputs["magnitude"] == "negligible"

    def test_small_effect(self):
        """Groups with high within-group variance relative to mean diff should give small effect."""
        k = StatisticsKernel()
        group_a = [10.0, 20.0, 5.0, 15.0, 25.0, 8.0, 18.0]
        group_b = [11.0, 21.0, 6.0, 16.0, 26.0, 9.0, 19.0]
        r = k.effect_size(group_a, group_b)
        # With high variance, a small mean shift should give negligible/small d
        assert r.outputs["magnitude"] in ("negligible", "small")

    def test_too_few_values_raises(self):
        """Less than 2 values per group must raise ValueError."""
        k = StatisticsKernel()
        with pytest.raises(ValueError, match="at least 2 values per group"):
            k.effect_size([1.0], [2.0, 3.0])
        with pytest.raises(ValueError, match="at least 2 values per group"):
            k.effect_size([1.0, 2.0], [3.0])

    def test_reproducibility_hash_deterministic(self):
        """Same inputs → same hash for effect_size."""
        k = StatisticsKernel()
        r1 = k.effect_size([1.0, 2.0], [3.0, 4.0], input_node_ids=["a", "b", "c", "d"])
        r2 = k.effect_size([1.0, 2.0], [3.0, 4.0], input_node_ids=["a", "b", "c", "d"])
        assert r1.reproducibility_hash == r2.reproducibility_hash


# ═══════════════════════════════════════════════════════════════════════════════
#  Core Wiring Tests (Victor.compute_statistics / compute_effect_size)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_victor_with_mock_graph():
    """
    Create a Victor instance with a mock-LLM config and a temporary graph,
    then mock the embedder so graph.add_node() doesn't try to load sentence_transformers.
    """
    from victor.core import Victor
    from victor.config import VictorConfig

    config = VictorConfig(use_mock_llm=True)
    tmpdir = tempfile.mkdtemp()
    config.home_dir = Path(tmpdir)
    config.vector_db_dir = Path(tmpdir) / "vector_db"
    config.graph_file = Path(tmpdir) / "graph" / "kg.json"
    config.llm_log_file = Path(tmpdir) / "logs" / "llm.jsonl"
    config.extraction_log_file = Path(tmpdir) / "logs" / "extract.jsonl"

    v = Victor(config=config)
    # Mock the embedder so add_node doesn't need sentence_transformers
    v.embedder.embed = MagicMock(return_value=[0.1] * 384)
    return v, tmpdir


class TestCoreComputeStatistics:
    """Test Victor.compute_statistics() wiring through to graph."""

    def test_compute_statistics_creates_computed_node(self):
        """Should create a COMPUTED node with correct metadata."""
        v, tmpdir = _make_victor_with_mock_graph()

        # Add an experiment node with numeric results
        v.graph.add_node(
            node_id="exp_001",
            ntype=NodeType.EXPERIMENT,
            label="Baseline experiment",
            metadata={
                "results": json.dumps({"accuracy": 0.85, "f1": 0.82, "precision": 0.88}),
                "epistemic_status": EpistemicStatus.EXPERIMENT.value,
            },
        )

        # After the Bug 2 fix, metric_name must match an actual key in results_dict.
        # Passing metric_name="accuracy" pulls only that field (no cross-metric conflation).
        result = v.compute_statistics(["exp_001"], metric_name="accuracy")

        # Should have created a COMPUTED node
        assert result["computed_node_id"].startswith("computed_")
        assert result["kernel"] == "statistics"
        assert result["n_values"] == 1  # single metric, no conflation
        import pytest as _pytest
        assert result["outputs"]["mean"] == _pytest.approx(0.85)

        # Verify the node exists in the graph
        node = v.graph.get_node(result["computed_node_id"])
        assert node is not None
        assert node["ntype"] == NodeType.COMPUTED
        assert "Statistics" in node["label"]

        # Verify DERIVED_FROM edge exists
        inspection = v.graph.inspect_node(result["computed_node_id"])
        out_edges = inspection["out_edges"]
        derived = [e for e in out_edges if e["etype"] == EdgeType.DERIVED_FROM]
        assert len(derived) == 1
        assert derived[0]["to"] == "exp_001"

    def test_compute_statistics_node_not_found(self):
        """Should raise ValueError for missing node."""
        v, tmpdir = _make_victor_with_mock_graph()
        with pytest.raises(ValueError, match="Node not found"):
            v.compute_statistics(["nonexistent_node"])

    def test_compute_statistics_no_numeric_values(self):
        """Should raise ValueError when node has no numeric values."""
        v, tmpdir = _make_victor_with_mock_graph()
        v.graph.add_node(
            node_id="note_001",
            ntype=NodeType.NOTE,
            label="Just a note",
            metadata={"text": "no numbers here"},
        )
        with pytest.raises(ValueError, match="No numeric values"):
            v.compute_statistics(["note_001"])

    def test_compute_statistics_with_value_key(self):
        """Should pull numeric values from 'value' key in metadata."""
        v, tmpdir = _make_victor_with_mock_graph()
        v.graph.add_node(
            node_id="meas_001",
            ntype=NodeType.COMPUTED,
            label="Measurement",
            metadata={"value": 7.5, "epistemic_status": "measurement"},
        )
        result = v.compute_statistics(["meas_001"], metric_name="value")
        assert result["outputs"]["mean"] == 7.5
        assert result["n_values"] == 1


class TestCoreComputeEffectSize:
    """Test Victor.compute_effect_size() wiring through to graph."""

    def test_compute_effect_size_creates_computed_node(self):
        """Should create a COMPUTED node with Cohen's d outputs."""
        v, tmpdir = _make_victor_with_mock_graph()

        # Add two experiment nodes
        v.graph.add_node(
            node_id="exp_a",
            ntype=NodeType.EXPERIMENT,
            label="Control group",
            metadata={
                "results": json.dumps({"score": 10.0}),
                "epistemic_status": EpistemicStatus.EXPERIMENT.value,
            },
        )
        v.graph.add_node(
            node_id="exp_b",
            ntype=NodeType.EXPERIMENT,
            label="Treatment group",
            metadata={
                "results": json.dumps({"score": 20.0}),
                "epistemic_status": EpistemicStatus.EXPERIMENT.value,
            },
        )

        # Need at least 2 values per group for effect_size
        v.graph.add_node(
            node_id="exp_a2",
            ntype=NodeType.EXPERIMENT,
            label="Control group 2",
            metadata={
                "results": json.dumps({"score": 11.0}),
                "epistemic_status": EpistemicStatus.EXPERIMENT.value,
            },
        )
        v.graph.add_node(
            node_id="exp_b2",
            ntype=NodeType.EXPERIMENT,
            label="Treatment group 2",
            metadata={
                "results": json.dumps({"score": 21.0}),
                "epistemic_status": EpistemicStatus.EXPERIMENT.value,
            },
        )

        result = v.compute_effect_size(
            group_a_node_ids=["exp_a", "exp_a2"],
            group_b_node_ids=["exp_b", "exp_b2"],
            metric_name="score",
        )

        assert result["computed_node_id"].startswith("computed_")
        assert result["kernel"] == "statistics.effect_size"
        assert "cohens_d" in result["outputs"]
        assert result["n_group_a"] == 2
        assert result["n_group_b"] == 2

        # Verify DERIVED_FROM edges to all 4 input nodes
        inspection = v.graph.inspect_node(result["computed_node_id"])
        derived = [e for e in inspection["out_edges"] if e["etype"] == EdgeType.DERIVED_FROM]
        assert len(derived) == 4


# ═══════════════════════════════════════════════════════════════════════════════
#  StatisticsKernel attribute on Victor
# ═══════════════════════════════════════════════════════════════════════════════

class TestVictorHasStatisticsKernel:
    def test_statistics_kernel_attribute_exists(self):
        """Victor instance should have a statistics_kernel attribute."""
        v, tmpdir = _make_victor_with_mock_graph()
        assert hasattr(v, "statistics_kernel")
        assert isinstance(v.statistics_kernel, StatisticsKernel)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])