# Baby Sleep Tracker - Refactoring & Feature Roadmap

## Current State Summary

The app is a solid foundation: Flask backend (1,097-line `main.py`) with MediaPipe face/pose detection, SVM blanket model, multi-signal voting for sleep/wake, React+TypeScript frontend with D3 charts, and file-based CSV storage. It supports RTSP cameras and Docker deployment.

---

## Phase 0: Architecture Refactoring (Foundation)

Before adding features, the monolithic `main.py` needs to be modularized. This is critical for maintainability as we add crying detection, diaper tracking, etc.

### 0.1 - Split `main.py` into modules

```
backend/
├── app.py                    # Flask app factory + API routes
├── config.py                 # All env vars, constants, thresholds
├── camera/
│   ├── rtsp_reader.py        # FFmpeg RTSP thread (existing code)
│   └── frame_queue.py        # Thread-safe frame deque
├── detectors/
│   ├── base.py               # Abstract detector interface
│   ├── sleep_detector.py     # SleepyBaby class (eyes, mouth, movement, blanket)
│   ├── cry_detector.py       # NEW: Audio-based crying detection
│   └── coral_detector.py     # NEW: Edge TPU object/pose detection
├── models/
│   ├── blanket_svm.py        # SVM train/predict logic
│   └── cry_model.py          # NEW: TFLite crying classifier
├── trackers/
│   ├── sleep_tracker.py      # Sleep state machine + debouncing
│   ├── cry_tracker.py        # NEW: Cry event tracking
│   └── diaper_tracker.py     # NEW: Diaper change tracking
├── notifications/
│   ├── notifier.py           # Notification dispatcher
│   ├── pushover.py           # Pushover push notifications
│   ├── telegram.py           # Telegram bot
│   └── webhook.py            # Generic webhook support
├── storage/
│   ├── csv_store.py          # Current CSV file logic (legacy compat)
│   └── sqlite_store.py       # NEW: SQLite for structured data
└── utils/
    ├── image.py              # gamma_correction, resize, etc. (from helpers.py)
    └── geometry.py           # euclidean, ratios, etc.
```

### 0.2 - Replace CSV with SQLite

CSV append-only works but doesn't scale. SQLite gives structured queries, relationships, and still runs on RPi with zero config.

```sql
CREATE TABLE sleep_events (
    id INTEGER PRIMARY KEY,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    state TEXT CHECK(state IN ('asleep', 'awake')),
    confidence REAL,
    detection_reasons JSON
);

CREATE TABLE cry_events (
    id INTEGER PRIMARY KEY,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    intensity TEXT CHECK(intensity IN ('fussing', 'crying', 'screaming')),
    duration_seconds INTEGER
);

CREATE TABLE diaper_events (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    type TEXT CHECK(type IN ('wet', 'dirty', 'both', 'dry')),
    notes TEXT
);

CREATE TABLE feeding_events (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    type TEXT CHECK(type IN ('breast', 'bottle', 'solid')),
    duration_minutes INTEGER,
    amount_oz REAL,
    notes TEXT
);

CREATE TABLE notifications_log (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    event_type TEXT,
    channel TEXT,
    message TEXT,
    delivered BOOLEAN
);
```

### 0.3 - Centralized config system

```python
# config.py - centralize all thresholds
CORAL_TPU_ENABLED = True
CRYING_DETECTION_ENABLED = True
SLEEP_DEBOUNCE_SECONDS = 180
CRY_CONFIDENCE_THRESHOLD = 0.7
NOTIFICATION_COOLDOWN_SECONDS = 300
EYE_OPEN_THRESHOLD = 0.25
MOUTH_OPEN_THRESHOLD = 0.6
```

---

## Phase 1: Coral USB Edge TPU Integration

The Coral USB Accelerator runs TFLite models at ~30fps with minimal CPU load on the Pi, freeing resources for audio processing.

### 1.1 - Install Edge TPU runtime on RPi 4B

