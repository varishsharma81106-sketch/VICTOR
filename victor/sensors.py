"""
Sensor pipeline — Victor v4.6
Step 2 of PRD Section 7: Reality → Artifact pipeline

Architecture
─────────────
StreamIngestorBase   abstract interface for live sensor sources
VisionClassifierBase abstract interface for image classifiers
CLIPClassifier       zero-shot image classification via transformers CLIP
MockClassifier       deterministic stand-in for testing (no model download)
CameraIngestor       image-file or webcam → ObservationResult

Design principles
─────────────────
• Classifiers are injected; CameraIngestor doesn't import torch directly.
• CLIP is lazy-loaded so `import victor` stays fast when CLIP isn't needed.
• Every public method returns a fully populated ObservationResult — all 6
  Epistemic Artifact properties set at creation time, not after the fact.
• image_path in ObservationResult is always a saved copy, never a temp file.
  Provenance requires that the file still exists when you query it later.
"""
from __future__ import annotations

import logging
import shutil
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, TYPE_CHECKING

logger = logging.getLogger(__name__)

from .models import ObservationResult, EpistemicStatus

# Default gaps populated per sensor type.  Researcher can extend at call time.
_DEFAULT_GAPS: Dict[str, List[str]] = {
    "camera": [
        "Verify with secondary instrument (spectrometer, hardness test, etc.)",
        "Confirm model calibration on this sample class",
        "Independent visual inspection by domain expert",
    ],
    "audio": [
        "Verify with calibrated decibel meter",
        "Confirm classifier accuracy on this acoustic environment",
        "Rule out background noise contamination",
    ],
    "manual": [
        "No automated verification; confidence reflects researcher judgment",
    ],
}


