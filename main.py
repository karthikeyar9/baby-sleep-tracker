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
from threading import Thread

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.config import APP_DIR, LOG_FILE, DEBUG
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
