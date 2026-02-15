import csv
import json
import logging
import os
import sqlite3
from datetime import datetime

from backend.config import DB_PATH, SLEEP_LOGS_CSV

logger = logging.getLogger(__name__)

_connection = None


def get_connection():
    """Get or create the SQLite connection (singleton per process)."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _init_tables(_connection)
    return _connection


def _init_tables(conn):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sleep_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP,
            state TEXT CHECK(state IN ('asleep', 'awake')),
            confidence REAL,
            detection_reasons TEXT
        );

        CREATE TABLE IF NOT EXISTS cry_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP,
            intensity TEXT CHECK(intensity IN ('fussing', 'crying', 'screaming')),
            duration_seconds INTEGER
        );

        CREATE TABLE IF NOT EXISTS diaper_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            type TEXT CHECK(type IN ('wet', 'dirty', 'both', 'dry')),
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS feeding_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            type TEXT CHECK(type IN ('breast', 'bottle', 'solid')),
            duration_minutes INTEGER,
            amount_oz REAL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS notifications_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            event_type TEXT,
            channel TEXT,
            message TEXT,
            delivered BOOLEAN DEFAULT 0
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Sleep events
# ---------------------------------------------------------------------------

def log_sleep_event(state, confidence=None, reasons=None):
    """Log a sleep/wake state transition."""
    conn = get_connection()
    now = datetime.now().isoformat()
    reasons_json = json.dumps(reasons) if reasons else None
    conn.execute(
        "INSERT INTO sleep_events (start_time, state, confidence, detection_reasons) VALUES (?, ?, ?, ?)",
        (now, state, confidence, reasons_json),
    )
    conn.commit()


def get_sleep_events(since=None, limit=100):
    """Get recent sleep events."""
    conn = get_connection()
    if since:
        rows = conn.execute(
            "SELECT * FROM sleep_events WHERE start_time >= ? ORDER BY start_time DESC LIMIT ?",
            (since, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sleep_events ORDER BY start_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_last_sleep_event():
    """Get the most recent sleep event."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sleep_events ORDER BY start_time DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Cry events
# ---------------------------------------------------------------------------

def log_cry_start(intensity="crying"):
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO cry_events (start_time, intensity) VALUES (?, ?)",
        (now, intensity),
    )
    conn.commit()


def log_cry_end(duration_seconds):
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE cry_events SET end_time = ?, duration_seconds = ? WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1",
        (now, duration_seconds),
    )
    conn.commit()


def get_cry_events(since=None, limit=50):
    conn = get_connection()
    if since:
        rows = conn.execute(
            "SELECT * FROM cry_events WHERE start_time >= ? ORDER BY start_time DESC LIMIT ?",
            (since, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM cry_events ORDER BY start_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Diaper events
# ---------------------------------------------------------------------------

def log_diaper_event(diaper_type, notes=""):
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO diaper_events (timestamp, type, notes) VALUES (?, ?, ?)",
        (now, diaper_type, notes),
    )
    conn.commit()


def get_diaper_events(since=None, limit=50):
    conn = get_connection()
    if since:
        rows = conn.execute(
            "SELECT * FROM diaper_events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (since, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM diaper_events ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_diaper_stats(date_str=None):
    """Get diaper statistics for a given date (defaults to today)."""
    conn = get_connection()
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM diaper_events WHERE DATE(timestamp) = ?",
        (date_str,),
    ).fetchone()["cnt"]

    wet = conn.execute(
        "SELECT COUNT(*) as cnt FROM diaper_events WHERE type IN ('wet', 'both') AND DATE(timestamp) = ?",
        (date_str,),
    ).fetchone()["cnt"]

    dirty = conn.execute(
        "SELECT COUNT(*) as cnt FROM diaper_events WHERE type IN ('dirty', 'both') AND DATE(timestamp) = ?",
        (date_str,),
    ).fetchone()["cnt"]

    last = conn.execute(
        "SELECT * FROM diaper_events ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()

    daily_avg_7d = conn.execute(
        "SELECT COUNT(*) / 7.0 as avg FROM diaper_events WHERE DATE(timestamp) >= DATE('now', '-7 days')"
    ).fetchone()["avg"]

    return {
        "date": date_str,
        "total": total,
        "wet": wet,
        "dirty": dirty,
        "daily_average_7d": round(daily_avg_7d, 1),
        "last_change": dict(last) if last else None,
    }


# ---------------------------------------------------------------------------
# Feeding events
# ---------------------------------------------------------------------------

def log_feeding_event(feeding_type, duration_minutes=None, amount_oz=None, notes=""):
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO feeding_events (timestamp, type, duration_minutes, amount_oz, notes) VALUES (?, ?, ?, ?, ?)",
        (now, feeding_type, duration_minutes, amount_oz, notes),
    )
    conn.commit()


def get_feeding_events(since=None, limit=50):
    conn = get_connection()
    if since:
        rows = conn.execute(
            "SELECT * FROM feeding_events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (since, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM feeding_events ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Notifications log
# ---------------------------------------------------------------------------

def log_notification(event_type, channel, message, delivered=True):
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO notifications_log (timestamp, event_type, channel, message, delivered) VALUES (?, ?, ?, ?, ?)",
        (now, event_type, channel, message, delivered),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# CSV Legacy support
# ---------------------------------------------------------------------------

def write_sleep_csv(is_awake, timestamp):
    """Write to the legacy CSV file for backward compatibility with the frontend."""
    state = "1" if is_awake else "0"
    log_string = f"{state},{timestamp}\n"
    with open(SLEEP_LOGS_CSV, "a+", encoding="utf-8") as f:
        f.write(log_string)


def migrate_csv_to_sqlite():
    """One-time migration of existing sleep_logs.csv into SQLite."""
    if not os.path.exists(SLEEP_LOGS_CSV):
        return

    conn = get_connection()
    existing = conn.execute("SELECT COUNT(*) as cnt FROM sleep_events").fetchone()["cnt"]
    if existing > 0:
        return  # already migrated

    with open(SLEEP_LOGS_CSV, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            state = "awake" if row[0].strip() == "1" else "asleep"
            try:
                ts = datetime.fromtimestamp(int(row[1].strip())).isoformat()
            except (ValueError, OSError):
                continue
            conn.execute(
                "INSERT INTO sleep_events (start_time, state) VALUES (?, ?)",
                (ts, state),
            )
    conn.commit()
    logger.info("Migrated CSV sleep logs to SQLite (%s)", DB_PATH)
