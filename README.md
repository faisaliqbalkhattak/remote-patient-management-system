# Latency-Aware Fog Node Selection (LFNS) for Remote Health Tracking

This repository contains the complete implementation, evaluation suite, single-MCU firmware, schemas, and AI development skills for the **Latency-Aware Fog Node Selection for a Remote Health Tracking System**. 

---

## ⚡ Edge Processor Architecture: Single ESP32-S3

The architecture utilizes a **Single ESP32-S3 Development Board**

### 🎯 Single-Side (Left Row) Breadboard Wiring
All sensors connect exclusively to the **Left Pin Row** of the ESP32-S3 development board, allowing clean and compact wiring with zero crossover jumpers:
* **`3.3V` & `GND`:** Power rail for AD8232 & MAX30102.
* **`GPIO4` (ADC1_CH3):** AD8232 ECG analog output (Wi-Fi safe, no ADC conflict).
* **`GPIO5` & `GPIO6`:** AD8232 `LO+` & `LO-` Leads-off detach alerts.
* **`GPIO8` & `GPIO9`:** MAX30102 Hardware I2C bus (`SDA`, `SCL`).
* **`GPIO10`:** MAX30102 FIFO Data-Ready Interrupt (`INT`).
* **`GPIO16` & `GPIO17`:** NIBP Blood Pressure Hardware UART1 (`RX1`, `TX1`).

Complete electrical specifications and diagrams are detailed in [HARDWARE_PINOUT_GUIDE.md](HARDWARE_PINOUT_GUIDE.md).

---

## 📁 Repository Structure

```
project-code/
├── .claude/skills/lfns-iot-health-tracking/
│   └── SKILL.md              # OpenCode/Claude AI Skill definition (auto-loaded)
├── skills/lfns-iot-health-tracking/
│   └── SKILL.md              # Portable copy of the AI Skill
├── ARCHITECTURE.md           # End-to-end architecture, dual-core pipeline, sequence flows
├── DATA_SCHEMAS.md           # Formal JSON and inter-core queue data schemas
├── HARDWARE_PINOUT_GUIDE.md  # Detailed left-side pinout guide & wiring table
├── docs/images/              # Hardware photos & reference pinout diagrams
│   ├── ad8232_ecg_module.png
│   ├── esp32_s3_dev_board.png
│   ├── max30102_sensor_front.png
│   └── max30102_sensor_back_pinout.jpeg
├── core/
│   ├── __init__.py           # Package exports
│   ├── models.py             # Data entities (FogNode, HealthTask, SimulationResult)
│   ├── lfns_engine.py        # Selection algorithms (LFNS, Nearest-Node, Round-Robin)
│   ├── mock_sensors.py       # Realistic AD8232 ECG, MAX30102 PPG, and NIBP simulators
│   ├── numerical_example.py  # Verification of the LFNS numerical model (62.07% reduction)
│   └── simulation.py         # Full benchmark across core scenarios (light/heavy, busy, slow, disconnect)
├── firmware/
│   └── esp32_gateway_client/ # Unified ESP32-S3 dual-core FreeRTOS C++ firmware
└── README.md                 # Project documentation
```

---

## 🚀 Quick Start

### 1. Run the Worked Numerical Example
Verifies the analytical model comparing F1 Ward Gateway vs F3 Clinic Server:
```bash
python core/numerical_example.py
```
**Expected Output:**
* Nearest-Node (F1): `145.0 ms`
* LFNS (F3): `55.0 ms`
* Percentage Reduction: `62.07%`

### 2. Run the Full Simulation Benchmark
Executes discrete-event simulations for the 4 core test scenarios (Medium/Heavy load, One busy node, Slower network, Node disconnection) and benchmarks LFNS against Nearest-Node and Round-Robin baselines:
```bash
python core/simulation.py
```

### 3. Test the Synthetic Sensors
```python
from core.mock_sensors import MockAD8232ECG, MockMAX30102, MockNIBP

ecg = MockAD8232ECG().generate_window()
spo2 = MockMAX30102().read()
bp = MockNIBP().read()

print("ECG RR-interval:", ecg["rr_interval_ms"])
print("Pulse & SpO2:", spo2)
print("Blood Pressure:", bp)
```

---


## 4. Edge Hardware Architecture: The Left-Side Pinout Design

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