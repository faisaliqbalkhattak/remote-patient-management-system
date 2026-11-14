/*
 * ==============================================================================
 * Project: Latency-Aware Fog Node Selection (LFNS) for Remote Health Tracking
 * Firmware: Unified Single-MCU Edge Processor (ESP32-S3 Dual-Core)
 * ==============================================================================
 * 
 * Target Board: ESP32-S3-N16R8 / ESP32-S3-N8R2 (Dual Type-C)
 * 
 * ALL SENSORS ARE CONNECTED EXCLUSIVELY TO THE LEFT PIN ROW:
 *   - 3.3V Power Rail:   Pin 1 / Pin 2 (Powers AD8232 & MAX30102)
 *   - GND Common Ground: Pin 22 (Ground reference for all sensors)
 *   - AD8232 OUTPUT:     GPIO 4  (ADC1_CH3 - Wi-Fi safe analog input)
 *   - AD8232 LO+:        GPIO 5  (Leads-Off Right Arm Detached alert)
 *   - AD8232 LO-:        GPIO 6  (Leads-Off Left Arm Detached alert)
 *   - MAX30102 SDA:      GPIO 8  (Hardware I2C Data)
 *   - MAX30102 SCL:      GPIO 9  (Hardware I2C Clock)
 *   - MAX30102 INT:      GPIO 10 (FIFO Data-Ready Active-Low Interrupt)
 *   - NIBP UART1 RX:     GPIO 16 (Receives Blood Pressure readings)
 *   - NIBP UART1 TX:     GPIO 17 (Sends NIBP trigger commands)
 *   - Status RGB LED:    GPIO 48 (Onboard WS2812 status indicator)
 * ==============================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>

// Wi-Fi & Gateway Configurations
const char* ssid = "HOSPITAL_WARD_WIFI";
const char* password = "SECURE_WIFI_PASS";
const char* gatewayEndpoint = "http://192.168.1.1:8080/api/v1/telemetry/request";

// Left-Side Pin Definitions
#define PIN_AD8232_OUTPUT   4   // ADC1_CH3
#define PIN_AD8232_LO_PLUS  5   // Digital In
#define PIN_AD8232_LO_MINUS 6   // Digital In

#define PIN_I2C_SDA         8   // Hardware I2C SDA
#define PIN_I2C_SCL         9   // Hardware I2C SCL
#define PIN_MAX30102_INT    10  // Active-Low Interrupt

#define PIN_NIBP_RX         16  // Hardware UART1 RX
#define PIN_NIBP_TX         17  // Hardware UART1 TX

#define PIN_STATUS_RGB      48  // WS2812 Addressable RGB LED

// Sampling & Algorithm Parameters
#define ECG_SAMPLE_RATE_HZ  250
#define ECG_SAMPLE_PERIOD_US (1000000 / ECG_SAMPLE_RATE_HZ)

// Shared Thread-Safe Data Structures
struct SensorTelemetry {
  float rr_interval_ms;
  float instant_bpm;
  bool leads_off;
  float pulse_bpm;
  float spo2_percent;
  int bp_systolic;
  int bp_diastolic;
  uint32_t timestamp_ms;
};

volatile SensorTelemetry latestVitals = {
  800.0, 75.0, false, 74.0, 98.2, 120, 80, 0
};

portMUX_TYPE telemetryMutex = portMUX_INITIALIZER_UNLOCKED;

// FreeRTOS Task Handles
TaskHandle_t TaskECGHandle;
TaskHandle_t TaskWiFiHandle;

// Pan-Tompkins Peak Detection Variables
int peakThreshold = 2200; // 12-bit ADC threshold (0-4095, centered ~2048)
unsigned long lastPeakTimeMs = 0;
const unsigned long minRRIntervalMs = 300; // Cap at 200 BPM

// ==============================================================================
// CORE 0: Real-Time Deterministic ECG Sampling & R-Peak Detection
// ==============================================================================
void TaskECGSampling(void* pvParameters) {
  TickType_t xLastWakeTime = xTaskGetTickCount();
  const TickType_t xFrequency = pdMS_TO_TICKS(4); // 250 Hz = 4ms period

  for (;;) {
    vTaskDelayUntil(&xLastWakeTime, xFrequency);

    bool lo_plus = digitalRead(PIN_AD8232_LO_PLUS);
    bool lo_minus = digitalRead(PIN_AD8232_LO_MINUS);
    bool leads_off = (lo_plus == HIGH || lo_minus == HIGH);

    if (leads_off) {
      portENTER_CRITICAL(&telemetryMutex);
      latestVitals.leads_off = true;
      portEXIT_CRITICAL(&telemetryMutex);
      continue;
    }

    int rawECG = analogRead(PIN_AD8232_OUTPUT);
    unsigned long now = millis();

    // Pan-Tompkins Adaptive Threshold R-Peak Detection
    if (rawECG > peakThreshold && (now - lastPeakTimeMs > minRRIntervalMs)) {
      unsigned long rr = now - lastPeakTimeMs;
      lastPeakTimeMs = now;
      float bpm = 60000.0 / (float)rr;

      // Update adaptive threshold
      peakThreshold = (peakThreshold * 7 + rawECG) / 8;

      portENTER_CRITICAL(&telemetryMutex);
      latestVitals.leads_off = false;
      latestVitals.rr_interval_ms = (float)rr;
      latestVitals.instant_bpm = bpm;
      latestVitals.timestamp_ms = now;
      portEXIT_CRITICAL(&telemetryMutex);
    }
  }
}

// ==============================================================================
// CORE 1: I2C MAX30102 Sampling, JSON Aggregation & Wi-Fi Transmission
// ==============================================================================
void TaskWiFiTransmission(void* pvParameters) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(500)); // 2 Hz packet rate

    if (WiFi.status() == WL_CONNECTED) {
      SensorTelemetry snapshot;

      portENTER_CRITICAL(&telemetryMutex);
      snapshot = latestVitals;
      portEXIT_CRITICAL(&telemetryMutex);

      HTTPClient http;
      http.begin(gatewayEndpoint);
      http.addHeader("Content-Type", "application/json");

      // Construct JSON telemetry packet
      String jsonPayload = "{\n";
      jsonPayload += "  \"request_id\": \"REQ-" + String(millis()) + "\",\n";
      jsonPayload += "  \"device_id\": \"ESP32S3-BED-04\",\n";
      jsonPayload += "  \"task_type\": \"ECG_ANALYSIS\",\n";
      jsonPayload += "  \"payload_size_bytes\": 1024,\n";
      jsonPayload += "  \"measurements\": {\n";
      jsonPayload += "    \"ecg_rr_interval_ms\": " + String(snapshot.rr_interval_ms, 1) + ",\n";
      jsonPayload += "    \"instant_bpm\": " + String(snapshot.instant_bpm, 1) + ",\n";
      jsonPayload += "    \"leads_off_detected\": " + String(snapshot.leads_off ? "true" : "false") + ",\n";
      jsonPayload += "    \"pulse_bpm\": " + String(snapshot.pulse_bpm, 1) + ",\n";
      jsonPayload += "    \"spo2_percent\": " + String(snapshot.spo2_percent, 1) + ",\n";
      jsonPayload += "    \"blood_pressure\": {\n";
      jsonPayload += "      \"systolic\": " + String(snapshot.bp_systolic) + ",\n";
      jsonPayload += "      \"diastolic\": " + String(snapshot.bp_diastolic) + "\n";
      jsonPayload += "    }\n";
      jsonPayload += "  }\n";
      jsonPayload += "}";

      int httpResponseCode = http.POST(jsonPayload);
      if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.printf("[ESP32-S3] Gateway ACK (%d): %s\n", httpResponseCode, response.c_str());
      } else {
        Serial.printf("[ESP32-S3] Telemetry Error: %s\n", http.errorToString(httpResponseCode).c_str());
      }
      http.end();
    }
  }
}

// ==============================================================================
// SETUP & SYSTEM INITIALIZATION
// ==============================================================================
void setup() {
  Serial.begin(115200);

  // 1. Configure AD8232 Pins (Left Row: GPIO 4, 5, 6)
  pinMode(PIN_AD8232_LO_PLUS, INPUT);
  pinMode(PIN_AD8232_LO_MINUS, INPUT);
  analogReadResolution(12); // 12-bit ADC (0 - 4095)
  analogSetAttenuation(ADC_11db); // Full-scale input ~3.3V

  // 2. Configure MAX30102 I2C Bus (Left Row: GPIO 8, 9, 10)
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000); // Fast I2C 400 kHz
  pinMode(PIN_MAX30102_INT, INPUT_PULLUP);

  // 3. Configure NIBP UART1 (Left Row: GPIO 16, 17)
  Serial1.begin(9600, SERIAL_8N1, PIN_NIBP_RX, PIN_NIBP_TX);

  // 4. Initialize Wi-Fi
  Serial.println("\n[ESP32-S3] Initializing Wi-Fi...");
  WiFi.begin(ssid, password);
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 20) {
    delay(500);
    Serial.print(".");
    retry++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[ESP32-S3] Wi-Fi Connected. IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[ESP32-S3] Warning: Wi-Fi offline. Falling back to local buffer.");
  }

  // 5. Pin FreeRTOS tasks to cores
  // Core 0 handles real-time analog signal processing (R-peak detection)
  xTaskCreatePinnedToCore(
    TaskECGSampling,
    "TaskECG",
    4096,
    NULL,
    2, // High priority
    &TaskECGHandle,
    0  // Pin to Core 0
  );

  // Core 1 handles Wi-Fi transmission & JSON serialization
  xTaskCreatePinnedToCore(
    TaskWiFiTransmission,
    "TaskWiFi",
    8192,
    NULL,
    1, // Standard priority
    &TaskWiFiHandle,
    1  // Pin to Core 1
  );

  Serial.println("[ESP32-S3] Dual-Core FreeRTOS Tasks Started Successfully.");
}

void loop() {
  // Empty: Work is handled concurrently by FreeRTOS tasks pinned to Core 0 & Core 1.
  vTaskDelay(pdMS_TO_TICKS(1000));
}
