from abc import ABC, abstractmethod


class BaseDetector(ABC):
    """Abstract base class for all detectors."""

    @abstractmethod
    def process_frame(self, frame):
        """Process a single video frame and return detection results."""
        ...

    @abstractmethod
    def get_state(self):
        """Return the current detection state."""
        ...
