# `scripts/` — Utility Scripts

## Purpose

Contains standalone utility scripts used for data preparation and other one-off tasks.

## Key Files

- **`compile_bidmc.py`** — Compiles the 53 individual BIDMC patient CSV files (`data/raw/bidmc/bidmc*_Numerics.csv`) into a single consolidated CSV (`data/raw/bidmc/bidmc_compiled_numerics.csv`).
  - Reads each file with `skipinitialspace=True` to handle column name whitespace issues.
  - Selects and renames columns: `Time [s]` → `Time`, `HR`, `SpO2`.
  - Extracts a `patient_id` from each filename.
  - Concatenates all DataFrames and writes the output to disk.
  - Run: `python scripts/compile_bidmc.py`
