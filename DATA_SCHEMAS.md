# Data Schemas Specification

This document defines all communication payload schemas used between the Edge ESP32-S3 processor, the Local Gateway, the Fog Nodes (F1–F4), the Cloud Server, and the User Dashboard.

---

## 1. Internal FreeRTOS Inter-Core Message (Core 0 to Core 1)

* **Mechanism:** FreeRTOS thread-safe queue (`xQueueECG`)
* **Frequency:** Driven by 250 Hz ADC timer ISR and R-peak events

### C-Structure:
```c
typedef struct {
    uint32_t timestamp_ms;
    uint16_t raw_adc;          // 12-bit ADC reading from GPIO4 (ADC1_CH3)
    bool r_peak_detected;
    float rr_interval_ms;      // Elapsed time since prior QRS peak
    bool leads_disconnected;   // Read from GPIO5 (LO+) and GPIO6 (LO-)
} ECG_Sample_t;
```

---

## 2. ESP32-S3 to Local Gateway (Wi-Fi Telemetry Request)

* **Protocol:** HTTP POST or MQTT JSON payload over Wi-Fi 802.11 b/g/n
* **Endpoint / Topic:** `/api/v1/telemetry/request` or `health/telemetry/requests`

### Schema:
```json
{
  "request_id": "REQ-2026-000941",
  "device_id": "ESP32S3-BED-04",
  "patient_id": "PATIENT-8812",
  "timestamp": 1731580800123,
  "task_type": "ECG_ANALYSIS",
  "priority": "HIGH",
  "payload_size_bytes": 1024,
  "measurements": {
    "ecg_rr_interval_ms": 820.0,
    "ecg_sample_window": [2048, 2060, 2180, 3120, 2800, 2050, 2040],
    "leads_off_detected": false,
    "pulse_bpm": 74.2,
    "spo2_percent": 98.4,
    "blood_pressure": {
      "systolic": 118,
      "diastolic": 78,
      "map": 91
    }
  },
  "qos_requirements": {
    "max_acceptable_delay_ms": 200,
    "required_memory_mb": 16,
    "task_compute_cycles_mflops": 5.0
  }
}
```

---

## 3. Fog Node Registration & Heartbeat to Gateway

* **Protocol:** WebSocket or HTTP periodic heartbeat (interval: 500 ms - 2000 ms)
* **Endpoint / Topic:** `/api/v1/nodes/heartbeat` or `health/nodes/status`

### Schema:
```json
{
  "node_id": "F3",
  "node_name": "Clinic Server",
  "status": "CONNECTED",
  "authorization_token": "AUTH-CLINIC-SECURE-992",
  "supported_tasks": ["ECG_ANALYSIS", "VITALS_FUSION", "ARRHYTHMIA_DETECTION", "NIBP_TRENDING"],
  "specs": {
    "processing_mflops": 5000,
    "total_memory_mb": 8192,
    "available_memory_mb": 6144,
    "communication_cost_score": 1.2
  },
  "current_state": {
    "active_tasks_count": 2,
    "queue_length": 2,
    "estimated_queue_wait_ms": 10.0,
    "observed_network_rtt_ms": 30.0,
    "cpu_utilization_percent": 24.5
  },
  "timestamp": 1731580800100
}
```

---

## 4. Fog Node Task Response to Gateway & Dashboard

* **Endpoint / Topic:** `/api/v1/telemetry/response` or `health/telemetry/results`

### Schema:
```json
{
  "request_id": "REQ-2026-000941",
  "processed_by_node": "F3",
  "selection_algorithm": "LFNS",
  "timestamps": {
    "created_at_sensor": 1731580800123,
    "dispatched_by_gateway": 1731580800128,
    "arrived_at_fog": 1731580800143,
    "execution_started": 1731580800153,
    "execution_finished": 1731580800163,
    "received_at_dashboard": 1731580800178
  },
  "latency_breakdown_ms": {
    "t_device": 15.0,
    "t_selection_overhead": 5.0,
    "t_network": 30.0,
    "t_queue": 10.0,
    "t_processing": 10.0,
    "t_total_response": 55.0
  },
  "analysis_results": {
    "heart_rate_bpm": 73.2,
    "rhythm_classification": "NORMAL_SINUS_RHYTHM",
    "arrhythmia_detected": false,
    "spo2_status": "NORMAL",
    "bp_category": "OPTIMAL",
    "signal_quality_index": 0.96
  },
  "historical_data_synced_to_cloud": false
}
```

---

## 5. Evaluation & Benchmark Log Schema

Used by the simulation scripts to aggregate comparative baselines:

```json
{
  "scenario": "one_busy_node",
  "run_id": 42,
  "request_count": 1000,
  "results": {
    "LFNS": {
      "mean_response_time_ms": 58.4,
      "p95_response_time_ms": 78.1,
      "task_completion_ratio": 1.0,
      "packet_drop_count": 0,
      "selected_node_distribution": { "F1": 12, "F2": 210, "F3": 680, "F4": 98 }
    },
    "NEAREST_NODE": {
      "mean_response_time_ms": 154.2,
      "p95_response_time_ms": 290.0,
      "task_completion_ratio": 0.94,
      "packet_drop_count": 60,
      "selected_node_distribution": { "F1": 1000, "F2": 0, "F3": 0, "F4": 0 }
    },
    "ROUND_ROBIN": {
      "mean_response_time_ms": 92.6,
      "p95_response_time_ms": 165.0,
      "task_completion_ratio": 0.99,
      "packet_drop_count": 10,
      "selected_node_distribution": { "F1": 250, "F2": 250, "F3": 250, "F4": 250 }
    }
  },
  "percentage_improvement_over_nearest": 62.13,
  "percentage_improvement_over_round_robin": 36.93
}
```