```bash
echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | \
  sudo tee /etc/apt/sources.list.d/coral-edgetpu.list
sudo apt update
sudo apt install libedgetpu1-std python3-pycoral
pip install pycoral tflite-runtime
```

### 1.2 - Replace MediaPipe pose detection with MoveNet on Coral

MediaPipe is CPU-heavy. MoveNet Lightning compiled for Edge TPU is faster and more accurate for pose estimation.

```python
# detectors/coral_detector.py
from pycoral.adapters import common, detect
from pycoral.utils.edgetpu import make_interpreter

class CoralPoseDetector:
    def __init__(self, model_path="models/movenet_single_pose_lightning_edgetpu.tflite"):
        self.interpreter = make_interpreter(model_path)
        self.interpreter.allocate_tensors()

    def detect_pose(self, frame):
        resized = cv2.resize(frame, (192, 192))
        common.set_input(self.interpreter, resized)
        self.interpreter.invoke()
        keypoints = common.output_tensor(self.interpreter, 0).copy()
        return self._parse_keypoints(keypoints)

    def is_eyes_visible(self, keypoints):
        left_eye = keypoints[1]
        right_eye = keypoints[2]
        return left_eye[2] > 0.3 and right_eye[2] > 0.3
```

### 1.3 - Models to download for Coral TPU

| Model | Purpose | Source |
|-------|---------|--------|
| `movenet_single_pose_lightning` | Body pose (17 keypoints) | TF Hub → compile with edgetpu_compiler |
| `ssd_mobilenet_v2_coco` | Person detection (bounding box) | Coral model zoo |
| `yamnet_edgetpu` | Audio classification (crying) | TF Hub / Coral |

### 1.4 - Hybrid detection strategy

Keep current MediaPipe eye/mouth analysis as a fallback when the baby's face is clearly visible, but use Coral TPU for:
- Fast person detection (is baby in crib?)
- Pose estimation (body position, movement)
- Audio event classification (crying — see Phase 2)

---

## Phase 2: Baby Crying Detection (Audio)

### 2.1 - Audio capture from RTSP stream

Most RTSP cameras include audio. Extract it alongside video:

```python
# camera/audio_reader.py
class RTSPAudioReader:
    def __init__(self, rtsp_url, sample_rate=16000):
        self.sample_rate = sample_rate
        self.process = subprocess.Popen([
            'ffmpeg', '-i', rtsp_url,
            '-vn',                    # no video
            '-acodec', 'pcm_s16le',   # raw PCM
            '-ar', str(sample_rate),  # 16kHz
            '-ac', '1',               # mono
            '-f', 's16le',            # raw format
            'pipe:1'
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def read_chunk(self, duration_seconds=2.0):
        num_samples = int(self.sample_rate * duration_seconds)
        raw = self.process.stdout.read(num_samples * 2)
        if len(raw) < num_samples * 2:
            return None
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
```

### 2.2 - Crying detection with YAMNet on Coral TPU

YAMNet is a pre-trained audio classifier (521 classes including "baby crying", "infant crying", "screaming"). Run it on Coral for real-time inference:

```python
# detectors/cry_detector.py
class CryDetector:
    CRY_CLASSES = {20: 'crying_baby', 21: 'whimper', 394: 'infant_cry'}

    def __init__(self, model_path="models/yamnet_edgetpu.tflite"):
        self.interpreter = make_interpreter(model_path)
        self.interpreter.allocate_tensors()
        self.cry_buffer = deque(maxlen=5)

    def classify_audio(self, audio_chunk):
        common.set_input(self.interpreter, audio_chunk)
        self.interpreter.invoke()
        scores = common.output_tensor(self.interpreter, 0)
        cry_score = max(scores[i] for i in self.CRY_CLASSES if i < len(scores))
        self.cry_buffer.append(cry_score)
        avg_score = np.mean(self.cry_buffer)
        is_crying = avg_score > 0.6
        return is_crying, avg_score

    def get_intensity(self, confidence):
        if confidence > 0.85: return 'screaming'
        if confidence > 0.7: return 'crying'
        return 'fussing'
```

