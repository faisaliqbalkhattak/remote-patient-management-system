# Architecture & Implementation Specification: LFNS Remote Health Tracking System
---

## 1. System Overview

1. **Integrated Perception & Edge Tier (Single ESP32-S3):**
   * **AD8232 ECG Sensor:** Sampled directly by ESP32-S3 ADC1 at 250 Hz on Core 0. R-peak detection executed via FreeRTOS high-priority task.
   * **MAX30102 Pulse Oximeter:** Read directly via Hardware I2C Master on Core 1.
   * **NIBP Module:** Interfaced via Hardware UART1 (`GPIO16/GPIO17`) on Core 1.
   * **Telemetry Aggregator & Wi-Fi Transmitter:** FreeRTOS Wi-Fi task assembling and streaming JSON requests.
2. **Access & Gateway Tier:** Local Wi-Fi Gateway running the LFNS decision engine, connection manager, load tracker, and local cache.
3. **Fog Computing Tier:** Heterogeneous fog nodes (F1: Ward Gateway, F2: Caregiver Tablet, F3: Clinic Server, F4: Hospital Server) executing task queues.
4. **Cloud & Presentation Tier:** Cloud database for long-term historical records; Web/Mobile dashboard for real-time clinician monitoring.

---

## 2. Edge Hardware Architecture: The Left-Side Pinout Design

To achieve clean, compact breadboard wiring without crossover wires spanning across the ESP32-S3 dev board, **all sensors are wired exclusively to the Left Row of Pins**:

```
                          ESP32-S3 Dev Board
                          +-----------------+
           [ 3.3V Power ] | 3.3V            | GND
           [ 3.3V Power ] | 3.3V            | GPIO43 (U0TXD)
           [ Reset ]      | RST             | GPIO44 (U0RXD)
      AD8232 OUTPUT (ADC) | GPIO4 (ADC1_CH3)| GPIO1
          AD8232 LO+ (In) | GPIO5           | GPIO2
          AD8232 LO- (In) | GPIO6           | GPIO42
                          | GPIO7           | GPIO41
                          | GPIO15          | GPIO40
          NIBP UART1 RX   | GPIO16 (U1RXD)  | GPIO39
          NIBP UART1 TX   | GPIO17 (U1TXD)  | GPIO38
                          | GPIO18          | GPIO37
      MAX30102 SDA (I2C)  | GPIO8 (I2C_SDA) | GPIO36
                          | GPIO3           | GPIO35
                          | GPIO46          | GPIO0 (BOOT)
      MAX30102 SCL (I2C)  | GPIO9 (I2C_SCL) | GPIO45
      MAX30102 INT (IRQ)  | GPIO10 (INT)    | GPIO48 (RGB)
                          | GPIO11          | GPIO47
                          | GPIO12          | GPIO21
                          | GPIO13          | GPIO20
                          | GPIO14          | GPIO19
           [ 5V Power In] | 5Vin            | GND
           [ Power Ground]| GND             | GND
                          +-----------------+
```

### Why This Specific Left-Side Pin Allocation Works Flawlessly:
1. **Wi-Fi + ADC Independence:** `GPIO4` belongs to **ADC1** (`ADC1_CH3`). On the ESP32-S3 architecture, **ADC1 can be sampled continuously while Wi-Fi is actively transmitting** (unlike ADC2, which is disabled during Wi-Fi packet transmission).
2. **I2C Routing:** ESP32-S3 features an internal GPIO matrix, allowing Hardware I2C (Wire) to bind to `GPIO8` (SDA) and `GPIO9` (SCL) with zero performance degradation.
3. **Interrupt Pin:** `GPIO10` supports external falling-edge interrupts with an internal pull-up, perfectly matching the open-drain active-LOW `INT` of the MAX30102.
4. **Secondary UART:** `GPIO16` and `GPIO17` provide dedicated Hardware UART1 for NIBP or debugging without interfering with primary programming UART0 (`GPIO43/44`).
5. **Direct Power Accessibility:** Both `3.3V` (Pins 1 & 2) and `GND` (Pin 22) are present on the exact same row!

---

## 3. Dual-Core FreeRTOS Task Distribution

