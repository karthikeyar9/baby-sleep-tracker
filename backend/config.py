import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APP_DIR = os.getenv("APP_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = APP_DIR
DB_PATH = os.path.join(APP_DIR, "baby_tracker.db")
SLEEP_LOGS_CSV = os.path.join(APP_DIR, "sleep_logs.csv")
SLEEP_LOGS_FORECAST_CSV = os.path.join(APP_DIR, "sleep_logs_forecasted.csv")
BLANKET_MODEL_PATH = os.path.join(APP_DIR, "blanket_model", "creepy_baby_model.pkl")
BLANKET_MODEL_INPUT_DIR = os.path.join(APP_DIR, "blanket_model", "input")
BLANKET_MODEL_OUTPUT_DIR = os.path.join(APP_DIR, "blanket_model", "output")
BLANKET_MODEL_CURRENT_OUTPUT_DIR = os.path.join(APP_DIR, "blanket_model", "current_output")
IMAGE_DATA_JSON = os.path.join(BLANKET_MODEL_OUTPUT_DIR, "image_data.json")
CROP_AREA_FILE = os.path.join(APP_DIR, "user_defined_crop_area.txt")
NOTIFICATIONS_FILE = os.path.join(APP_DIR, "notifications.txt")
LOG_FILE = os.path.join(APP_DIR, "sleepy_logs.log")

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
CAM_URL = os.getenv("CAM_URL", "")
VIDEO_PATH = os.getenv("VIDEO_PATH", "")
# Default RTSP frame dimensions (from ffprobe of the camera)
RTSP_FRAME_WIDTH = int(os.getenv("RTSP_FRAME_WIDTH", "2304"))
RTSP_FRAME_HEIGHT = int(os.getenv("RTSP_FRAME_HEIGHT", "1296"))
MAX_FRAME_WIDTH = 1920
MAX_FRAME_HEIGHT = 1080

# ---------------------------------------------------------------------------
# Detection thresholds
# ---------------------------------------------------------------------------
CLASSIFIER_RESOLUTION = 256
FPS = 30
# How many frames per second to actually process through ML pipeline (lower = less CPU)
PROCESS_FPS = int(os.getenv("PROCESS_FPS", "2"))
# FFmpeg output frame rate (lower = less decode work)
FFMPEG_OUTPUT_FPS = int(os.getenv("FFMPEG_OUTPUT_FPS", "5"))

# Eye detection
EYE_CLOSED_RATIO_THRESHOLD = 5
EYES_OPEN_Q_SIZE = 30
EYES_OPEN_VOTE_THRESHOLD = 0.75

# Mouth detection
MOUTH_OPEN_RATIO = 0.8

# Movement detection
MOVEMENT_Q_SIZE = 10
MOVEMENT_STD_THRESHOLD = 30

# Awake voting
AWAKE_Q_SIZE = 15
AWAKE_THRESHOLD = 0.6
EYES_AWAKE_VOTE_WEIGHT = 3

# Blanket model
BLANKET_IMAGE_DIFF_THRESHOLD = 75

# Debounce timings (seconds)
DEBOUNCE_WAKE_EVENT = 180
DEBOUNCE_WAKE_STATUS = 10
DEBOUNCE_VOTING = 1
DEBOUNCE_NO_EYES = 1
DEBOUNCE_NO_BODY = 1
DEBOUNCE_BLANKET = 1
DEBOUNCE_PERIODIC_CHECK = 5

# MediaPipe
MEDIAPIPE_MIN_DETECTION_CONFIDENCE = 0.3
MEDIAPIPE_MIN_TRACKING_CONFIDENCE = 0.3

# ---------------------------------------------------------------------------
# Servers
# ---------------------------------------------------------------------------
FLASK_PORT = int(os.getenv("FLASK_PORT", "8001"))
RESOURCE_SERVER_PORT = int(os.getenv("RESOURCE_SERVER_PORT", "8000"))
FLASK_HOST = "0.0.0.0"

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1")
OWL_MODE = os.getenv("OWL", "False").lower() in ("true", "1")
CORAL_TPU_ENABLED = os.getenv("CORAL_TPU_ENABLED", "False").lower() in ("true", "1")
CORAL_MODEL_PATH = os.getenv("CORAL_MODEL_PATH", "")
CRYING_DETECTION_ENABLED = os.getenv("CRYING_DETECTION_ENABLED", "False").lower() in ("true", "1")
BABY_AGE_MONTHS = int(os.getenv("BABY_AGE_MONTHS", "1"))

# ---------------------------------------------------------------------------
# Crying detection (Phase 2)
# ---------------------------------------------------------------------------
CRY_MODEL_PATH = os.getenv("CRY_MODEL_PATH", "")
CRY_CONFIDENCE_THRESHOLD = float(os.getenv("CRY_CONFIDENCE_THRESHOLD", "0.6"))
AUDIO_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
AUDIO_CHUNK_SECONDS = float(os.getenv("AUDIO_CHUNK_SECONDS", "2.0"))

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
NOTIFICATION_COOLDOWN_SECONDS = int(os.getenv("NOTIFICATION_COOLDOWN_SECONDS", "300"))
PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN", "")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_CHAT_ID = os.getenv("TELEGRAM_BOT_CHAT_ID", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# ---------------------------------------------------------------------------
# Smart home
# ---------------------------------------------------------------------------
HATCH_IP = os.getenv("HATCH_IP", "")
