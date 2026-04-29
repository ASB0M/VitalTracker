# ================================================================
#  fog/dashboard/app.py
#  Streamlit dashboard for VitalTracker.
#  Reads live data from SQLite and auto-refreshes every 5 seconds.
#
#  RUN:
#    pip install streamlit plotly
#    streamlit run app.py
# ================================================================

import os
import sqlite3
import json
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# ── Config ────────────────────────────────────────────────────
BASE_PATH  = r'C:\Users\Saqib\OneDrive\Desktop\VitalTracker'
DB_PATH = r'C:\Users\Saqib\OneDrive\Desktop\VitalTracker\data\patient_vitals.db'
MODEL_PATH = os.path.join(BASE_PATH, 'models', 'lstm_autoencoder')

config_path = os.path.join(MODEL_PATH, 'config.json')
with open(config_path) as f:
    config = json.load(f)

THRESHOLD = config['anomaly_threshold']
P99       = config['train_error_stats']['p99']
HISTORY_N = 200    # number of recent readings to show in charts

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title = 'VitalTracker',
    page_icon  = '🫀',
    layout     = 'wide',
)

# Auto-refresh every 5 seconds
st_autorefresh(interval=5000, key='autorefresh')

# ── DB helpers ────────────────────────────────────────────────
# Remove the cached connection function entirely and replace with this
def get_connection():
    return sqlite3.connect(
        r'C:\Users\Saqib\OneDrive\Desktop\VitalTracker\data\patient_vitals.db',
        check_same_thread=False
    )

def fetch_vitals(conn, n=HISTORY_N):
    return pd.read_sql_query(f"""
        SELECT id, received_at, heart_rate, spo2, passed_sanity
        FROM vitals
        WHERE hr_valid = 1 AND spo2_valid = 1
          AND heart_rate IS NOT NULL AND spo2 IS NOT NULL
        ORDER BY id DESC
        LIMIT {n}
    """, conn).iloc[::-1].reset_index(drop=True)

def fetch_alerts(conn, n=50):
    return pd.read_sql_query(f"""
        SELECT a.detected_at, a.anomaly_score, a.severity,
               v.heart_rate, v.spo2
        FROM anomaly_alerts a
        LEFT JOIN vitals v ON a.vitals_id = v.id
        ORDER BY a.id DESC
        LIMIT {n}
    """, conn)

def fetch_latest(conn):
    row = pd.read_sql_query("""
        SELECT heart_rate, spo2, received_at
        FROM vitals
        WHERE hr_valid=1 AND spo2_valid=1
          AND heart_rate IS NOT NULL AND spo2 IS NOT NULL
        ORDER BY id DESC LIMIT 1
    """, conn)
    return row.iloc[0] if len(row) else None

# ── Colour helpers ────────────────────────────────────────────
def hr_status(hr):
    if hr is None: return '⚪', 'No data'
    if hr < 60:    return '🔵', 'Bradycardia'
    if hr > 100:   return '🔴', 'Tachycardia'
    return '🟢', 'Normal'

def spo2_status(spo2):
    if spo2 is None:  return '⚪', 'No data'
    if spo2 < 90:     return '🔴', 'Critical'
    if spo2 < 95:     return '🟠', 'Low'
    return '🟢', 'Normal'

def severity_badge(sev):
    return {'high': '🔴 HIGH', 'medium': '🟠 MEDIUM', 'normal': '🟢 NORMAL'}.get(sev, sev)

# ── Layout ────────────────────────────────────────────────────
conn = get_connection()

st.title('🫀 VitalTracker — Patient Monitor')
st.caption(f'Anomaly threshold: {THRESHOLD:.6f} (p95) | Auto-refreshes every 5s')
st.divider()

# ── Row 1: Live vitals cards ──────────────────────────────────
latest = fetch_latest(conn)
col1, col2, col3 = st.columns(3)

if latest is not None:
    hr    = latest['heart_rate']
    spo2  = latest['spo2']
    ts    = latest['received_at']

    hr_icon,   hr_label   = hr_status(hr)
    spo2_icon, spo2_label = spo2_status(spo2)

    with col1:
        st.metric(
            label = f'{hr_icon} Heart Rate',
            value = f'{int(hr)} bpm',
            delta = hr_label
        )
    with col2:
        st.metric(
            label = f'{spo2_icon} SpO2',
            value = f'{int(spo2)} %',
            delta = spo2_label
        )
    with col3:
        st.metric(
            label = '🕐 Last Reading',
            value = ts[11:19] if ts else '—'    # show HH:MM:SS
        )
else:
    st.warning('No valid readings yet. Is the ESP32 and MQTT subscriber running?')

st.divider()

