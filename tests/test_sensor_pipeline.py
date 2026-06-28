"""
Tests for the Reality → Artifact pipeline (Victor v4.6 Step 2).

All tests use MockClassifier and a tmp image file so:
  - no GPU required
  - no model download required
  - no camera hardware required
  - deterministic results in CI

Coverage
─────────
TestObservationResult    — 6-property dataclass completeness
TestMockClassifier       — classifier abstraction contract
TestCameraIngestor       — file-mode observation pipeline
TestGraphAddObservation  — graph.add_observation() → MEASUREMENT node
TestCoreObserve          — core.observe() end-to-end
TestObservationQuery     — graph can retrieve observation by semantic query
"""
import json
import tempfile
import uuid
from pathlib import Path

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_tiny_image(path: Path) -> Path:
    """Write a 4×4 white JPEG so PIL can open it without a real camera."""
    try:
        from PIL import Image
        img = Image.new("RGB", (4, 4), color=(200, 200, 200))
        img.save(str(path), "JPEG")
    except ImportError:
        # Fallback: write minimal valid JPEG bytes (4×4 white, baseline)
        path.write_bytes(
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e'
            b'\xff\xc0\x00\x0b\x08\x00\x04\x00\x04\x01\x01\x11\x00'
            b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
            b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfa\x00\xff\xd9'
        )
    return path


