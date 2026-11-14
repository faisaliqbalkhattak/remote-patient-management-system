---
name: lfns-iot-health-tracking
description: Expert skill for developing, simulating, testing, and benchmarking the Latency-Aware Fog Node Selection (LFNS) IoT remote health tracking system. Covers sensor data ingestion (AD8232 ECG on ADC1, MAX30102 pulse/SpO2 on I2C, NIBP), single-MCU ESP32-S3 dual-core firmware workflows, local gateway dynamic node selection algorithms, fog node queuing, baseline comparisons (Nearest-Node, Round-Robin), and evaluation metrics. Use whenever working on the LFNS project, writing IoT code, running fog computing simulations, or calculating latency breakdowns.
---

# Skill: Latency-Aware Fog Node Selection (LFNS) for Remote Health Tracking

## Project Overview
This skill provides comprehensive architectural context, algorithms, formulas, data schemas, and simulation templates for the **Latency-Aware Fog Node Selection for a Remote Health Tracking System**.

### Primary Goal
Eliminate latency bottlenecks caused by routing all patient telemetry to the nearest fog node (which frequently leads to queue congestion). Intelligently distribute requests across heterogeneous, multi-tier fog nodes (Ward Gateway, Caregiver Tablet, Clinic Server, Hospital Server) to minimize end-to-end response time for critical health vitals (ECG, Pulse/SpO₂, NIBP).

---

## System Architecture & Pipeline (Unified ESP32-S3 Edge)

```
[ Electrodes ] -> [ AD8232 ECG Module ]
                       | (Analog Signal)
                       v
[ MAX30102 ] -> [    ESP32-S3   ] <- [ NIBP Module ]
(Pulse/SpO2     (Core 0: ADC1 Sampling 250Hz & R-Peak Detection
 via I2C)        Core 1: I2C Polling, Packet Formation & Wi-Fi)
                       | (Wi-Fi 802.11 b/g/n)
                       v
               [ Local Gateway ]
         (LFNS Decision & Load Tracker)
          /        |         |         \
         v         v         v          v
       [F1]      [F2]       [F3]       [F4]
      Ward    Caregiver    Clinic    Hospital
     Gateway   Tablet      Server     Server
        \          |         |         /
         +---------+---------+--------+
                       |
                       v
           [ Local Gateway Return ]
          /                        \
         v                          v
  [ User Dashboard ]       [ Cloud Storage ]
 (Mobile/Web Patient &   (Background Upload,
 Caregiver Real-time UI)  Long-term Analysis)
```

---

## Edge Pinout Design: Single-Side (Left Row) Pin Allocation
To keep breadboard wiring clean and avoid crossover wires, all sensors connect exclusively to the **Left Pin Row** of the ESP32-S3:
* **Power:** `3.3V` (Pin 1) & `GND` (Pin 22)
* **AD8232 ECG:**
  * `OUTPUT` $\to$ **`GPIO4`** (ADC1_CH3 — Wi-Fi safe, no contention)
  * `LO+` $\to$ **`GPIO5`** (Digital In, Leads-Off Right)
  * `LO-` $\to$ **`GPIO6`** (Digital In, Leads-Off Left)
* **MAX30102 Pulse Oximeter:**
  * `SDA` $\to$ **`GPIO8`** (Hardware I2C Data)
  * `SCL` $\to$ **`GPIO9`** (Hardware I2C Clock)
  * `INT` $\to$ **`GPIO10`** (Active-Low Interrupt)
* **NIBP Module:**
  * `RX / TX` $\to$ **`GPIO16` / `GPIO17`** (Hardware UART1)

---

## Mathematical Formulations

### 1. End-to-End Latency ($T_{\text{total}}$)
$$T_{\text{total}} = T_{\text{device}} + T_{\text{network}} + T_{\text{queue}} + T_{\text{processing}} + T_{\text{overhead}}$$

* $T_{\text{device}}$: Time to collect sensor readings, digitize via ADC1, run Pan-Tompkins R-peak detection, and assemble the request payload on ESP32-S3.
* $T_{\text{network}}$: Round-trip time (RTT) for sending the request to the fog node and receiving the result at the gateway.
* $T_{\text{queue}}$: Time the task waits in the fog node's execution queue prior to execution.
* $T_{\text{processing}}$: Active compute time required by the fog node to execute the specific medical algorithm.
* $T_{\text{overhead}}$: Gateway selection latency, serialization/deserialization, and dashboard rendering overhead.

### 2. Node Delay Estimate ($\text{Estimate}_{\text{node}}$)
For every eligible fog node $i$:
$$\text{Estimate}_i = T_{\text{network}, i} + T_{\text{queue}, i} + T_{\text{processing}, i}$$

### 3. Selection & Tiebreaking Rules
1. **Eligibility Filtering:** Node must be:
   - Status: `CONNECTED`
   - Security: `AUTHORIZED`
   - Capability: `SUPPORTS_TASK` (e.g. ECG analysis vs simple vitals parsing)
   - Resources: Available RAM $\ge$ Task Minimum Requirement
2. **Minimum Delay Criterion:**
   $$i^* = \arg\min_{i \in \text{Eligible}} (\text{Estimate}_i)$$
3. **Tiebreaker:** If $\text{Estimate}_a == \text{Estimate}_b$, choose the node with lower **communication cost** (e.g., lower power consumption or lower bandwidth cost).
4. **Immediate Workload Update:** Update estimated queue depth immediately upon dispatching to avoid stale state (thundering herd problem).
5. **Failover:** If no node is eligible, return an `UNAVAILABLE` status, buffer request in local ESP32-S3 flash storage, and retry.

### 4. Percentage Reduction Metric
$$\text{Percentage Reduction} = \frac{\text{Baseline Latency} - \text{LFNS Latency}}{\text{Baseline Latency}} \times 100$$

---

## Fog Nodes Specification

| Node ID | Node Role | Typical Network Delay | Typical Processing Capacity | Characteristics |
|---|---|---|---|---|
| **F1** | Ward Gateway | Lowest (~10 ms) | Moderate / High Load | Nearest physical proximity, easily congested by multiple beds. |
| **F2** | Caregiver Tablet | Low-Medium (~20 ms) | Limited (Battery constrained) | Mobile node, good for light tasks when in close range. |
| **F3** | Clinic Server | Medium (~30 ms) | High (Dedicated server) | Robust compute, lower queuing delay during non-peak ward events. |
| **F4** | Hospital Server | Higher (~50 ms) | Very High (Enterprise server) | Farthest network hops, but virtually zero queue delay and minimal compute time. |

---

## Test Scenarios & Baselines
1. **Nearest-Node Selection:** Always routes requests to the node with the lowest network latency (F1).
2. **Round-Robin Selection:** Rotates requests sequentially among all authorized and capable nodes ($F_1 \to F_2 \to F_3 \to F_4 \to F_1$).
3. **4 Test Scenarios:** (1) Light/Medium/Heavy Load, (2) One Busy Node, (3) Slower Network/Large Payload, (4) Node Disconnection.
