# ================================================================
#  FOG LAYER — MQTT Subscriber + SQLite Ingestion
#  Connects to HiveMQ Public Broker, receives patient vitals
#  from ESP32, validates them, and stores to a local SQLite DB.
#
#  INSTALL DEPENDENCIES:
#    pip install paho-mqtt
#
#  RUN:
#    python mqtt_subscriber.py
# ================================================================

import paho.mqtt.client as mqtt
import sqlite3
import json
import time
import logging
from datetime import datetime, timezone

# ================================================================
#  SECTION 1 — CONFIGURATION
# ================================================================

# --- HiveMQ Public Broker ---
BROKER_HOST     = "broker.hivemq.com"
BROKER_PORT     = 1883
CLIENT_ID       = "fog_layer_subscriber"          # must be different from ESP32 client ID
TOPIC_VITALS    = "vitals/patient01"
TOPIC_STATUS    = "status/patient01"
KEEPALIVE       = 60

# --- SQLite ---
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "..", "data", "patient_vitals.db")

# --- Validation thresholds (physiological sanity check) ---
HR_MIN          = 30                              # bpm — below this is sensor noise
HR_MAX          = 220                             # bpm — above this is sensor noise
SPO2_MIN        = 70                              # % — below 70 is almost certainly bad reading
SPO2_MAX        = 100                             # %

# ================================================================
#  SECTION 2 — LOGGING SETUP
# ================================================================

logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt  = "%H:%M:%S",
    handlers = [
        logging.StreamHandler(),                  # print to console
        logging.FileHandler("ingestion.log"),     # also save to log file
    ]
)
log = logging.getLogger(__name__)

# ================================================================
#  SECTION 3 — DATABASE SETUP
# ================================================================

