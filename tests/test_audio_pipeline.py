"""
Tests for Phase 1A: AudioIngestor + AudioClassifierBase + MockAudioClassifier.

Principles verified:
  1. AudioIngestor subclasses StreamIngestorBase (plugin architecture).
  2. MockAudioClassifier works without librosa or any heavy dependency.
  3. Audio observation produces a MEASUREMENT node with all 6 properties.
  4. Audio-specific gaps are populated (different from camera gaps).
  5. Audio observation persists through graph save/reload.

All tests use MockAudioClassifier — no microphone, no librosa, no GPU.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from victor.sensors import (
    AudioIngestor, AudioClassifierBase, MockAudioClassifier,
    LibrosaFeatureClassifier, StreamIngestorBase,
    ClassificationResult,
)
from victor.models import ObservationResult, EpistemicStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_graph_file(tmp_path):
    return tmp_path / "graph.json"


@pytest.fixture
def mock_embedder():
    emb = MagicMock()
    _cache = {}

    def _embed(text):
        if text not in _cache:
            import hashlib
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            v = [((h >> i) & 0xFF) / 255.0 for i in range(0, 384 * 8, 8)]
            _cache[text] = v[:384]
        return _cache[text]

    emb.embed.side_effect = _embed
    emb.cosine = staticmethod(lambda a, b: sum(x * y for x, y in zip(a, b)))
    return emb


@pytest.fixture
def mock_audio_classifier():
    return MockAudioClassifier(
        fixed_label="speech",
        fixed_confidence=0.92,
    )


@pytest.fixture
def mock_audio_file(tmp_path):
    """Create a minimal valid WAV file for testing file-mode ingest."""
    import wave
    import struct

    path = tmp_path / "test_audio.wav"
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        # 0.5 seconds of silence
        frames = b"\x00\x00" * 11025
        wf.writeframes(frames)
    return path


# ── AudioClassifierBase interface tests ───────────────────────────────────────

class TestMockAudioClassifier:
    def test_returns_first_label_by_default(self):
        clf = MockAudioClassifier()
        result = clf.classify(Path("/fake/path.wav"), ["speech", "music", "noise"])
        assert result.label == "speech"
        assert result.confidence == pytest.approx(0.87)
        assert result.model_used == "mock_audio"

    def test_fixed_label_override(self):
        clf = MockAudioClassifier(fixed_label="music")
        result = clf.classify(Path("/fake/path.wav"), ["speech", "music", "noise"])
        assert result.label == "music"

    def test_all_scores_populated(self):
        clf = MockAudioClassifier()
        result = clf.classify(Path("/fake/path.wav"), ["a", "b", "c"])
        assert len(result.all_scores) == 3
        assert result.all_scores["a"] == pytest.approx(0.87)
        assert result.all_scores["b"] == pytest.approx(0.05)

    def test_classify_empty_labels(self):
        clf = MockAudioClassifier(fixed_label="unknown")
        result = clf.classify(Path("/fake/path.wav"), [])
        assert result.label == "unknown"

    def test_subclass_of_audio_classifier_base(self):
        assert issubclass(MockAudioClassifier, AudioClassifierBase)


# ── AudioIngestor tests ───────────────────────────────────────────────────────

class TestAudioIngestor:
    def test_file_mode_produces_observation_result(
        self, mock_audio_file, mock_audio_classifier, tmp_path
    ):
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        result = ingestor.observe(
            candidate_labels=["speech", "music", "noise"],
            save_dir=tmp_path / "obs",
        )
        assert isinstance(result, ObservationResult)
        assert result.sensor_type == "audio"
        assert result.label == "speech"
        assert result.confidence == pytest.approx(0.92)

    def test_file_mode_copies_audio_to_save_dir(
        self, mock_audio_file, mock_audio_classifier, tmp_path
    ):
        obs_dir = tmp_path / "observations"
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        result = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=obs_dir,
        )
        saved_path = result.metadata.get("audio_path")
        assert saved_path is not None
        assert Path(saved_path).exists()
        assert Path(saved_path).parent == obs_dir

    def test_six_properties_all_set(self, mock_audio_file, mock_audio_classifier, tmp_path):
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        result = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_path / "obs",
        )
        # 1. Origin
        assert result.sensor_type == "audio"
        assert result.sensor_id.startswith("file:")
        assert result.model_used == "mock_audio"
        # 2. Type
        assert result.epistemic_status == EpistemicStatus.MEASUREMENT.value
        # 3. Confidence
        assert result.confidence > 0
        # 4. Contradictions (empty at creation)
        assert result.contradictions == []
        # 5. Gaps (audio-specific)
        assert len(result.gaps) >= 3
        assert any("decibel" in g.lower() for g in result.gaps)
        # 6. Age
        assert result.timestamp is not None

    def test_extra_gaps_appended_to_defaults(
        self, mock_audio_file, mock_audio_classifier, tmp_path
    ):
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        result = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_path / "obs",
            extra_gaps=["Custom verification step"],
        )
        assert "Custom verification step" in result.gaps
        # Default gaps still present
        assert any("decibel" in g.lower() for g in result.gaps)

    def test_session_id_auto_generated_if_none(
        self, mock_audio_file, mock_audio_classifier, tmp_path
    ):
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        result = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_path / "obs",
        )
        assert result.session_id is not None
        assert len(result.session_id) > 0

    def test_custom_session_id_preserved(
        self, mock_audio_file, mock_audio_classifier, tmp_path
    ):
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        result = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_path / "obs",
            session_id="field_session_42",
        )
        assert result.session_id == "field_session_42"

    def test_duration_in_metadata_for_mic_mode(
        self, mock_audio_classifier, tmp_path
    ):
        """When no audio_path is given, duration should be in metadata."""
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=None,
            duration=10,
        )
        # We can't test _record_audio without a microphone, but we can test
        # that the ingestor is configured correctly.
        assert ingestor._duration == 10
        assert ingestor._audio_path is None

    def test_sensor_type_class_variable(self):
        assert AudioIngestor.sensor_type == "audio"

    def test_subclass_of_stream_ingestor_base(self):
        assert issubclass(AudioIngestor, StreamIngestorBase)


# ── Graph integration tests ───────────────────────────────────────────────────

class TestGraphAddAudioObservation:
    def test_add_audio_observation_returns_node_id(
        self, tmp_graph_file, mock_embedder, mock_audio_file, mock_audio_classifier
    ):
        from victor.graph import VictorKnowledgeGraph

        graph = VictorKnowledgeGraph(graph_file=tmp_graph_file, embedder=mock_embedder)
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        obs = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_graph_file.parent / "obs",
        )
        node_id = graph.add_observation(obs)
        assert node_id is not None
        assert node_id == obs.observation_id

    def test_audio_node_is_observation_type(
        self, tmp_graph_file, mock_embedder, mock_audio_file, mock_audio_classifier
    ):
        from victor.graph import VictorKnowledgeGraph
        from victor.models import NodeType

        graph = VictorKnowledgeGraph(graph_file=tmp_graph_file, embedder=mock_embedder)
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        obs = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_graph_file.parent / "obs",
        )
        node_id = graph.add_observation(obs)
        node = graph.get_node(node_id)
        assert node["ntype"] == NodeType.OBSERVATION

    def test_audio_epistemic_status_is_measurement(
        self, tmp_graph_file, mock_embedder, mock_audio_file, mock_audio_classifier
    ):
        from victor.graph import VictorKnowledgeGraph

        graph = VictorKnowledgeGraph(graph_file=tmp_graph_file, embedder=mock_embedder)
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        obs = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_graph_file.parent / "obs",
        )
        node_id = graph.add_observation(obs)
        node = graph.get_node(node_id)
        assert node["metadata"]["epistemic_status"] == EpistemicStatus.MEASUREMENT.value

    def test_audio_all_six_properties_in_node_metadata(
        self, tmp_graph_file, mock_embedder, mock_audio_file, mock_audio_classifier
    ):
        from victor.graph import VictorKnowledgeGraph

        graph = VictorKnowledgeGraph(graph_file=tmp_graph_file, embedder=mock_embedder)
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        obs = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_graph_file.parent / "obs",
        )
        node_id = graph.add_observation(obs)
        node = graph.get_node(node_id)
        meta = node["metadata"]
        # All 6 properties
        assert "sensor_type" in meta
        assert "sensor_id" in meta
        assert "model_used" in meta
        assert "confidence" in meta
        assert "gaps" in meta
        assert "timestamp" in meta

    def test_audio_has_high_importance(
        self, tmp_graph_file, mock_embedder, mock_audio_file, mock_audio_classifier
    ):
        from victor.graph import VictorKnowledgeGraph

        graph = VictorKnowledgeGraph(graph_file=tmp_graph_file, embedder=mock_embedder)
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        obs = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_graph_file.parent / "obs",
        )
        node_id = graph.add_observation(obs)
        node = graph.get_node(node_id)
        assert node["metadata"]["importance_score"] >= 0.8

    def test_save_and_reload_preserves_audio_observation(
        self, tmp_graph_file, mock_embedder, mock_audio_file, mock_audio_classifier
    ):
        from victor.graph import VictorKnowledgeGraph

        graph = VictorKnowledgeGraph(graph_file=tmp_graph_file, embedder=mock_embedder)
        ingestor = AudioIngestor(
            classifier=mock_audio_classifier,
            audio_path=mock_audio_file,
        )
        obs = ingestor.observe(
            candidate_labels=["speech", "music"],
            save_dir=tmp_graph_file.parent / "obs",
        )
        node_id = graph.add_observation(obs)
        graph.save()

        graph2 = VictorKnowledgeGraph(graph_file=tmp_graph_file, embedder=mock_embedder)
        node = graph2.get_node(node_id)
        assert node is not None
        assert node["metadata"]["sensor_type"] == "audio"
        assert node["metadata"]["label"] == "speech"


# ── Core integration tests ────────────────────────────────────────────────────

class TestCoreAudioObserve:
    def test_audio_observe_via_core(self, mock_audio_file, mock_audio_classifier):
        from victor.core import Victor
        from victor.config import VictorConfig

        config = VictorConfig(use_mock_llm=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            config.home_dir = Path(tmpdir)
            config.vector_db_dir = Path(tmpdir) / "vector_db"
            config.graph_file = Path(tmpdir) / "graph" / "kg.json"
            config.llm_log_file = Path(tmpdir) / "logs" / "llm.jsonl"
            config.extraction_log_file = Path(tmpdir) / "logs" / "extract.jsonl"

            v = Victor(config=config)
            v.embedder.embed = MagicMock(return_value=[0.1] * 384)

            result = v.observe(
                sensor="audio",
                audio_path=mock_audio_file,
                candidate_labels=["speech", "music", "noise"],
                classifier=mock_audio_classifier,
            )
            assert result["node_id"] is not None
            assert result["label"] == "speech"
            assert result["confidence"] > 0
            assert result["epistemic_status"] == EpistemicStatus.MEASUREMENT.value
            assert any("decibel" in g.lower() for g in result["gaps"])

    def test_audio_observe_persists_to_graph(self, mock_audio_file, mock_audio_classifier):
        from victor.core import Victor
        from victor.config import VictorConfig

        config = VictorConfig(use_mock_llm=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            config.home_dir = Path(tmpdir)
            config.vector_db_dir = Path(tmpdir) / "vector_db"
            config.graph_file = Path(tmpdir) / "graph" / "kg.json"
            config.llm_log_file = Path(tmpdir) / "logs" / "llm.jsonl"
            config.extraction_log_file = Path(tmpdir) / "logs" / "extract.jsonl"

            v = Victor(config=config)
            v.embedder.embed = MagicMock(return_value=[0.1] * 384)

            result = v.observe(
                sensor="audio",
                audio_path=mock_audio_file,
                candidate_labels=["speech", "music"],
                classifier=mock_audio_classifier,
            )
            node_id = result["node_id"]
            node = v.graph.get_node(node_id)
            assert node is not None
            assert node["metadata"]["sensor_type"] == "audio"

    def test_audio_observe_requires_labels(self, mock_audio_file, mock_audio_classifier):
        from victor.core import Victor
        from victor.config import VictorConfig

        config = VictorConfig(use_mock_llm=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            config.home_dir = Path(tmpdir)
            config.vector_db_dir = Path(tmpdir) / "vector_db"
            config.graph_file = Path(tmpdir) / "graph" / "kg.json"
            config.llm_log_file = Path(tmpdir) / "logs" / "llm.jsonl"
            config.extraction_log_file = Path(tmpdir) / "logs" / "extract.jsonl"

            v = Victor(config=config)
            v.embedder.embed = MagicMock(return_value=[0.1] * 384)

            with pytest.raises(ValueError, match="candidate_labels"):
                v.observe(
                    sensor="audio",
                    audio_path=mock_audio_file,
                    candidate_labels=None,
                    classifier=mock_audio_classifier,
                )

    def test_camera_still_works_after_audio_added(self, mock_audio_classifier):
        """Regression: camera observations must still work."""
        from victor.core import Victor
        from victor.config import VictorConfig
        from victor.sensors import MockClassifier

        config = VictorConfig(use_mock_llm=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            config.home_dir = Path(tmpdir)
            config.vector_db_dir = Path(tmpdir) / "vector_db"
            config.graph_file = Path(tmpdir) / "graph" / "kg.json"
            config.llm_log_file = Path(tmpdir) / "logs" / "llm.jsonl"
            config.extraction_log_file = Path(tmpdir) / "logs" / "extract.jsonl"

            v = Victor(config=config)
            v.embedder.embed = MagicMock(return_value=[0.1] * 384)

            clf = MockClassifier(fixed_label="steel", fixed_confidence=0.95)
            # We need a dummy image file for camera mode
            img_path = Path(tmpdir) / "test.jpg"
            img_path.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100)

            result = v.observe(
                sensor="camera",
                image_path=img_path,
                candidate_labels=["steel", "aluminum"],
                classifier=clf,
            )
            assert result["label"] == "steel"
            assert result["sensor_id"].startswith("file:")


# ── CLI option validation tests ───────────────────────────────────────────────

class TestAudioCliOptions:
    def test_sensor_choice_includes_audio(self):
        from victor.cli import cli
        # The click.Choice should include "audio"
        observe_cmd = None
        for cmd_name, cmd in cli.commands.items():
            if cmd_name == "observe":
                observe_cmd = cmd
                break
        assert observe_cmd is not None
        # Find the --sensor option
        sensor_opt = None
        for p in observe_cmd.params:
            if getattr(p, "name", None) == "sensor":
                sensor_opt = p
                break
        assert sensor_opt is not None
        assert "audio" in [c.lower() for c in sensor_opt.type.choices]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
