"""Baby Sleep Tracker — main entry point.

Starts all threads:
1. Resource server (port 8000) — serves CSV files
2. Camera receiver — reads frames from RTSP/USB camera
3. Sleep detector — processes frames through ML pipeline
4. Flask API server (port 8001) — REST API + video feed
"""

import logging
import os
import sys
import time
from collections import deque
from threading import Thread

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.config import (
    APP_DIR, LOG_FILE, DEBUG, CAM_URL,
    CRYING_DETECTION_ENABLED, CRY_MODEL_PATH,
)
from backend.camera.frame_queue import create_frame_queues
from backend.camera.rtsp_reader import receive
from backend.models.blanket_svm import load_model
from backend.detectors.sleep_detector import SleepDetector
from backend.app import run_flask_app, start_resource_server
from backend.storage.sqlite_store import get_connection, migrate_csv_to_sqlite

# ---------------------------------------------------------------------------
# Logging — file only, no console spam
# ---------------------------------------------------------------------------

log_level = logging.DEBUG if DEBUG else logging.WARNING
logging.basicConfig(
    filename=LOG_FILE,
    filemode="a+",
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    level=log_level,
)
logger = logging.getLogger(__name__)


def main():
    print("Baby Sleep Tracker starting...")

    # Initialize database
    get_connection()
    migrate_csv_to_sqlite()

    # Load ML model
    blanket_model = load_model()

    # Create shared frame queues
    frame_q, cropped_raw_frame_q, debug_frame_q = create_frame_queues()

    # Initialize sleep detector
    detector = SleepDetector(blanket_model)
    print("Ready.")

    # Start resource server (port 8000) as daemon
    resource_thread = Thread(target=start_resource_server, daemon=True)
    resource_thread.start()

    # Start camera receiver as daemon
    camera_thread = Thread(target=receive, args=(frame_q,), daemon=True)
    camera_thread.start()

    # Start frame processor as daemon
    processor_thread = Thread(
        target=detector.live,
        args=(frame_q, debug_frame_q, cropped_raw_frame_q),
        daemon=True,
    )
    processor_thread.start()

    # -----------------------------------------------------------------------
    # Crying detection (Phase 2) — audio extraction + classification
    # -----------------------------------------------------------------------
    if CRYING_DETECTION_ENABLED:
        from backend.camera.audio_reader import receive_audio
        from backend.detectors.cry_detector import CryDetector
        from backend.trackers.cry_tracker import CryTracker
        from backend.notifications.notifier import NotificationDispatcher

        audio_q = deque(maxlen=10)
        cry_detector = CryDetector(model_path=CRY_MODEL_PATH or None)
        cry_tracker = CryTracker()
        notifier = NotificationDispatcher()

        def process_audio():
            """Pop audio chunks, classify, and track cry events."""
            while True:
                if not audio_q:
                    time.sleep(0.1)
                    continue

                chunk = audio_q.popleft()
                is_crying, confidence = cry_detector.classify_audio(chunk)
                event = cry_tracker.update(is_crying, confidence)

                if event is not None:
                    event_type, value = event
                    if event_type == "cry_start":
                        intensity = CryDetector.get_intensity(value)
                        notifier.notify(
                            "baby_crying",
                            f"Baby is {intensity}! (confidence: {value:.0%})",
                            priority="high",
                        )
                    elif event_type == "cry_stop":
                        notifier.notify(
                            "baby_stopped_crying",
                            f"Baby stopped crying after {value:.0f} seconds.",
                            priority="normal",
                        )

        audio_thread = Thread(
            target=receive_audio, args=(CAM_URL, audio_q), daemon=True
        )
        audio_thread.start()

        cry_thread = Thread(target=process_audio, daemon=True)
        cry_thread.start()

        print("Crying detection enabled.")
    else:
        print("Crying detection disabled.")

    # -----------------------------------------------------------------------
    # Diaper change reminders — always enabled
    # -----------------------------------------------------------------------
    from backend.trackers.diaper_tracker import DiaperTracker
    from backend.notifications.notifier import NotificationDispatcher

    diaper_tracker = DiaperTracker()
    if CRYING_DETECTION_ENABLED:
        diaper_notifier = notifier  # reuse the one from crying detection
    else:
        diaper_notifier = NotificationDispatcher()

    def diaper_reminder_loop():
        while True:
            result = diaper_tracker.check_reminder_needed()
            if result:
                _, hours = result
                diaper_notifier.notify(
                    "diaper_reminder",
                    f"No diaper change logged in {hours}h. Time to check?",
                )
            time.sleep(300)  # check every 5 minutes

    diaper_thread = Thread(target=diaper_reminder_loop, daemon=True)
    diaper_thread.start()
    print("Diaper change reminders enabled.")

    # Start Flask API server (non-daemon — keeps main thread alive)
    frame_queues = (frame_q, cropped_raw_frame_q, debug_frame_q)
    flask_thread = Thread(
        target=run_flask_app,
        args=(detector, frame_queues),
        daemon=False,
    )
    flask_thread.start()

    try:
        flask_thread.join()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
