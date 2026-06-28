"""
test_metric_conflation.py — regression tests for compute_effect_size metric bug

Bug (v4.6): compute_effect_size._pull_values() iterated all
results_dict.values() instead of extracting a specific named metric.
This silently averaged precision + recall + f1 (or any other numeric fields
stored together) into one list, producing Cohen's d over meaningless data.

compute_statistics() already did it correctly (metric_name parameter).
compute_effect_size now has the same parameter and the same extraction logic.

Ref: PRD v3.3 Section 5 (kernels.py metric conflation open bug).
"""

import json
import tempfile
from pathlib import Path

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from victor import Victor
from victor.config import VictorConfig


@pytest.fixture
def victor(tmp_path):
    cfg = VictorConfig(use_mock_llm=True, use_mock_embedder=True)
    cfg.home_dir = tmp_path
    cfg.vector_db_dir = tmp_path / "vector_db"
    cfg.graph_file = tmp_path / "graph" / "kg.json"
    cfg.llm_log_file = tmp_path / "logs" / "llm.jsonl"
    cfg.extraction_log_file = tmp_path / "logs" / "extract.jsonl"
    v = Victor(config=cfg)
    v.embedder.embed = MagicMock(return_value=[0.1] * 384)
    return v


def _add_experiment_with_multi_metric_results(victor, label, results_dict):
    """Add an EXPERIMENT node whose 'results' metadata field is a JSON dict
    with multiple numeric keys (e.g. precision, recall, f1)."""
    node_id = f"exp_{label.replace(' ', '_')}"
    victor.graph.add_node(
        node_id=node_id,
        ntype="experiment",
        label=label,
        metadata={
            "results": json.dumps(results_dict),
            "epistemic_status": "EXPERIMENT",
            "importance_score": 0.8,
        },
    )
    return node_id


# ---------------------------------------------------------------------------
# 1. Metric conflation: multi-metric nodes must not be averaged together
# ---------------------------------------------------------------------------

def test_effect_size_extracts_only_named_metric(victor):
    """
    Nodes with results = {precision: 0.9, recall: 0.6, f1: 0.72} should
    contribute only the requested metric, not all three values.

    Before the fix: _pull_values returned [0.9, 0.6, 0.72] per node.
    After the fix: it returns [0.9] if metric_name="precision".
    """
    nid_a1 = _add_experiment_with_multi_metric_results(
        victor, "exp_a1", {"precision": 0.90, "recall": 0.60, "f1": 0.72}
    )
    nid_a2 = _add_experiment_with_multi_metric_results(
        victor, "exp_a2", {"precision": 0.88, "recall": 0.65, "f1": 0.74}
    )
    nid_b1 = _add_experiment_with_multi_metric_results(
        victor, "exp_b1", {"precision": 0.70, "recall": 0.80, "f1": 0.74}
    )
    nid_b2 = _add_experiment_with_multi_metric_results(
        victor, "exp_b2", {"precision": 0.72, "recall": 0.82, "f1": 0.76}
    )

    # Compute effect size on 'precision' only
    result = victor.compute_effect_size(
        group_a_node_ids=[nid_a1, nid_a2],
        group_b_node_ids=[nid_b1, nid_b2],
        metric_name="precision",
    )

    # Group A precision mean ≈ 0.89, Group B precision mean ≈ 0.71
    # Cohen's d should be large-positive (A > B)
    cohens_d = result["outputs"]["cohens_d"]
    assert cohens_d > 0, (
        f"Expected positive Cohen's d (A precision > B precision), got {cohens_d}"
    )

    # The n_values in outputs['n'] from compute_effect_size uses group sizes
    # (this is effect_size, not compute_statistics, so just check outputs exist)
    assert "mean_a" in result["outputs"]
    assert "mean_b" in result["outputs"]

    # Mean values should be close to the actual precision means, not some
    # average of precision+recall+f1 (which would be ~0.74 for both groups)
    mean_a = result["outputs"]["mean_a"]
    mean_b = result["outputs"]["mean_b"]
    assert abs(mean_a - 0.89) < 0.01, f"mean_a should be ~0.89, got {mean_a}"
    assert abs(mean_b - 0.71) < 0.01, f"mean_b should be ~0.71, got {mean_b}"