class _TinyEmbedder:
    """Embedder that never calls a model — for graph tests."""
    def embed(self, text: str):
        return [float(ord(c) % 10) / 10 for c in text[:8]] + [0.0] * max(0, 8 - len(text))

    @staticmethod
    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na  = sum(x ** 2 for x in a) ** 0.5
        nb  = sum(x ** 2 for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0


# ── TestObservationResult ──────────────────────────────────────────────────────

class TestObservationResult:
    def test_all_six_properties_present(self):
        """An ObservationResult has all 6 Epistemic Artifact properties."""
        from victor.models import ObservationResult, EpistemicStatus

        obs = ObservationResult(
            sensor_type = "camera",
            sensor_id   = "file:sample.jpg",
            model_used  = "mock",
            session_id  = "s1",
            label       = "high-carbon steel",
            confidence  = 0.87,
            gaps        = ["spectrometer confirmation needed"],
        )

        # 1. Origin
        assert obs.sensor_type == "camera"
        assert obs.sensor_id   == "file:sample.jpg"
        assert obs.model_used  == "mock"
        assert obs.session_id  == "s1"

        # 2. Type
        assert obs.epistemic_status == EpistemicStatus.MEASUREMENT.value

        # 3. Confidence
        assert obs.label      == "high-carbon steel"
        assert obs.confidence == pytest.approx(0.87)

        # 4. Contradictions — empty at creation
        assert obs.contradictions == []

        # 5. Gaps
        assert "spectrometer confirmation needed" in obs.gaps

        # 6. Age
        assert obs.timestamp        # ISO string, non-empty
        assert obs.decay_status == "active"

    def test_observation_id_unique(self):
        from victor.models import ObservationResult
        a = ObservationResult(sensor_type="camera", sensor_id="x", model_used="mock", session_id="s")
        b = ObservationResult(sensor_type="camera", sensor_id="x", model_used="mock", session_id="s")
        assert a.observation_id != b.observation_id

    def test_to_label_format(self):
        from victor.models import ObservationResult
        obs = ObservationResult(
            sensor_type="camera", sensor_id="file:x.jpg",
            model_used="mock", session_id="s1",
            label="steel sample", timestamp="2026-06-23T10:31:00+00:00",
        )
        lbl = obs.to_label()
        assert "camera" in lbl
        assert "steel sample" in lbl
        assert "2026-06-23" in lbl

    def test_epistemic_status_is_measurement(self):
        """Sensor observations MUST be MEASUREMENT — not note, not literature."""
        from victor.models import ObservationResult, EpistemicStatus
        obs = ObservationResult(
            sensor_type="camera", sensor_id="x", model_used="mock", session_id="s"
        )
        assert obs.epistemic_status == EpistemicStatus.MEASUREMENT.value


# ── TestMockClassifier ─────────────────────────────────────────────────────────

class TestMockClassifier:
    def test_returns_first_label_by_default(self, tmp_path):
        from victor.sensors import MockClassifier
        img = _make_tiny_image(tmp_path / "img.jpg")
        clf = MockClassifier()
        result = clf.classify(img, ["steel", "aluminum", "copper"])
        assert result.label == "steel"
        assert 0.0 < result.confidence <= 1.0
        assert result.model_used == "mock"

    def test_fixed_label_override(self, tmp_path):
        from victor.sensors import MockClassifier
        img = _make_tiny_image(tmp_path / "img.jpg")
        clf = MockClassifier(fixed_label="aluminum", fixed_confidence=0.72)
        result = clf.classify(img, ["steel", "aluminum", "copper"])
        assert result.label      == "aluminum"
        assert result.confidence == pytest.approx(0.72)

    def test_all_scores_populated(self, tmp_path):
        from victor.sensors import MockClassifier
        labels = ["steel", "aluminum", "copper"]
        img    = _make_tiny_image(tmp_path / "img.jpg")
        result = MockClassifier().classify(img, labels)
        assert set(result.all_scores.keys()) == set(labels)

    def test_classify_empty_labels(self, tmp_path):
        from victor.sensors import MockClassifier
        img    = _make_tiny_image(tmp_path / "img.jpg")
        result = MockClassifier().classify(img, [])
        assert result.label == "unknown"


# ── TestCameraIngestor ─────────────────────────────────────────────────────────

class TestCameraIngestor:
    def test_file_mode_produces_observation_result(self, tmp_path):
        from victor.sensors import CameraIngestor, MockClassifier
        from victor.models import ObservationResult

        img  = _make_tiny_image(tmp_path / "sample.jpg")
        clf  = MockClassifier(fixed_label="high-carbon steel", fixed_confidence=0.87)
        sdir = tmp_path / "obs"

        ingestor = CameraIngestor(classifier=clf, image_path=img)
        obs      = ingestor.observe(
            candidate_labels = ["high-carbon steel", "aluminum"],
            save_dir         = sdir,
        )

        assert isinstance(obs, ObservationResult)
        assert obs.label      == "high-carbon steel"
        assert obs.confidence == pytest.approx(0.87)
        assert obs.sensor_type == "camera"
        assert obs.image_path is not None
        assert Path(obs.image_path).exists()     # saved copy must exist

    def test_image_copy_saved_to_obs_dir(self, tmp_path):
        from victor.sensors import CameraIngestor, MockClassifier
        img  = _make_tiny_image(tmp_path / "original.jpg")
        sdir = tmp_path / "store"
        clf  = MockClassifier()

        obs = CameraIngestor(classifier=clf, image_path=img).observe(
            candidate_labels=["x"], save_dir=sdir,
        )

        saved = Path(obs.image_path)
        assert saved.parent == sdir
        assert saved.exists()
        # Original not deleted
        assert img.exists()

    def test_six_properties_all_set(self, tmp_path):
        from victor.sensors import CameraIngestor, MockClassifier
        from victor.models import EpistemicStatus

        img = _make_tiny_image(tmp_path / "img.jpg")
        clf = MockClassifier()
        obs = CameraIngestor(classifier=clf, image_path=img).observe(
            candidate_labels = ["steel"],
            save_dir         = tmp_path / "obs",
            extra_gaps       = ["custom gap"],
            session_id       = "field-session-1",
        )

        # 1. Origin
        assert obs.sensor_id.startswith("file:")
        assert obs.model_used == "mock"
        assert obs.session_id == "field-session-1"

        # 2. Type
        assert obs.epistemic_status == EpistemicStatus.MEASUREMENT.value

        # 3. Confidence
        assert 0.0 <= obs.confidence <= 1.0

        # 4. Contradictions
        assert obs.contradictions == []

        # 5. Gaps
        assert "custom gap" in obs.gaps
        assert len(obs.gaps) >= 2           # custom + default gaps

        # 6. Age
        assert obs.timestamp
        assert obs.decay_status == "active"

    def test_extra_gaps_appended_to_defaults(self, tmp_path):
        from victor.sensors import CameraIngestor, MockClassifier

        img = _make_tiny_image(tmp_path / "img.jpg")
        obs = CameraIngestor(
            classifier=MockClassifier(), image_path=img,
        ).observe(
            candidate_labels = ["x"],
            save_dir         = tmp_path / "obs",
            extra_gaps       = ["needs spectrometry", "needs hardness test"],
        )
        assert "needs spectrometry" in obs.gaps
        assert "needs hardness test" in obs.gaps
        # Default camera gaps also present
        assert any("Verify" in g or "calibration" in g or "secondary" in g.lower()
                   for g in obs.gaps)

    def test_session_id_auto_generated_if_none(self, tmp_path):
        from victor.sensors import CameraIngestor, MockClassifier

        img = _make_tiny_image(tmp_path / "img.jpg")
        obs = CameraIngestor(classifier=MockClassifier(), image_path=img).observe(
            candidate_labels=["x"], save_dir=tmp_path / "obs",
        )
        assert obs.session_id   # non-empty
        # Valid UUID
        uuid.UUID(obs.session_id)


# ── TestGraphAddObservation ────────────────────────────────────────────────────

class TestGraphAddObservation:
    def _make_graph(self, tmp_path):
        from victor.graph import VictorKnowledgeGraph
        gf = tmp_path / "graph" / "kg.json"
        gf.parent.mkdir(parents=True)
        return VictorKnowledgeGraph(gf, _TinyEmbedder())

    def _make_obs(self, **kwargs):
        from victor.models import ObservationResult
        defaults = dict(
            sensor_type = "camera",
            sensor_id   = "file:sample.jpg",
            model_used  = "mock",
            session_id  = "s1",
            label       = "high-carbon steel",
            confidence  = 0.87,
            gaps        = ["spectrometer needed"],
        )
        defaults.update(kwargs)
        return ObservationResult(**defaults)

    def test_add_observation_returns_node_id(self, tmp_path):
        g   = self._make_graph(tmp_path)
        obs = self._make_obs()
        nid = g.add_observation(obs)
        assert nid == obs.observation_id

    def test_node_is_observation_type(self, tmp_path):
        from victor.models import NodeType
        g   = self._make_graph(tmp_path)
        nid = g.add_observation(self._make_obs())
        node = g.get_node(nid)
        assert node["ntype"] == NodeType.OBSERVATION

    def test_epistemic_status_is_measurement(self, tmp_path):
        from victor.models import EpistemicStatus
        g   = self._make_graph(tmp_path)
        nid = g.add_observation(self._make_obs())
        node = g.get_node(nid)
        assert node["metadata"]["epistemic_status"] == EpistemicStatus.MEASUREMENT.value

    def test_all_six_properties_in_node_metadata(self, tmp_path):
        g   = self._make_graph(tmp_path)
        obs = self._make_obs(
            image_path = "/tmp/some.jpg",
            gaps       = ["spectrometer", "hardness test"],
        )
        nid  = g.add_observation(obs)
        meta = g.get_node(nid)["metadata"]

        # 1. Origin
        assert meta["sensor_type"] == "camera"
        assert meta["sensor_id"]   == "file:sample.jpg"
        assert meta["model_used"]  == "mock"
        assert meta["session_id"]  == "s1"

        # 2. Type
        assert "epistemic_status" in meta

        # 3. Confidence
        assert meta["label"]      == "high-carbon steel"
        assert meta["confidence"] == pytest.approx(0.87)

        # 4. Contradictions
        assert meta["contradictions"] == []

        # 5. Gaps
        assert "spectrometer" in meta["gaps"]
        assert "hardness test" in meta["gaps"]

        # 6. Age
        assert meta["timestamp"]
        assert meta["decay_status"] == "active"

    def test_observation_embeds_in_graph(self, tmp_path):
        g   = self._make_graph(tmp_path)
        nid = g.add_observation(self._make_obs())
        assert nid in g._embeddings
        assert len(g._embeddings[nid]) > 0

    def test_observation_has_high_importance(self, tmp_path):
        """MEASUREMENT nodes should have the highest default importance score."""
        from victor.models import NodeType
        g   = self._make_graph(tmp_path)
        nid = g.add_observation(self._make_obs())
        meta = g.get_node(nid)["metadata"]
        assert meta.get("importance_score", 0.0) >= 0.85

    def test_save_and_reload_preserves_observation(self, tmp_path):
        from victor.graph import VictorKnowledgeGraph
        from victor.models import EpistemicStatus

        gf  = tmp_path / "graph" / "kg.json"
        gf.parent.mkdir(parents=True)

        g1  = VictorKnowledgeGraph(gf, _TinyEmbedder())
        obs = self._make_obs()
        g1.add_observation(obs)
        g1.save()

        g2   = VictorKnowledgeGraph(gf, _TinyEmbedder())
        node = g2.get_node(obs.observation_id)
        assert node is not None
        assert node["metadata"]["label"] == "high-carbon steel"
        assert node["metadata"]["epistemic_status"] == EpistemicStatus.MEASUREMENT.value

    def test_semantic_query_finds_observation(self, tmp_path):
        """graph.semantic_query('what did I observe') should surface MEASUREMENT nodes."""
        g   = self._make_graph(tmp_path)
        obs = self._make_obs(label="high-carbon steel")
        g.add_observation(obs)

        results = g.semantic_query("observation measurement today", top_k=5)
        node_ids = [r[0] for r in results]
        assert obs.observation_id in node_ids


# ── TestCoreObserve ────────────────────────────────────────────────────────────

class TestCoreObserve:
    def _make_victor(self, tmp_dir):
        """Build a minimal Victor instance pointing at tmp_dir."""
        import sys
        sys.path.insert(0, "/home/claude/victor")
        from victor.config import VictorConfig
        from victor.core import Victor

        cfg = VictorConfig(
            home_dir          = tmp_dir,
            use_mock_llm      = True,
            use_mock_embedder = True,
        )
        return Victor(cfg)

    def test_observe_returns_dict_with_six_properties(self, tmp_path):
        from victor.sensors import MockClassifier
        img = _make_tiny_image(tmp_path / "img.jpg")

        v   = self._make_victor(tmp_path)
        clf = MockClassifier(fixed_label="aluminum", fixed_confidence=0.75)

        result = v.observe(
            sensor           = "camera",
            image_path       = img,
            candidate_labels = ["aluminum", "copper", "steel"],
            classifier       = clf,
        )

        assert result["label"]             == "aluminum"
        assert result["confidence"]        == pytest.approx(0.75)
        assert result["epistemic_status"]  == "measurement"
        assert result["node_id"]
        assert result["gaps"]
        assert result["timestamp"]

    def test_observe_persists_to_graph(self, tmp_path):
        from victor.sensors import MockClassifier
        img = _make_tiny_image(tmp_path / "img.jpg")
        v   = self._make_victor(tmp_path)
        clf = MockClassifier()

        result = v.observe(
            sensor="camera", image_path=img,
            candidate_labels=["steel"], classifier=clf,
        )

        # Graph must be reloadable and contain the node
        from victor.graph import VictorKnowledgeGraph
        g2   = VictorKnowledgeGraph(v.graph.graph_file, v.embedder)
        node = g2.get_node(result["node_id"])
        assert node is not None
        assert node["metadata"]["label"] == "steel"

    def test_observe_requires_labels(self, tmp_path):
        img = _make_tiny_image(tmp_path / "img.jpg")
        v   = self._make_victor(tmp_path)

        with pytest.raises(ValueError, match="candidate_labels"):
            v.observe(sensor="camera", image_path=img)

    def test_observe_image_saved_in_observations_dir(self, tmp_path):
        from victor.sensors import MockClassifier
        img    = _make_tiny_image(tmp_path / "img.jpg")
        v      = self._make_victor(tmp_path)
        result = v.observe(
            sensor="camera", image_path=img,
            candidate_labels=["x"], classifier=MockClassifier(),
        )
        assert result["image_path"]
        assert Path(result["image_path"]).exists()
        obs_dir = tmp_path / "observations"
        assert Path(result["image_path"]).parent == obs_dir

    def test_observe_unknown_sensor_raises(self, tmp_path):
        v = self._make_victor(tmp_path)
        with pytest.raises(NotImplementedError, match="spectrometer"):
            v.observe(sensor="spectrometer", candidate_labels=["x"])


# ── TestObservationQuery ───────────────────────────────────────────────────────

class TestObservationQuery:
    """
    Verifies that after storing an observation, 'what did I observe today?'
    returns the MEASUREMENT node.  Uses the graph directly (no LLM needed).
    """

    def _make_graph(self, tmp_path):
        from victor.graph import VictorKnowledgeGraph
        gf = tmp_path / "graph" / "kg.json"
        gf.parent.mkdir(parents=True)
        return VictorKnowledgeGraph(gf, _TinyEmbedder())

    def test_observation_retrievable_by_date_query(self, tmp_path):
        from victor.models import ObservationResult, NodeType

        g = self._make_graph(tmp_path)
        obs = ObservationResult(
            sensor_type = "camera",
            sensor_id   = "file:metal.jpg",
            model_used  = "mock",
            session_id  = "s1",
            label       = "high-carbon steel",
            confidence  = 0.87,
            gaps        = ["spectrometer needed"],
        )
        g.add_observation(obs)

        # Semantic search — the embedding of the query should find the node
        results = g.semantic_query("what did I observe today", top_k=5)
        found_ntypes = [g.get_node(r[0])["ntype"] for r in results]
        assert NodeType.OBSERVATION in found_ntypes

    def test_multiple_observations_all_in_graph(self, tmp_path):
        from victor.models import ObservationResult, NodeType

        g    = self._make_graph(tmp_path)
        ids  = []
        for label in ["steel", "aluminum", "copper"]:
            obs = ObservationResult(
                sensor_type="camera", sensor_id="file:x.jpg",
                model_used="mock", session_id="s1",
                label=label, confidence=0.80,
            )
            ids.append(g.add_observation(obs))

        obs_nodes = g.list_nodes(NodeType.OBSERVATION)
        assert len(obs_nodes) == 3
        found_labels = {n["metadata"]["label"] for n in obs_nodes}
        assert found_labels == {"steel", "aluminum", "copper"}
