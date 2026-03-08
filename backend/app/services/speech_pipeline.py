from __future__ import annotations

import io
import os
from math import exp
from pathlib import Path
from typing import Any

from app.schemas import AudioMetadata, LanguageRoutingResult, ResidentProfile, SpeechResult
from app.services.env_utils import ensure_dotenv_loaded


def resolve_dialect_label(
    *, language: str, exact_dialect: str, dialect_confidence: float, threshold: float = 0.75
) -> tuple[str, bool]:
    if dialect_confidence >= threshold:
        return exact_dialect, False

    fallback_by_language = {
        "Chinese": "Chinese (Southern dialect group)",
        "Malay": "Malay (general)",
        "Tamil": "Tamil (general)",
        "English": "English (general)",
    }
    return fallback_by_language.get(language, f"{language} (general)"), True


class SpeechPipelineService:
    model_version = "speech-openai-whisper-v1"

    _language_aliases = {
        "en": "English",
        "english": "English",
        "zh": "Chinese",
        "zh-cn": "Chinese",
        "zh-tw": "Chinese",
        "cmn": "Chinese",
        "yue": "Chinese",
        "mandarin": "Chinese",
        "cantonese": "Chinese",
        "chinese": "Chinese",
        "ms": "Malay",
        "malay": "Malay",
        "ta": "Tamil",
        "tamil": "Tamil",
    }

    def __init__(self) -> None:
        self.whisper_model = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")
        self.translation_model = os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4o-mini")

    def process(
        self,
        *,
        case_id: str,
        resident_profile: ResidentProfile,
        audio_metadata: AudioMetadata,
    ) -> SpeechResult:
        audio_bytes, audio_warning = self._read_audio_bytes(audio_metadata.stored_path)
        transcript_info = self._transcribe_audio_bytes(audio_bytes=audio_bytes, audio_filename=audio_metadata.filename)
        detected_language = self._normalize_language(transcript_info["detected_language"])
        dialect_confidence = round(float(transcript_info["language_confidence"]), 3)

        exact_dialect = resident_profile.preferred_dialect
        if detected_language.lower() != resident_profile.preferred_language.lower():
            exact_dialect = detected_language
        dialect_label, fallback_used = resolve_dialect_label(
            language=detected_language,
            exact_dialect=exact_dialect,
            dialect_confidence=dialect_confidence,
        )

        translation_info = self._translate_to_english(
            transcript_text=transcript_info["text"],
            detected_language=detected_language,
        )
        speech_confidence = transcript_info["asr_confidence"]
        if speech_confidence is None:
            speech_confidence = dialect_confidence

        evidence = [
            f"transcription_provider={transcript_info['provider']}",
            f"raw_detected_language={transcript_info['detected_language']}",
            f"detected_language={detected_language}",
            f"dialect_confidence={dialect_confidence:.2f}",
            "fallback_label_used=true" if fallback_used else "fallback_label_used=false",
            f"case_id={case_id}",
        ]
        if audio_warning:
            evidence.append(f"warning={audio_warning}")
        if transcript_info["warning"]:
            evidence.append(f"warning={transcript_info['warning']}")
        if translation_info["warning"]:
            evidence.append(f"warning={translation_info['warning']}")

        return SpeechResult(
            detected_language=detected_language,
            detected_dialect=exact_dialect,
            dialect_confidence=dialect_confidence,
            dialect_label=dialect_label,
            transcript_original=transcript_info["text"],
            transcript_english=translation_info["translated_text"],
            speech_confidence=round(max(0.0, min(1.0, float(speech_confidence))), 3),
            evidence=evidence,
        )

    @staticmethod
    def to_language_routing_result(speech_result: SpeechResult) -> LanguageRoutingResult:
        routing_map = {
            "Chinese": "Route to Chinese-language capable operator",
            "Malay": "Route to Malay-language capable operator",
            "Tamil": "Route to Tamil-language capable operator",
            "English": "Standard English operator queue",
        }
        fallback_used = speech_result.dialect_label != speech_result.detected_dialect
        routing_hint = routing_map.get(
            speech_result.detected_language,
            f"Route to operator with {speech_result.detected_language} support",
        )
        return LanguageRoutingResult(
            primary_language=speech_result.detected_language,
            dialect_label=speech_result.dialect_label,
            routing_hint=routing_hint,
            confidence=round((speech_result.speech_confidence + speech_result.dialect_confidence) / 2, 3),
            fallback_used=fallback_used,
            evidence=[
                f"detected_language={speech_result.detected_language}",
                f"dialect_label={speech_result.dialect_label}",
            ],
        )

    @classmethod
    def _normalize_language(cls, raw_language: str | None) -> str:
        normalized = (raw_language or "").strip().lower()
        if not normalized:
            return "Unknown"
        if normalized in cls._language_aliases:
            return cls._language_aliases[normalized]

        short_code = normalized.split("-", maxsplit=1)[0]
        if short_code in cls._language_aliases:
            return cls._language_aliases[short_code]

        return normalized.title()

    @staticmethod
    def _read_audio_bytes(stored_path: str) -> tuple[bytes, str | None]:
        path = Path(stored_path)
        try:
            return path.read_bytes(), None
        except Exception as exc:
            return b"", f"audio_read_failed:{type(exc).__name__}"

    def _transcribe_audio_bytes(self, *, audio_bytes: bytes, audio_filename: str) -> dict[str, Any]:
        default_result: dict[str, Any] = {
            "provider": "none",
            "text": "",
            "asr_confidence": None,
            "detected_language": "unknown",
            "language_confidence": 0.0,
            "warning": None,
        }

        if not audio_bytes:
            default_result["warning"] = "asr_openai: no audio provided"
            return default_result

        ensure_dotenv_loaded()
        if not os.getenv("OPENAI_API_KEY"):
            default_result["warning"] = "asr_openai: OPENAI_API_KEY not set"
            return default_result

        try:
            from openai import OpenAI
        except Exception:
            default_result["warning"] = "asr_openai: openai package unavailable"
            return default_result

        try:
            client = OpenAI()
            buffer = io.BytesIO(audio_bytes)
            buffer.name = audio_filename or "audio.wav"

            response = client.audio.transcriptions.create(
                model=self.whisper_model,
                file=buffer,
                response_format="verbose_json",
            )

            text = (getattr(response, "text", "") or "").strip()
            language = getattr(response, "language", None) or "unknown"

            segment_confidences: list[float] = []
            for segment in getattr(response, "segments", []) or []:
                avg_logprob = getattr(segment, "avg_logprob", None)
                if avg_logprob is None:
                    continue
                try:
                    segment_confidences.append(max(0.0, min(1.0, float(exp(float(avg_logprob))))))
                except Exception:
                    continue

            asr_confidence = (
                round(sum(segment_confidences) / len(segment_confidences), 3) if segment_confidences else None
            )
            language_confidence = 0.99 if language != "unknown" and bool(text) else 0.0

            return {
                "provider": "openai_whisper_api",
                "text": text,
                "asr_confidence": asr_confidence,
                "detected_language": language,
                "language_confidence": language_confidence,
                "warning": None,
            }
        except Exception as exc:
            default_result["warning"] = f"asr_openai failed: {exc}"
            return default_result

    def _translate_to_english(self, *, transcript_text: str, detected_language: str) -> dict[str, str | None]:
        if not transcript_text:
            return {"translated_text": "", "warning": None}

        language = detected_language.strip().lower()
        if language.startswith("en") or language == "english":
            return {"translated_text": transcript_text, "warning": None}

        ensure_dotenv_loaded()
        if not os.getenv("OPENAI_API_KEY"):
            return {
                "translated_text": transcript_text,
                "warning": "translation: OPENAI_API_KEY not set",
            }

        try:
            from openai import OpenAI
        except Exception:
            return {
                "translated_text": transcript_text,
                "warning": "translation: openai package unavailable",
            }

        try:
            client = OpenAI()
            prompt = "Translate to English. Preserve urgency and emergency meaning. Text:\n" + transcript_text
            response = client.chat.completions.create(
                model=self.translation_model,
                messages=[
                    {"role": "system", "content": "You are a careful emergency-call translator."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            translated = (response.choices[0].message.content or "").strip()
            return {"translated_text": translated or transcript_text, "warning": None}
        except Exception as exc:
            return {
                "translated_text": transcript_text,
                "warning": f"translation failed: {exc}",
            }
