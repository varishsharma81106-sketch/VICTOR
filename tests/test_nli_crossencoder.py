"""
test_nli_crossencoder.py — unit tests for NLI cross-encoder integration.

All tests use MockNLICrossEncoder — no model download required.

Coverage:
  TestNLICrossEncoderClass   — MockNLICrossEncoder interface contract
  TestConflictDetectorNLI    — judge() override logic (6 cases)
  TestConflictJudgmentFields — new provenance fields on ConflictJudgment
  TestCoreNLIWiring          — Victor instantiation with use_mock_nli=True
"""
import pytest

from victor.reasoning import (
    ConflictDetector,
    ConflictJudgment,
    MockNLICrossEncoder,
    NLICrossEncoder,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

class _MockLLM:
    """Minimal LLM stub — always returns the same direction via generate_structured."""

    def __init__(self, direction: str = "confirm", confidence: float = 0.8):
        self._direction  = direction
        self._confidence = confidence

    def generate_structured(self, prompt, response_schema=None, retries=1):
        import json
        import types
        payload = json.dumps({
            "reasoning":  "mock reasoning",
            "direction":  self._direction,
            "confidence": self._confidence,
        })
        resp = types.SimpleNamespace(text=payload)
        return resp


def _make_detector(
    llm_direction: str   = "confirm",
    llm_confidence: float = 0.8,
    nli_direction: str   = "inconclusive",
    nli_confidence: float = 0.0,
    nli_override_threshold: float = 0.5,
) -> ConflictDetector:
    llm = _MockLLM(direction=llm_direction, confidence=llm_confidence)
    nli = MockNLICrossEncoder(direction=nli_direction, confidence=nli_confidence)
    return ConflictDetector(llm=llm, nli=nli, nli_override_threshold=nli_override_threshold)


# ──────────────────────────────────────────────────────────────────────────────
# TestNLICrossEncoderClass
# ──────────────────────────────────────────────────────────────────────────────

class TestNLICrossEncoderClass:
    def test_mock_returns_fixed_direction(self):
        nli = MockNLICrossEncoder(direction="contradict", confidence=0.9)
        direction, confidence = nli.predict("claim text", "evidence text")
        assert direction == "contradict"
        assert confidence == pytest.approx(0.9)

    def test_mock_default_is_inconclusive(self):
        nli = MockNLICrossEncoder()
        direction, confidence = nli.predict("a", "b")
        assert direction == "inconclusive"
        assert confidence == 0.0

    def test_mock_is_subclass_of_nli(self):
        assert issubclass(MockNLICrossEncoder, NLICrossEncoder)

    def test_mock_predict_ignores_input_text(self):
        """predict() result is fixed regardless of the text passed in."""
        nli = MockNLICrossEncoder(direction="confirm", confidence=0.7)
        d1, c1 = nli.predict("foo", "bar")
        d2, c2 = nli.predict("completely different", "inputs")
        assert d1 == d2
        assert c1 == c2


# ──────────────────────────────────────────────────────────────────────────────
# TestConflictJudgmentFields
# ──────────────────────────────────────────────────────────────────────────────

class TestConflictJudgmentFields:
    def test_default_nli_fields_are_none(self):
        j = ConflictJudgment(direction="confirm", confidence=0.9, reason="r")
        assert j.nli_direction  is None
        assert j.nli_confidence is None
        assert j.nli_override   is False

    def test_explicit_nli_fields_stored(self):
        j = ConflictJudgment(
            direction="contradict", confidence=0.8, reason="r",
            nli_direction="contradict", nli_confidence=0.75, nli_override=True,
        )
        assert j.nli_direction  == "contradict"
        assert j.nli_confidence == pytest.approx(0.75)
        assert j.nli_override   is True

    def test_nli_override_false_by_default(self):
        j = ConflictJudgment(direction="confirm", confidence=0.5, reason="x")
        assert j.nli_override is False


# ──────────────────────────────────────────────────────────────────────────────
# TestConflictDetectorNLI — override logic
# ──────────────────────────────────────────────────────────────────────────────

class TestConflictDetectorNLI:

    # ── Override cases (NLI says contradict, LLM too lenient) ────────────────

    def test_override_when_llm_confirm_nli_contradict(self):
        """Core agreement-bias case: LLM says confirm, NLI says contradict."""
        det = _make_detector(
            llm_direction="confirm",
            nli_direction="contradict",
            nli_confidence=0.85,
        )
        j = det.judge("Drug X reduces blood pressure.",
                      "Drug X showed no significant effect on blood pressure.")
        assert j.direction    == "contradict"
        assert j.nli_override is True
        assert j.nli_direction  == "contradict"
        assert j.nli_confidence == pytest.approx(0.85)
        assert "NLI override" in j.reason

    def test_override_when_llm_inconclusive_nli_contradict(self):
        """Second agreement-bias case: LLM says inconclusive, NLI says contradict."""
        det = _make_detector(
            llm_direction="inconclusive",
            nli_direction="contradict",
            nli_confidence=0.75,
        )
        j = det.judge("claim", "evidence")
        assert j.direction    == "contradict"
        assert j.nli_override is True

    def test_override_confidence_comes_from_nli(self):
        """When NLI overrides, the returned confidence is the NLI confidence."""
        det = _make_detector(
            llm_direction="confirm", llm_confidence=0.9,
            nli_direction="contradict", nli_confidence=0.72,
        )
        j = det.judge("claim", "evidence")
        assert j.confidence == pytest.approx(0.72)

    # ── Non-override cases ────────────────────────────────────────────────────

    def test_no_override_when_llm_contradict(self):
        """LLM already says contradict — no override needed regardless of NLI."""
        det = _make_detector(
            llm_direction="contradict",
            nli_direction="contradict",
            nli_confidence=0.9,
        )
        j = det.judge("claim", "evidence")
        assert j.nli_override is False
        assert j.direction == "contradict"

    def test_no_override_when_nli_confidence_below_threshold(self):
        """NLI says contradict but below threshold — LLM verdict kept."""
        det = _make_detector(
            llm_direction="confirm",
            nli_direction="contradict",
            nli_confidence=0.4,          # below default threshold of 0.5
            nli_override_threshold=0.5,
        )
        j = det.judge("claim", "evidence")
        assert j.direction    == "confirm"
        assert j.nli_override is False

    def test_no_override_when_nli_agrees(self):
        """LLM and NLI both say confirm — no override."""
        det = _make_detector(
            llm_direction="confirm",
            nli_direction="confirm",
            nli_confidence=0.9,
        )
        j = det.judge("claim", "evidence")
        assert j.direction    == "confirm"
        assert j.nli_override is False

    # ── Provenance always stored ──────────────────────────────────────────────

    def test_nli_provenance_stored_even_without_override(self):
        """NLI direction and confidence are stored even when no override happens."""
        det = _make_detector(
            llm_direction="confirm",
            nli_direction="confirm",
            nli_confidence=0.88,
        )
        j = det.judge("claim", "evidence")
        assert j.nli_direction  == "confirm"
        assert j.nli_confidence == pytest.approx(0.88)

    def test_nli_none_returns_llm_judgment_unchanged(self):
        """When no NLI is configured, judge() returns the LLM judgment with no NLI fields."""
        llm = _MockLLM(direction="confirm", confidence=0.9)
        det = ConflictDetector(llm=llm, nli=None)
        j   = det.judge("claim", "evidence")
        assert j.direction      == "confirm"
        assert j.nli_direction  is None
        assert j.nli_confidence is None
        assert j.nli_override   is False

    def test_custom_threshold_respected(self):
        """nli_override_threshold=0.9 — NLI at 0.85 should NOT override."""
        det = _make_detector(
            llm_direction="confirm",
            nli_direction="contradict",
            nli_confidence=0.85,
            nli_override_threshold=0.9,
        )
        j = det.judge("claim", "evidence")
        assert j.direction    == "confirm"
        assert j.nli_override is False


# ──────────────────────────────────────────────────────────────────────────────
# TestCoreNLIWiring
# ──────────────────────────────────────────────────────────────────────────────

class TestCoreNLIWiring:
    """Victor instantiation with use_mock_nli=True — no real model, no LLM."""

    def _make_victor(self, use_nli: bool = True):
        import tempfile
        from victor.config import VictorConfig
        from victor.core import Victor
        with tempfile.TemporaryDirectory() as tmp:
            cfg = VictorConfig(
                home_dir            = tmp,
                use_mock_llm        = True,
                use_mock_embedder   = True,
                use_nli_crossencoder= use_nli,
                use_mock_nli        = True,
            )
            return Victor(config=cfg)

    def test_victor_has_nli_on_conflict_detector(self):
        v = self._make_victor(use_nli=True)
        assert v.conflict_detector.nli is not None
        assert isinstance(v.conflict_detector.nli, MockNLICrossEncoder)

    def test_victor_nli_disabled_sets_none(self):
        v = self._make_victor(use_nli=False)
        assert v.conflict_detector.nli is None

    def test_victor_nli_threshold_from_config(self):
        import tempfile
        from victor.config import VictorConfig
        from victor.core import Victor
        with tempfile.TemporaryDirectory() as tmp:
            cfg = VictorConfig(
                home_dir             = tmp,
                use_mock_llm         = True,
                use_mock_embedder    = True,
                use_nli_crossencoder = True,
                use_mock_nli         = True,
                nli_override_threshold = 0.75,
            )
            v = Victor(config=cfg)
        assert v.conflict_detector.nli_override_threshold == pytest.approx(0.75)


# ──────────────────────────────────────────────────────────────────────────────
# TestNLICrossEncoderV53Features — label_order param and validate_label_order()
# ──────────────────────────────────────────────────────────────────────────────

class TestNLICrossEncoderV53Features:
    """v5.3 additions: explicit label_order param and validate_label_order()."""

    # ── label_order constructor param ─────────────────────────────────────────

    def test_label_order_param_accepted(self):
        """Explicit label_order is accepted and stored without error."""
        nli = NLICrossEncoder(label_order=["entailment", "neutral", "contradiction"])
        assert nli._explicit_label_order == ["entailment", "neutral", "contradiction"]

    def test_label_order_lowercased(self):
        """label_order values are normalised to lowercase."""
        nli = NLICrossEncoder(label_order=["ENTAILMENT", "Neutral", "CONTRADICTION"])
        assert nli._explicit_label_order == ["entailment", "neutral", "contradiction"]

    def test_label_order_none_by_default(self):
        """Without label_order=, explicit override is None (auto-detect runs)."""
        nli = NLICrossEncoder()
        assert nli._explicit_label_order is None

    def test_label_order_wrong_values_raises(self):
        """A list with an invalid label name raises ValueError."""
        with pytest.raises(ValueError, match="permutation"):
            NLICrossEncoder(label_order=["entailment", "neutral", "WRONG"])

    def test_label_order_wrong_length_raises(self):
        """A list with only two elements raises ValueError."""
        with pytest.raises(ValueError, match="permutation"):
            NLICrossEncoder(label_order=["entailment", "neutral"])

    def test_label_order_duplicate_raises(self):
        """A list with a duplicate label raises ValueError."""
        with pytest.raises(ValueError, match="permutation"):
            NLICrossEncoder(label_order=["entailment", "entailment", "contradiction"])

    # ── validate_label_order() ────────────────────────────────────────────────

    def _make_validating_mock(self, entailment_dir: str, contradiction_dir: str) -> NLICrossEncoder:
        """
        Return an NLICrossEncoder subclass whose predict() returns known results
        for the two smoke-test pairs, so validate_label_order() can be exercised
        without loading any real model.
        """
        class _Stub(NLICrossEncoder):
            def __init__(self):
                super().__init__()
                self._entail_dir = entailment_dir
                self._contra_dir = contradiction_dir

            def predict(self, premise: str, hypothesis: str) -> tuple:
                if "sleeping" in premise:       # entailment pair
                    return self._entail_dir, 0.9
                return self._contra_dir, 0.9    # contradiction pair

        return _Stub()

    def test_validate_passes_on_correct_mapping(self):
        """validate_label_order() returns True when both pairs are correct."""
        stub = self._make_validating_mock(
            entailment_dir="confirm", contradiction_dir="contradict"
        )
        assert stub.validate_label_order() is True

    def test_validate_raises_on_inverted_entailment(self):
        """validate_label_order() raises RuntimeError when entailment pair returns wrong label."""
        stub = self._make_validating_mock(
            entailment_dir="contradict", contradiction_dir="contradict"
        )
        with pytest.raises(RuntimeError, match="Label order validation FAILED"):
            stub.validate_label_order()

    def test_validate_raises_on_inverted_contradiction(self):
        """validate_label_order() raises RuntimeError when contradiction pair returns wrong label."""
        stub = self._make_validating_mock(
            entailment_dir="confirm", contradiction_dir="confirm"
        )
        with pytest.raises(RuntimeError, match="Label order validation FAILED"):
            stub.validate_label_order()

    def test_validate_error_message_contains_model_name(self):
        """RuntimeError message includes the model name for diagnostics."""
        class _Bad(NLICrossEncoder):
            def __init__(self):
                super().__init__(model_name="some/test-model")
            def predict(self, p, h):
                return "contradict", 0.9   # always wrong for entailment pair

        with pytest.raises(RuntimeError, match="some/test-model"):
            _Bad().validate_label_order()

    def test_validate_error_message_contains_known_orders(self):
        """RuntimeError lists known correct orders so the user can fix the flag."""
        class _Bad(NLICrossEncoder):
            def predict(self, p, h):
                return "contradict", 0.9

        with pytest.raises(RuntimeError, match="nli-deberta-v3-base"):
            _Bad().validate_label_order()


# ──────────────────────────────────────────────────────────────────────────────
# TestScifactBenchmarkV53Flags — --nli-label-order and --skip-nli-smoke-test
# ──────────────────────────────────────────────────────────────────────────────

class TestScifactBenchmarkV53Flags:
    """CLI flag tests for the v5.3 benchmark additions."""

    def _parse(self, argv):
        from victor.scifact_benchmark import build_parser
        return build_parser().parse_args(argv)

    def test_nli_label_order_flag_accepted(self):
        args = self._parse(["--nli-label-order", "entailment,neutral,contradiction"])
        assert args.nli_label_order == "entailment,neutral,contradiction"

    def test_nli_label_order_default_is_none(self):
        args = self._parse([])
        assert args.nli_label_order is None

    def test_skip_nli_smoke_test_flag(self):
        args = self._parse(["--skip-nli-smoke-test"])
        assert args.skip_nli_smoke_test is True

    def test_skip_nli_smoke_test_default_false(self):
        args = self._parse([])
        assert args.skip_nli_smoke_test is False

    def test_label_order_and_skip_smoke_test_together(self):
        args = self._parse([
            "--nli-label-order", "contradiction,neutral,entailment",
            "--skip-nli-smoke-test",
        ])
        assert args.nli_label_order == "contradiction,neutral,entailment"
        assert args.skip_nli_smoke_test is True
