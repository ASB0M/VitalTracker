# ================================================================
#  DB VIEWER — Quick utility to inspect collected vitals
#  Run this in a separate terminal while mqtt_subscriber.py runs
#
#  Usage:
#    python db_viewer.py          # shows last 20 readings
#    python db_viewer.py 50       # shows last 50 readings
# ================================================================

import sqlite3
import sys
from datetime import datetime

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "..", "data", "patient_vitals.db")
LIMIT   = int(sys.argv[1]) if len(sys.argv) > 1 else 20

conn   = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT received_at, heart_rate, spo2, hr_valid, spo2_valid, passed_sanity
    FROM vitals
    ORDER BY id DESC
    LIMIT ?
""", (LIMIT,))

rows = cursor.fetchall()
conn.close()

if not rows:
    print("No data yet. Is mqtt_subscriber.py running?")
else:
    print(f"\n{'Timestamp':<28} {'HR (bpm)':<12} {'SpO2 (%)':<12} {'Sane?'}")
    print("-" * 65)
    for row in reversed(rows):
        ts, hr, spo2, hr_v, spo2_v, sane = row
        hr_str   = str(hr)   if hr_v   else "-"
        spo2_str = str(spo2) if spo2_v else "-"
        sane_str = "Yes" if sane else "No"
        print(f"{ts:<28} {hr_str:<12} {spo2_str:<12} {sane_str}")

    print(f"\n  Showing {len(rows)} of latest records from {DB_PATH}")