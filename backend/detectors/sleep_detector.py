import logging
import time
import statistics
from collections import deque

import cv2
import mediapipe as mp

from backend.config import (
    CLASSIFIER_RESOLUTION,
    MAX_FRAME_WIDTH,
    MAX_FRAME_HEIGHT,
    FPS,
    PROCESS_FPS,
    MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
    MEDIAPIPE_MIN_TRACKING_CONFIDENCE,
    EYES_OPEN_Q_SIZE,
    AWAKE_Q_SIZE,
    MOVEMENT_Q_SIZE,
    EYES_OPEN_VOTE_THRESHOLD,
    EYES_AWAKE_VOTE_WEIGHT,
    MOVEMENT_STD_THRESHOLD,
    AWAKE_THRESHOLD,
    BLANKET_IMAGE_DIFF_THRESHOLD,
    DEBOUNCE_WAKE_EVENT,
    DEBOUNCE_WAKE_STATUS,
    DEBOUNCE_VOTING,
    DEBOUNCE_NO_EYES,
    DEBOUNCE_NO_BODY,
    DEBOUNCE_BLANKET,
    DEBOUNCE_PERIODIC_CHECK,
    CROP_AREA_FILE,
    BLANKET_MODEL_CURRENT_OUTPUT_DIR,
    OWL_MODE,
    APP_DIR,
    SLEEP_LOGS_CSV,
    CORAL_TPU_ENABLED,
    CORAL_MODEL_PATH,
)
from backend.detectors.coral_detector import CoralPoseDetector
from backend.utils.geometry import check_eyes_open, check_mouth_open
from backend.utils.image import maintain_aspect_ratio_resize
from backend.storage import sqlite_store

logger = logging.getLogger(__name__)

# MediaPipe face mesh landmark indices
LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]

# Lip connections for visualization
TOP_LIP = frozenset([
    (324, 308), (78, 191), (191, 80), (80, 81), (81, 82),
    (82, 13), (13, 312), (312, 311), (311, 310),
    (310, 415), (415, 308),
    (375, 291), (61, 185), (185, 40), (40, 39), (39, 37),
    (37, 0), (0, 267),
    (267, 269), (269, 270), (270, 409), (409, 291),
])
BOTTOM_LIP = frozenset([
    (61, 146), (146, 91), (91, 181), (181, 84), (84, 17),
    (17, 314), (314, 405), (405, 321), (321, 375),
    (78, 95), (95, 88), (88, 178), (178, 87), (87, 14),
    (14, 317), (317, 402), (402, 318), (318, 324),
])


def _debounce(seconds):
    """Decorator: only allow the function to be called once every `seconds`."""
    def decorate(f):
        t = None

        def wrapped(*args, **kwargs):
            nonlocal t
            now = time.time()
            if t is None or now - t >= seconds:
                result = f(*args, **kwargs)
                t = time.time()
                return result
        return wrapped
    return decorate


