import math
import numpy as np

from backend.config import EYE_CLOSED_RATIO_THRESHOLD, MOUTH_OPEN_RATIO


def euclidean(point, point1):
    """Euclidean distance between two MediaPipe landmark points."""
    return math.sqrt((point1.x - point.x) ** 2 + (point1.y - point.y) ** 2)


def closed_ratio(landmarks, left_eye_indices, right_eye_indices):
    """Returns a ratio representing how open/closed the eyes are.

    Higher ratio = more closed (horizontal distance >> vertical distance).
    """
    rh_right = landmarks[right_eye_indices[0]]
    rh_left = landmarks[right_eye_indices[8]]
    rv_top = landmarks[right_eye_indices[12]]
    rv_bottom = landmarks[right_eye_indices[4]]

    lh_right = landmarks[left_eye_indices[0]]
    lh_left = landmarks[left_eye_indices[8]]
    lv_top = landmarks[left_eye_indices[12]]
    lv_bottom = landmarks[left_eye_indices[4]]

    rh_distance = euclidean(rh_right, rh_left)
    rv_distance = euclidean(rv_top, rv_bottom)
    lv_distance = euclidean(lv_top, lv_bottom)
    lh_distance = euclidean(lh_right, lh_left)

    re_ratio = rh_distance / rv_distance
    le_ratio = lh_distance / lv_distance
    return (re_ratio + le_ratio) / 2


def check_eyes_open(landmarks, left_eye_indices, right_eye_indices):
    """Returns 1 if eyes are open, 0 if closed."""
    ratio = closed_ratio(landmarks, left_eye_indices, right_eye_indices)
    if ratio > EYE_CLOSED_RATIO_THRESHOLD:
        return 0  # closed
    return 1  # open


def _landmark_to_array(landmark):
    return np.array([landmark.x, landmark.y, landmark.z])


def get_top_lip_height(landmarks):
    p39 = _landmark_to_array(landmarks[39])
    p81 = _landmark_to_array(landmarks[81])
    p0 = _landmark_to_array(landmarks[0])
    p13 = _landmark_to_array(landmarks[13])
    p269 = _landmark_to_array(landmarks[269])
    p311 = _landmark_to_array(landmarks[311])

    d1 = np.linalg.norm(p39 - p81)
    d2 = np.linalg.norm(p0 - p13)
    d3 = np.linalg.norm(p269 - p311)
    return (d1 + d2 + d3) / 3


def get_bottom_lip_height(landmarks):
    p181 = _landmark_to_array(landmarks[181])
    p178 = _landmark_to_array(landmarks[178])
    p17 = _landmark_to_array(landmarks[17])
    p14 = _landmark_to_array(landmarks[14])
    p405 = _landmark_to_array(landmarks[405])
    p402 = _landmark_to_array(landmarks[402])

    d1 = np.linalg.norm(p181 - p178)
    d2 = np.linalg.norm(p17 - p14)
    d3 = np.linalg.norm(p405 - p402)
    return (d1 + d2 + d3) / 3


def get_mouth_height(landmarks):
    p178 = _landmark_to_array(landmarks[178])
    p81 = _landmark_to_array(landmarks[81])
    p14 = _landmark_to_array(landmarks[14])
    p13 = _landmark_to_array(landmarks[13])
    p402 = _landmark_to_array(landmarks[402])
    p311 = _landmark_to_array(landmarks[311])

    d1 = np.linalg.norm(p178 - p81)
    d2 = np.linalg.norm(p14 - p13)
    d3 = np.linalg.norm(p402 - p311)
    return (d1 + d2 + d3) / 3


def check_mouth_open(landmarks):
    """Returns 1 if mouth is open, 0 if closed."""
    top_lip_height = get_top_lip_height(landmarks)
    bottom_lip_height = get_bottom_lip_height(landmarks)
    mouth_height = get_mouth_height(landmarks)

    if mouth_height > min(top_lip_height, bottom_lip_height) * MOUTH_OPEN_RATIO:
        return 1
    return 0
