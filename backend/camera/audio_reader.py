"""Audio extraction from RTSP camera stream via FFmpeg.

Runs a separate FFmpeg subprocess that extracts audio only (-vn),
outputting raw PCM: 16kHz, mono, 16-bit signed little-endian.
"""

import logging
import subprocess
import time

import numpy as np

from backend.config import AUDIO_SAMPLE_RATE, AUDIO_CHUNK_SECONDS

logger = logging.getLogger(__name__)


def read_chunk(process, sample_rate, duration):
    """Read a single audio chunk from the FFmpeg process.

    Returns:
        numpy float32 array normalized to [-1, 1], or None on failure.
    """
    num_samples = int(sample_rate * duration)
    num_bytes = num_samples * 2  # 16-bit = 2 bytes per sample

    raw = process.stdout.read(num_bytes)
    if len(raw) != num_bytes:
        return None

    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def receive_audio(cam_url, audio_q):
    """Continuously extract audio from camera stream and push chunks to queue.

    Designed to run in a daemon thread. Matches the pattern of
    ``backend.camera.rtsp_reader._receive_rtsp``.

    Args:
        cam_url: RTSP URL of the camera stream.
        audio_q: collections.deque to push float32 audio chunks into.
    """
    sample_rate = AUDIO_SAMPLE_RATE
    chunk_duration = AUDIO_CHUNK_SECONDS

    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", cam_url,
        "-vn",                  # no video
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",             # mono
        "-f", "s16le",
        "-",
    ]

    while True:
        try:
            logger.info("Starting audio FFmpeg for %s", cam_url)
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=10 ** 6,
            )

            while True:
                chunk = read_chunk(process, sample_rate, chunk_duration)
                if chunk is None:
                    logger.warning("Audio stream interrupted, reconnecting...")
                    break
                audio_q.append(chunk)

            process.kill()
            process.wait()
        except Exception as e:
            logger.error("Audio FFmpeg error: %s", e)

        # Back off before reconnect
        time.sleep(5)
