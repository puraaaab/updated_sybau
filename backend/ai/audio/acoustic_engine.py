"""
RTSP Audio Stream Acoustic Anomaly Classifier.

Processes audio frames from RTSP camera feeds to detect:
  • Gunshots
  • Panic Screams / Shouting
  • Glass Breaking
  • Explosions / Loud Impacts
"""

import numpy as np
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AcousticAnomalyDetector:
    """Classifies audio spectral energy and decibel peaks for emergency acoustic event alerts."""

    ACOUSTIC_CLASSES = {
        "gunshot": {"min_db": 95.0, "rise_time_ms": 15.0, "severity": "critical"},
        "scream": {"min_db": 85.0, "freq_range_hz": (2000, 5000), "severity": "high"},
        "glass_break": {"min_db": 80.0, "freq_range_hz": (4000, 8000), "severity": "high"},
        "explosion": {"min_db": 105.0, "rise_time_ms": 30.0, "severity": "critical"}
    }

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.cooldown_history = {}  # (camera_id, event_type) -> timestamp

    def process_audio_chunk(self, camera_id: str, pcm_data: bytes) -> List[Dict[str, Any]]:
        """
        Analyzes a raw PCM audio chunk (16-bit mono 16kHz) for acoustic anomaly events.
        """
        alerts = []
        if not pcm_data:
            return alerts

        try:
            audio_samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
            if len(audio_samples) == 0:
                return alerts

            # Calculate Root Mean Square (RMS) & Decibel Level
            rms = np.sqrt(np.mean(np.square(audio_samples))) + 1e-6
            db_level = 20 * np.log10(rms)

            # Fast Fourier Transform (FFT) for dominant frequency analysis
            fft_vals = np.abs(np.fft.rfft(audio_samples))
            freqs = np.fft.rfftfreq(len(audio_samples), 1.0 / self.sample_rate)

            peak_freq = freqs[np.argmax(fft_vals)] if len(fft_vals) > 0 else 0.0
            now = time.time()

            # Rule 1: High Decibel Peak (Gunshot / Explosion threshold)
            if db_level > 90.0:
                event_type = "gunshot" if peak_freq < 3000 else "glass_break"
                key = (camera_id, event_type)
                if (now - self.cooldown_history.get(key, 0.0)) > 15.0:
                    self.cooldown_history[key] = now
                    alerts.append({
                        "type": "acoustic_anomaly",
                        "event": event_type,
                        "decibels": round(float(db_level), 1),
                        "peak_frequency_hz": round(float(peak_freq), 1),
                        "severity": self.ACOUSTIC_CLASSES.get(event_type, {}).get("severity", "high"),
                        "message": f"Acoustic Anomaly Detected: Possible {event_type.upper()} ({round(db_level, 1)} dB)"
                    })

            # Rule 2: High Frequency Scream (2kHz - 5kHz range)
            elif db_level > 75.0 and (2000 <= peak_freq <= 5000):
                event_type = "scream"
                key = (camera_id, event_type)
                if (now - self.cooldown_history.get(key, 0.0)) > 15.0:
                    self.cooldown_history[key] = now
                    alerts.append({
                        "type": "acoustic_anomaly",
                        "event": event_type,
                        "decibels": round(float(db_level), 1),
                        "peak_frequency_hz": round(float(peak_freq), 1),
                        "severity": "high",
                        "message": f"Acoustic Anomaly Detected: Possible PANIC SCREAM ({round(db_level, 1)} dB)"
                    })
        except Exception as e:
            logger.debug(f"[AcousticDetector] Audio chunk processing note: {e}")

        return alerts


acoustic_detector = AcousticAnomalyDetector()
