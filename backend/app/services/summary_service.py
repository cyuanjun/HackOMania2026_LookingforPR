from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from typing import Any

from app.schemas import CaseDetail, RecommendedAction
from app.services.env_utils import ensure_dotenv_loaded


class SummaryService:
    _VALID_ACTIONS = {
        "operator_callback",
        "community_response",
        "ambulance_dispatch",
    }

    _ACTION_ALIASES = {
        "callback": "operator_callback",
        "operator callback": "operator_callback",
        "community": "community_response",
        "community response": "community_response",
        "ambulance": "ambulance_dispatch",
        "dispatch ambulance": "ambulance_dispatch",
    }

    def __init__(self) -> None:
        self.summary_model = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")
        self.max_points = 5

    @staticmethod
    def _address(case: CaseDetail) -> str:
        address_parts = [part for part in [case.resident_profile.block, case.resident_profile.unit] if part]
        address = " ".join(address_parts)
        if case.resident_profile.postal_code:
            address = f"{address} (S{case.resident_profile.postal_code})".strip()
        return address or "address unavailable"

    @staticmethod
    def _days_since_discharge(case: CaseDetail) -> int | None:
        raw = case.raw_medical_history.last_discharge_date
        if not raw:
            return None
        try:
            discharge_day = date.fromisoformat(raw)
            reference = datetime.fromisoformat(case.metadata.updated_at).date()
        except ValueError:
            return None
        elapsed = (reference - discharge_day).days
        return elapsed if elapsed >= 0 else None

    @staticmethod
    def _yes_no(value: bool) -> str:
        return "Yes" if value else "No"

    @staticmethod
    def _normalize_points(raw_text: str, max_points: int) -> list[str]:
        lines = [line.strip() for line in raw_text.replace("\r\n", "\n").split("\n") if line.strip()]
        points: list[str] = []
        for line in lines:
            normalized = line.lstrip("-*0123456789.) ").strip()
            if normalized:
                points.append(normalized)
            if len(points) >= max_points:
                break
        return points

    def _base_points(self, case: CaseDetail) -> list[str]:
        triage = case.triage_result
        speech = case.speech_result
        routing = case.language_routing_result
        medical_flags = case.derived_medical_flags
        history_flags = case.derived_history_flags

        if triage is None or speech is None or routing is None or medical_flags is None or history_flags is None:
            return [
                "Case is pending AI assessment.",
                "Speech, routing, derived flags, and triage summary will appear after processing completes.",
            ]

        discharge_days = self._days_since_discharge(case)
        recent_discharge_risk = discharge_days is not None and discharge_days <= 30
        total_calls = max(0, case.raw_call_history.total_calls_last_30d)
        false_alarms = max(0, case.raw_call_history.false_alarm_count_last_30d)
        false_alarm_ratio = (false_alarms / total_calls) if total_calls > 0 else 0.0
        social_vulnerability = case.resident_profile.living_alone and (
            case.resident_profile.mobility_status.strip().lower() != "independent"
        )

        active_medical_flags: list[str] = []
        if medical_flags.high_fall_risk:
            active_medical_flags.append("high_fall_risk")
        if medical_flags.cardio_risk:
            active_medical_flags.append("cardio_risk")
        if medical_flags.respiratory_risk:
            active_medical_flags.append("respiratory_risk")
        if medical_flags.cognitive_risk:
            active_medical_flags.append("cognitive_risk")
        if medical_flags.polypharmacy_risk:
            active_medical_flags.append("polypharmacy_risk")

        active_history_flags: list[str] = []
        if history_flags.frequent_caller:
            active_history_flags.append("frequent_caller")
        if history_flags.recent_urgent_pattern:
            active_history_flags.append("recent_urgent_pattern")
        if history_flags.repeated_false_alarms:
            active_history_flags.append("repeated_false_alarms")
        if history_flags.escalation_trend:
            active_history_flags.append("escalation_trend")

        transcript_hint = speech.transcript_english.strip() or speech.transcript_original.strip() or "No transcript text."
        if len(transcript_hint) > 120:
            transcript_hint = f"{transcript_hint[:117]}..."

        medical_text = ", ".join(active_medical_flags) if active_medical_flags else "none"
        history_text = ", ".join(active_history_flags) if active_history_flags else "none"
        discharge_text = f"{discharge_days}d" if discharge_days is not None else "no record"

        return [
            (
                f"Resident {case.resident_profile.name}, age {case.resident_profile.age}, "
                f"at {self._address(case)}; living alone {self._yes_no(case.resident_profile.living_alone)}."
            ),
            (
                f"Language {speech.detected_language}/{speech.dialect_label}; "
                f"route: {routing.routing_hint}; speech confidence {speech.speech_confidence:.2f}."
            ),
            (
                f"Medical flags: {medical_text}. History flags: {history_text}. "
                f"Calls 30d: {total_calls} total, {case.raw_call_history.urgent_calls_last_30d} urgent, {false_alarms} false alarms."
            ),
            (
                f"Derived features: fall {'high' if medical_flags.high_fall_risk else 'low'}, "
                f"cardiac {'high' if medical_flags.cardio_risk else 'low'}, discharge {'high' if recent_discharge_risk else 'low'} ({discharge_text}), "
                f"social {'high' if social_vulnerability else 'low'}, false-alarm ratio {false_alarm_ratio * 100:.0f}%."
            ),
            (
                f"Triage: {triage.urgency_class.value}, action {triage.recommended_action.value}, "
                f"confidence {triage.overall_confidence:.2f}. Transcript: {transcript_hint}"
            ),
        ]

    def _build_llm_payload(self, case: CaseDetail, fallback_points: list[str]) -> str:
        discharge_days = self._days_since_discharge(case)
        total_calls = max(0, case.raw_call_history.total_calls_last_30d)
        false_alarms = max(0, case.raw_call_history.false_alarm_count_last_30d)
        false_alarm_ratio = (false_alarms / total_calls) if total_calls > 0 else 0.0
        social_vulnerability = case.resident_profile.living_alone and (
            case.resident_profile.mobility_status.strip().lower() != "independent"
        )
        recent_discharge_risk = discharge_days is not None and discharge_days <= 30

        payload = {
            "case_id": case.metadata.case_id,
            "state": case.metadata.state.value,
            "resident_profile": case.resident_profile.model_dump(),
            "audio_metadata": case.audio_metadata.model_dump(),
            "raw_medical_history": case.raw_medical_history.model_dump(),
            "derived_medical_flags": case.derived_medical_flags.model_dump() if case.derived_medical_flags else None,
            "raw_call_history": case.raw_call_history.model_dump(),
            "derived_history_flags": case.derived_history_flags.model_dump() if case.derived_history_flags else None,
            "speech_result": case.speech_result.model_dump() if case.speech_result else None,
            "language_routing_result": case.language_routing_result.model_dump() if case.language_routing_result else None,
            "triage_result": case.triage_result.model_dump() if case.triage_result else None,
            "derived_features": {
                "fall_risk": "elevated" if (case.derived_medical_flags and case.derived_medical_flags.high_fall_risk) else "low",
                "cardiac_risk": "elevated" if (case.derived_medical_flags and case.derived_medical_flags.cardio_risk) else "low",
                "recent_discharge_risk": "elevated" if recent_discharge_risk else "low",
                "recent_discharge_days": discharge_days,
                "social_vulnerability": "elevated" if social_vulnerability else "low",
                "false_alarm_ratio_pct": round(false_alarm_ratio * 100),
            },
            "fallback_summary_points": fallback_points,
            "allowed_operator_recommendations": sorted(self._VALID_ACTIONS),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @classmethod
    def _normalize_action(cls, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().lower().replace("-", "_")
        if normalized in cls._VALID_ACTIONS:
            return normalized
        return cls._ACTION_ALIASES.get(normalized)

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def _llm_assessment(self, case: CaseDetail, fallback_points: list[str]) -> dict[str, Any] | None:
        triage = case.triage_result
        if triage is None:
            return None

        ensure_dotenv_loaded()
        if not os.getenv("OPENAI_API_KEY"):
            return None

        try:
            from openai import OpenAI
        except Exception:
            return None

        payload_json = self._build_llm_payload(case, fallback_points)

        system_prompt = (
            "You are a GovTech emergency triage summarizer for operators. "
            "Use only provided JSON facts. Do not hallucinate. Keep output concise and operational. "
            "Do not give treatment advice. Preserve uncertainty when confidence is low."
        )
        user_prompt = (
            "Return JSON only with keys:\n"
            "summary_points: array of 4-5 short sentences\n"
            "overall_risk_score_0_to_100: integer 0-100\n"
            "operator_recommendation: one of operator_callback, community_response, ambulance_dispatch\n"
            "recommendation_rationale: short sentence\n\n"
            "Rules:\n"
            "- Use all available features (raw + derived + triage + transcript + routing).\n"
            "- Summary must be point-form friendly and factual.\n"
            "- Recommendation must align with risk indicators and operator-in-control workflow.\n\n"
            f"CASE_DATA_JSON:\n{payload_json}"
        )

        try:
            client = OpenAI()
            response = client.chat.completions.create(
                model=self.summary_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            raw = (response.choices[0].message.content or "").strip()
            parsed = self._extract_json_object(raw)
            if not parsed:
                return None

            raw_points = parsed.get("summary_points")
            points: list[str] = []
            if isinstance(raw_points, list):
                joined = "\n".join(f"- {item}" for item in raw_points if isinstance(item, str))
                points = self._normalize_points(joined, self.max_points)
            if len(points) < 4:
                points = fallback_points[: self.max_points]

            raw_score = parsed.get("overall_risk_score_0_to_100")
            try:
                score = int(round(float(raw_score)))
            except Exception:
                score = int(round((triage.overall_confidence or 0.0) * 100))
            score = max(0, min(100, score))

            action = self._normalize_action(str(parsed.get("operator_recommendation", "")))
            if not action:
                action = triage.recommended_action.value

            rationale = str(parsed.get("recommendation_rationale", "")).strip()
            if not rationale:
                rationale = "Recommendation derived from multi-signal risk indicators and transcript context."
            if len(rationale) > 180:
                rationale = f"{rationale[:177]}..."

            return {
                "summary_points": points[: self.max_points],
                "overall_risk_score_0_to_100": score,
                "operator_recommendation": action,
                "recommendation_rationale": rationale,
            }
        except Exception:
            return None

    def generate(self, case: CaseDetail) -> str:
        fallback_points = self._base_points(case)
        llm = self._llm_assessment(case, fallback_points)
        points = fallback_points

        if llm:
            points = list(llm["summary_points"])
            if case.triage_result is not None:
                llm_score = int(llm["overall_risk_score_0_to_100"])
                llm_action = str(llm["operator_recommendation"])
                llm_reason = str(llm["recommendation_rationale"])

                case.triage_result.stage_evidence["llm_assessment"] = {
                    "model": self.summary_model,
                    "overall_risk_score_0_to_100": llm_score,
                    "operator_recommendation": llm_action,
                    "recommendation_rationale": llm_reason,
                }
                case.triage_result.stage_evidence["llm_overall_risk_score"] = llm_score
                case.triage_result.stage_evidence["llm_operator_recommendation"] = llm_action

                try:
                    case.triage_result.recommended_action = RecommendedAction(llm_action)
                except Exception:
                    pass

                case.triage_result.reasoning = (
                    f"{case.triage_result.reasoning} "
                    f"LLM risk score {llm_score}/100; recommended {llm_action}: {llm_reason}"
                )

                has_risk_line = any("risk score" in point.lower() for point in points)
                has_reco_line = any("recommend" in point.lower() for point in points)

                if not has_risk_line:
                    points.append(f"LLM overall risk score: {llm_score}/100.")
                if not has_reco_line:
                    points.append(f"LLM operator recommendation: {llm_action}. {llm_reason}")

        return "\n".join(f"- {point}" for point in points[: self.max_points])
