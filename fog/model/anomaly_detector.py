# ================================================================
#  fog/model/anomaly_detector.py
#  Compares reconstruction error against threshold and writes
#  alerts to the anomaly_alerts table in SQLite.
#  Also runs as a standalone background loop.
# ================================================================

import os
import sqlite3
import json
import time
import logging
from datetime import datetime, timezone
from inference import load_model_and_scaler, run_inference

# ── Config ────────────────────────────────────────────────────
BASE_PATH   = r'C:\Users\Saqib\OneDrive\Desktop\VitalTracker'
MODEL_PATH  = os.path.join(BASE_PATH, 'models', 'lstm_autoencoder')
DB_PATH = r'C:\Users\Saqib\OneDrive\Desktop\VitalTracker\data\patient_vitals.db'
POLL_EVERY  = 5     # seconds between inference passes

# Load threshold from config.json
config_path = os.path.join(MODEL_PATH, 'config.json')
with open(config_path) as f:
    config = json.load(f)

THRESHOLD   = config['anomaly_threshold']
P99         = config['train_error_stats']['p99']

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.INFO,
    format  = '%(asctime)s  [%(levelname)s]  %(message)s',
    datefmt = '%H:%M:%S',
    handlers= [
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(BASE_PATH, 'fog', 'anomaly_detector.log'))
    ]
)
log = logging.getLogger(__name__)


def get_severity(score):
    """
    Maps reconstruction error to severity level.
    p95 → medium, p99 → high
    """
    if score >= P99:
        return 'high'
    elif score >= THRESHOLD:
        return 'medium'
    return 'normal'


def write_alert(conn, vitals_id, score, severity):
    """Writes an anomaly alert to the database."""
    detected_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO anomaly_alerts (detected_at, vitals_id, anomaly_score, severity)
        VALUES (?, ?, ?, ?)
    """, (detected_at, vitals_id, score, severity))
    conn.commit()


def alert_already_exists(conn, vitals_id):
    """Prevent duplicate alerts for the same reading."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM anomaly_alerts WHERE vitals_id = ?", (vitals_id,)
    )
    return cursor.fetchone() is not None


def run_loop():
    """Main detection loop — runs until interrupted."""
    log.info('=' * 50)
    log.info('  Anomaly Detector — Starting')
    log.info(f'  Threshold  : {THRESHOLD:.6f} (medium)')
    log.info(f'  P99        : {P99:.6f} (high)')
    log.info(f'  Poll every : {POLL_EVERY}s')
    log.info('=' * 50)

    log.info('Loading model and scaler...')
    model, scaler = load_model_and_scaler()
    log.info('Model ready.\n')

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)

    try:
        while True:
            result = run_inference(model, scaler, conn)

            if result is None:
                log.info('Waiting for enough data (need 60 valid readings)...')
            else:
                vitals_id, score = result
                severity = get_severity(score)

                if severity != 'normal':
                    if not alert_already_exists(conn, vitals_id):
                        write_alert(conn, vitals_id, score, severity)
                        log.warning(
                            f'ALERT [{severity.upper()}] '
                            f'vitals_id={vitals_id} '
                            f'score={score:.6f}'
                        )
                    else:
                        log.info(f'Score={score:.6f} [{severity}] — alert already logged')
                else:
                    log.info(f'Score={score:.6f} [normal]')

            time.sleep(POLL_EVERY)

    except KeyboardInterrupt:
        log.info('Detector stopped.')
        conn.close()


if __name__ == '__main__':
    run_loop()