### 2.3 - Sliding window with debounce

```python
# trackers/cry_tracker.py
class CryTracker:
    def __init__(self, onset_threshold=3, offset_threshold=5):
        self.is_crying = False
        self.consecutive_cry = 0
        self.consecutive_quiet = 0
        self.cry_start_time = None
        self.onset_threshold = onset_threshold
        self.offset_threshold = offset_threshold

    def update(self, is_crying, confidence):
        event = None
        if is_crying:
            self.consecutive_cry += 1
            self.consecutive_quiet = 0
            if not self.is_crying and self.consecutive_cry >= self.onset_threshold:
                self.is_crying = True
                self.cry_start_time = time.time()
                event = ('cry_start', confidence)
        else:
            self.consecutive_quiet += 1
            self.consecutive_cry = 0
            if self.is_crying and self.consecutive_quiet >= self.offset_threshold:
                self.is_crying = False
                duration = time.time() - self.cry_start_time
                event = ('cry_stop', duration)
        return event
```

### 2.4 - If RTSP cameras don't have audio

Add a USB microphone to the RPi 4B ($10 USB mic):
```bash
arecord -l
arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 test.wav
```

---

## Phase 3: Push Notifications

### 3.1 - Notification dispatcher (multi-channel)

```python
# notifications/notifier.py
class NotificationDispatcher:
    def __init__(self, config):
        self.channels = []
        self.cooldowns = {}
        self.cooldown_seconds = config.NOTIFICATION_COOLDOWN_SECONDS

        if config.PUSHOVER_TOKEN:
            self.channels.append(PushoverNotifier(config))
        if config.TELEGRAM_BOT_TOKEN:
            self.channels.append(TelegramNotifier(config))
        if config.WEBHOOK_URL:
            self.channels.append(WebhookNotifier(config))

    def notify(self, event_type, message, priority='normal'):
        now = time.time()
        if event_type in self.cooldowns:
            if now - self.cooldowns[event_type] < self.cooldown_seconds:
                return False
        self.cooldowns[event_type] = now
        for channel in self.channels:
            channel.send(message, priority=priority)
        return True
```

### 3.2 - Pushover (recommended for mobile push)

- $5 one-time purchase, no subscription
- Works on iOS + Android
- Supports priority levels, sounds, images

```python
# notifications/pushover.py
class PushoverNotifier:
    def send(self, message, priority='normal', image_path=None):
        data = {
            'token': self.app_token,
            'user': self.user_key,
            'message': message,
            'priority': 1 if priority == 'urgent' else 0,
            'sound': 'baby' if priority == 'urgent' else 'pushover',
        }
        files = {}
        if image_path:
            files['attachment'] = open(image_path, 'rb')
        requests.post('https://api.pushover.net/1/messages.json',
                      data=data, files=files)
```

### 3.3 - Notification events

| Event | Message | Priority | Cooldown |
|-------|---------|----------|----------|
| Baby crying | "Baby is crying! (confidence: 85%)" + snapshot | Urgent | 5 min |
| Baby stopped crying | "Baby stopped crying after 3 min" | Normal | None |
| Baby woke up | "Baby woke up after 45 min nap" | High | 10 min |
| Baby fell asleep | "Baby fell asleep at 2:30 PM" | Low | None |
| No baby detected | "Baby not detected in crib" | Urgent | 15 min |
| Camera offline | "Camera feed lost" | Urgent | 30 min |

---

## Phase 4: Diaper Change Tracking

Manual-entry feature with smart analytics.

### 4.1 - Backend API endpoints

