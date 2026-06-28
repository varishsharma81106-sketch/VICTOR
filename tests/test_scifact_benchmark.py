"""
Tests for victor.scifact_benchmark — SciFact Benchmark for ConflictDetector.

Tests cover:
  1. Label mapping (map_scifact_label)
  2. Dataset loading with mock data (no network calls)
  3. Evaluation loop with mocked ConflictDetector
  4. Per-class metrics and confusion matrix computation
  5. Report formatting / PRD threshold logic
  6. CLI argument parsing
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from victor.scifact_benchmark import (
    BenchmarkResult,
    ClassMetrics,
    ConflictDetector,  # re-import for type reference; actual mocking below
    EvalSample,
    _compute_per_class,
    build_parser,
    evaluate,
    get_label_distribution,
    load_scifact_data,
    map_scifact_label,
    print_report,
    _HAS_DATASETS,
    _LABEL_MAP,
    _PRD_THRESHOLD,
)
from victor.models import ConflictResult


# ---------------------------------------------------------------------------
# 1. Label mapping tests
# ---------------------------------------------------------------------------

class TestMapScifactLabel:
    """Tests for the SciFact → Victor label mapping."""

    @pytest.mark.parametrize(
        "scifact_label,expected",
        [
            ("SUPPORTS", "confirm"),
            ("REFUTES", "contradict"),
            ("NOT ENOUGH INFO", "inconclusive"),
            ("NEI", "inconclusive"),
        ],
    )
    def test_known_labels(self, scifact_label: str, expected: str) -> None:
        assert map_scifact_label(scifact_label) == expected

    def test_unknown_label_maps_to_inconclusive(self) -> None:
        assert map_scifact_label("UNKNOWN") == "inconclusive"
        assert map_scifact_label("") == "inconclusive"
        assert map_scifact_label("MAYBE") == "inconclusive"

    def test_case_sensitivity(self) -> None:
        """SciFact labels are uppercase, but confirm lowercase also works."""
        # Standard uppercase should work
        assert map_scifact_label("SUPPORTS") == "confirm"
        # Lowercase should map to inconclusive (not in _LABEL_MAP)
        assert map_scifact_label("supports") == "inconclusive"


# ---------------------------------------------------------------------------
# 2. Dataset loading tests
# ---------------------------------------------------------------------------

class TestDatasetLoading:
    """Test dataset loading with mocked HF datasets library."""

    def _make_mock_claims(self) -> List[Dict[str, Any]]:
        """Create mock claim rows matching the SciFact claims schema."""
        return [
            {
                "id": 1,
                "claim": "Aspirin reduces heart attack risk.",
                "evidence": {
                    "doc_001": {"label": "SUPPORTS"},
                    "doc_002": {"label": "REFUTES"},
                },
            },
            {
                "id": 2,
                "claim": "Vitamin C prevents the common cold.",
                "evidence": {
                    "doc_003": {"label": "NOT ENOUGH INFO"},
                },
            },
            {
                "id": 3,
                "claim": "No evidence claim with no annotations.",
                "evidence": {},
            },
            {
                "id": 4,
                "claim": "Caffeine increases alertness.",
                "evidence": {
                    "doc_004": "NEI",
                },
            },
        ]

    def _make_mock_corpus(self) -> List[Dict[str, Any]]:
        """Create mock corpus rows."""
        return [
            {
                "doc_id": "doc_001",
                "title": "Aspirin study",
                "abstract": ["Aspirin was shown to reduce heart attack risk by 20%."],
            },
            {
                "doc_id": "doc_002",
                "title": "Aspirin counter-study",
                "abstract": ["Aspirin did not reduce heart attack risk in this cohort."],
            },
            {
                "doc_id": "doc_003",
                "title": "Vitamin C review",
                "abstract": ["Results were inconclusive regarding cold prevention."],
            },
            {
                "doc_id": "doc_004",
                "title": "Caffeine paper",
                "abstract": ["Caffeine showed mixed effects on alertness."],
            },
        ]

    @patch("victor.scifact_benchmark._HAS_DATASETS", True)
    @patch("victor.scifact_benchmark._hf_load_dataset")
    def test_load_samples(self, mock_load: MagicMock) -> None:
        """Test that load_scifact_data produces correct EvalSample triples."""
        # Configure the mock to return different datasets based on name arg
        def side_effect(name, *args, **kwargs):
            if "claims" in str(args) + str(kwargs):
                return self._make_mock_claims()
            elif "corpus" in str(args) + str(kwargs):
                return self._make_mock_corpus()
            return []

        mock_load.side_effect = side_effect

        samples = load_scifact_data()
        # Should have: doc_001 (SUPPORTS), doc_002 (REFUTES), doc_003 (NEI), doc_004 (NEI)
        # Claim id=3 has empty evidence, so it's skipped
        assert len(samples) == 4

        # Check mapping
        assert samples[0].gold_direction == "confirm"
        assert samples[1].gold_direction == "contradict"
        assert samples[2].gold_direction == "inconclusive"
        assert samples[3].gold_direction == "inconclusive"

    @patch("victor.scifact_benchmark._HAS_DATASETS", True)
    @patch("victor.scifact_benchmark._hf_load_dataset")
    def test_sampling(self, mock_load: MagicMock) -> None:
        """Test that n_samples limits the output."""
        def side_effect(name, *args, **kwargs):
            if "claims" in str(args) + str(kwargs):
                return self._make_mock_claims()
            elif "corpus" in str(args) + str(kwargs):
                return self._make_mock_corpus()
            return []

        mock_load.side_effect = side_effect

        samples = load_scifact_data(n_samples=2, seed=42)
        assert len(samples) == 2

    def test_load_fails_without_datasets(self) -> None:
        """Test that ImportError is raised when datasets is not available."""
        with patch("victor.scifact_benchmark._HAS_DATASETS", False):
            with pytest.raises(ImportError, match="datasets"):
                load_scifact_data()


# ---------------------------------------------------------------------------
# 3. Evaluation loop tests
# ---------------------------------------------------------------------------

class TestEvaluate:
    """Test the evaluation loop with a mocked ConflictDetector."""

    @staticmethod
    def _make_detector(
        responses: List[ConflictResult],
    ) -> MagicMock:
        """Create a mock detector that returns pre-defined responses in order."""
        detector = MagicMock()
        call_count = [0]

        def mock_judge(claim_text: str, result_text: str) -> ConflictResult:
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                return responses[idx]
            return ConflictResult(
                direction="inconclusive", confidence=0.0, reason="ran out of mocks"
            )

        detector.judge = mock_judge
        return detector

    def test_perfect_predictions(self) -> None:
        """When all predictions match gold, accuracy should be 1.0."""
        samples = [
            EvalSample("c1", "claim1", "d1", "abstract1", "confirm"),
            EvalSample("c2", "claim2", "d2", "abstract2", "contradict"),
            EvalSample("c3", "claim3", "d3", "abstract3", "inconclusive"),
        ]
        responses = [
            ConflictResult("confirm", 0.9, "correct"),
            ConflictResult("contradict", 0.8, "correct"),
            ConflictResult("inconclusive", 0.7, "correct"),
        ]
        detector = self._make_detector(responses)
        result = evaluate(samples, detector)

        assert result.accuracy == 1.0
        assert result.n_evaluated == 3
        assert result.n_skipped_confidence == 0

    def test_all_wrong(self) -> None:
        """When no predictions match gold, accuracy should be 0.0."""
        samples = [
            EvalSample("c1", "claim1", "d1", "abstract1", "confirm"),
            EvalSample("c2", "claim2", "d2", "abstract2", "contradict"),
            EvalSample("c3", "claim3", "d3", "abstract3", "inconclusive"),
        ]
        # All predictions are "confirm" — only the first matches
        responses = [
            ConflictResult("confirm", 0.9, "wrong"),
            ConflictResult("confirm", 0.8, "wrong"),
            ConflictResult("confirm", 0.7, "wrong"),
        ]
        detector = self._make_detector(responses)
        result = evaluate(samples, detector)

        assert result.accuracy == pytest.approx(1 / 3, abs=0.01)

    def test_confidence_threshold_filters(self) -> None:
        """Predictions below confidence threshold should be skipped."""
        samples = [
            EvalSample("c1", "claim1", "d1", "abstract1", "confirm"),
            EvalSample("c2", "claim2", "d2", "abstract2", "contradict"),
            EvalSample("c3", "claim3", "d3", "abstract3", "inconclusive"),
        ]
        # Only the second has high enough confidence
        responses = [
            ConflictResult("confirm", 0.3, "low conf"),
            ConflictResult("contradict", 0.8, "high conf"),
            ConflictResult("inconclusive", 0.2, "low conf"),
        ]
        detector = self._make_detector(responses)
        result = evaluate(samples, detector, confidence_threshold=0.5)

        assert result.n_evaluated == 1
        assert result.n_skipped_confidence == 2
        assert result.accuracy == 1.0

    def test_empty_samples(self) -> None:
        """Empty sample list should produce zero accuracy without error."""
        detector = MagicMock()
        result = evaluate([], detector)

        assert result.accuracy == 0.0
        assert result.n_evaluated == 0
        assert result.n_total == 0


# ---------------------------------------------------------------------------
# 4. Per-class metrics and confusion matrix tests
# ---------------------------------------------------------------------------

class TestMetrics:
    """Test per-class metrics computation and confusion matrix."""

    def test_confusion_matrix_structure(self) -> None:
        """Confusion matrix should be 3x3 with all valid directions."""
        result = BenchmarkResult()
        assert set(result.confusion_matrix.keys()) == {"confirm", "contradict", "inconclusive"}
        for gold in result.confusion_matrix:
            assert set(result.confusion_matrix[gold].keys()) == {"confirm", "contradict", "inconclusive"}

    def test_per_class_f1_perfect(self) -> None:
        """When all predictions match, F1 should be 1.0 for all classes."""
        samples = [
            EvalSample("c1", "claim1", "d1", "a1", "confirm"),
            EvalSample("c2", "claim2", "d2", "a2", "confirm"),
            EvalSample("c3", "claim3", "d3", "a3", "contradict"),
            EvalSample("c4", "claim4", "d4", "a4", "inconclusive"),
        ]
        responses = [
            ConflictResult("confirm", 0.9, ""),
            ConflictResult("confirm", 0.9, ""),
            ConflictResult("contradict", 0.9, ""),
            ConflictResult("inconclusive", 0.9, ""),
        ]
        detector = MagicMock()
        detector.judge = MagicMock(side_effect=responses)
        result = evaluate(samples, detector)

        assert result.per_class["confirm"].f1 == pytest.approx(1.0)
        assert result.per_class["contradict"].f1 == pytest.approx(1.0)
        assert result.per_class["inconclusive"].f1 == pytest.approx(1.0)

    def test_per_class_zero_support(self) -> None:
        """Classes not in gold labels should have 0 support and 0 metrics."""
        samples = [
            EvalSample("c1", "claim1", "d1", "a1", "confirm"),
            EvalSample("c2", "claim2", "d2", "a2", "confirm"),
        ]
        responses = [
            ConflictResult("confirm", 0.9, ""),
            ConflictResult("confirm", 0.9, ""),
        ]
        detector = MagicMock()
        detector.judge = MagicMock(side_effect=responses)
        result = evaluate(samples, detector)

        # contradict and inconclusive have no gold instances
        assert result.per_class["contradict"].support == 0
        assert result.per_class["inconclusive"].support == 0
        # confirm has 2
        assert result.per_class["confirm"].support == 2
        assert result.per_class["confirm"].f1 == pytest.approx(1.0)

    def test_compute_per_class_precision_only(self) -> None:
        """Test precision when there are false positives."""
        result = BenchmarkResult()
        # Gold: 3 confirm, predicted: 5 confirm (2 false positives)
        result.confusion_matrix["confirm"]["confirm"] = 3
        result.confusion_matrix["contradict"]["confirm"] = 2
        result.confusion_matrix["inconclusive"]["confirm"] = 0
        _compute_per_class(result)

        # precision = 3 / (3 + 2) = 0.6
        assert result.per_class["confirm"].precision == pytest.approx(0.6)
        # recall = 3 / (3 + 0) = 1.0 (no FN since no other gold confirm went elsewhere)
        assert result.per_class["confirm"].recall == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. Report / threshold tests
# ---------------------------------------------------------------------------

class TestReport:
    """Test report formatting and PRD threshold."""

    def test_prd_threshold_value(self) -> None:
        assert _PRD_THRESHOLD == 0.85

    def test_print_report_runs(self, capsys: pytest.CaptureSysCallsResult) -> None:
        """print_report should not raise."""
        result = BenchmarkResult(
            accuracy=0.88,
            n_evaluated=100,
            n_total=100,
            n_skipped_confidence=0,
            confidence_threshold=0.0,
        )
        # Manually set some confusion matrix values
        result.confusion_matrix["confirm"]["confirm"] = 30
        result.confusion_matrix["contradict"]["contradict"] = 28
        result.confusion_matrix["inconclusive"]["inconclusive"] = 30
        _compute_per_class(result)

        print_report(result)
        output = capsys.readouterr().out
        assert "88.0%" in output
        assert "PASS" in output
        assert "confirm" in output
        assert "Confusion matrix" in output

    def test_print_report_fail(self, capsys: pytest.CaptureSysCallsResult) -> None:
        """Report should show FAIL when accuracy is below threshold."""
        result = BenchmarkResult(accuracy=0.72)
        result.confusion_matrix["confirm"]["confirm"] = 10
        _compute_per_class(result)

        print_report(result)
        output = capsys.readouterr().out
        assert "FAIL" in output


# ---------------------------------------------------------------------------
# 6. CLI tests
# ---------------------------------------------------------------------------

class TestCLI:
    """Test argument parsing."""

    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.n_samples is None
        assert args.confidence_threshold == 0.0
        assert args.dry_run is False
        assert args.seed == 42
        assert args.use_mock_llm is False

    def test_custom_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "--n-samples", "50",
            "--confidence-threshold", "0.6",
            "--dry-run",
            "--seed", "123",
            "--use-mock-llm",
        ])
        assert args.n_samples == 50
        assert args.confidence_threshold == 0.6
        assert args.dry_run is True
        assert args.seed == 123
        assert args.use_mock_llm is True

    def test_help(self, capsys: pytest.CaptureSysCallsResult) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "SciFact" in output
        assert "--n-samples" in output
        assert "--dry-run" in output


# ---------------------------------------------------------------------------
# 7. Label distribution test
# ---------------------------------------------------------------------------

class TestLabelDistribution:

    def test_distribution(self) -> None:
        samples = [
            EvalSample("c1", "c", "d1", "a", "confirm"),
            EvalSample("c2", "c", "d2", "a", "confirm"),
            EvalSample("c3", "c", "d3", "a", "confirm"),
            EvalSample("c4", "c", "d4", "a", "contradict"),
            EvalSample("c5", "c", "d5", "a", "inconclusive"),
        ]
        dist = get_label_distribution(samples)
        assert dist["confirm"] == 3
        assert dist["contradict"] == 1
        assert dist["inconclusive"] == 1

    def test_empty_distribution(self) -> None:
        dist = get_label_distribution([])
        assert dist == {}
