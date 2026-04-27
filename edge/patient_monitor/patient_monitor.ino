// ================================================================
//  PATIENT VITALS MONITOR — ESP32 + MAX30102 + MQTT
//  Author  : Your Name
//  Version : 1.0
//
//  REQUIRED LIBRARIES (install via Arduino IDE Library Manager):
//    - PubSubClient         by Nick O'Leary
//    - SparkFun MAX3010x    by SparkFun Electronics
//    - ArduinoJson          by Benoit Blanchon
//
//  WIRING (MAX30102 → ESP32):
//    VIN  → 3.3V
//    GND  → GND
//    SDA  → GPIO 21
//    SCL  → GPIO 22
//    INT  → GPIO 19  (optional, not used here)
// ================================================================

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"
#include "heartRate.h"

// ================================================================
//  SECTION 1 — CONFIGURATION (only edit this section)
// ================================================================

// --- WiFi ---
const char* WIFI_SSID       = "ASB";
const char* WIFI_PASSWORD   = "10203040";

// --- MQTT Broker (IP of your fog layer / PC) ---
const char* MQTT_BROKER   = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT_ID = "patient_monitor_01";  // keep as is
const char* MQTT_USER       = "";                   // leave empty if broker has no auth
const char* MQTT_PASS       = "";

// --- MQTT Topics ---
const char* TOPIC_VITALS    = "vitals/patient01";   // main data stream
const char* TOPIC_STATUS    = "status/patient01";   // device online/offline

// --- Sampling & Publishing ---
const int   SAMPLE_BUFFER   = 100;                  // samples per SpO2 calculation cycle
const int   PUBLISH_EVERY_N_CYCLES = 1;             // publish after every N cycles (keep at 1)

// ================================================================
//  SECTION 2 — GLOBALS (do not edit)
// ================================================================

WiFiClient   wifiClient;
PubSubClient mqttClient(wifiClient);
MAX30105     particleSensor;

// Sample buffers for SpO2 algorithm
uint32_t irBuffer[100];
uint32_t redBuffer[100];

// Output values from SpO2 algorithm
int32_t  spo2;
int8_t   validSPO2;
int32_t  heartRate;
int8_t   validHeartRate;

// Heart rate beat detection (for live HR finger-on detection)
const byte RATE_SIZE = 4;
byte       rates[RATE_SIZE];
byte       rateSpot = 0;
long       lastBeat = 0;
float      beatsPerMinute;
int        beatAvg;

unsigned long lastPublishTime = 0;
int           cycleCount      = 0;

// ================================================================
//  SECTION 3 — WIFI
// ================================================================

void connectWiFi() {
  Serial.print("[WiFi] Connecting to: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    attempts++;
    if (attempts > 40) {
      Serial.println("\n[WiFi] Failed to connect. Restarting...");
      ESP.restart();
    }
  }

  Serial.println();
  Serial.print("[WiFi] Connected. IP: ");
  Serial.println(WiFi.localIP());
}

void ensureWiFi() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Connection lost. Reconnecting...");
    connectWiFi();
  }
}

// ================================================================
//  SECTION 4 — MQTT
// ================================================================

void connectMQTT() {
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setKeepAlive(60);

  while (!mqttClient.connected()) {
    Serial.print("[MQTT] Connecting to broker at ");
    Serial.print(MQTT_BROKER);
    Serial.print("...");

    bool connected = (strlen(MQTT_USER) > 0)
      ? mqttClient.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS,
                           TOPIC_STATUS, 1, true, "offline")
      : mqttClient.connect(MQTT_CLIENT_ID,
                           TOPIC_STATUS, 1, true, "offline");

    if (connected) {
      Serial.println(" connected.");
      mqttClient.publish(TOPIC_STATUS, "online", true);  // retained message
    } else {
      Serial.print(" failed. State=");
      Serial.println(mqttClient.state());
      Serial.println("[MQTT] Retrying in 3 seconds...");
      delay(3000);
    }
  }
}

void ensureMQTT() {
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] Connection lost. Reconnecting...");
    connectMQTT();
  }
  mqttClient.loop();
}

// ================================================================
//  SECTION 5 — SENSOR INIT
// ================================================================

void initSensor() {
  Serial.println("[Sensor] Initialising MAX30102...");

  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("[Sensor] ERROR: MAX30102 not found. Check wiring!");
    while (true) { delay(1000); }   // halt here — no sensor, no point continuing
  }

  // Sensor configuration
  byte ledBrightness = 60;    // 0=off, 255=max (50mA)
  byte sampleAverage = 4;     // 1, 2, 4, 8, 16, 32
  byte ledMode       = 2;     // 1=Red only, 2=Red+IR (needed for SpO2)
  int  sampleRate    = 100;   // samples/sec: 50, 100, 200, 400, 800, 1000, 1600, 3200
  int  pulseWidth    = 411;   // microseconds
  int  adcRange      = 4096;  // 2048, 4096, 8192, 16384

  particleSensor.setup(ledBrightness, sampleAverage, ledMode,
                       sampleRate, pulseWidth, adcRange);
  particleSensor.setPulseAmplitudeRed(0x0A);   // low red LED for heartrate
  particleSensor.setPulseAmplitudeGreen(0);    // green not used

  Serial.println("[Sensor] MAX30102 ready.");
}

