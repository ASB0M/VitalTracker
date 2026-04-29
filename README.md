# VitalTracker

## Project Overview

VitalTracker is an end-to-end IoT patient monitoring system that captures real-time heart rate (HR) and blood oxygen saturation (SpO2) readings from a MAX30102 pulse oximeter sensor via an ESP32 microcontroller, streams them over MQTT to a fog computing layer, stores them in a local SQLite database, and runs real-time anomaly detection using an LSTM Autoencoder trained on the PhysioNet BIDMC PPG and Respiration Dataset.

The system detects abnormal vital sign patterns — including bradycardia, hypoxia, and combined anomalies — by comparing the reconstruction error of incoming vitals windows against a threshold derived from training data. Detected anomalies are classified by severity (normal, medium, high) and logged to the database. A live Streamlit dashboard provides real-time visualisation of vitals, anomaly scores, and alert history.

**Primary use cases:**

- Continuous ICU patient monitoring with automated anomaly alerting.
- Research and prototyping of edge-fog architectures for physiological signal processing.
- Educational reference for IoT + ML pipeline integration.

## Architecture & Methodology

The system follows a three-tier edge-fog architecture:

```
┌────────────────────┐       MQTT        ┌────────────────────────────────────┐
│   EDGE LAYER       │ ───────────────►  │          FOG LAYER                 │
│   (ESP32 + MAX30102)│   broker.hivemq  │                                    │
│                    │      .com:1883    │  ┌──────────────┐                  │
│  - Sensor sampling │                  │  │ mqtt_sub-    │  ── SQLite ──►   │
│  - SpO2 algorithm  │                  │  │ scriber.py   │   patient_       │
│  - Beat detection  │                  │  └──────────────┘   vitals.db      │
│  - JSON publish    │                  │                        │            │
└────────────────────┘                  │  ┌──────────────┐      │            │
                                        │  │ anomaly_     │ ◄────┘            │
                                        │  │ detector.py  │                   │
                                        │  └──────────────┘                   │
                                        │         │                           │
                                        │         ▼                           │
                                        │  ┌──────────────┐                   │
                                        │  │ dashboard/   │                   │
                                        │  │ app.py       │  (Streamlit)      │
                                        │  └──────────────┘                   │
                                        └────────────────────────────────────┘
```

### Edge Layer (`edge/`)

- **Hardware:** ESP32 microcontroller + MAX30102 pulse oximeter (I2C, GPIO 21/22).
- **Firmware:** Arduino C++ (`patient_monitor.ino`).
- **Protocol:** MQTT via PubSubClient. JSON payloads published to `vitals/patient01`.
- **Algorithm:** SparkFun `maxim_heart_rate_and_oxygen_saturation()` over 100-sample buffers. Rolling beat-average (window of 4) for real-time HR. Finger detection via IR threshold (>50,000).

### Fog Layer (`fog/`)

- **Ingestion** (`fog/ingestion/mqtt_subscriber.py`): Paho MQTT v5 subscriber. Physiological validation (HR: 30–220 bpm, SpO2: 70–100%). All readings stored to SQLite with validity and sanity flags.
- **Inference** (`fog/model/inference.py`): Loads the LSTM Autoencoder and MinMaxScaler. Fetches the latest 60-reading valid window from SQLite, normalises, and computes reconstruction error (MSE).
- **Anomaly Detection** (`fog/model/anomaly_detector.py`): Polls every 5 seconds. Classifies anomaly severity based on p95 (medium) and p99 (high) thresholds from training error distribution. Writes alerts to `anomaly_alerts` table.
- **Dashboard** (`fog/dashboard/app.py`): Streamlit app with 5-second auto-refresh. Displays live vitals cards with clinical labels, HR/SpO2 time-series charts with threshold bands, anomaly score chart, and alert log.

### ML Pipeline (`notebooks/`)

Executed offline. Four sequential notebooks:

1. **EDA** — Dataset exploration (53 ICU patients, ~25,500 readings at 1 Hz).
2. **Preprocessing** — Missing value handling, MinMaxScaler normalisation (fit on train only), patient-level train/test split (42/10), sliding window creation (size 60, step 1).
3. **Model Training** — Symmetric LSTM Autoencoder (64→32 encoder, 32→64 decoder). EarlyStopping + ModelCheckpoint. Best validation loss: `0.00168`. Threshold (p95): `0.00277`.
4. **Model Evaluation** — Synthetic anomaly injection. Results: Precision `0.334`, Recall `1.0`, F1 `0.501`, ROC-AUC `1.0`.

### Data

- **Source:** [PhysioNet BIDMC PPG and Respiration Dataset](https://physionet.org/content/bidmc/1.0.0/) — 53 ICU patients, 8-minute recordings each.
- **Compilation:** `scripts/compile_bidmc.py` merges 53 individual CSVs into a single file.
- **Runtime DB:** `data/patient_vitals.db` (SQLite) — populated by `mqtt_subscriber.py`.

## Setup & Installation

### Prerequisites

- Python 3.10+
- Arduino IDE (for ESP32 firmware flashing)
- An ESP32 development board with a MAX30102 sensor module

### 1. Clone the repository

```bash
git clone https://github.com/your-username/VitalTracker.git
cd VitalTracker
```

### 2. Create a Python virtual environment and install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Download the BIDMC dataset

Download the 53 `*_Numerics.csv` files from [PhysioNet BIDMC](https://physionet.org/content/bidmc/1.0.0/) and place them in `data/raw/bidmc/`.

### 4. Compile the raw data

```bash
python scripts/compile_bidmc.py
```

### 5. Run the ML pipeline notebooks

Open and execute the notebooks in order:

```bash
jupyter notebook notebooks/
```

1. `1-EDA.ipynb`
2. `2-Preprocessing.ipynb`
3. `3-Model_Training.ipynb`
4. `4-Model_Evaluation.ipynb`

After completion, trained model artifacts will be in `models/lstm_autoencoder/`.

### 6. Flash the ESP32 firmware

1. Open `edge/patient_monitor/patient_monitor.ino` in the Arduino IDE.
2. Install the required libraries via Library Manager:
   - `PubSubClient`
   - `SparkFun MAX3010x`
   - `ArduinoJson`
3. Update `WIFI_SSID` and `WIFI_PASSWORD` to match your network.
4. Flash to the ESP32 board.

### 7. Start the fog layer services

In separate terminals:

```bash
# Terminal 1 — MQTT Ingestion
python fog/ingestion/mqtt_subscriber.py

# Terminal 2 — Anomaly Detection
python fog/model/anomaly_detector.py

# Terminal 3 — Dashboard
streamlit run fog/dashboard/app.py
```

## Usage

### Monitoring vitals

Once all three fog services are running and the ESP32 is powered on with a finger on the sensor, the Streamlit dashboard (default: `http://localhost:8501`) will display:

- **Live vitals cards:** Current HR, SpO2, and last reading timestamp with clinical status indicators.
- **Time-series charts:** Rolling HR and SpO2 plots with normal/abnormal threshold bands.
- **Anomaly score chart:** Reconstruction error per inference window with p95/p99 threshold lines.
- **Alert log:** Table of detected anomaly events with severity, score, HR, and SpO2 at detection time.

### Inspecting the database

```bash
python fog/ingestion/db_viewer.py       # Last 20 readings
python fog/ingestion/db_viewer.py 100   # Last 100 readings
```

### Retraining the model

Re-run notebooks `2-Preprocessing.ipynb` through `4-Model_Evaluation.ipynb`. Updated artifacts will be saved to `models/lstm_autoencoder/` and automatically picked up by the inference service on next restart.

## License

MIT License. See [LICENSE](LICENSE) for details.