```python
@app.route('/api/diaper', methods=['POST'])
def log_diaper():
    data = request.json
    db.execute("INSERT INTO diaper_events (timestamp, type, notes) VALUES (?, ?, ?)",
               (datetime.now(), data['type'], data.get('notes', '')))
    return jsonify({'status': 'ok'})

@app.route('/api/diaper/stats', methods=['GET'])
def diaper_stats():
    today = date.today()
    stats = {
        'today_count': ...,
        'today_wet': ...,
        'today_dirty': ...,
        'last_change': ...,
        'daily_average_7d': ...,
        'history': ...,
    }
    return jsonify(stats)
```

### 4.2 - Frontend: Quick-log diaper widget

```
┌──────────────────────────────┐
│  Diaper Tracker              │
│                              │
│  [Wet] [Dirty] [Both]       │  ← One-tap buttons
│                              │
│  Last change: 45 min ago     │
│  Today: 6 changes (4W, 2D)  │
│  Avg/day (7d): 8.2          │
│                              │
│  > View history              │
└──────────────────────────────┘
```

### 4.3 - Smart alerts

```python
last_change = db.get_last_diaper_event()
if time.time() - last_change.timestamp > 4 * 3600:
    notifier.notify('diaper_reminder',
        f"No diaper change logged in {hours}h. Time to check?",
        priority='normal')
```

---

## Phase 5: Enhanced Sleep Tracking & Analytics

### 5.1 - Improve sleep state machine

```python
class SleepState(Enum):
    AWAKE = 'awake'
    DROWSY = 'drowsy'
    LIGHT_SLEEP = 'light'
    DEEP_SLEEP = 'deep'
    CRYING = 'crying'
```

### 5.2 - Wake window tracking by age

```python
WAKE_WINDOWS = {
    0: (0.5, 1.0),    # Newborn: 30-60 min
    3: (1.25, 1.75),  # 3 months: 75-105 min
    6: (2.0, 3.0),    # 6 months: 2-3 hours
    9: (2.5, 3.5),    # 9 months: 2.5-3.5 hours
    12: (3.0, 4.0),   # 12 months: 3-4 hours
    18: (4.0, 6.0),   # 18 months: 4-6 hours
}
```

### 5.3 - Frontend dashboard improvements

- Daily summary card: total sleep, number of naps, longest stretch
- Weekly trends chart (D3): average nap duration over time
- Wake window countdown timer with color coding (green -> yellow -> red)
- Nap vs night sleep breakdown
- Export to CSV/PDF for pediatrician visits

---

## Phase 6: Frontend Modernization ✅

### 6.1 - Centralized API layer ✅

```
webapp/src/
├── api/
│   ├── types.ts            # Shared TypeScript interfaces
│   ├── client.ts           # Typed fetch wrappers (fetchApi, fetchText, fetchCSV)
│   └── endpoints.ts        # All API functions (sleep, diaper, feeding, legacy, csv)
├── hooks/
│   ├── usePolling.ts       # Generic polling hook (replaces setInterval patterns)
│   └── useApi.ts           # One-shot API hook with refetch
├── utils/
│   └── formatters.ts       # Shared formatMinutes, formatTime, timeAgo
```

### 6.2 - Bug fixes & refactoring ✅

- Fixed SleepDashboard using wrong env var (`REACT_APP_RESOURCE_SERVER_IP` → `REACT_APP_BACKEND_IP`)
- All components refactored to use centralized API client and shared hooks
- Eliminated 3 duplicate `formatMinutes` implementations
- Removed scattered `process.env` access from components

---

## Phase 7: Testing & Enhancement

Stabilize existing features, improve reliability, and fill gaps before adding new capabilities.

### 7.1 - End-to-end testing

- Test all API endpoints with real data on RPi hardware
- Verify polling intervals and data freshness across all components
- Test error states: backend down, camera disconnected, empty database
- Validate CORS behavior from different network devices (phone, tablet)

### 7.2 - Error handling & resilience

- Add user-visible error states in frontend (toast/banner when API unreachable)
- Add retry logic in `usePolling` for transient failures
- Handle stale data gracefully (show "last updated X ago" when polling fails)
- Add loading skeletons instead of blank states

