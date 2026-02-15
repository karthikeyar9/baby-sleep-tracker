"""Flask API server and resource server."""

import json
import os
import shutil
import time
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread

import cv2
import numpy as np
from flask import Flask, request, Response, jsonify
from flask_cors import CORS, cross_origin
from PIL import Image

from backend.config import (
    APP_DIR,
    FLASK_PORT,
    FLASK_HOST,
    RESOURCE_SERVER_PORT,
    CROP_AREA_FILE,
    NOTIFICATIONS_FILE,
    BLANKET_MODEL_INPUT_DIR,
    BLANKET_MODEL_CURRENT_OUTPUT_DIR,
    CLASSIFIER_RESOLUTION,
)
from backend.models import blanket_svm
from backend.utils.image import maintain_aspect_ratio_resize
from backend.storage import sqlite_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resource server (port 8000) — serves CSV files with CORS
# ---------------------------------------------------------------------------

class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        return super().end_headers()


def start_resource_server():
    """Start the HTTP resource server on port 8000 (blocking)."""
    httpd = HTTPServer(("0.0.0.0", RESOURCE_SERVER_PORT), CORSRequestHandler)
    logger.info("Resource server started on port %d", RESOURCE_SERVER_PORT)
    httpd.serve_forever()


# ---------------------------------------------------------------------------
# Flask API server (port 8001)
# ---------------------------------------------------------------------------

