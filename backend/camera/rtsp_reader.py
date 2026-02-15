import subprocess
import time
import logging

import cv2
import numpy as np

from backend.config import (
    CAM_URL,
    RTSP_FRAME_WIDTH,
    RTSP_FRAME_HEIGHT,
    FFMPEG_OUTPUT_FPS,
)

logger = logging.getLogger(__name__)


def receive(producer_q):
    """Continuously read frames from camera and push to the producer queue.

    Supports RTSP streams (via FFmpeg) and local devices / video files
    (via OpenCV VideoCapture).
    """
    cam_url = CAM_URL
    logger.info("Connecting to camera at: %s", cam_url)

    if "rtsp://" in cam_url:
        _receive_rtsp(cam_url, producer_q)
    else:
        _receive_opencv(cam_url, producer_q)


def _receive_rtsp(cam_url, producer_q):
    """Read frames from an RTSP stream using FFmpeg subprocess."""
    logger.info("Using FFmpeg pipe for RTSP stream")

    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", cam_url,
        "-r", str(FFMPEG_OUTPUT_FPS),
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-an",
        "-",
    ]

    width, height = RTSP_FRAME_WIDTH, RTSP_FRAME_HEIGHT
    frame_size = width * height * 3

    try:
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10 ** 8,
        )
        logger.info("FFmpeg connected to camera")

        while True:
            raw_frame = process.stdout.read(frame_size)
            if len(raw_frame) != frame_size:
                logger.warning("Incomplete frame, reconnecting...")
                break
            img = np.frombuffer(raw_frame, dtype=np.uint8).reshape((height, width, 3))
            producer_q.append(img)
    except Exception as e:
        logger.error("FFmpeg error: %s", e)


def _receive_opencv(cam_url, producer_q):
    """Read frames from a local camera or video file using OpenCV."""
    logger.info("Using OpenCV VideoCapture")

    cap = cv2.VideoCapture(cam_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if cap.isOpened():
        logger.info("Camera connected")
    else:
        logger.error("Could not connect to camera")
        return

    while cap.isOpened():
        ret, img = cap.read()
        if ret:
            producer_q.append(img)
        else:
            logger.warning("Failed to read frame")
            time.sleep(0.1)