### 7.3 - Sleep detection accuracy

- Tune eye/mouth/movement thresholds for different lighting conditions
- Test and improve blanket SVM model with more training samples
- Validate wake window calculations against actual baby schedule
- Add night mode handling (IR camera low-light frames)

### 7.4 - Notification reliability

- Test Pushover/Telegram delivery end-to-end
- Verify cooldown timers prevent notification spam
- Test notification toggle (Settings page) persists across restarts
- Add notification history page in frontend

### 7.5 - Data integrity

- Verify SQLite migrations from CSV work with large datasets
- Test diaper stats aggregation across timezone boundaries
- Validate weekly trends with gaps in data (days with no events)
- Add database backup strategy (periodic SQLite dump)

### 7.6 - Performance on RPi

- Profile CPU/memory usage with all threads running
- Optimize frame processing FPS vs detection accuracy tradeoff
- Test with multiple simultaneous frontend clients
- Measure Coral TPU inference latency vs MediaPipe fallback

---

## Build Order (Iteration Plan)

| Sprint | Focus | Effort | Status |
|--------|-------|--------|--------|
| **1** | Phase 0: Refactor main.py into modules, add SQLite | Medium | ✅ Done |
| **2** | Phase 1: Coral TPU integration (person detection + pose) | Medium | ✅ Done |
| **3** | Phase 2: Crying detection (audio extraction + YAMNet) | High | ✅ Done |
| **4** | Phase 3: Push notifications (Pushover + events) | Low | ✅ Done |
| **5** | Phase 4: Diaper tracking (API + frontend widget) | Low | ✅ Done |
| **6** | Phase 5: Enhanced sleep analytics + wake windows | Medium | ✅ Done |
| **7** | Phase 6: Frontend modernization (API layer + hooks) | Medium | ✅ Done |
| **8** | Phase 7: Testing & enhancement | Medium | 🔜 Next |

---

## Hardware Setup (RPi 4B + Coral)

```
┌─────────────────────────────────────────┐
│              Raspberry Pi 4B            │
│                                         │
│  ┌──────────┐  ┌──────────┐            │
│  │ RTSP Cam │──│ FFmpeg   │──> Video   │
│  │ (WiFi)   │  │ decoder  │   frames   │
│  └──────────┘  └──────────┘            │
│                      │                  │
│                      ├──> Audio PCM     │
│                      │    (16kHz mono)  │
│                      │                  │
│  ┌──────────┐  ┌─────v─────┐           │
│  │ Coral USB│──│ TFLite    │           │
│  │ Edge TPU │  │ Inference │           │
│  └──────────┘  │ - Pose    │           │
│                │ - Person  │           │
│                │ - Audio   │           │
│                └─────┬─────┘           │
│                      │                  │
│                ┌─────v─────┐           │
│                │ Flask API │──> SQLite  │
│                │ + Socket  │──> Notify  │
│                └─────┬─────┘           │
│                      │                  │
│                ┌─────v─────┐           │
│                │ React App │           │
│                │ :3000     │           │
│                └───────────┘           │
└─────────────────────────────────────────┘
```

---

## Key Dependencies to Add

```txt
# requirements.txt additions
pycoral~=2.0               # Coral Edge TPU runtime (RPi only)
tflite-runtime~=2.14       # TFLite without full TF (RPi only)
flask-socketio~=5.3        # WebSocket support
python-pushover~=0.4       # Push notifications
python-telegram-bot~=20.0  # Telegram bot
```

---

## Platform Notes

### Mac (Development)
- Coral Edge TPU USB works on macOS (install libedgetpu from coral.ai)
- MediaPipe works natively
- Use `VIDEO_PATH` env var to test with a recorded video file
- SQLite works everywhere

### Raspberry Pi 4B (Production)
- Install Edge TPU runtime from coral apt repo
- Use RTSP cameras over WiFi
- Consider USB microphone if RTSP camera lacks audio
- Use systemd service for auto-start
- Docker deployment recommended
