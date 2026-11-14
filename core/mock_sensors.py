"""
Sensor simulators for the IoT edge nodes (ATmega328P + ESP32).
Generates realistic data for AD8232 ECG, MAX30102 Pulse/SpO2, and NIBP blood pressure.
"""

import math
import random
import time
from typing import Dict, Any, List


class MockAD8232ECG:
    """
    Simulates AD8232 Single-Lead Heart Rate Monitor digitized by ATmega328P ADC.
    Generates synthetic ECG waveforms with P-Q-R-S-T waves and detected R-peaks.
    """

    def __init__(self, baseline_hr_bpm: float = 75.0, sampling_rate_hz: int = 250):
        self.baseline_hr_bpm = baseline_hr_bpm
        self.sampling_rate_hz = sampling_rate_hz
        self.phase = 0.0

    def generate_window(self, window_size: int = 250) -> Dict[str, Any]:
        """Generates a window of ECG samples and detected R-peak timestamps."""
        samples: List[int] = []
        r_peaks_indices: List[int] = []

        rr_interval_s = 60.0 / self.baseline_hr_bpm
        samples_per_beat = int(rr_interval_s * self.sampling_rate_hz)

        for i in range(window_size):
            t = (self.phase + i) % samples_per_beat
            fraction = t / samples_per_beat

            # Base signal (isoelectric line ~512 on 10-bit ADC)
            val = 512.0

            # P wave (~0.12 - 0.20)
            if 0.12 <= fraction <= 0.20:
                val += 30.0 * math.sin((fraction - 0.12) / 0.08 * math.pi)
            # Q wave (~0.22 - 0.24)
            elif 0.22 <= fraction <= 0.24:
                val -= 40.0 * math.sin((fraction - 0.22) / 0.02 * math.pi)
            # R peak (~0.24 - 0.28)
            elif 0.24 < fraction <= 0.28:
                peak_height = 350.0 * math.sin((fraction - 0.24) / 0.04 * math.pi)
                val += peak_height
                if 0.255 <= fraction <= 0.265:
                    r_peaks_indices.append(i)
            # S wave (~0.28 - 0.32)
            elif 0.28 < fraction <= 0.32:
                val -= 60.0 * math.sin((fraction - 0.28) / 0.04 * math.pi)
            # T wave (~0.40 - 0.55)
            elif 0.40 <= fraction <= 0.55:
                val += 60.0 * math.sin((fraction - 0.40) / 0.15 * math.pi)

            # High-frequency physiological / ambient noise
            noise = random.gauss(0, 3.0)
            samples.append(int(max(0, min(1023, val + noise))))

        self.phase = (self.phase + window_size) % samples_per_beat

        rr_interval_ms = (60.0 / self.baseline_hr_bpm) * 1000.0 + random.uniform(-15.0, 15.0)

        return {
            "sensor": "AD8232_ECG",
            "samples": samples,
            "r_peak_detected": len(r_peaks_indices) > 0,
            "rr_interval_ms": round(rr_interval_ms, 1),
            "estimated_instant_bpm": round(60000.0 / rr_interval_ms, 1),
        }


class MockMAX30102:
    """
    Simulates MAX30102 Pulse Oximetry and Heart-Rate sensor over I2C to ESP32.
    """

    def __init__(self, target_spo2: float = 98.2, target_bpm: float = 74.0):
        self.target_spo2 = target_spo2
        self.target_bpm = target_bpm

    def read(self) -> Dict[str, Any]:
        spo2 = round(self.target_spo2 + random.uniform(-0.6, 0.4), 1)
        bpm = round(self.target_bpm + random.uniform(-1.5, 1.5), 1)
        return {
            "sensor": "MAX30102",
            "spo2_percent": min(100.0, max(70.0, spo2)),
            "pulse_bpm": bpm,
            "perfusion_index": round(random.uniform(1.2, 3.5), 2),
            "status": "VALID",
        }


class MockNIBP:
    """
    Simulates Non-Invasive Blood Pressure (NIBP) oscillometric measurement.
    """

    def __init__(self, sys_base: int = 120, dia_base: int = 80):
        self.sys_base = sys_base
        self.dia_base = dia_base

    def read(self) -> Dict[str, Any]:
        systolic = self.sys_base + random.randint(-4, 4)
        diastolic = self.dia_base + random.randint(-3, 3)
        mean_arterial_pressure = round((2 * diastolic + systolic) / 3, 1)

        category = "NORMAL"
        if systolic >= 140 or diastolic >= 90:
            category = "HYPERTENSION_STAGE_2"
        elif systolic >= 130 or diastolic >= 80:
            category = "HYPERTENSION_STAGE_1"
        elif systolic >= 120 and diastolic < 80:
            category = "ELEVATED"

        return {
            "sensor": "NIBP",
            "systolic_mmhg": systolic,
            "diastolic_mmhg": diastolic,
            "map_mmhg": mean_arterial_pressure,
            "category": category,
            "timestamp": time.time(),
        }
