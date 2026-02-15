"""Cry detection module — stub for Phase 2 implementation.

Will use YAMNet (audio classification) running on Coral Edge TPU
or CPU-based TFLite to detect baby crying from audio streams.
"""

import logging
from collections import deque

logger = logging.getLogger(__name__)


class CryDetector:
    """Detects baby crying from audio input.

    TODO (Phase 2):
    - Load YAMNet TFLite model (optionally Edge TPU compiled)
    - Process 2-second audio chunks at 16kHz
    - Classify into: crying_baby, whimper, infant_cry, silence, etc.
    - Use sliding window buffer for temporal smoothing
    """

    # YAMNet class indices for baby-related sounds
    CRY_CLASSES = {20: "crying_baby", 21: "whimper", 394: "infant_cry"}

    def __init__(self, model_path=None):
        self.enabled = False
        self.cry_buffer = deque(maxlen=5)
        self.model = None

        if model_path:
            self._load_model(model_path)

    def _load_model(self, model_path):
        """Load the audio classification model."""
        try:
            # TODO: Implement TFLite / Coral model loading
            # from pycoral.adapters import common
            # from pycoral.utils.edgetpu import make_interpreter
            # self.interpreter = make_interpreter(model_path)
            # self.interpreter.allocate_tensors()
            # self.enabled = True
            logger.info("Cry detector model loaded from %s", model_path)
        except Exception as e:
            logger.warning("Could not load cry detector model: %s", e)
            self.enabled = False

    def classify_audio(self, audio_chunk):
        """Classify an audio chunk.

        Args:
            audio_chunk: numpy array of float32 audio samples (16kHz, mono)

        Returns:
            tuple: (is_crying: bool, confidence: float)
        """
        if not self.enabled:
            return False, 0.0

        # TODO: Implement actual inference
        # common.set_input(self.interpreter, audio_chunk)
        # self.interpreter.invoke()
        # scores = common.output_tensor(self.interpreter, 0)
        # cry_score = max(scores[i] for i in self.CRY_CLASSES if i < len(scores))
        # self.cry_buffer.append(cry_score)
        # avg_score = np.mean(self.cry_buffer)
        # return avg_score > 0.6, avg_score

        return False, 0.0

    def get_intensity(self, confidence):
        if confidence > 0.85:
            return "screaming"
        if confidence > 0.7:
            return "crying"
        return "fussing"
