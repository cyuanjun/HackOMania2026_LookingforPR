"""Shared configuration for the non-speech audio pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


VERSION = "0.1.0"


@dataclass(slots=True)
class AppConfig:
    target_sample_rate: int = 16_000
    min_duration_sec: float = 0.35
    max_duration_sec: float = 120.0
    supported_extensions: tuple[str, ...] = (".wav", ".mp3", ".m4a")
    silence_top_db: float = 35.0
    silence_after_impact_sec: float = 1.0
    peak_threshold: float = 0.72
    peak_distance_sec: float = 0.18
    explanation_limit: int = 4
    use_optional_yamnet: bool = True
    yamnet_bucket_top_k: int = 3
    crying_detect_threshold: float = 0.5
    shouting_detect_threshold: float = 0.5
    impact_detect_threshold: float = 0.6
    silence_after_impact_detect_threshold: float = 0.65
    fall_sound_detect_threshold: float = 0.65
    breathing_irregularity_detect_threshold: float = 0.7
    silence_after_impact_gate_threshold: float = 0.55
    yamnet_bucket_patterns: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "crying": (
                "crying",
                "sobbing",
                "sob",
                "whimper",
                "moan",
                "groan",
                "wail",
                "whine",
                "sniff",
                "lament",
                "bawl",
            ),
            "shouting": ("shout", "yell", "scream", "shriek"),
            "impact": ("thud", "bang", "crash", "slam", "breaking", "smash", "thump", "thwack"),
            "breathing": ("breathing", "wheeze", "gasp", "snoring", "pant", "respir"),
        }
    )


DEFAULT_CONFIG = AppConfig()
