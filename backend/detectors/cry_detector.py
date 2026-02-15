"""Cry detection module — YAMNet audio classification.

Uses YAMNet (TFLite) to detect baby crying from audio streams.
Supports Coral Edge TPU acceleration with CPU TFLite fallback.
"""

import logging
from collections import deque

import numpy as np

from backend.config import CRY_CONFIDENCE_THRESHOLD, CORAL_TPU_ENABLED

logger = logging.getLogger(__name__)


class CryDetector:
    """Detects baby crying from audio input using YAMNet."""

    # YAMNet class indices for baby-related sounds
    CRY_CLASSES = {20: "crying_baby", 21: "whimper", 394: "infant_cry"}

    # YAMNet expects 0.975s patches at 16kHz
    PATCH_SAMPLES = 15600

    def __init__(self, model_path=None):
        self.enabled = False
        self.cry_buffer = deque(maxlen=5)
        self.interpreter = None
        self.threshold = CRY_CONFIDENCE_THRESHOLD

        if model_path:
            self._load_model(model_path)

    def _load_model(self, model_path):
        """Load YAMNet TFLite model, trying Coral Edge TPU first."""
        # Try Coral Edge TPU
        if CORAL_TPU_ENABLED:
            try:
                from pycoral.utils.edgetpu import make_interpreter
                self.interpreter = make_interpreter(model_path)
                self.interpreter.allocate_tensors()
                self.enabled = True
                logger.info("Cry detector loaded on Coral Edge TPU: %s", model_path)
                return
            except Exception as e:
                logger.warning("Coral TPU load failed, trying CPU: %s", e)

        # Fall back to CPU TFLite
        try:
            import tflite_runtime.interpreter as tflite
            self.interpreter = tflite.Interpreter(model_path=model_path)
            self.interpreter.allocate_tensors()
            self.enabled = True
            logger.info("Cry detector loaded on CPU TFLite: %s", model_path)
        except Exception as e:
            logger.warning("Could not load cry detector model: %s", e)
            self.enabled = False

    def classify_audio(self, audio_chunk):
        """Classify an audio chunk for crying.

        Args:
            audio_chunk: numpy float32 array of audio samples (16kHz, mono)

        Returns:
            tuple: (is_crying: bool, confidence: float)
        """
        if not self.enabled or self.interpreter is None:
            return False, 0.0

        input_details = self.interpreter.get_input_details()
        output_details = self.interpreter.get_output_details()

        # Split chunk into 0.975s patches and take max cry score
        max_cry_score = 0.0
        num_samples = len(audio_chunk)

        for start in range(0, num_samples - self.PATCH_SAMPLES + 1, self.PATCH_SAMPLES):
            patch = audio_chunk[start:start + self.PATCH_SAMPLES]
            patch = patch.astype(np.float32)

            # Reshape for model input
            self.interpreter.resize_tensor_input(input_details[0]["index"], patch.shape)
            self.interpreter.allocate_tensors()
            self.interpreter.set_tensor(input_details[0]["index"], patch)
            self.interpreter.invoke()

            scores = self.interpreter.get_tensor(output_details[0]["index"]).flatten()
            cry_score = max(
                (scores[i] for i in self.CRY_CLASSES if i < len(scores)),
                default=0.0,
            )
            max_cry_score = max(max_cry_score, float(cry_score))

        self.cry_buffer.append(max_cry_score)
        avg_score = float(np.mean(self.cry_buffer))
        return avg_score > self.threshold, avg_score

    @staticmethod
    def get_intensity(confidence):
        """Map confidence score to a human-readable intensity label."""
        if confidence > 0.85:
            return "screaming"
        if confidence > 0.7:
            return "crying"
        return "fussing"
