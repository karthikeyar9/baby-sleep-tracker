"""Coral Edge TPU detector — MoveNet Lightning pose estimation.

Uses the MoveNet Single Pose Lightning model compiled for Edge TPU
to detect 17 COCO body keypoints at high speed on Raspberry Pi.
"""

import logging
import os

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# MoveNet COCO keypoint indices
NOSE = 0
LEFT_EYE = 1
RIGHT_EYE = 2
LEFT_EAR = 3
RIGHT_EAR = 4
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12
LEFT_KNEE = 13
RIGHT_KNEE = 14
LEFT_ANKLE = 15
RIGHT_ANKLE = 16

_NUM_KEYPOINTS = 17

# Minimum average confidence to consider a person detected
_PERSON_CONFIDENCE_THRESHOLD = 0.2
# Minimum number of keypoints above threshold to count as detected
_MIN_VISIBLE_KEYPOINTS = 4


class CoralPoseDetector:
    """Pose detection using MoveNet on Coral Edge TPU.

    Detects 17 COCO body keypoints. Output format per keypoint: [y, x, confidence]
    where y and x are normalized to [0, 1] relative to the input image.
    """

    def __init__(self, model_path=None):
        self.enabled = False
        self.interpreter = None
        self._input_size = None

        if model_path and os.path.isfile(model_path):
            self._load_model(model_path)

    def _load_model(self, model_path):
        try:
            from pycoral.adapters import common
            from pycoral.utils.edgetpu import make_interpreter

            self.interpreter = make_interpreter(model_path)
            self.interpreter.allocate_tensors()
            self._input_size = common.input_size(self.interpreter)
            self.enabled = True
            logger.info("Coral pose detector loaded from %s (input size: %s)",
                        model_path, self._input_size)
        except Exception as e:
            logger.warning("Could not load Coral pose detector: %s", e)
            self.enabled = False

    def detect_pose(self, frame):
        """Run MoveNet pose estimation on a BGR frame.

        Args:
            frame: numpy array (H, W, 3) in BGR format (from OpenCV).

        Returns:
            numpy array of shape (17, 3) with [y, x, confidence] per keypoint,
            or None if detector is not enabled.
        """
        if not self.enabled:
            return None

        from pycoral.adapters import common

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, self._input_size)

        common.set_input(self.interpreter, resized)
        self.interpreter.invoke()

        pose = common.output_tensor(self.interpreter, 0).copy().reshape(_NUM_KEYPOINTS, 3)
        return pose

    def get_wrist_positions(self, pose, frame_shape):
        """Extract left and right wrist positions in pixel coordinates.

        Matches the format used by SleepDetector.movement_q:
            (left_wrist_xy, right_wrist_xy)

        Args:
            pose: (17, 3) array from detect_pose().
            frame_shape: (height, width, channels) of the original frame.

        Returns:
            Tuple of ((left_x, left_y), (right_x, right_y)) in pixel coords,
            or None if pose is None.
        """
        if pose is None:
            return None

        h, w = frame_shape[:2]

        left_wrist = (
            float(pose[LEFT_WRIST][1] * w),   # x = col * width
            float(pose[LEFT_WRIST][0] * h),   # y = row * height
        )
        right_wrist = (
            float(pose[RIGHT_WRIST][1] * w),
            float(pose[RIGHT_WRIST][0] * h),
        )
        return left_wrist, right_wrist

    def is_person_detected(self, pose):
        """Check if a person is visible based on keypoint confidences.

        Args:
            pose: (17, 3) array from detect_pose(), or None.

        Returns:
            True if enough keypoints have sufficient confidence, False otherwise.
            Returns None if detector is not enabled or pose is None.
        """
        if not self.enabled or pose is None:
            return None

        confidences = pose[:, 2]
        visible = np.sum(confidences > _PERSON_CONFIDENCE_THRESHOLD)
        return int(visible) >= _MIN_VISIBLE_KEYPOINTS

    def draw_keypoints(self, frame, pose, min_confidence=0.2):
        """Draw detected keypoints on a frame for debugging.

        Args:
            frame: BGR image to draw on (modified in-place).
            pose: (17, 3) array from detect_pose().
            min_confidence: Only draw keypoints above this threshold.

        Returns:
            The annotated frame.
        """
        if pose is None:
            return frame

        h, w = frame.shape[:2]
        for i in range(_NUM_KEYPOINTS):
            y_norm, x_norm, conf = pose[i]
            if conf < min_confidence:
                continue
            cx = int(x_norm * w)
            cy = int(y_norm * h)
            cv2.circle(frame, (cx, cy), 4, (0, 255, 0), cv2.FILLED)

        return frame
