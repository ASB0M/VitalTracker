# `edge/` — Edge Layer (ESP32 Firmware)

## Purpose

Contains the Arduino/C++ firmware that runs on an ESP32 microcontroller. This layer is responsible for:

1. Interfacing with the MAX30102 pulse oximeter sensor via I2C.
2. Sampling raw IR and Red LED values from the sensor.
3. Computing Heart Rate (BPM) and SpO2 (%) using the SparkFun `spo2_algorithm` and `heartRate` libraries.
4. Publishing validated vitals as JSON payloads to an MQTT broker over WiFi.

## Subdirectory

### `patient_monitor/`

- **`patient_monitor.ino`** — Main Arduino sketch. Performs the following:
  - Connects to a configured WiFi network (`WIFI_SSID`/`WIFI_PASSWORD`).
  - Initialises the MAX30102 sensor with specific LED brightness, sample rate, and pulse width settings.
  - Connects to the HiveMQ public MQTT broker (`broker.hivemq.com:1883`).
  - Collects a buffer of 100 IR/Red samples per cycle and runs the Maxim SpO2 algorithm.
  - Detects heartbeats in real-time using a rolling average (window of 4).
  - Publishes a JSON payload to `vitals/patient01` containing `device_id`, `timestamp_ms`, `heart_rate`, `spo2`, and validity flags.
  - Publishes online/offline status messages (retained) to `status/patient01`.
  - Implements automatic WiFi and MQTT reconnection logic.

## Hardware Wiring

| MAX30102 Pin | ESP32 Pin |
|---|---|
| VIN | 3.3V |
| GND | GND |
| SDA | GPIO 21 |
| SCL | GPIO 22 |

## Required Arduino Libraries

Install via the Arduino IDE Library Manager:

- `PubSubClient` by Nick O'Leary
- `SparkFun MAX3010x` by SparkFun Electronics
- `ArduinoJson` by Benoit Blanchon
