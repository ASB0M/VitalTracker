# `data/` — Datasets and Databases

## Purpose

Central data directory. Stores raw source datasets, processed ML-ready arrays, and the runtime SQLite database used by the fog layer services.

## Contents

### `raw/bidmc/`

- 53 individual patient CSV files (`bidmc_01_Numerics.csv` through `bidmc_53_Numerics.csv`) from the [PhysioNet BIDMC PPG and Respiration Dataset](https://physionet.org/content/bidmc/1.0.0/).
- `bidmc_compiled_numerics.csv` — Consolidated file produced by `scripts/compile_bidmc.py`. Contains columns: `Time`, `HR`, `SpO2`, `patient_id`.

### `processed/`

ML-ready artifacts produced by `notebooks/2-Preprocessing.ipynb`:

- `X_train.npy` — Training windows. Shape: `(N_train, 60, 2)`.
- `X_test.npy` — Test windows. Shape: `(N_test, 60, 2)`.
- `train_errors.npy` — Per-window reconstruction errors for the training set (computed during training).
- `test_errors.npy` — Per-window reconstruction errors for the test set (computed during evaluation).
- `test_meta.csv` — Metadata for test windows (patient IDs, timestamps).

### `patient_vitals.db`

SQLite database populated at runtime by `fog/ingestion/mqtt_subscriber.py`. Contains two tables:

- `vitals` — All ingested readings with columns: `id`, `received_at`, `device_id`, `device_ts_ms`, `heart_rate`, `spo2`, `hr_valid`, `spo2_valid`, `passed_sanity`.
- `anomaly_alerts` — Alert records written by `fog/model/anomaly_detector.py` with columns: `id`, `detected_at`, `vitals_id` (FK), `anomaly_score`, `severity`.

> **Note:** `data/raw/`, `data/processed/`, and database files are listed in `.gitignore` and are not tracked in version control.
