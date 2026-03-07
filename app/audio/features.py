"""Acoustic feature extraction for non-speech reasoning."""

from __future__ import annotations

from typing import Any

import numpy as np

from app.audio.silence import detect_silence_regions


def _find_peaks(signal: np.ndarray, threshold: float, min_distance_samples: int) -> np.ndarray:
    peaks: list[int] = []
    last_peak = -min_distance_samples
    for idx in range(1, len(signal) - 1):
        if signal[idx] >= threshold and signal[idx] >= signal[idx - 1] and signal[idx] >= signal[idx + 1]:
            if idx - last_peak >= min_distance_samples:
                peaks.append(idx)
                last_peak = idx
    return np.asarray(peaks, dtype=np.int32)


def extract_acoustic_features(
    audio: np.ndarray,
    sample_rate: int,
    silence_top_db: float,
    peak_threshold: float,
    peak_distance_sec: float,
) -> dict[str, Any]:
    """Compute robust demo-friendly acoustic features."""

    defaults = {
        "rms_energy_mean": 0.0,
        "rms_energy_max": 0.0,
        "zero_crossing_rate_mean": 0.0,
        "spectral_centroid_mean": 0.0,
        "bandwidth_mean": 0.0,
        "onset_strength_mean": 0.0,
        "silence_ratio": 1.0,
        "peak_count": 0,
        "sudden_impact_score": 0.0,
        "breathing_variability_score": 0.0,
        "unstable_modulation_score": 0.0,
        "sustained_high_energy_score": 0.0,
        "peak_indices": np.asarray([], dtype=np.int32),
        "peak_index": None,
    }
    if audio.size == 0:
        return defaults

    frame_length = 1024
    hop_length = 256

    def _frame_audio(signal: np.ndarray) -> np.ndarray:
        if len(signal) < frame_length:
            padded = np.pad(signal, (0, frame_length - len(signal)))
            return padded.reshape(1, -1)
        frames = []
        for start in range(0, len(signal) - frame_length + 1, hop_length):
            frames.append(signal[start : start + frame_length])
        return np.asarray(frames, dtype=np.float32)

    frames = _frame_audio(audio)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    zcr = np.mean(np.abs(np.diff(np.signbit(frames), axis=1)), axis=1)

    window = np.hanning(frame_length).astype(np.float32)
    spectra = np.abs(np.fft.rfft(frames * window, axis=1))
    freqs = np.fft.rfftfreq(frame_length, d=1.0 / sample_rate)
    spectral_sums = np.sum(spectra, axis=1) + 1e-6
    centroid = np.sum(spectra * freqs, axis=1) / spectral_sums
    bandwidth = np.sqrt(np.sum(spectra * np.square(freqs - centroid[:, None]), axis=1) / spectral_sums)

    frame_energy_diff = np.diff(rms, prepend=rms[0])
    onset_env = np.maximum(frame_energy_diff, 0.0)
    silence = detect_silence_regions(audio, sample_rate, top_db=silence_top_db)

    amplitude = np.abs(audio)
    min_distance_samples = max(1, int(sample_rate * peak_distance_sec))
    peak_indices = _find_peaks(amplitude, threshold=peak_threshold, min_distance_samples=min_distance_samples)
    peak_index = int(np.argmax(amplitude)) if amplitude.size else None
    peak_norm = min(float(np.max(amplitude)) / 0.95, 1.0)
    onset_norm = min(float(np.percentile(onset_env, 95)) / 0.12, 1.0) if onset_env.size else 0.0
    broadband_norm = min(float(np.percentile(bandwidth, 90)) / 3500.0, 1.0) if bandwidth.size else 0.0

    # A short, sharp burst is more consistent with impact than with sustained vocal activity.
    short_burst_score = 0.0
    if peak_index is not None and amplitude[peak_index] > 0:
        burst_threshold = max(float(amplitude[peak_index]) * 0.25, 0.08)
        left = peak_index
        right = peak_index
        while left > 0 and amplitude[left] >= burst_threshold:
            left -= 1
        while right < len(amplitude) - 1 and amplitude[right] >= burst_threshold:
            right += 1
        burst_width_sec = (right - left) / sample_rate
        short_burst_score = float(np.clip(1.0 - (burst_width_sec / 0.22), 0.0, 1.0))

    sudden_impact_score = np.clip(
        (0.35 * peak_norm) + (0.25 * onset_norm) + (0.15 * broadband_norm) + (0.25 * short_burst_score),
        0.0,
        1.0,
    )

    abs_audio = np.abs(audio)
    window = max(sample_rate // 4, 1)
    envelope = None
    if len(abs_audio) >= window:
        kernel = np.ones(window, dtype=np.float32) / window
        envelope = np.convolve(abs_audio, kernel, mode="same")
        breathing_variability = float(np.std(envelope) / (np.mean(envelope) + 1e-6))
    else:
        breathing_variability = 0.0

    # Envelope instability is a lightweight proxy for crying-like variation.
    unstable_modulation = 0.0
    if envelope is not None and len(envelope) > 4:
        env_diff = np.abs(np.diff(envelope))
        env_mean = float(np.mean(envelope)) + 1e-6
        unstable_modulation = float(np.clip((np.std(env_diff) / env_mean) / 0.25, 0.0, 1.0))

    # Sustained elevated RMS helps separate shouting from impulse-like bursts.
    high_energy_threshold = max(0.08, float(np.percentile(rms, 75)))
    high_energy_mask = rms >= high_energy_threshold
    longest_run = 0
    current_run = 0
    for is_high in high_energy_mask:
        if is_high:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    longest_run_sec = longest_run * hop_length / sample_rate
    high_energy_level = min(float(np.percentile(rms, 90)) / 0.2, 1.0)
    sustained_high_energy_score = float(
        np.clip((0.4 * high_energy_level) + (0.6 * min(longest_run_sec / 0.9, 1.0)), 0.0, 1.0)
    )

    return {
        "rms_energy_mean": round(float(np.mean(rms)), 4),
        "rms_energy_max": round(float(np.max(rms)), 4),
        "zero_crossing_rate_mean": round(float(np.mean(zcr)), 4),
        "spectral_centroid_mean": round(float(np.mean(centroid)), 2),
        "bandwidth_mean": round(float(np.mean(bandwidth)), 2),
        "onset_strength_mean": round(float(np.mean(onset_env)), 4) if onset_env.size else 0.0,
        "silence_ratio": round(float(silence["silence_ratio"]), 3),
        "peak_count": int(len(peak_indices)),
        "sudden_impact_score": round(float(sudden_impact_score), 3),
        "breathing_variability_score": round(float(min(breathing_variability / 1.5, 1.0)), 3),
        "unstable_modulation_score": round(float(min((0.85 * unstable_modulation) + (0.15 * min(breathing_variability / 1.2, 1.0)), 1.0)), 3),
        "sustained_high_energy_score": round(float(sustained_high_energy_score), 3),
        "peak_indices": peak_indices,
        "peak_index": peak_index,
    }