// ================================================================
//  SECTION 6 — PUBLISH VITALS
// ================================================================

void publishVitals(int hr, int spo2Val, bool hrValid, bool spo2Valid) {
  StaticJsonDocument<256> doc;

  doc["device_id"]   = MQTT_CLIENT_ID;
  doc["timestamp_ms"] = millis();

  // Only include valid readings — fog layer should handle missing fields
  if (hrValid) {
    doc["heart_rate"] = hr;
  } else {
    doc["heart_rate"] = nullptr;
  }

  if (spo2Valid) {
    doc["spo2"] = spo2Val;
  } else {
    doc["spo2"] = nullptr;
  }

  doc["hr_valid"]   = hrValid;
  doc["spo2_valid"] = spo2Valid;

  char payload[256];
  serializeJson(doc, payload);

  bool published = mqttClient.publish(TOPIC_VITALS, payload);

  Serial.print("[MQTT] Published → ");
  Serial.print(TOPIC_VITALS);
  Serial.print(" | HR: ");
  Serial.print(hrValid ? String(hr) : "invalid");
  Serial.print(" bpm | SpO2: ");
  Serial.print(spo2Valid ? String(spo2Val) : "invalid");
  Serial.println(published ? " ✓" : " ✗ (publish failed)");
}

// ================================================================
//  SECTION 7 — SETUP
// ================================================================

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n========================================");
  Serial.println("  Patient Monitor — Booting");
  Serial.println("========================================");

  connectWiFi();
  initSensor();
  connectMQTT();

  Serial.println("[System] Ready. Place finger on sensor...\n");
}

// ================================================================
//  SECTION 8 — MAIN LOOP
// ================================================================

void loop() {
  ensureWiFi();
  ensureMQTT();

  // ── Collect SAMPLE_BUFFER readings ──────────────────────────
  for (byte i = 0; i < SAMPLE_BUFFER; i++) {
    while (!particleSensor.available()) {
      particleSensor.check();   // poll sensor FIFO
    }

    redBuffer[i] = particleSensor.getRed();
    irBuffer[i]  = particleSensor.getIR();
    particleSensor.nextSample();

    // Print raw IR to serial so you can verify finger placement
    Serial.print("[Raw] IR=");
    Serial.print(irBuffer[i]);

    // Check for heartbeat using beat detection on the fly
    if (checkForBeat(irBuffer[i])) {
      long delta     = millis() - lastBeat;
      lastBeat       = millis();
      beatsPerMinute = 60.0 / (delta / 1000.0);

      if (beatsPerMinute > 30 && beatsPerMinute < 255) {
        rates[rateSpot++] = (byte)beatsPerMinute;
        rateSpot %= RATE_SIZE;

        beatAvg = 0;
        for (byte x = 0; x < RATE_SIZE; x++) beatAvg += rates[x];
        beatAvg /= RATE_SIZE;
      }
    }

    Serial.print("  |  Avg HR=");
    Serial.println(beatAvg);
  }

  // ── Run SpO2 Algorithm on collected buffer ───────────────────
  maxim_heart_rate_and_oxygen_saturation(
    irBuffer, SAMPLE_BUFFER, redBuffer,
    &spo2, &validSPO2,
    &heartRate, &validHeartRate
  );

  cycleCount++;

  // ── Publish every N cycles ───────────────────────────────────
  if (cycleCount >= PUBLISH_EVERY_N_CYCLES) {
    cycleCount = 0;

    // Sanity check: if IR reading is too low, finger is not on sensor
    bool fingerDetected = (irBuffer[SAMPLE_BUFFER - 1] > 50000);

    if (!fingerDetected) {
      Serial.println("[Sensor] No finger detected — skipping publish.");
    } else {
      publishVitals(
        (int)heartRate,
        (int)spo2,
        (bool)validHeartRate,
        (bool)validSPO2
      );
    }
  }

  // ── Reuse last 25 samples to maintain continuity ─────────────
  // (SparkFun recommended approach — avoids gaps between cycles)
  for (byte i = 25; i < SAMPLE_BUFFER; i++) {
    redBuffer[i - 25] = redBuffer[i];
    irBuffer[i - 25]  = irBuffer[i];
  }
}