# ── Row 2: Time series charts ─────────────────────────────────
vitals_df = fetch_vitals(conn)

if len(vitals_df) > 1:
    col_hr, col_spo2 = st.columns(2)

    with col_hr:
        fig_hr = go.Figure()
        fig_hr.add_trace(go.Scatter(
            x=vitals_df['received_at'], y=vitals_df['heart_rate'],
            mode='lines', name='HR',
            line=dict(color='#E05252', width=1.5)
        ))
        fig_hr.add_hrect(y0=0,   y1=60,  fillcolor='#4A90D9', opacity=0.08, line_width=0)
        fig_hr.add_hrect(y0=100, y1=220, fillcolor='#E05252', opacity=0.08, line_width=0)
        fig_hr.add_hline(y=60,  line_dash='dot', line_color='#4A90D9', opacity=0.5)
        fig_hr.add_hline(y=100, line_dash='dot', line_color='#E05252', opacity=0.5)
        fig_hr.update_layout(
            title='Heart Rate (bpm)',
            height=280, margin=dict(l=10,r=10,t=40,b=10),
            xaxis_title=None, yaxis_title='bpm',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        st.plotly_chart(fig_hr, use_container_width=True)

    with col_spo2:
        fig_spo2 = go.Figure()
        fig_spo2.add_trace(go.Scatter(
            x=vitals_df['received_at'], y=vitals_df['spo2'],
            mode='lines', name='SpO2',
            line=dict(color='#3DBE7A', width=1.5)
        ))
        fig_spo2.add_hrect(y0=0,  y1=90, fillcolor='#E05252', opacity=0.08, line_width=0)
        fig_spo2.add_hrect(y0=90, y1=95, fillcolor='#F5A623', opacity=0.08, line_width=0)
        fig_spo2.add_hline(y=95, line_dash='dot', line_color='#F5A623', opacity=0.5)
        fig_spo2.add_hline(y=90, line_dash='dot', line_color='#E05252', opacity=0.5)
        fig_spo2.update_layout(
            title='SpO2 (%)',
            height=280, margin=dict(l=10,r=10,t=40,b=10),
            xaxis_title=None, yaxis_title='%',
            yaxis_range=[80, 101],
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        st.plotly_chart(fig_spo2, use_container_width=True)
else:
    st.info('Collecting readings — charts will appear once data starts flowing.')

st.divider()

# ── Row 3: Anomaly score chart ────────────────────────────────
st.subheader('📈 Anomaly Score')

alerts_df = fetch_alerts(conn, n=200)

if len(alerts_df) > 0:
    fig_score = go.Figure()

    fig_score.add_trace(go.Scatter(
        x=alerts_df['detected_at'], y=alerts_df['anomaly_score'],
        mode='lines+markers', name='Anomaly Score',
        line=dict(color='#7B68EE', width=1.5),
        marker=dict(size=4)
    ))
    fig_score.add_hline(
        y=THRESHOLD, line_dash='dash', line_color='orange',
        annotation_text=f'p95 threshold ({THRESHOLD:.5f})',
        annotation_position='top left'
    )
    fig_score.add_hline(
        y=P99, line_dash='dash', line_color='red',
        annotation_text=f'p99 ({P99:.5f})',
        annotation_position='top left'
    )
    fig_score.update_layout(
        height=250, margin=dict(l=10,r=10,t=20,b=10),
        xaxis_title=None, yaxis_title='MSE',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
    )
    st.plotly_chart(fig_score, use_container_width=True)
else:
    st.info('No anomaly scores yet. Start anomaly_detector.py to begin scoring.')

st.divider()

# ── Row 4: Alert log ──────────────────────────────────────────
st.subheader('🚨 Alert Log')

alert_display = fetch_alerts(conn, n=20)

if len(alert_display) > 0:
    alert_display['severity'] = alert_display['severity'].apply(severity_badge)
    alert_display.columns     = ['Time', 'Score', 'Severity', 'HR (bpm)', 'SpO2 (%)']
    alert_display['Score']    = alert_display['Score'].round(6)
    alert_display['Time']     = alert_display['Time'].str[11:19]
    st.dataframe(alert_display, use_container_width=True, hide_index=True)
else:
    st.success('No alerts. Patient vitals are within normal range.')

# ── Footer ────────────────────────────────────────────────────
st.divider()
total = pd.read_sql_query("SELECT COUNT(*) as n FROM vitals", conn).iloc[0]['n']
n_alerts = pd.read_sql_query("SELECT COUNT(*) as n FROM anomaly_alerts", conn).iloc[0]['n']
st.caption(f'Total readings in DB: {int(total):,}  |  Total alerts: {int(n_alerts)}  |  Model: LSTM Autoencoder trained on PhysioNet BIDMC')