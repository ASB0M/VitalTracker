# `notebooks/` — Jupyter Notebooks

## Purpose

Contains the ordered sequence of Jupyter notebooks that implement the offline machine learning pipeline: data exploration, preprocessing, model training, and model evaluation. All notebooks operate on the PhysioNet BIDMC PPG and Respiration Dataset.

## Key Files

- **`1-EDA.ipynb`** — Exploratory Data Analysis.
  - Loads the compiled BIDMC dataset (`data/raw/bidmc/bidmc_compiled_numerics.csv`).
  - Reports dataset dimensions (25,493 rows × 53 patients), HR/SpO2 ranges, and missing value counts.
  - Visualises per-patient recording duration, overall HR/SpO2 distributions, per-patient boxplots, inter-patient variability, time-series samples, correlation analysis, and missing data patterns.

- **`2-Preprocessing.ipynb`** — Data Preprocessing.
  - Handles missing values, normalises features using `MinMaxScaler`, splits data by patient into train (42 patients) and test (10 patients) sets, and creates sliding windows (window size: 60, step: 1).
  - Saves processed arrays (`X_train.npy`, `X_test.npy`) and metadata to `data/processed/`.
  - Serialises the scaler to `models/lstm_autoencoder/scaler.pkl`.

- **`3-Model_Training.ipynb`** — LSTM Autoencoder Training.
  - Defines and trains a symmetric LSTM Autoencoder (encoder: 64 → 32 LSTM units; decoder: 32 → 64 LSTM units + TimeDistributed Dense output).
  - Uses `EarlyStopping` and `ModelCheckpoint` callbacks.
  - Saves the trained model to `models/lstm_autoencoder/model.keras` and full configuration (including threshold statistics) to `models/lstm_autoencoder/config.json`.

- **`4-Model_Evaluation.ipynb`** — Model Evaluation.
  - Loads the trained model and test data.
  - Computes per-window reconstruction errors (MSE).
  - Injects synthetic anomalies (bradycardia, hypoxia, combined) to evaluate detection performance.
  - Reports precision, recall, F1, ROC-AUC, PR-AUC.
  - Generates evaluation plots saved to `models/lstm_autoencoder/`.