def test_effect_size_different_metric_gives_different_result(victor):
    """
    Requesting metric_name='recall' vs 'precision' on the same nodes must
    produce different Cohen's d values. Before the fix they would produce
    the same value (all metrics averaged together).

    Note: effect_size requires >= 2 values per group, so each group has 2 nodes.
    """
    nid_a1 = _add_experiment_with_multi_metric_results(
        victor, "exp_c1a", {"precision": 0.90, "recall": 0.50}
    )
    nid_a2 = _add_experiment_with_multi_metric_results(
        victor, "exp_c2a", {"precision": 0.88, "recall": 0.52}
    )
    nid_b1 = _add_experiment_with_multi_metric_results(
        victor, "exp_c1b", {"precision": 0.60, "recall": 0.85}
    )
    nid_b2 = _add_experiment_with_multi_metric_results(
        victor, "exp_c2b", {"precision": 0.62, "recall": 0.83}
    )

    res_prec = victor.compute_effect_size([nid_a1, nid_a2], [nid_b1, nid_b2], metric_name="precision")
    res_rec  = victor.compute_effect_size([nid_a1, nid_a2], [nid_b1, nid_b2], metric_name="recall")

    d_prec = res_prec["outputs"]["cohens_d"]
    d_rec  = res_rec["outputs"]["cohens_d"]

    # precision: A(0.90) > B(0.60) → d_prec > 0
    # recall:    A(0.50) < B(0.85) → d_rec < 0
    assert d_prec > 0, f"Expected positive d for precision (A>B), got {d_prec}"
    assert d_rec  < 0, f"Expected negative d for recall (A<B), got {d_rec}"

    # And they must not be equal
    assert abs(d_prec - d_rec) > 0.01, (
        f"Precision and recall gave same Cohen's d ({d_prec}) — "
        "metric extraction is still broken"
    )


def test_effect_size_raises_on_missing_metric(victor):
    """
    Asking for a metric that doesn't exist in a node should raise ValueError,
    not silently return empty results or fall through to unrelated fields.
    """
    nid_a = _add_experiment_with_multi_metric_results(
        victor, "exp_d1", {"precision": 0.90, "recall": 0.60}
    )
    nid_b = _add_experiment_with_multi_metric_results(
        victor, "exp_d2", {"precision": 0.70, "recall": 0.80}
    )

    with pytest.raises(ValueError, match="nonexistent_metric"):
        victor.compute_effect_size([nid_a], [nid_b], metric_name="nonexistent_metric")


def test_effect_size_default_metric_is_value(victor):
    """
    Default metric_name='value' must still work for simple MEASUREMENT nodes
    that store a direct 'value' field in metadata (not a results JSON).
    """
    victor.graph.add_node(
        "meas_e1", ntype="measurement", label="Measurement E1",
        metadata={"value": 1.5, "epistemic_status": "MEASUREMENT", "importance_score": 0.9},
    )
    victor.graph.add_node(
        "meas_e2", ntype="measurement", label="Measurement E2",
        metadata={"value": 1.8, "epistemic_status": "MEASUREMENT", "importance_score": 0.9},
    )
    victor.graph.add_node(
        "meas_e3", ntype="measurement", label="Measurement E3",
        metadata={"value": 3.0, "epistemic_status": "MEASUREMENT", "importance_score": 0.9},
    )
    victor.graph.add_node(
        "meas_e4", ntype="measurement", label="Measurement E4",
        metadata={"value": 3.5, "epistemic_status": "MEASUREMENT", "importance_score": 0.9},
    )

    # Should work without specifying metric_name
    result = victor.compute_effect_size(
        ["meas_e1", "meas_e2"],
        ["meas_e3", "meas_e4"],
    )
    assert "cohens_d" in result["outputs"]
    # Group B is larger, so cohens_d should be negative
    assert result["outputs"]["cohens_d"] < 0


def test_compute_statistics_metric_name_unchanged(victor):
    """
    Confirm compute_statistics() still correctly uses metric_name
    (regression guard — this was already correct before v4.9).
    """
    nid = _add_experiment_with_multi_metric_results(
        victor, "exp_stats", {"precision": 0.85, "recall": 0.70, "f1": 0.77}
    )

    result = victor.compute_statistics([nid], metric_name="precision")
    assert abs(result["outputs"]["mean"] - 0.85) < 0.0001, (
        f"compute_statistics extracted wrong metric: mean={result['outputs']['mean']}"
    )
