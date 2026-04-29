# ================================================================
#  fog/model/inference.py
#  Loads the trained LSTM Autoencoder and scaler, reads the latest
#  unscored windows from SQLite, computes reconstruction error,
#  and passes results to anomaly_detector.py
# ================================================================

import os
import sqlite3
import pickle
import numpy as np
import tensorflow as tf
from datetime import datetime, timezone

# Silence TF logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
tf.config.set_visible_devices([], 'GPU')

BASE_PATH    = r'C:\Users\Saqib\OneDrive\Desktop\VitalTracker'
MODEL_PATH   = os.path.join(BASE_PATH, 'models', 'lstm_autoencoder')
DB_PATH = r'C:\Users\Saqib\OneDrive\Desktop\VitalTracker\data\patient_vitals.db'

WINDOW_SIZE  = 60      # must match preprocessingS
FEATURES     = ['heart_rate', 'spo2']
BATCH_SIZE   = 32


def load_model_and_scaler():
    model_file  = os.path.join(MODEL_PATH, 'model.keras')
    scaler_file = os.path.join(MODEL_PATH, 'scaler.pkl')

    if not os.path.exists(model_file):
        raise FileNotFoundError(f'Model not found: {model_file}')
    if not os.path.exists(scaler_file):
        raise FileNotFoundError(f'Scaler not found: {scaler_file}')

    model  = tf.keras.models.load_model(model_file)
    with open(scaler_file, 'rb') as f:
        scaler = pickle.load(f)

    return model, scaler


def fetch_latest_window(conn, n=WINDOW_SIZE):
    """
    Fetches the latest N valid readings from SQLite.
    Returns a list of (id, heart_rate, spo2) or None if not enough data.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, heart_rate, spo2
        FROM vitals
        WHERE passed_sanity = 1
          AND hr_valid = 1
          AND spo2_valid = 1
          AND heart_rate IS NOT NULL
          AND spo2 IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
    """, (n,))
    rows = cursor.fetchall()

    if len(rows) < n:
        return None   # not enough data yet

    return list(reversed(rows))   # oldest → newest


def compute_reconstruction_error(model, scaler, window_rows):
    """
    Takes a list of (id, hr, spo2) tuples, normalises, runs through model,
    returns (last_vitals_id, reconstruction_error).
    """
    ids  = [r[0] for r in window_rows]
    vals = np.array([[r[1], r[2]] for r in window_rows], dtype=np.float32)

    # Normalise using the same scaler from training
    vals_scaled = scaler.transform(vals)

    # Shape: (1, WINDOW_SIZE, 2)
    X = vals_scaled.reshape(1, WINDOW_SIZE, 2)

    # Reconstruct
    X_pred = model.predict(X, verbose=0)

    # MSE over timesteps and features
    error = float(np.mean(np.square(X - X_pred)))

    return ids[-1], error   # return id of most recent reading + error


def run_inference(model, scaler, conn):
    """
    Single inference pass. Returns (vitals_id, score) or None.
    """
    window = fetch_latest_window(conn)
    if window is None:
        return None

    vitals_id, score = compute_reconstruction_error(model, scaler, window)
    return vitals_id, score