def init_db():
    """
    Creates the SQLite database and tables if they don't exist.
    Called once at startup.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Main vitals table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vitals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at     TEXT    NOT NULL,         -- ISO timestamp (UTC) when fog received it
            device_id       TEXT    NOT NULL,         -- ESP32 client ID
            device_ts_ms    INTEGER,                  -- millis() from ESP32 (for drift analysis)
            heart_rate      INTEGER,                  -- BPM, NULL if invalid
            spo2            INTEGER,                  -- %, NULL if invalid
            hr_valid        INTEGER NOT NULL,         -- 1 = valid, 0 = invalid
            spo2_valid      INTEGER NOT NULL,
            passed_sanity   INTEGER NOT NULL          -- 1 = passed our own threshold check
        )
    """)

    # Anomaly alerts table (will be populated later by the model)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_at     TEXT    NOT NULL,
            vitals_id       INTEGER,                  -- FK to vitals table
            anomaly_score   REAL,
            severity        TEXT,                     -- 'low', 'medium', 'high'
            FOREIGN KEY (vitals_id) REFERENCES vitals(id)
        )
    """)

    conn.commit()
    conn.close()
    log.info(f"Database initialised at: {DB_PATH}")

# ================================================================
#  SECTION 4 — DATA VALIDATION
# ================================================================

def validate_reading(hr, spo2, hr_valid, spo2_valid):
    """
    Applies physiological sanity checks on top of the ESP32's own
    validity flags. Returns True only if values are within range.
    Even if ESP32 says valid, extreme values indicate sensor noise.
    """
    if hr_valid and hr is not None:
        if not (HR_MIN <= hr <= HR_MAX):
            log.warning(f"HR {hr} bpm outside sanity range [{HR_MIN}-{HR_MAX}] — rejected")
            return False

    if spo2_valid and spo2 is not None:
        if not (SPO2_MIN <= spo2 <= SPO2_MAX):
            log.warning(f"SpO2 {spo2}% outside sanity range [{SPO2_MIN}-{SPO2_MAX}] — rejected")
            return False

    return True

# ================================================================
#  SECTION 5 — DATABASE WRITE
# ================================================================

def store_reading(payload: dict, passed_sanity: bool):
    """
    Writes a single validated reading to SQLite.
    Even failed sanity checks are stored (with passed_sanity=0)
    so we have a complete record for model analysis later.
    """
    received_at = datetime.now(timezone.utc).isoformat()

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO vitals (
                received_at, device_id, device_ts_ms,
                heart_rate, spo2,
                hr_valid, spo2_valid, passed_sanity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            received_at,
            payload.get("device_id", "unknown"),
            payload.get("timestamp_ms"),
            payload.get("heart_rate"),
            payload.get("spo2"),
            1 if payload.get("hr_valid") else 0,
            1 if payload.get("spo2_valid") else 0,
            1 if passed_sanity else 0,
        ))

        conn.commit()
        conn.close()
        return True

    except sqlite3.Error as e:
        log.error(f"Database write failed: {e}")
        return False

# ================================================================
#  SECTION 6 — MQTT CALLBACKS
# ================================================================

def on_connect(client, userdata, flags, rc, properties=None):
    rc_value = getattr(rc, 'value', rc)
    rc_codes = {
        0: "Connected successfully",
        1: "Bad protocol version",
        2: "Client ID rejected",
        3: "Broker unavailable",
        4: "Bad credentials",
        5: "Not authorised",
    }
    message = rc_codes.get(rc_value, f"Unknown error (rc={rc_value})")

    if rc_value == 0:
        log.info(f"[MQTT] {message}")
        # Subscribe to topics after successful connect
        client.subscribe(TOPIC_VITALS, qos=1)
        client.subscribe(TOPIC_STATUS, qos=0)
        log.info(f"[MQTT] Subscribed to: {TOPIC_VITALS}")
    else:
        log.error(f"[MQTT] Connection failed — {message}")


def on_disconnect(client, userdata, rc, properties=None):
    rc_value = getattr(rc, 'value', rc)
    if rc_value != 0:
        log.warning(f"[MQTT] Unexpected disconnect (rc={rc_value}). Will auto-reconnect...")


def on_message(client, userdata, msg):
    topic   = msg.topic
    raw     = msg.payload.decode("utf-8", errors="replace")

    # ── Status messages ────────────────────────────────────────
    if topic == TOPIC_STATUS:
        log.info(f"[STATUS] Device is: {raw}")
        return

    # ── Vitals messages ────────────────────────────────────────
    if topic == TOPIC_VITALS:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error(f"[PARSE] Bad JSON received: {raw[:80]} — {e}")
            return

        # Extract fields
        hr         = payload.get("heart_rate")
        spo2       = payload.get("spo2")
        hr_valid   = bool(payload.get("hr_valid", False))
        spo2_valid = bool(payload.get("spo2_valid", False))

        # Validate
        passed = validate_reading(hr, spo2, hr_valid, spo2_valid)

        # Store regardless (passed_sanity flag tells us which to trust)
        stored = store_reading(payload, passed)

        # Console summary
        hr_str   = f"{hr} bpm"   if (hr_valid and hr is not None)   else "invalid"
        spo2_str = f"{spo2}%"    if (spo2_valid and spo2 is not None) else "invalid"
        status   = "✓ stored" if stored else "✗ DB error"
        sanity   = "✓ sane"   if passed  else "⚠ out of range"

        log.info(
            f"[VITALS] HR: {hr_str:<12} SpO2: {spo2_str:<8} "
            f"| {sanity:<16} | {status}"
        )

# ================================================================
#  SECTION 7 — MAIN
# ================================================================

def main():
    log.info("=" * 55)
    log.info("  Vital Monitor — Fog Ingestion Service")
    log.info("=" * 55)

    # Init DB
    init_db()

    # Setup MQTT client
    client = mqtt.Client(
        client_id          = CLIENT_ID,
        protocol           = mqtt.MQTTv5,
        callback_api_version = mqtt.CallbackAPIVersion.VERSION2,
    )

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    # Enable auto-reconnect
    client.reconnect_delay_set(min_delay=2, max_delay=30)

    # Connect
    log.info(f"[MQTT] Connecting to {BROKER_HOST}:{BROKER_PORT}...")
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=KEEPALIVE)
    except Exception as e:
        log.critical(f"[MQTT] Could not reach broker: {e}")
        return

    log.info("[System] Listening for data... (Ctrl+C to stop)\n")

    try:
        client.loop_forever()          # blocking — handles reconnects automatically
    except KeyboardInterrupt:
        log.info("\n[System] Shutting down gracefully...")
        client.disconnect()


if __name__ == "__main__":
    main()