# ── Classification result ──────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    """
    Output of one classifier run on one image/audio frame.
    Kept separate from ObservationResult so classifiers can be hot-swapped
    without changing the artifact structure.
    """
    label:      str
    confidence: float          # 0.0 – 1.0
    model_used: str
    all_scores: Dict[str, float] = field(default_factory=dict)
    raw: Any = None            # model output, for debugging


# ── Vision classifier abstraction ─────────────────────────────────────────────

class VisionClassifierBase(ABC):
    """
    Swap any classifier in by implementing this interface.
    CameraIngestor receives a VisionClassifierBase instance; it never
    calls torch or transformers directly.
    """

    @abstractmethod
    def classify(
        self,
        image_path: Path,
        candidate_labels: List[str],
    ) -> ClassificationResult:
        """
        Classify `image_path` against `candidate_labels`.
        Returns the top label and its confidence.
        """


class CLIPClassifier(VisionClassifierBase):
    """
    Zero-shot image classification via openai/clip-vit-base-patch32.

    Lazy-loads the model on first call so `import victor` stays fast.
    Requires: transformers, torch, Pillow.
    The model (~600 MB) is downloaded to ~/.cache/huggingface on first use
    and cached locally — offline-first from second run onward.
    """

    MODEL_ID = "openai/clip-vit-base-patch32"

    def __init__(self) -> None:
        self._model     = None
        self._processor = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        logger.info("Loading CLIP model %s (first use; cached after this)", self.MODEL_ID)
        try:
            from transformers import CLIPModel, CLIPProcessor
            self._processor = CLIPProcessor.from_pretrained(self.MODEL_ID)
            self._model     = CLIPModel.from_pretrained(self.MODEL_ID)
            self._model.eval()
            logger.info("CLIP loaded OK")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load CLIP model '{self.MODEL_ID}'. "
                "Ensure transformers and torch are installed and the model "
                "has been cached (requires one network access)."
            ) from exc

    def classify(
        self,
        image_path: Path,
        candidate_labels: List[str],
    ) -> ClassificationResult:
        self._ensure_loaded()

        import torch
        from PIL import Image

        image  = Image.open(image_path).convert("RGB")
        inputs = self._processor(
            text=candidate_labels,
            images=image,
            return_tensors="pt",
            padding=True,
        )

        with torch.no_grad():
            outputs = self._model(**inputs)
            probs   = outputs.logits_per_image.softmax(dim=1)[0]

        scores = {label: float(prob) for label, prob in zip(candidate_labels, probs)}
        top_label = max(scores, key=scores.__getitem__)

        return ClassificationResult(
            label      = top_label,
            confidence = scores[top_label],
            model_used = self.MODEL_ID,
            all_scores = scores,
        )


class MockClassifier(VisionClassifierBase):
    """
    Deterministic classifier for tests and CI — never downloads anything.
    Returns the first candidate label with a fixed confidence.
    """

    def __init__(self, fixed_label: Optional[str] = None, fixed_confidence: float = 0.87) -> None:
        self._fixed_label      = fixed_label
        self._fixed_confidence = fixed_confidence

    def classify(
        self,
        image_path: Path,
        candidate_labels: List[str],
    ) -> ClassificationResult:
        label = self._fixed_label or (candidate_labels[0] if candidate_labels else "unknown")
        return ClassificationResult(
            label      = label,
            confidence = self._fixed_confidence,
            model_used = "mock",
            all_scores = {l: (self._fixed_confidence if l == label else 0.05)
                          for l in candidate_labels},
        )


# ── Stream ingestor base ───────────────────────────────────────────────────────

class StreamIngestorBase(ABC):
    """
    Abstract base for live-sensor ingestors.

    Parallel to IngestorBase (file-based) but for streaming/sensor sources.
    Instead of ingest(filepath) → IngestResult it exposes observe() →
    ObservationResult, which the graph consumes via add_observation().
    """

    sensor_type: str = ""   # subclasses set this as a class variable

    @abstractmethod
    def observe(
        self,
        *,
        candidate_labels: List[str],
        save_dir:         Path,
        extra_gaps:       Optional[List[str]] = None,
        session_id:       Optional[str]       = None,
        metadata:         Optional[Dict[str, Any]] = None,
    ) -> ObservationResult:
        """
        Capture one observation and return a fully-populated ObservationResult.

        Parameters
        ──────────
        candidate_labels  Labels to classify against.  For manual mode: pass a
                          single-element list containing the researcher's description.
        save_dir          Directory to save the raw capture for provenance.
        extra_gaps        Additional "what needs verification" strings beyond the
                          sensor-type defaults.
        session_id        Groups observations from the same fieldwork session.
        metadata          Arbitrary extras attached to the graph node.
        """


# ── Camera ingestor ────────────────────────────────────────────────────────────

class CameraIngestor(StreamIngestorBase):
    """
    Captures one image (from a file or webcam) and classifies it.

    Modes
    ──────
    image_path provided  → load that file, classify, save a dated copy
    camera_index set     → capture one frame from the webcam

    Both modes save a copy to save_dir/<observation_id>.jpg for provenance.
    The ObservationResult.image_path points to that saved copy, not the
    original, so the artifact is self-contained.
    """

    sensor_type: str = "camera"

    def __init__(
        self,
        classifier:   Optional[VisionClassifierBase] = None,
        image_path:   Optional[Path]                 = None,
        camera_index: int                            = 0,
    ) -> None:
        """
        classifier     Vision classifier to use.  If None, a CLIPClassifier
                       is constructed on first use (lazy — no model load here).
        image_path     Pre-existing image to observe.  If None, captures from webcam.
        camera_index   OpenCV camera device index (ignored when image_path is set).
        """
        self._classifier   = classifier       # None = lazy CLIPClassifier
        self._image_path   = image_path
        self._camera_index = camera_index

    def _get_classifier(self) -> VisionClassifierBase:
        if self._classifier is None:
            self._classifier = CLIPClassifier()
        return self._classifier

    def _capture_frame(self, save_dir: Path, obs_id: str) -> Path:
        """Capture one frame from the webcam and save it."""
        try:
            import cv2
        except ImportError as exc:
            raise ImportError(
                "Webcam capture requires OpenCV: pip install opencv-python"
            ) from exc

        cap = cv2.VideoCapture(self._camera_index)
        if not cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera at index {self._camera_index}. "
                "Pass --image <path> to classify an existing image instead."
            )

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            raise RuntimeError("Camera capture returned empty frame.")

        out_path = save_dir / f"{obs_id}.jpg"
        cv2.imwrite(str(out_path), frame)
        logger.info("Camera frame saved to %s", out_path)
        return out_path

    def _copy_image(self, src: Path, save_dir: Path, obs_id: str) -> Path:
        """Copy an existing image into the observation store."""
        suffix   = src.suffix or ".jpg"
        out_path = save_dir / f"{obs_id}{suffix}"
        shutil.copy2(src, out_path)
        logger.info("Image copied to %s", out_path)
        return out_path

    def observe(
        self,
        *,
        candidate_labels: List[str],
        save_dir:         Path,
        extra_gaps:       Optional[List[str]] = None,
        session_id:       Optional[str]       = None,
        metadata:         Optional[Dict[str, Any]] = None,
    ) -> ObservationResult:
        """
        Capture + classify one image → ObservationResult with all 6 properties.

        All 6 Epistemic Artifact properties are populated here — not deferred.
        """
        obs_id     = str(uuid.uuid4())
        session_id = session_id or str(uuid.uuid4())
        save_dir.mkdir(parents=True, exist_ok=True)

        # ── Capture ────────────────────────────────────────────────────────────
        if self._image_path is not None:
            sensor_id  = f"file:{self._image_path.name}"
            saved_path = self._copy_image(self._image_path, save_dir, obs_id)
        else:
            sensor_id  = f"camera:{self._camera_index}"
            saved_path = self._capture_frame(save_dir, obs_id)

        # ── Classify ───────────────────────────────────────────────────────────
        clf = self._get_classifier()
        result = clf.classify(saved_path, candidate_labels)

        logger.info(
            "Classified as '%s' (confidence=%.3f, model=%s)",
            result.label, result.confidence, result.model_used,
        )

        # ── Populate all 6 Epistemic Artifact properties ───────────────────────
        gaps = list(_DEFAULT_GAPS.get("camera", []))
        if extra_gaps:
            gaps.extend(extra_gaps)

        obs = ObservationResult(
            # 1. Origin
            sensor_type = self.sensor_type,
            sensor_id   = sensor_id,
            model_used  = result.model_used,
            session_id  = session_id,
            # 2. Type — always MEASUREMENT for sensor data
            epistemic_status = EpistemicStatus.MEASUREMENT.value,
            # 3. Confidence
            label      = result.label,
            confidence = result.confidence,
            # 4. Contradictions — empty at creation
            contradictions = [],
            # 5. Gaps — default + extra
            gaps = gaps,
            # 6. Age — set by ObservationResult.__post_init__ default
            observation_id = obs_id,
            image_path     = str(saved_path),
            metadata       = {
                "all_scores":   result.all_scores,
                "camera_index": self._camera_index,
                **(metadata or {}),
            },
        )

        return obs


# ── Audio classifier abstraction ───────────────────────────────────────────────

class AudioClassifierBase(ABC):
    """
    Abstract interface for audio classifiers.
    AudioIngestor receives an AudioClassifierBase instance; it never calls
    librosa or torch directly.
    """

    @abstractmethod
    def classify(
        self,
        audio_path: Path,
        candidate_labels: List[str],
    ) -> ClassificationResult:
        """
        Classify `audio_path` against `candidate_labels`.
        Returns the top label and its confidence.
        """


class MockAudioClassifier(AudioClassifierBase):
    """
    Deterministic audio classifier for tests and CI — never downloads anything.
    Returns the first candidate label with a fixed confidence.
    """

    def __init__(self, fixed_label: Optional[str] = None, fixed_confidence: float = 0.87) -> None:
        self._fixed_label = fixed_label
        self._fixed_confidence = fixed_confidence

    def classify(
        self,
        audio_path: Path,
        candidate_labels: List[str],
    ) -> ClassificationResult:
        label = self._fixed_label or (candidate_labels[0] if candidate_labels else "unknown")
        return ClassificationResult(
            label=label,
            confidence=self._fixed_confidence,
            model_used="mock_audio",
            all_scores={l: (self._fixed_confidence if l == label else 0.05)
                        for l in candidate_labels},
        )


class LibrosaFeatureClassifier(AudioClassifierBase):
    """
    Audio classifier using librosa feature extraction + simple heuristics.

    Extracts MFCCs, spectral centroid, zero-crossing rate, and RMS energy.
    Uses lightweight heuristics to map features to candidate labels —
    no neural network download required. Suitable for offline/embedded use.

    For production, replace with PANNsClassifier (ONNX Runtime) which uses
    a proper pretrained audio neural network.
    """

    MODEL_ID = "librosa-heuristic"

    def classify(
        self,
        audio_path: Path,
        candidate_labels: List[str],
    ) -> ClassificationResult:
        try:
            import librosa
            import numpy as np
        except ImportError as exc:
            raise ImportError(
                "Librosa feature classification requires: pip install librosa"
            ) from exc

        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)

        # Extract features
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        zcr = librosa.feature.zero_crossing_rate(y)
        rms = librosa.feature.rms(y=y)

        features = {
            "duration": duration,
            "mfcc_mean": float(np.mean(mfccs)),
            "mfcc_std": float(np.std(mfccs)),
            "spectral_centroid_mean": float(np.mean(spectral_centroid)),
            "zcr_mean": float(np.mean(zcr)),
            "rms_mean": float(np.mean(rms)),
            "rms_max": float(np.max(rms)),
        }

        # Simple heuristic scoring against candidate labels
        # Higher spectral centroid → higher frequency content
        # Higher ZCR → more noise-like / percussive
        # Higher RMS → louder
        scores = {}
        for label in candidate_labels:
            label_lower = label.lower()
            score = 0.5  # base score

            # Boost by feature heuristics
            if features["spectral_centroid_mean"] > 2000:
                if any(k in label_lower for k in ("high", "treble", "bird", "speech", "voice")):
                    score += 0.3
            if features["spectral_centroid_mean"] < 1000:
                if any(k in label_lower for k in ("low", "bass", "rumble", "drone")):
                    score += 0.3
            if features["zcr_mean"] > 0.1:
                if any(k in label_lower for k in ("percussion", "noise", "click", "pulse")):
                    score += 0.25
            if features["rms_mean"] > 0.1:
                if any(k in label_lower for k in ("loud", "strong", "intense")):
                    score += 0.2
            if features["duration"] > 5.0:
                if any(k in label_lower for k in ("ambient", "background", "sustained")):
                    score += 0.15

            scores[label] = min(score, 0.95)

        top_label = max(scores, key=scores.__getitem__)

        return ClassificationResult(
            label=top_label,
            confidence=scores[top_label],
            model_used=self.MODEL_ID,
            all_scores=scores,
            raw=features,
        )


# ── Audio ingestor ─────────────────────────────────────────────────────────────

class AudioIngestor(StreamIngestorBase):
    """
    Captures one audio clip (from a file or microphone) and classifies it.

    Modes
    ──────
    audio_path provided  → load that file, classify, save a dated copy
    duration set         → record from the microphone for N seconds

    Both modes save a copy to save_dir/<observation_id>.wav for provenance.
    The ObservationResult.metadata["audio_path"] points to that saved copy.
    """

    sensor_type: str = "audio"

    def __init__(
        self,
        classifier:   Optional[AudioClassifierBase] = None,
        audio_path:   Optional[Path]                = None,
        duration:     int                           = 5,
        sample_rate:  int                           = 22050,
    ) -> None:
        """
        classifier     Audio classifier to use.  If None, a LibrosaFeatureClassifier
                       is constructed on first use (lazy — no import here).
        audio_path     Pre-existing audio file to observe.  If None, records from mic.
        duration       Recording duration in seconds (ignored when audio_path is set).
        sample_rate    Target sample rate for recording.
        """
        self._classifier  = classifier   # None = lazy LibrosaFeatureClassifier
        self._audio_path  = audio_path
        self._duration    = duration
        self._sample_rate = sample_rate

    def _get_classifier(self) -> AudioClassifierBase:
        if self._classifier is None:
            self._classifier = LibrosaFeatureClassifier()
        return self._classifier

    def _record_audio(self, save_dir: Path, obs_id: str) -> Path:
        """Record audio from the microphone and save it."""
        try:
            import sounddevice as sd
            import numpy as np
            import wave
        except ImportError as exc:
            raise ImportError(
                "Microphone recording requires sounddevice and numpy:\n"
                "  pip install sounddevice numpy"
            ) from exc

        logger.info("Recording %d seconds of audio…", self._duration)
        recording = sd.rec(
            int(self._duration * self._sample_rate),
            samplerate=self._sample_rate,
            channels=1,
            dtype=np.float32,
        )
        sd.wait()

        out_path = save_dir / f"{obs_id}.wav"
        with wave.open(str(out_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self._sample_rate)
            wf.writeframes((recording * 32767).astype(np.int16).tobytes())

        logger.info("Audio recorded and saved to %s", out_path)
        return out_path

    def _copy_audio(self, src: Path, save_dir: Path, obs_id: str) -> Path:
        """Copy an existing audio file into the observation store."""
        suffix  = src.suffix or ".wav"
        out_path = save_dir / f"{obs_id}{suffix}"
        shutil.copy2(src, out_path)
        logger.info("Audio copied to %s", out_path)
        return out_path

    def observe(
        self,
        *,
        candidate_labels: List[str],
        save_dir:         Path,
        extra_gaps:       Optional[List[str]] = None,
        session_id:       Optional[str]       = None,
        metadata:         Optional[Dict[str, Any]] = None,
    ) -> ObservationResult:
        """
        Capture + classify one audio clip → ObservationResult with all 6 properties.
        """
        obs_id     = str(uuid.uuid4())
        session_id = session_id or str(uuid.uuid4())
        save_dir.mkdir(parents=True, exist_ok=True)

        # ── Capture ────────────────────────────────────────────────────────────
        if self._audio_path is not None:
            sensor_id  = f"file:{self._audio_path.name}"
            saved_path = self._copy_audio(self._audio_path, save_dir, obs_id)
        else:
            sensor_id  = f"microphone:{self._duration}s"
            saved_path = self._record_audio(save_dir, obs_id)

        # ── Classify ───────────────────────────────────────────────────────────
        clf = self._get_classifier()
        result = clf.classify(saved_path, candidate_labels)

        logger.info(
            "Classified as '%s' (confidence=%.3f, model=%s)",
            result.label, result.confidence, result.model_used,
        )

        # ── Populate all 6 Epistemic Artifact properties ───────────────────────
        gaps = list(_DEFAULT_GAPS.get("audio", []))
        if extra_gaps:
            gaps.extend(extra_gaps)

        obs = ObservationResult(
            # 1. Origin
            sensor_type = self.sensor_type,
            sensor_id   = sensor_id,
            model_used  = result.model_used,
            session_id  = session_id,
            # 2. Type — always MEASUREMENT for sensor data
            epistemic_status = EpistemicStatus.MEASUREMENT.value,
            # 3. Confidence
            label      = result.label,
            confidence = result.confidence,
            # 4. Contradictions — empty at creation
            contradictions = [],
            # 5. Gaps — default + extra
            gaps = gaps,
            # 6. Age — set by ObservationResult default
            observation_id = obs_id,
            metadata       = {
                "audio_path":   str(saved_path),
                "duration":     self._duration if self._audio_path is None else None,
                "sample_rate":  self._sample_rate,
                "all_scores":   result.all_scores,
                "features":     result.raw if result.raw else {},
                **(metadata or {}),
            },
        )

        return obs