class SleepDetector:
    """Core sleep detection engine using MediaPipe face mesh and pose.

    Heuristics:
    1) no eyes -> no body -> blanket model: BABY -> asleep
    2) no eyes -> no body -> blanket model: NO_BABY -> awake
    3) no eyes -> body found -> moving -> awake
    4) no eyes -> body found -> not moving -> asleep
    5) eyes -> open -> awake
    6) eyes -> closed -> movement -> awake
    7) eyes -> closed -> no movement -> asleep
    8) eyes -> closed -> mouth open -> awake (crying/yawning)
    """

    def __init__(self, blanket_model):
        self.blanket_model = blanket_model
        self.frame_dim = (MAX_FRAME_WIDTH, MAX_FRAME_HEIGHT)
        self.next_frame = 0
        self.fps = FPS

        # MediaPipe setup
        self.mp_pose = mp.solutions.pose
        self.mp_face = mp.solutions.face_mesh
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MEDIAPIPE_MIN_TRACKING_CONFIDENCE,
        )
        self.face = self.mp_face.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MEDIAPIPE_MIN_TRACKING_CONFIDENCE,
        )
        self.mp_draw = mp.solutions.drawing_utils

        # Voting queues
        self.eyes_open_q = deque(maxlen=EYES_OPEN_Q_SIZE)
        self.awake_q = deque(maxlen=AWAKE_Q_SIZE)
        self.awake_q.append(0)
        self.movement_q = deque(maxlen=MOVEMENT_Q_SIZE)
        self.image_comparison_q = deque(maxlen=2)
        self.eyes_open_state = False

        # State
        self.multi_face_landmarks = []
        self.is_awake = False
        self.body_found = False
        self.model_sees_baby = None
        self.model_proba = ",,"
        self.vote_reasons = []
        self.allow_model_movement_votes = False
        self.lock_model_use = False

        # Focus region
        self.focus_bounding_box = self._load_focus_region()

        # Coral Edge TPU fallback for pose detection
        self.coral_detector = None
        if CORAL_TPU_ENABLED:
            self.coral_detector = CoralPoseDetector(CORAL_MODEL_PATH)
            if not self.coral_detector.enabled:
                logger.warning("Coral TPU enabled in config but detector failed to initialize")
                self.coral_detector = None

        # Owl mode (easter egg)
        self.ser = None
        if OWL_MODE:
            import serial
            logger.info("OWL mode activated")
            self.ser = serial.Serial("/dev/ttyACM0", 9600, timeout=0)

    def _load_focus_region(self):
        """Load the user-defined crop area from file."""
        try:
            with open(CROP_AREA_FILE, "r", encoding="utf-8") as f:
                crop_area = f.read().strip()
            parts = crop_area.split(",")
            if parts[0] == "":
                return (None, None, None, None)
            x = int(float(parts[0]))
            y = int(float(parts[1]))
            w = int(float(parts[2]))
            h = int(float(parts[3]))
            return (x, y, w, h)
        except Exception:
            return (None, None, None, None)

    def set_focus_region(self, x, y, w, h):
        self.focus_bounding_box = (x, y, w, h)

    def reset_focus_region(self):
        self.focus_bounding_box = (None, None, None, None)

    # ------------------------------------------------------------------
    # Throttled helpers
    # ------------------------------------------------------------------

    @_debounce(DEBOUNCE_NO_EYES)
    def _throttled_handle_no_eyes(self):
        if len(self.eyes_open_q) > 0:
            logger.debug("No face found, depreciate queue")
            self.eyes_open_q.popleft()

    @_debounce(DEBOUNCE_NO_BODY)
    def _throttled_handle_no_body(self):
        pass

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def _process_face_and_pose(self, img, debug_img):
        """Run MediaPipe face mesh + pose on a frame. Returns (debug_img, body_found)."""
        results = self.face.process(img)
        results_pose = self.pose.process(img)

        if results_pose.pose_landmarks:
            self.body_found = True
            shape = img.shape
            left_wrist = (
                shape[1] * results_pose.pose_landmarks.landmark[15].x,
                shape[0] * results_pose.pose_landmarks.landmark[15].y,
            )
            right_wrist = (
                shape[1] * results_pose.pose_landmarks.landmark[16].x,
                shape[0] * results_pose.pose_landmarks.landmark[16].y,
            )
            self.movement_q.append((left_wrist, right_wrist))

            # Draw pose landmarks (body only, skip head)
            CUTOFF_THRESHOLD = 10
            body_connections = frozenset(
                [t for t in self.mp_pose.POSE_CONNECTIONS if t[0] > CUTOFF_THRESHOLD and t[1] > CUTOFF_THRESHOLD]
            )
            for idx, lm in enumerate(results_pose.pose_landmarks.landmark):
                if idx <= CUTOFF_THRESHOLD:
                    lm.visibility = 0
                    continue
                h, w, _ = debug_img.shape
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(debug_img, (cx, cy), 5, (255, 0, 0), cv2.FILLED)
            self.mp_draw.draw_landmarks(
                debug_img,
                results_pose.pose_landmarks,
                body_connections,
                landmark_drawing_spec=self.mp_draw.DrawingSpec(color=(255, 0, 0), thickness=2, circle_radius=2),
            )
        else:
            # Coral fallback: try Edge TPU pose when MediaPipe finds no body
            if self.coral_detector is not None:
                pose = self.coral_detector.detect_pose(img)
                if self.coral_detector.is_person_detected(pose):
                    self.body_found = True
                    wrists = self.coral_detector.get_wrist_positions(pose, img.shape)
                    if wrists:
                        self.movement_q.append(wrists)
                    # Draw Coral keypoints in green (distinct from MediaPipe's blue)
                    self.coral_detector.draw_keypoints(debug_img, pose)
                    logger.debug("Coral fallback: person detected")
                else:
                    self.body_found = False
                    self._throttled_handle_no_body()
            else:
                self.body_found = False
                self._throttled_handle_no_body()

        self.multi_face_landmarks = results.multi_face_landmarks
        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark
            eyes_are_open = check_eyes_open(landmarks, LEFT_EYE, RIGHT_EYE)

            if eyes_are_open == 0:
                mouth_is_open = check_mouth_open(landmarks)
                if mouth_is_open:
                    logger.debug("Eyes closed, mouth open, crying or yawning.")
                    self.eyes_open_q.append(1)
                else:
                    logger.debug("Eyes closed, mouth closed, sleeping.")
                    self.eyes_open_q.append(0)
            else:
                logger.debug("Eyes open, awake.")
                self.eyes_open_q.append(1)
        else:
            self._throttled_handle_no_eyes()

        return debug_img, self.body_found

    @_debounce(DEBOUNCE_VOTING)
    def _awake_voting_logic(self):
        if len(self.eyes_open_q) > len(self.eyes_open_q) / 2:
            avg = sum(self.eyes_open_q) / len(self.eyes_open_q)
            if avg > EYES_OPEN_VOTE_THRESHOLD:
                self.eyes_open_state = True
                logger.debug("Eyes open: vote awake")
                self.awake_q.append(EYES_AWAKE_VOTE_WEIGHT)
                self.vote_reasons.append("Eyes Open")
            else:
                self.eyes_open_state = False
                self.awake_q.append(0)
                self.vote_reasons.append("Eyes Closed")

    @_debounce(DEBOUNCE_VOTING)
    def _movement_voting_logic(self):
        if not self.body_found:
            if len(self.movement_q):
                self.movement_q.popleft()
        elif len(self.movement_q) > 5:
            left_wrist_list = [c[0] for c in self.movement_q]
            left_wrist_x = [c[0] for c in left_wrist_list]
            left_wrist_y = [c[1] for c in left_wrist_list]

            right_wrist_list = [c[1] for c in self.movement_q]
            right_wrist_x = [c[0] for c in right_wrist_list]
            right_wrist_y = [c[1] for c in right_wrist_list]

            std_lx = statistics.pstdev(left_wrist_x) - 1
            std_ly = statistics.pstdev(left_wrist_y) - 1
            std_rx = statistics.pstdev(right_wrist_x) - 1
            std_ry = statistics.pstdev(right_wrist_y) - 1

            avg_std = (((std_lx + std_ly) / 2) + ((std_rx + std_ry) / 2)) / 2

            if int(avg_std) < MOVEMENT_STD_THRESHOLD:
                logger.debug("No movement, vote sleeping")
                self.awake_q.append(0)
                self.vote_reasons.append("Not moving")
            else:
                logger.debug("Movement, vote awake")
                self.awake_q.append(1)
                self.vote_reasons.append("Moving")

    @_debounce(DEBOUNCE_BLANKET)
    def _blanket_logic(self, image, raw_uncropped_image):
        blurred = cv2.GaussianBlur(image, (3, 3), 0)
        self.image_comparison_q.append(blurred)

        if len(self.image_comparison_q) == 2 and self.allow_model_movement_votes:
            self.allow_model_movement_votes = False
            try:
                image_diff = float(abs(self.image_comparison_q[0].astype(float) - self.image_comparison_q[1].astype(float)).mean())
            except Exception:
                return
            if image_diff > BLANKET_IMAGE_DIFF_THRESHOLD:
                self.awake_q.append(image_diff / 60)
                self.vote_reasons.append("Movement")

        try:
            if not self.body_found and not self.lock_model_use and self.blanket_model is not None:
                y = self.blanket_model.predict_proba([blurred.flatten()])
                self.allow_model_movement_votes = True

                if y[0][0] > 0.5:
                    self.model_sees_baby = True
                    self.awake_q.append(0)
                    self.vote_reasons.append("Baby present")
                    if len(self.image_comparison_q) == 2:
                        try:
                            image_diff = float(abs(self.image_comparison_q[0].astype(float) - self.image_comparison_q[1].astype(float)).mean())
                        except Exception:
                            image_diff = 0
                        if image_diff < BLANKET_IMAGE_DIFF_THRESHOLD:
                            self.awake_q.append(0)
                            self.vote_reasons.append("Baby not moving")
                else:
                    self.model_sees_baby = False
                    self.awake_q.append(1)
                    self.vote_reasons.append("No baby present")

                self.model_proba = f"{y[0][0]},{y[0][1]},{time.time()}"
        except Exception as e:
            self.model_sees_baby = None
            logger.error("Blanket model error: %s", e)

        cv2.imwrite(
            f"{BLANKET_MODEL_CURRENT_OUTPUT_DIR}/raw_uncropped.png",
            raw_uncropped_image,
        )

    @_debounce(DEBOUNCE_WAKE_EVENT)
    def _write_wakeness_event(self, wake_status, img):
        """Record a wake/sleep state transition."""
        timestamp = int(time.time())

        # Write to legacy CSV
        sqlite_store.write_sleep_csv(wake_status, timestamp)

        # Write to SQLite
        state = "awake" if wake_status else "asleep"
        avg_awake = sum(self.awake_q) / len(self.awake_q) if self.awake_q else 0
        sqlite_store.log_sleep_event(state, confidence=avg_awake, reasons=list(set(self.vote_reasons)))

        if wake_status:
            logger.info("1,%s", timestamp)
            self.is_awake = True
            if OWL_MODE and self.ser:
                time.sleep(5)
                self.ser.write(bytes(str(999999) + "\n", "utf-8"))
        else:
            logger.info("0,%s", timestamp)
            p = f"{APP_DIR}/{timestamp}.png"
            cv2.imwrite(p, img)
            self.is_awake = False

    @_debounce(DEBOUNCE_WAKE_STATUS)
    def _set_wakeness_status(self, img):
        if len(self.awake_q):
            avg_awake = sum(self.awake_q) / len(self.awake_q)
            if avg_awake >= AWAKE_THRESHOLD and not self.is_awake:
                self._write_wakeness_event(True, img)
            elif avg_awake < AWAKE_THRESHOLD and self.is_awake:
                self._write_wakeness_event(False, img)

    @_debounce(DEBOUNCE_PERIODIC_CHECK)
    def _periodic_wakeness_check(self):
        logger.debug("Is baby awake: %s", self.is_awake)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_frame(self, raw_img, raw_uncropped_image, debug_frame_q):
        """Process a single frame through the full detection pipeline.

        Returns the annotated debug image.
        """
        debug_img = raw_img.copy()
        raw_img.flags.writeable = False

        # Clear vote reasons for this frame
        self.vote_reasons = []

        debug_img, body_found = self._process_face_and_pose(raw_img, debug_img)
        self._awake_voting_logic()
        self._movement_voting_logic()
        self._blanket_logic(raw_img.copy(), raw_uncropped_image)
        self._set_wakeness_status(debug_img)
        self._periodic_wakeness_check()

        return debug_img

    def draw_face_landmarks(self, debug_img):
        """Draw face mesh landmarks on the debug image."""
        if not self.multi_face_landmarks:
            return debug_img

        for face_landmarks in self.multi_face_landmarks:
            self.mp_draw.draw_landmarks(
                image=debug_img,
                landmark_list=face_landmarks,
                connections=self.mp_face.FACEMESH_RIGHT_EYE,
                landmark_drawing_spec=None,
                connection_drawing_spec=self.mp_draw.DrawingSpec(color=(255, 150, 255), thickness=1, circle_radius=1),
            )
            self.mp_draw.draw_landmarks(
                image=debug_img,
                landmark_list=face_landmarks,
                connections=self.mp_face.FACEMESH_LEFT_EYE,
                landmark_drawing_spec=None,
                connection_drawing_spec=self.mp_draw.DrawingSpec(color=(255, 255, 0), thickness=1, circle_radius=1),
            )
            self.mp_draw.draw_landmarks(
                image=debug_img,
                landmark_list=face_landmarks,
                connections=TOP_LIP,
                landmark_drawing_spec=None,
                connection_drawing_spec=self.mp_draw.DrawingSpec(color=(255, 150, 255), thickness=1, circle_radius=1),
            )
            self.mp_draw.draw_landmarks(
                image=debug_img,
                landmark_list=face_landmarks,
                connections=BOTTOM_LIP,
                landmark_drawing_spec=None,
                connection_drawing_spec=self.mp_draw.DrawingSpec(color=(255, 255, 0), thickness=1, circle_radius=1),
            )

        return debug_img

    def get_awake_probability(self):
        """Get current awake probability (0-1)."""
        if not self.awake_q:
            return 0.0
        return sum(self.awake_q) / len(self.awake_q)

    def get_result_and_reasons(self):
        """Get the current result and voting reasons. Clears reasons after read."""
        avg_awake = self.get_awake_probability()
        reasons = list(set(self.vote_reasons))
        return avg_awake, reasons

    def live(self, consumer_q, debug_frame_q, cropped_raw_frame_q):
        """Main processing loop: consume frames and run detection.

        Throttled to PROCESS_FPS to avoid burning CPU on every incoming frame.
        """
        min_interval = 1.0 / PROCESS_FPS if PROCESS_FPS > 0 else 0.5
        last_process_time = 0.0

        while True:
            if len(consumer_q) > 0:
                try:
                    img = consumer_q.pop()
                    # Drain stale frames so we always process the latest
                    consumer_q.clear()
                except IndexError:
                    time.sleep(0.05)
                    continue
            else:
                time.sleep(0.05)
                continue

            # Throttle: skip frame if we processed one too recently
            now = time.time()
            elapsed = now - last_process_time
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

            x, y, w, h = self.focus_bounding_box

            if img.shape[0] > MAX_FRAME_HEIGHT and img.shape[1] > MAX_FRAME_WIDTH:
                img, _ = maintain_aspect_ratio_resize(
                    img, width=self.frame_dim[0], height=self.frame_dim[1]
                )

            if x is None:
                cropped_raw_frame_q.append(img)
                last_process_time = time.time()
                logger.debug("Bounds not set, not running AI logic.")
                continue

            img_to_process = img[y:y + h, x:x + w]
            img_to_process, _ = maintain_aspect_ratio_resize(img_to_process, width=CLASSIFIER_RESOLUTION)
            cropped_raw_frame_q.append(img_to_process)

            debug_img = self.process_frame(img_to_process, img, debug_frame_q)
            last_process_time = time.time()

            if self.multi_face_landmarks:
                debug_img = self.draw_face_landmarks(debug_img)
                debug_frame_q.append(debug_img)
