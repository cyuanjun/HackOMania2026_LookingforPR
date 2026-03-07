"""Non-speech distress event detection."""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any

import numpy as np

from app.audio.features import extract_acoustic_features
from app.audio.silence import detect_silence_after_impact
from app.config import AppConfig, DEFAULT_CONFIG


def _clamp(value: float) -> float:
    return round(float(np.clip(value, 0.0, 1.0)), 3)


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _ensure_ssl_ca_bundle() -> None:
    """Point HTTPS cert verification to certifi CA bundle when available."""

    try:
        import certifi
    except Exception:
        return

    ca_path = certifi.where()
    if ca_path:
        os.environ.setdefault("SSL_CERT_FILE", ca_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)
        os.environ.setdefault("CURL_CA_BUNDLE", ca_path)


def _load_class_names_from_csv(csv_path: str) -> list[str]:
    try:
        with open(csv_path, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            names: list[str] = []
            for row in reader:
                # YAMNet class map usually exposes "display_name".
                if "display_name" in row and row["display_name"]:
                    names.append(row["display_name"])
                elif "name" in row and row["name"]:
                    names.append(row["name"])
            return names
    except Exception:
        return []


def _optional_yamnet_scores(audio: np.ndarray, sample_rate: int, config: AppConfig) -> dict[str, float]:
    """Try YAMNet if tensorflow_hub is already available.

    TODO: Replace this with a cached model service for production deployment.
    """

    scores = {
        "crying": 0.0,
        "shouting": 0.0,
        "impact": 0.0,
        "breathing": 0.0,
    }
    if not config.use_optional_yamnet:
        return scores

    try:
        import tensorflow as tf
        import tensorflow_hub as hub
    except Exception:
        return scores

    try:
        _ensure_ssl_ca_bundle()
        model = hub.load(config.yamnet_model_url)
        waveform = tf.convert_to_tensor(audio, dtype=tf.float32)
        yamnet_scores, *rest = model(waveform)
        mean_scores = np.mean(yamnet_scores.numpy(), axis=0)

        class_names: list[str] = []
        if rest and hasattr(rest[-1], "numpy"):
            maybe_map = rest[-1].numpy()
            if len(maybe_map.shape) == 1 and maybe_map.dtype.kind in {"S", "U", "O"}:
                class_names = [name.decode("utf-8") if isinstance(name, bytes) else str(name) for name in maybe_map]
        if not class_names and hasattr(model, "class_map_path"):
            class_map_path = model.class_map_path().numpy().decode("utf-8")
            with tf.io.gfile.GFile(class_map_path) as csv_file:
                reader = csv.DictReader(io.StringIO(csv_file.read()))
                class_names = [row["display_name"] for row in reader]
        if not class_names:
            # Fallback: inspect resolved TF-Hub cache directory for class map CSV.
            try:
                resolved = hub.resolve(config.yamnet_model_url)
                resolved_path = Path(str(resolved))
                csv_candidates = sorted(resolved_path.rglob("*class_map*.csv"))
                for candidate in csv_candidates:
                    class_names = _load_class_names_from_csv(str(candidate))
                    if class_names:
                        break
            except Exception:
                pass
        if not class_names:
            return scores

        pairs = dict(zip(class_names, mean_scores, strict=False))

        def _bucket_confidence(bucket_name: str) -> float:
            # Aggregate related YAMNet classes into a stable event bucket instead of trusting one label.
            patterns = config.yamnet_bucket_patterns[bucket_name]
            matched_scores = [
                float(score)
                for class_name, score in pairs.items()
                if any(pattern in class_name.lower() for pattern in patterns)
            ]
            if not matched_scores:
                return 0.0
            matched_scores.sort(reverse=True)
            top_scores = matched_scores[: config.yamnet_bucket_top_k]
            confidence = (0.7 * top_scores[0]) + (0.3 * float(np.mean(top_scores)))
            if bucket_name == "crying":
                confidence = (0.85 * confidence) + (0.15 * top_scores[0])
            return _clip01(confidence)

        return {
            "crying": _bucket_confidence("crying"),
            "shouting": _bucket_confidence("shouting"),
            "impact": _bucket_confidence("impact"),
            "breathing": _bucket_confidence("breathing"),
        }
    except Exception:
        return scores


def detect_events(
    audio: np.ndarray,
    sample_rate: int,
    config: AppConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Detect distress-related non-speech events with YAMNet-first evidence plus heuristics."""

    defaults = {
        "non_speech_events": {
            "crying_detected": False,
            "crying_confidence": 0.0,
            "shouting_detected": False,
            "shouting_confidence": 0.0,
            "impact_detected": False,
            "impact_confidence": 0.0,
            "fall_sound_detected": False,
            "fall_sound_confidence": 0.0,
            "breathing_irregularity_detected": False,
            "breathing_irregularity_confidence": 0.0,
            "silence_after_impact_detected": False,
            "silence_after_impact_confidence": 0.0,
        },
        "acoustic_features": {
            "rms_energy_mean": 0.0,
            "rms_energy_max": 0.0,
            "silence_ratio": 1.0,
            "peak_count": 0,
            "sudden_impact_score": 0.0,
            "breathing_variability_score": 0.0,
        },
        "explanations": [],
        "event_model": "heuristic_refinement_v2",
    }
    if audio.size == 0:
        return defaults

    try:
        features = extract_acoustic_features(
            audio,
            sample_rate,
            silence_top_db=config.silence_top_db,
            peak_threshold=config.peak_threshold,
            peak_distance_sec=config.peak_distance_sec,
        )
        yamnet = _optional_yamnet_scores(audio, sample_rate, config)
        yamnet_available = max(yamnet.values()) > 0.0
        impact_index = int(features["peak_index"]) if features["peak_index"] is not None else None

        unstable_modulation = float(features["unstable_modulation_score"])
        sustained_high_energy = float(features["sustained_high_energy_score"])

        rms_mean = float(features["rms_energy_mean"])
        rms_max = float(features["rms_energy_max"])
        silence_ratio = float(features["silence_ratio"])
        impact_score = float(features["sudden_impact_score"])
        breathing_var = float(features["breathing_variability_score"])
        low_energy_score = float(np.clip(1.0 - (rms_mean / 0.12), 0.0, 1.0))
        crying_texture_score = float(
            np.clip(
                (0.4 * unstable_modulation)
                + (0.25 * silence_ratio)
                + (0.2 * breathing_var)
                + (0.15 * low_energy_score),
                0.0,
                1.0,
            )
        )

        if yamnet_available:
            # YAMNet is the primary evidence source; heuristics only refine confidence.
            crying_conf = _clamp((0.58 * yamnet["crying"]) + (0.42 * crying_texture_score))
            shouting_conf = _clamp((0.7 * yamnet["shouting"]) + (0.3 * sustained_high_energy))
            impact_conf = _clamp((0.5 * yamnet["impact"]) + (0.5 * impact_score))
            breathing_conf = _clamp((0.75 * yamnet["breathing"]) + (0.25 * breathing_var))
        else:
            # If YAMNet is unavailable, keep the pipeline alive with conservative heuristic-only scores.
            crying_conf = _clamp((0.85 * crying_texture_score) + (0.15 * min(breathing_var, 0.8)))
            shouting_conf = _clamp(sustained_high_energy)
            impact_conf = _clamp((0.9 * impact_score) + (0.1 * min(features["peak_count"], 1.0)))
            breathing_conf = _clamp(breathing_var * max(0.0, 1.0 - impact_score))
        _, silence_conf = detect_silence_after_impact(
            audio,
            sample_rate,
            impact_index=impact_index,
            top_db=config.silence_top_db,
            min_silence_sec=config.silence_after_impact_sec,
            impact_confidence=impact_conf,
            impact_gate_threshold=config.silence_after_impact_gate_threshold,
        )
        fall_conf = _clamp((0.65 * impact_conf) + (0.25 * silence_conf) + (0.10 * max(crying_conf, shouting_conf)))

        explanations: list[tuple[float, str]] = []
        if crying_conf >= 0.45:
            if yamnet["crying"] > 0.0 and crying_texture_score > 0.2:
                explanations.append((crying_conf, "YAMNet detected crying-like audio and the signal showed unstable amplitude modulation."))
            elif yamnet["crying"] > 0.0:
                explanations.append((crying_conf, "YAMNet detected crying-like audio patterns."))
            else:
                explanations.append((crying_conf, "Low-energy unstable vocal texture resembles crying-like audio."))
        if shouting_conf >= 0.45:
            if yamnet["shouting"] > 0.0 and sustained_high_energy > 0.2:
                explanations.append((shouting_conf, "YAMNet detected shouting-like audio and energy stayed elevated over time."))
            elif sustained_high_energy > 0.35:
                explanations.append((shouting_conf, "Sustained high energy suggests shouting or raised voice activity."))
        if impact_conf >= 0.45:
            if yamnet["impact"] > 0.0 and impact_score > 0.2:
                explanations.append((impact_conf, "Impact confidence increased due to both YAMNet impact classes and a strong sudden energy peak."))
            else:
                explanations.append((impact_conf, "Strong sudden peak suggests an impact-like event."))
        if silence_conf >= 0.45:
            explanations.append((silence_conf, "Post-impact audio contains a substantial low-energy region."))
        if fall_conf >= 0.45:
            explanations.append((fall_conf, "Fall-like confidence increased because impact and post-impact silence co-occurred."))
        if breathing_conf >= 0.45:
            if yamnet["breathing"] > 0.0 and breathing_var > 0.15:
                explanations.append((breathing_conf, "YAMNet detected breathing-like audio and the envelope looked irregular."))
            elif breathing_var > 0.25:
                explanations.append((breathing_conf, "Envelope variability suggests irregular breathing-like acoustics."))
        if silence_ratio >= 0.5:
            explanations.append((min(silence_ratio, 1.0), "Large fraction of the clip is low-energy or silent."))

        explanations.sort(key=lambda item: item[0], reverse=True)

        return {
            "non_speech_events": {
                "crying_detected": crying_conf >= config.crying_detect_threshold,
                "crying_confidence": crying_conf,
                "shouting_detected": shouting_conf >= config.shouting_detect_threshold,
                "shouting_confidence": shouting_conf,
                "impact_detected": impact_conf >= config.impact_detect_threshold,
                "impact_confidence": impact_conf,
                "fall_sound_detected": fall_conf >= config.fall_sound_detect_threshold,
                "fall_sound_confidence": fall_conf,
                "breathing_irregularity_detected": breathing_conf >= config.breathing_irregularity_detect_threshold,
                "breathing_irregularity_confidence": breathing_conf,
                "silence_after_impact_detected": silence_conf >= config.silence_after_impact_detect_threshold,
                "silence_after_impact_confidence": silence_conf,
            },
            "acoustic_features": {
                "rms_energy_mean": _clamp(rms_mean),
                "rms_energy_max": _clamp(rms_max),
                "silence_ratio": _clamp(silence_ratio),
                "peak_count": int(features["peak_count"]),
                "sudden_impact_score": _clamp(impact_score),
                "breathing_variability_score": _clamp(breathing_var),
            },
            "explanations": [text for _, text in explanations[: config.explanation_limit]],
            "event_model": "yamnet_first_refinement_v2" if yamnet_available else "heuristic_refinement_v2",
        }
    except Exception:
        return defaults
