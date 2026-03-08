from __future__ import annotations

from datetime import date
from typing import Mapping

from app.schemas import (
    DerivedHistoryFlags,
    DerivedMedicalFlags,
    LanguageRoutingResult,
    RawCallHistory,
    RawMedicalHistory,
    RecommendedAction,
    ResidentProfile,
    SpeechResult,
    TriageResult,
    UrgencyClass,
)


class FusionEngineService:
    _ACTION_RANK: dict[RecommendedAction, int] = {
        RecommendedAction.OPERATOR_CALLBACK: 0,
        RecommendedAction.COMMUNITY_RESPONSE: 1,
        RecommendedAction.AMBULANCE_DISPATCH: 2,
    }
    _POLICY_ACTION_MAP: dict[str, RecommendedAction] = {
        "ambulance": RecommendedAction.AMBULANCE_DISPATCH,
        "community_responder": RecommendedAction.COMMUNITY_RESPONSE,
        "welfare_check": RecommendedAction.COMMUNITY_RESPONSE,
    }
    _DEFAULT_EMERGENCY_MIN_ACTIONS: dict[str, str] = {
        "stroke_like": "ambulance",
        "cardiac": "ambulance",
        "breathing_distress": "community_responder",
        "bleeding": "ambulance",
        "head_injury": "ambulance",
        "unconscious": "ambulance",
        "no_response": "ambulance",
        "fall": "welfare_check",
        "confusion": "welfare_check",
    }

    def __init__(self, emergency_min_actions: Mapping[str, str] | None = None) -> None:
        base = dict(self._DEFAULT_EMERGENCY_MIN_ACTIONS)
        if emergency_min_actions:
            for key, value in emergency_min_actions.items():
                normalized_key = key.strip().lower()
                normalized_value = value.strip().lower()
                if normalized_key and normalized_value in self._POLICY_ACTION_MAP:
                    base[normalized_key] = normalized_value
        self.emergency_min_actions = base

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _minimum_urgency_for_action(action: RecommendedAction) -> UrgencyClass:
        if action == RecommendedAction.AMBULANCE_DISPATCH:
            return UrgencyClass.URGENT
        if action == RecommendedAction.COMMUNITY_RESPONSE:
            return UrgencyClass.UNCERTAIN
        return UrgencyClass.NON_URGENT

    @staticmethod
    def _align_risk_score_to_urgency_band(*, risk_score: float, urgency: UrgencyClass) -> float:
        if urgency == UrgencyClass.URGENT:
            return max(risk_score, 0.72)
        if urgency == UrgencyClass.UNCERTAIN:
            return max(0.40, min(risk_score, 0.67))
        return min(risk_score, 0.39)

    @staticmethod
    def _days_since_iso(date_text: str | None) -> int | None:
        if not date_text:
            return None
        try:
            parsed = date.fromisoformat(date_text)
        except ValueError:
            return None
        return max(0, (date.today() - parsed).days)

    @staticmethod
    def _incident_features(speech: SpeechResult) -> tuple[dict[str, float], list[str]]:
        text = f"{speech.transcript_english or ''} {speech.transcript_original or ''}".lower()
        cues: list[str] = []

        fall_words = ("fell", "fall", "slipped", "slip", "tripped", "trip")
        cannot_get_up_words = ("can't get up", "cannot get up", "unable to get up", "cannot stand", "cant stand")
        pain_words = ("pain", "hurts", "hurt", "very painful", "severe pain")
        distress_words = ("help", "please send", "send someone", "emergency", "urgent")
        breathing_words = ("can't breathe", "cannot breathe", "breathless", "shortness of breath", "no air")
        crying_words = ("cry", "crying", "sob", "wail", "whimper")
        shouting_words = ("shout", "shouting", "yell", "yelling", "scream", "screaming")

        has_fall = any(word in text for word in fall_words)
        has_cannot_get_up = any(word in text for word in cannot_get_up_words)
        has_pain = any(word in text for word in pain_words)
        has_distress = any(word in text for word in distress_words)
        has_breathing = any(word in text for word in breathing_words)
        has_crying = any(word in text for word in crying_words)
        has_shouting = any(word in text for word in shouting_words) or text.count("!") >= 2

        if has_fall:
            cues.append("fall-related cue")
        if has_cannot_get_up:
            cues.append("unable-to-get-up cue")
        if has_pain:
            cues.append("pain cue")
        if has_distress:
            cues.append("distress/help cue")
        if has_crying:
            cues.append("crying cue")
        if has_shouting:
            cues.append("shouting cue")
        if has_breathing:
            cues.append("cannot-breathe cue")

        base_silence_proxy = FusionEngineService._clamp01((0.72 - speech.speech_confidence) / 0.72)
        silence_after_impact_proxy = max(base_silence_proxy, 0.35 if has_cannot_get_up else 0.0)
        impact_amplitude_proxy = 1.0 if has_cannot_get_up else (0.75 if has_pain else (0.45 if has_fall else 0.0))

        features = {
            "fall_sound_detected": float(has_fall),
            "impact_amplitude": impact_amplitude_proxy,
            "silence_after_impact": silence_after_impact_proxy,
            "crying_detected": float(has_crying or has_distress),
            "shouting_detected": float(has_shouting),
            "cannot_breathe_keyword": float(has_breathing),
        }
        return features, cues

    @staticmethod
    def _vulnerability_features(
        *,
        resident_profile: ResidentProfile | None,
        resident_age: int | None,
    ) -> tuple[dict[str, float], list[str]]:
        cues: list[str] = []
        age = resident_profile.age if resident_profile is not None else resident_age
        living_alone = bool(resident_profile.living_alone) if resident_profile is not None else False

        mobility_status = (resident_profile.mobility_status if resident_profile is not None else "").strip().lower()
        independent_terms = {"independent", "self-ambulating", "self ambulating", "mobile"}
        mobility_risk = bool(mobility_status and mobility_status not in independent_terms)

        emergency_contact = (resident_profile.emergency_contact if resident_profile is not None else "").strip().lower()
        caregiver_unavailable = (not emergency_contact) or emergency_contact in {"-", "none", "n/a", "na", "unknown"}

        elderly_score = 0.0
        if age is not None:
            if age >= 90:
                elderly_score = 1.0
            elif age >= 85:
                elderly_score = 0.9
            elif age >= 80:
                elderly_score = 0.75
            elif age >= 75:
                elderly_score = 0.6
            elif age >= 70:
                elderly_score = 0.45
        if elderly_score > 0.0 and age is not None:
            cues.append(f"age vulnerability ({age})")
        if living_alone:
            cues.append("living alone")
        if mobility_risk:
            cues.append(f"mobility risk ({mobility_status})")
        if caregiver_unavailable:
            cues.append("caregiver contact unavailable")

        return (
            {
                "living_alone_flag": float(living_alone),
                "elderly_flag": elderly_score,
                "mobility_risk_flag": float(mobility_risk),
                "caregiver_unavailable_flag": float(caregiver_unavailable),
            },
            cues,
        )

    def _medical_features(
        self,
        *,
        medical_flags: DerivedMedicalFlags,
        raw_medical_history: RawMedicalHistory | None,
    ) -> tuple[dict[str, float], list[str]]:
        cues: list[str] = []
        diagnoses = {item.strip().lower() for item in (raw_medical_history.diagnoses if raw_medical_history else [])}
        diabetes = any(
            "diabetes" in item
            or item in {"dm", "dm2", "t2dm", "type_2_diabetes", "ckd", "chronic_kidney_disease"}
            for item in diagnoses
        )
        dementia = medical_flags.cognitive_risk or any(
            "dementia" in item or "alzheimer" in item for item in diagnoses
        )
        discharge_days = self._days_since_iso(raw_medical_history.last_discharge_date if raw_medical_history else None)
        recent_discharge = bool(discharge_days is not None and discharge_days <= 30)

        if medical_flags.cardio_risk:
            cues.append("cardiac risk history present")
        if medical_flags.high_fall_risk:
            cues.append("fall risk history present")
        if diabetes:
            cues.append("diabetes risk factor present")
        if dementia:
            cues.append("dementia/cognitive risk present")
        if recent_discharge and discharge_days is not None:
            cues.append(f"recent discharge ({discharge_days}d)")

        return (
            {
                "cardiac_risk_flag": float(medical_flags.cardio_risk),
                "fall_risk_flag": float(medical_flags.high_fall_risk),
                "diabetes_flag": float(diabetes),
                "dementia_risk_flag": float(dementia),
                "recent_discharge_flag": float(recent_discharge),
            },
            cues,
        )

    @staticmethod
    def _history_features(
        *,
        history_flags: DerivedHistoryFlags,
        raw_call_history: RawCallHistory | None,
    ) -> tuple[dict[str, float], list[str]]:
        cues: list[str] = []
        total_calls = raw_call_history.total_calls_last_30d if raw_call_history is not None else 0
        urgent_calls = raw_call_history.urgent_calls_last_30d if raw_call_history is not None else 0
        false_alarms = raw_call_history.false_alarm_count_last_30d if raw_call_history is not None else 0

        false_alarm_rate = (false_alarms / total_calls) if total_calls > 0 else 0.0
        repeat_real_incident = history_flags.recent_urgent_pattern or history_flags.escalation_trend
        recent_emergency_history = urgent_calls >= 1 or history_flags.recent_urgent_pattern

        if total_calls > 0:
            cues.append(f"recent calls={total_calls}, urgent={urgent_calls}, false alarms={false_alarms}")
        if repeat_real_incident:
            cues.append("repeat real incident pattern")
        if recent_emergency_history:
            cues.append("recent emergency history")
        if false_alarm_rate >= 0.3:
            cues.append(f"high false alarm ratio ({false_alarm_rate * 100:.0f}%)")

        return (
            {
                "false_alarm_rate": false_alarm_rate,
                "repeat_real_incident_flag": float(repeat_real_incident),
                "recent_emergency_history_flag": float(recent_emergency_history),
            },
            cues,
        )

    @staticmethod
    def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)

    def _detect_emergency_tags(
        self,
        *,
        speech: SpeechResult,
        medical_flags: DerivedMedicalFlags,
    ) -> list[str]:
        text = f"{speech.transcript_original or ''} {speech.transcript_english or ''}".lower()
        tags: list[str] = []

        stroke_words = (
            "stroke",
            "face droop",
            "slurred speech",
            "can not speak",
            "cannot speak",
            "numb",
            "weakness one side",
            "one side weak",
        )
        cardiac_words = ("chest pain", "heart attack", "heart pain", "palpitation", "cardiac", "my heart")
        breathing_words = ("can't breathe", "cannot breathe", "breathless", "shortness of breath", "no air", "gasping")
        bleeding_words = ("bleeding", "blood everywhere", "bleeding heavily", "hemorrhage")
        head_words = ("head injury", "hit my head", "head trauma", "head bleeding")
        unconscious_words = ("unconscious", "passed out", "fainted", "collapsed", "unresponsive")
        no_response_words = ("not responding", "no response", "cannot wake", "can't wake")
        fall_words = ("fell", "fall", "slipped", "slip", "tripped", "trip", "can't get up", "cannot get up")
        confusion_words = ("confused", "disoriented", "not sure where", "memory loss", "i forgot where")

        if self._contains_any(text, stroke_words):
            tags.append("stroke_like")
        if self._contains_any(text, cardiac_words) or (medical_flags.cardio_risk and self._contains_any(text, breathing_words)):
            tags.append("cardiac")
        if self._contains_any(text, breathing_words):
            tags.append("breathing_distress")
        if self._contains_any(text, bleeding_words):
            tags.append("bleeding")
        if self._contains_any(text, head_words):
            tags.append("head_injury")
        if self._contains_any(text, unconscious_words):
            tags.append("unconscious")
        if self._contains_any(text, no_response_words):
            tags.append("no_response")
        if self._contains_any(text, fall_words):
            tags.append("fall")
        if self._contains_any(text, confusion_words) or medical_flags.cognitive_risk:
            tags.append("confusion")

        return list(dict.fromkeys(tags))

    def _policy_min_action(self, emergency_tags: list[str]) -> tuple[RecommendedAction | None, list[str]]:
        required_actions: list[RecommendedAction] = []
        evidence: list[str] = []
        for tag in emergency_tags:
            policy_action = self.emergency_min_actions.get(tag)
            if not policy_action:
                continue
            mapped = self._POLICY_ACTION_MAP.get(policy_action)
            if not mapped:
                continue
            required_actions.append(mapped)
            evidence.append(f"{tag}->{policy_action}")

        if not required_actions:
            return None, []
        strongest = max(required_actions, key=lambda action: self._ACTION_RANK[action])
        return strongest, evidence

    @staticmethod
    def _critical_combo_bonus(
        *,
        resident_profile: ResidentProfile | None,
        resident_age: int | None,
        incident_features: dict[str, float],
        vulnerability_features: dict[str, float],
        medical_features: dict[str, float],
        history_features: dict[str, float],
        emergency_tags: list[str],
    ) -> tuple[float, list[str]]:
        age = resident_profile.age if resident_profile is not None else resident_age
        living_alone = vulnerability_features.get("living_alone_flag", 0.0) >= 0.5
        elderly_very_high = age is not None and age >= 85
        fall_signal = incident_features.get("fall_sound_detected", 0.0) >= 0.5 or "fall" in emergency_tags
        high_impact_or_cannot_get_up = incident_features.get("impact_amplitude", 0.0) >= 0.95
        cardiac_risk = medical_features.get("cardiac_risk_flag", 0.0) >= 0.5
        breathing_signal = incident_features.get("cannot_breathe_keyword", 0.0) >= 0.5 or "breathing_distress" in emergency_tags
        recent_discharge = medical_features.get("recent_discharge_flag", 0.0) >= 0.5
        clean_history = history_features.get("false_alarm_rate", 0.0) <= 0.1
        recent_real_events = history_features.get("recent_emergency_history_flag", 0.0) >= 0.5

        bonus = 0.0
        reasons: list[str] = []

        if elderly_very_high and living_alone and fall_signal:
            bonus += 0.10
            reasons.append("elderly+living-alone+fall combo")
        if fall_signal and high_impact_or_cannot_get_up:
            bonus += 0.06
            reasons.append("fall+cannot-get-up combo")
        if cardiac_risk and (breathing_signal or "cardiac" in emergency_tags):
            bonus += 0.08
            reasons.append("cardiac+acute symptom combo")
        if recent_discharge and fall_signal:
            bonus += 0.05
            reasons.append("recent-discharge+fall combo")
        if clean_history and recent_real_events:
            bonus += 0.03
            reasons.append("clean-history+real-emergency pattern")

        return min(0.24, bonus), reasons

    def evaluate(
        self,
        *,
        speech: SpeechResult,
        routing: LanguageRoutingResult,
        medical_flags: DerivedMedicalFlags,
        history_flags: DerivedHistoryFlags,
        resident_profile: ResidentProfile | None = None,
        raw_medical_history: RawMedicalHistory | None = None,
        raw_call_history: RawCallHistory | None = None,
        resident_age: int | None = None,
    ) -> TriageResult:
        incident_features, incident_cues = self._incident_features(speech)
        vulnerability_features, vulnerability_cues = self._vulnerability_features(
            resident_profile=resident_profile,
            resident_age=resident_age,
        )
        medical_features, medical_cues = self._medical_features(
            medical_flags=medical_flags,
            raw_medical_history=raw_medical_history,
        )
        history_features, history_cues = self._history_features(
            history_flags=history_flags,
            raw_call_history=raw_call_history,
        )
        emergency_tags = self._detect_emergency_tags(speech=speech, medical_flags=medical_flags)
        min_required_action, policy_hits = self._policy_min_action(emergency_tags)

        incident_score = (
            0.34 * incident_features["fall_sound_detected"]
            + 0.22 * incident_features["impact_amplitude"]
            + 0.12 * incident_features["silence_after_impact"]
            + 0.08 * incident_features["crying_detected"]
            + 0.06 * incident_features["shouting_detected"]
            + 0.18 * incident_features["cannot_breathe_keyword"]
        )
        vulnerability_score = (
            0.42 * vulnerability_features["living_alone_flag"]
            + 0.38 * vulnerability_features["elderly_flag"]
            + 0.15 * vulnerability_features["mobility_risk_flag"]
            + 0.05 * vulnerability_features["caregiver_unavailable_flag"]
        )
        medical_score = (
            0.30 * medical_features["cardiac_risk_flag"]
            + 0.30 * medical_features["fall_risk_flag"]
            + 0.15 * medical_features["diabetes_flag"]
            + 0.10 * medical_features["dementia_risk_flag"]
            + 0.15 * medical_features["recent_discharge_flag"]
        )
        history_adjustment = (
            -0.15 * history_features["false_alarm_rate"]
            + 0.20 * history_features["repeat_real_incident_flag"]
            + 0.15 * history_features["recent_emergency_history_flag"]
        )

        base_weighted_risk = self._clamp01(
            0.45 * incident_score
            + 0.26 * vulnerability_score
            + 0.21 * medical_score
            + 0.08 * history_adjustment
        )
        combo_bonus, combo_reasons = self._critical_combo_bonus(
            resident_profile=resident_profile,
            resident_age=resident_age,
            incident_features=incident_features,
            vulnerability_features=vulnerability_features,
            medical_features=medical_features,
            history_features=history_features,
            emergency_tags=emergency_tags,
        )
        risk_score = self._clamp01(base_weighted_risk + combo_bonus)
        raw_risk_score = risk_score

        if risk_score >= 0.68:
            urgency = UrgencyClass.URGENT
            action = RecommendedAction.AMBULANCE_DISPATCH
        elif risk_score >= 0.38:
            urgency = UrgencyClass.UNCERTAIN
            action = RecommendedAction.COMMUNITY_RESPONSE
        else:
            urgency = UrgencyClass.NON_URGENT
            action = RecommendedAction.OPERATOR_CALLBACK

        overall_confidence = round(
            max(
                0.35,
                min(
                    0.95,
                    0.28
                    + abs(risk_score - 0.5) * 0.34
                    + speech.speech_confidence * 0.20
                    + (0.08 if risk_score >= 0.68 else 0.0),
                ),
            ),
            3,
        )

        guardrail_triggered = urgency == UrgencyClass.NON_URGENT and overall_confidence < 0.6
        if guardrail_triggered:
            urgency = UrgencyClass.UNCERTAIN
            action = RecommendedAction.COMMUNITY_RESPONSE

        policy_override_triggered = False
        if min_required_action is not None and self._ACTION_RANK[action] < self._ACTION_RANK[min_required_action]:
            action = min_required_action
            minimum_urgency = self._minimum_urgency_for_action(min_required_action)
            if self._ACTION_RANK[action] >= self._ACTION_RANK[RecommendedAction.AMBULANCE_DISPATCH]:
                urgency = UrgencyClass.URGENT
            elif minimum_urgency == UrgencyClass.UNCERTAIN and urgency == UrgencyClass.NON_URGENT:
                urgency = UrgencyClass.UNCERTAIN
            policy_override_triggered = True

        risk_score_before_band_alignment = risk_score
        risk_score = self._align_risk_score_to_urgency_band(risk_score=risk_score, urgency=urgency)
        risk_band_alignment_applied = abs(risk_score - risk_score_before_band_alignment) > 1e-9

        reasoning = self._build_reasoning(
            urgency=urgency,
            risk_score=risk_score,
            incident_score=incident_score,
            vulnerability_score=vulnerability_score,
            medical_score=medical_score,
            history_adjustment=history_adjustment,
            combo_bonus=combo_bonus,
            combo_reasons=combo_reasons,
            guardrail_triggered=guardrail_triggered,
            policy_override_triggered=policy_override_triggered,
            policy_hits=policy_hits,
            signal_cues=incident_cues + vulnerability_cues + medical_cues + history_cues,
        )

        return TriageResult(
            urgency_class=urgency,
            recommended_action=action,
            reasoning=reasoning,
            routing_hint=routing.routing_hint,
            overall_confidence=overall_confidence,
            stage_evidence={
                "incident_score": round(incident_score, 3),
                "vulnerability_score": round(vulnerability_score, 3),
                "medical_score": round(medical_score, 3),
                "history_adjustment": round(history_adjustment, 3),
                "base_weighted_risk": round(base_weighted_risk, 3),
                "critical_combo_bonus": round(combo_bonus, 3),
                "critical_combo_reasons": combo_reasons,
                "raw_risk_score_before_policy": round(raw_risk_score, 3),
                "risk_score_before_band_alignment": round(risk_score_before_band_alignment, 3),
                "risk_band_alignment_applied": risk_band_alignment_applied,
                "final_risk_score": round(risk_score, 3),
                "risk_score": round(risk_score, 3),
                "incident_components": {k: round(v, 3) for k, v in incident_features.items()},
                "vulnerability_components": {k: round(v, 3) for k, v in vulnerability_features.items()},
                "medical_components": {k: round(v, 3) for k, v in medical_features.items()},
                "history_components": {k: round(v, 3) for k, v in history_features.items()},
                "signals": incident_cues + vulnerability_cues + medical_cues + history_cues,
                "guardrail_triggered": guardrail_triggered,
                "emergency_tags_detected": emergency_tags,
                "emergency_min_policy_hits": policy_hits,
                "emergency_min_required_action": min_required_action.value if min_required_action else None,
                "emergency_min_override_triggered": policy_override_triggered,
                "speech": speech.model_dump(),
                "routing": routing.model_dump(),
                "medical_flags": medical_flags.model_dump(),
                "history_flags": history_flags.model_dump(),
            },
        )

    @staticmethod
    def _build_reasoning(
        *,
        urgency: UrgencyClass,
        risk_score: float,
        incident_score: float,
        vulnerability_score: float,
        medical_score: float,
        history_adjustment: float,
        combo_bonus: float,
        combo_reasons: list[str],
        guardrail_triggered: bool,
        policy_override_triggered: bool,
        policy_hits: list[str],
        signal_cues: list[str],
    ) -> str:
        cues = list(dict.fromkeys(signal_cues))
        if not cues:
            cues.append("no dominant high-risk indicator")

        base = (
            f"Risk score={risk_score:.2f} "
            f"(incident={incident_score:.2f}, vulnerability={vulnerability_score:.2f}, "
            f"medical={medical_score:.2f}, history_adj={history_adjustment:.2f}, combo={combo_bonus:.2f}); signals: "
            + ", ".join(cues)
            + "."
        )
        suffixes: list[str] = []
        if combo_bonus > 0 and combo_reasons:
            suffixes.append("Critical-combo boost applied (" + ", ".join(combo_reasons) + ").")
        if guardrail_triggered:
            suffixes.append("Confidence is low for a non-urgent decision, so triage is elevated to uncertain.")
        if policy_override_triggered and policy_hits:
            suffixes.append("Minimum emergency action policy applied (" + ", ".join(policy_hits) + ").")
        if not suffixes:
            suffixes.append(f"Final urgency is {urgency.value}.")
        return base + " " + " ".join(suffixes)