```
+---------------------------------------------------------------------------------------+
|                                    ESP32-S3                                           |
|                                                                                       |
|   [ Core 0: Real-Time Signal Processing ]      [ Core 1: Communication & Aggregation ]|
|                                                                                       |
|   +------------------------------------+       +------------------------------------+ |
|   | Task: AD8232 ECG Sampling          |       | Task: MAX30102 I2C Polling         | |
|   | • 250 Hz Timer Interrupt on ADC1   |       | • Interrupt-driven FIFO reads      | |
|   | • Digital High-Pass & Bandpass     |       | • SpO2 % & Pulse Rate Calculation  | |
|   | • Pan-Tompkins R-Peak Detection    |       +------------------------------------+ |
|   | • RR-Interval & Heart Rate (BPM)   |                          |                   |
|   +------------------------------------+                          v                   |
|                     |                          +------------------------------------+ |
|                     +------------------------> | Task: Packet Formation & Wi-Fi     | |
|                      (Internal FreeRTOS Queue) | • JSON formatting                  | |
|                                                | • HTTP POST / MQTT Dispatch        | |
|                                                | • Local flash ring buffer on drop  | |
|                                                +------------------------------------+ |
+-------------------------------------------------------------------|-------------------+
                                                                    | Wi-Fi 802.11 b/g/n
                                                                    v
                                                            [ Local Gateway ]
```

---

## 4. The LFNS Mathematical Engine

### Step 1: Filter Ineligible Nodes
A node $i$ is excluded from candidate set $\mathcal{C}$ if:
* $\text{Status}_i \neq \text{CONNECTED}$
* $\text{Auth}_i \neq \text{AUTHORIZED}$
* $\text{TaskType} \notin \text{SupportedTasks}_i$
* $\text{AvailableRAM}_i < \text{RequiredRAM}(\text{Task})$

### Step 2: Estimate Total Delay
For each $i \in \mathcal{C}$:
$$\text{Estimate}_i = T_{\text{network}, i} + T_{\text{queue}, i} + T_{\text{processing}, i}$$

Where:
* $T_{\text{network}, i}$: Estimated network latency based on rolling exponential moving average (EMA) of RTT.
* $T_{\text{queue}, i}$: Estimated queue time based on current unfinished jobs.
* $T_{\text{processing}, i}$: Estimated execution time for the incoming task based on node compute capacity.

### Step 3: Selection with Tie-Breaking
$$i^* = \arg\min_{i \in \mathcal{C}} \text{Estimate}_i$$
If $\text{Estimate}_a = \text{Estimate}_b$:
$$i^* = \arg\min_{k \in \{a, b\}} \text{CommCost}_k$$

### Step 4: Workload Update & Feedback Loop
* As soon as task $j$ is dispatched to $i^*$:
  $$T_{\text{queue}, i^*} \leftarrow T_{\text{queue}, i^*} + T_{\text{processing}, i^*}$$
* When the processed result returns from $i^*$:
  * Actual elapsed times ($T_{\text{queue}}^{\text{actual}}, T_{\text{processing}}^{\text{actual}}$) are recorded.
  * Node estimation parameters are updated via EMA.

---

## 5. Sequence Diagram

```
Patient    AD8232 / MAX30102       ESP32-S3 (Single Edge)      Local Gateway        Selected Fog (F3)   Dashboard / Cloud
   |              |                          |                         |                      |                   |
   |--Bio-Signals>|                          |                         |                      |                   |
   |              |--ADC1 (GPIO4: 250Hz)---->|                         |                      |                   |
   |              |--I2C (GPIO8/9: SpO2)---->|                         |                      |                   |
   |              |                          |--FreeRTOS R-Peak Det.---|                      |                   |
   |              |                          |--Assemble JSON Packet---|                      |                   |
   |              |                          |--Wi-Fi Request--------->|                      |                   |
   |              |                          |                         |--LFNS Decision-------|                   |
   |              |                          |                         |  (Selects F3: 55ms)  |                   |
   |              |                          |                         |--Dispatch Task------>|                   |
   |              |                          |                         |                      |--Queue & Compute--|
   |              |                          |                         |<--Return Result------|                   |
   |              |                          |                         |--Update State Tracker|                   |
   |              |                          |                         |--Forward Live Result-------------------->| (Dashboard)
   |              |                          |                         |--Background Sync------------------------>| (Cloud DB)
```