def create_flask_app(detector, frame_queues):
    """Create and configure the Flask application.

    Args:
        detector: SleepDetector instance
        frame_queues: tuple of (frame_q, cropped_raw_frame_q, debug_frame_q)
    """
    app = Flask(__name__)
    CORS(app)

    _frame_q, cropped_raw_frame_q, debug_frame_q = frame_queues

    # ------------------------------------------------------------------
    # Video feed endpoints
    # ------------------------------------------------------------------

    @app.route("/video_feed/<stream_type>")
    @cross_origin()
    def video_feed(stream_type):
        def yield_frame(stype):
            while True:
                ret = False
                buffer = None
                if stype == "processed":
                    if len(debug_frame_q) > 0:
                        ret, buffer = cv2.imencode(".jpg", debug_frame_q.popleft())
                else:
                    if len(cropped_raw_frame_q) > 0:
                        ret, buffer = cv2.imencode(".jpg", cropped_raw_frame_q.popleft())
                if ret:
                    frame = buffer.tobytes()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                    )
                else:
                    time.sleep(0.033)

        return Response(
            yield_frame(stream_type),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    # ------------------------------------------------------------------
    # Classification / detection endpoints
    # ------------------------------------------------------------------

    @app.route("/getClassificationProbabilities")
    @cross_origin()
    def get_classification_probabilities():
        if detector.focus_bounding_box[0] is None:
            return f"Bounds not set.,,, {detector.body_found}"
        return f"{detector.model_proba},{detector.body_found}"

    @app.route("/getResultAndReasons")
    @cross_origin()
    def get_result_and_reasons():
        avg_awake, reasons = detector.get_result_and_reasons()
        return f"{avg_awake},{','.join(reasons)}"

    # ------------------------------------------------------------------
    # Settings endpoints
    # ------------------------------------------------------------------

    @app.route("/getSleepNotificationsEnabled")
    @cross_origin()
    def get_sleep_notifications_enabled():
        try:
            with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "false"

    @app.route("/setSleepNotificationsEnabled/<enabled>")
    @cross_origin()
    def set_sleep_notifications_enabled(enabled):
        with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            f.write(enabled)
        return "ok"

    # ------------------------------------------------------------------
    # Focus region / retraining endpoints
    # ------------------------------------------------------------------

    @app.route("/setAIFocusRegion/<focus_region>")
    @cross_origin()
    def set_ai_focus_region(focus_region):
        detector.lock_model_use = True

        if focus_region == "reset":
            with open(CROP_AREA_FILE, "w", encoding="utf-8") as f:
                f.write(",,,")
            detector.reset_focus_region()
            detector.lock_model_use = False
            return "reset ok"

        with open(CROP_AREA_FILE, "w", encoding="utf-8") as f:
            f.write(focus_region)

        parts = focus_region.split(",")
        x = int(float(parts[0]))
        y = int(float(parts[1]))
        w = int(float(parts[2]))
        h = int(float(parts[3]))

        cur = detector.focus_bounding_box
        if cur[0] is None:
            detector.set_focus_region(x, y, w, h)
        else:
            detector.set_focus_region(cur[0] + x, cur[1] + y, w, h)

        # Retrain model with new bounds
        try:
            new_model = blanket_svm.retrain_from_images(detector.focus_bounding_box)
            if new_model is not None:
                detector.blanket_model = new_model
        except Exception as e:
            logger.error("Retrain failed: %s", e)

        detector.lock_model_use = False
        return "nice"

    @app.route("/retrainWithNewSample/<classification>")
    @cross_origin()
    def retrain_with_new_sample(classification):
        try:
            detector.lock_model_use = True

            new_input_path = os.path.join(
                BLANKET_MODEL_INPUT_DIR,
                classification,
                f"{classification}_{int(time.time())}.png",
            )
            raw_uncropped_path = os.path.join(BLANKET_MODEL_CURRENT_OUTPUT_DIR, "raw_uncropped.png")

            os.makedirs(os.path.dirname(new_input_path), exist_ok=True)
            shutil.move(raw_uncropped_path, new_input_path)

            new_model = blanket_svm.retrain_with_new_sample(
                classification, new_input_path, detector.focus_bounding_box
            )
            if new_model is not None:
                detector.blanket_model = new_model

        except Exception as e:
            logger.error("Retrain with new sample failed: %s", e)
        finally:
            detector.lock_model_use = False

        return "ok"

    # ------------------------------------------------------------------
    # NEW: Diaper tracking endpoints
    # ------------------------------------------------------------------

    @app.route("/api/diaper", methods=["POST"])
    @cross_origin()
    def log_diaper():
        data = request.json
        diaper_type = data.get("type", "wet")
        notes = data.get("notes", "")
        sqlite_store.log_diaper_event(diaper_type, notes)
        return jsonify({"status": "ok"})

    @app.route("/api/diaper/stats", methods=["GET"])
    @cross_origin()
    def diaper_stats():
        date_str = request.args.get("date")
        stats = sqlite_store.get_diaper_stats(date_str)
        return jsonify(stats)

    @app.route("/api/diaper/history", methods=["GET"])
    @cross_origin()
    def diaper_history():
        limit = request.args.get("limit", 50, type=int)
        events = sqlite_store.get_diaper_events(limit=limit)
        return jsonify(events)

    # ------------------------------------------------------------------
    # NEW: Sleep events API
    # ------------------------------------------------------------------

    @app.route("/api/sleep/events", methods=["GET"])
    @cross_origin()
    def sleep_events():
        limit = request.args.get("limit", 100, type=int)
        events = sqlite_store.get_sleep_events(limit=limit)
        return jsonify(events)

    @app.route("/api/sleep/stats", methods=["GET"])
    @cross_origin()
    def sleep_stats():
        from backend.trackers.sleep_tracker import SleepTracker
        tracker = SleepTracker()
        date_str = request.args.get("date")
        daily = tracker.get_daily_sleep_stats(date_str)
        wake_window = tracker.get_wake_window_status()
        night_sleep = tracker.get_night_sleep_stats(date_str)
        return jsonify({**daily, "wake_window": wake_window, "night_sleep": night_sleep})

    @app.route("/api/sleep/weekly", methods=["GET"])
    @cross_origin()
    def sleep_weekly():
        from backend.trackers.sleep_tracker import SleepTracker
        tracker = SleepTracker()
        trends = tracker.get_weekly_trends()
        return jsonify(trends)

    # ------------------------------------------------------------------
    # NEW: Cry events API
    # ------------------------------------------------------------------

    @app.route("/api/cry/events", methods=["GET"])
    @cross_origin()
    def cry_events():
        limit = request.args.get("limit", 50, type=int)
        events = sqlite_store.get_cry_events(limit=limit)
        return jsonify(events)

    # ------------------------------------------------------------------
    # NEW: Feeding events API
    # ------------------------------------------------------------------

    @app.route("/api/feeding", methods=["POST"])
    @cross_origin()
    def log_feeding():
        data = request.json
        sqlite_store.log_feeding_event(
            feeding_type=data.get("type", "bottle"),
            duration_minutes=data.get("duration_minutes"),
            amount_oz=data.get("amount_oz"),
            notes=data.get("notes", ""),
        )
        return jsonify({"status": "ok"})

    @app.route("/api/feeding/history", methods=["GET"])
    @cross_origin()
    def feeding_history():
        limit = request.args.get("limit", 50, type=int)
        events = sqlite_store.get_feeding_events(limit=limit)
        return jsonify(events)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.route("/api/health")
    @cross_origin()
    def health():
        return jsonify({
            "status": "ok",
            "is_awake": detector.is_awake,
            "body_found": detector.body_found,
            "model_sees_baby": detector.model_sees_baby,
            "focus_region_set": detector.focus_bounding_box[0] is not None,
        })

    return app


def run_flask_app(detector, frame_queues):
    """Create and run the Flask app (blocking)."""
    app = create_flask_app(detector, frame_queues)
    app.run(debug=False, use_reloader=False, port=FLASK_PORT, host=FLASK_HOST, threaded=True)
