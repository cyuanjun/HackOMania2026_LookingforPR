"""Shared configuration for the audio pipeline."""

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
    yamnet_model_url: str = "https://tfhub.dev/google/yamnet/1"
    use_llm_explanations: bool = True
    openai_whisper_model: str = "whisper-1"
    openai_translation_model: str = "gpt-4o-mini"
    openai_explanation_model: str = "gpt-4o-mini"
    # Grouped keyword lists are easier to extend and keep in sync than flat fields.
    speech_keyword_groups: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "help": (
                "help",
                "help me",
                "emergency",
                "save me",
                "ambulance",
                "please send an ambulance",
                "call an ambulance",
            ),
            "fall": (
                "fall",
                "fell",
                "fallen",
                "slipped",
                "i fell",
                "i slipped",
            ),
            "cannot_breathe": (
                "cannot breathe",
                "can't breathe",
                "hard to breathe",
                "difficulty breathing",
                "shortness of breath",
            ),
            "distress_generic": (
                "help",
                "pain",
                "hurt",
                "fall",
                "fell",
                "bleeding",
                "can't breathe",
                "cannot breathe",
                "chest pain",
                "stroke",
                "dizzy",
                "heart",
            ),
            "fall_phrases": (
                "fall",
                "fell",
                "slipped",
                "i fell",
                "i slipped",
                "on the floor",
                "cannot get up",
                "can't get up",
            ),
            "breathing_difficulty": (
                "can't breathe",
                "cannot breathe",
                "shortness of breath",
                "breathing hard",
                "hard to breathe",
                "breathing is hard",
                "breathing is very hard",
                "breathing",
            ),
            "chest_pain": (
                "chest pain",
                "heart pain",
                "tight in my chest",
                "tightness in my chest",
                "chest tightness",
                "pressure in my chest",
                "heart feels uncomfortable",
            ),
            "distress_boost": (
                "please help",
                "help me",
                "i fell",
                "i fall",
                "hard to breathe",
                "breathing is hard",
                "on the floor",
                "cannot get up",
            ),
        }
    )
    speech_core_regex_patterns: dict[str, tuple[tuple[str, str], ...]] = field(
        default_factory=lambda: {
            "help": (
                ("help me", r"\bhelp(?:\s+me)?\b"),
                ("emergency", r"\bemergenc(?:y|ies)\b"),
                ("ambulance", r"\b(?:call|send)?\s*(?:an?\s+)?ambulance\b"),
            ),
            "fall": (
                ("i fell", r"\bi\s+(?:have\s+)?(?:just\s+)?f(?:a|e)ll(?:en)?\b"),
                ("i slipped", r"\bi\s+slipp(?:ed|ing)\b"),
                ("cannot get up", r"\b(?:can(?:not|'?t)|unable\s+to)\s+get\s+up\b"),
            ),
            "cannot_breathe": (
                ("cannot breathe", r"\b(?:can(?:not|'?t)|unable\s+to)\s+breathe\b"),
                ("hard to breathe", r"\b(?:hard|difficult)\s+to\s+breathe\b"),
                ("shortness of breath", r"\bshort(?:ness)?\s+of\s+breath\b"),
                ("chest pain", r"\b(?:chest|heart)\s+pain\b"),
            ),
        }
    )
    speech_urgency_help_weight: float = 0.28
    speech_urgency_fall_weight: float = 0.22
    speech_urgency_cannot_breathe_weight: float = 0.35
    speech_urgency_voice_strength_weight: float = 0.10
    speech_urgency_shouting_weight: float = 0.05
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
