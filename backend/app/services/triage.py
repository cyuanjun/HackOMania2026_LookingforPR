from __future__ import annotations

from math import exp

from app.schemas.case import AudioModuleInput, ProfileRecord, ScoreFactor, ScoreResult


def _add_factor(
    factors: list[ScoreFactor],
    key: str,
    evidence: str,
    direction: str,
    weight: float,
    source_module: str,
) -> None:
    factors.append(
        ScoreFactor(
            key=key,
            evidence=evidence,
            direction=direction,  # type: ignore[arg-type]
            weight=weight,
            source_module=source_module,
        )
    )


def evaluate_case(
    profile: ProfileRecord,
    audio_module: AudioModuleInput | None,
) -> dict:
    unit = profile.unit_patient_information
    medical = profile.medical_history
    calls = profile.historical_call_history

    factors: list[ScoreFactor] = []
    score = 0.0
    inferred_emergency_type = "unknown"

    if unit.age >= 80:
        score += 1.2
        _add_factor(
            factors, "age_80_plus", "Age 80+ increases fragility risk.", "risk_up", 1.2, "profile"
        )

    if unit.living_alone_flag:
        score += 1.0
        _add_factor(
            factors, "living_alone", "Lives alone, lower immediate support.", "risk_up", 1.0, "profile"
        )

    if not unit.caregiver_available:
        score += 0.8
        _add_factor(
            factors, "no_caregiver", "No caregiver available now.", "risk_up", 0.8, "profile"
        )

    if medical.cardiac_risk_flag:
        score += 2.2
        inferred_emergency_type = "cardiac"
        _add_factor(
            factors, "cardiac_risk", "Cardiac-risk profile history.", "risk_up", 2.2, "medical_history"
        )

    if medical.fall_risk_flag:
        score += 1.4
        if inferred_emergency_type == "unknown":
            inferred_emergency_type = "fall"
        _add_factor(
            factors, "fall_risk", "Known fall-risk profile.", "risk_up", 1.4, "medical_history"
        )

    if medical.diabetes_flag:
        score += 0.7
        _add_factor(
            factors, "diabetes", "Diabetes comorbidity in profile.", "risk_up", 0.7, "medical_history"
        )

    if medical.dementia_risk_flag:
        score += 1.0
        _add_factor(
            factors, "dementia_risk", "Dementia-risk increases ambiguity and delay.", "risk_up", 1.0, "medical_history"
        )

    if medical.recent_discharge_flag:
        score += 1.1
        _add_factor(
            factors, "recent_discharge", "Recent discharge suggests unstable condition.", "risk_up", 1.1, "medical_history"
        )

    if calls.calls_last_7d >= 3:
        score += 1.3
        _add_factor(
            factors, "calls_last_7d", "Frequent recent calls in last 7 days.", "risk_up", 1.3, "call_history"
        )

    if calls.false_alarm_rate >= 0.45:
        score -= 0.8
        _add_factor(
            factors, "false_alarm_rate", "Historically high false-alarm rate.", "risk_down", 0.8, "call_history"
        )

    if calls.time_since_last_call <= 6:
        score += 0.9
        _add_factor(
            factors, "time_since_last_call", "Very recent previous call event.", "risk_up", 0.9, "call_history"
        )

    if calls.average_call_duration >= 6:
        score += 0.6
        _add_factor(
            factors, "avg_call_duration", "Longer call duration indicates sustained distress.", "risk_up", 0.6, "call_history"
        )

    if audio_module is not None:
        speech_score = audio_module.speech_distress_score or 0.0
        nonspeech_score = audio_module.non_speech_distress_score or 0.0
        if speech_score > 0:
            weight = round(2.2 * speech_score, 2)
            score += weight
            _add_factor(
                factors, "speech_distress", "Speech signals indicate distress.", "risk_up", weight, "audio_module"
            )
        if nonspeech_score > 0:
            weight = round(1.8 * nonspeech_score, 2)
            score += weight
            _add_factor(
                factors, "non_speech_distress", "Non-speech sounds indicate urgency.", "risk_up", weight, "audio_module"
            )

        speech_cues_lower = [cue.lower() for cue in audio_module.speech_cues]
        non_speech_cues_lower = [cue.lower() for cue in audio_module.non_speech_cues]
        cue_text = " ".join(speech_cues_lower + non_speech_cues_lower)

        if "chest" in cue_text or "heart" in cue_text:
            inferred_emergency_type = "cardiac"
            score += 1.4
            _add_factor(
                factors, "audio_cardiac_cues", "Audio cues suggest possible cardiac event.", "risk_up", 1.4, "audio_module"
            )
        elif "fall" in cue_text:
            inferred_emergency_type = "fall"
            score += 1.1
            _add_factor(
                factors, "audio_fall_cues", "Audio cues suggest a fall incident.", "risk_up", 1.1, "audio_module"
            )
        elif "breath" in cue_text or "gasp" in cue_text:
            inferred_emergency_type = "respiratory"
            score += 1.3
            _add_factor(
                factors, "audio_respiratory_cues", "Audio cues suggest respiratory distress.", "risk_up", 1.3, "audio_module"
            )

        if audio_module.estimated_emergency_type:
            inferred_emergency_type = audio_module.estimated_emergency_type

    score = round(score, 2)

    # Action confidence is computed as a probability over action logits.
    # This ties confidence directly to certainty of the chosen response.
    ambulance_logit = score
    callback_logit = max(0.0, 3.8 - abs(score - 4.0))
    community_logit = max(0.0, 3.0 - score)

    if inferred_emergency_type in {"cardiac", "respiratory"}:
        ambulance_logit += 1.0
    elif inferred_emergency_type == "fall":
        ambulance_logit += 0.5
        callback_logit += 0.4

    if calls.false_alarm_rate >= 0.45:
        community_logit += 0.6

    action_logits = {
        "ambulance_dispatch": ambulance_logit,
        "operator_callback": callback_logit,
        "community_response": community_logit,
    }

    max_logit = max(action_logits.values())
    exp_scores = {key: exp(value - max_logit) for key, value in action_logits.items()}
    exp_total = sum(exp_scores.values())
    action_probs = {key: value / exp_total for key, value in exp_scores.items()}

    recommended_action = max(action_probs, key=action_probs.get)
    confidence = round(action_probs[recommended_action], 2)

    if recommended_action == "ambulance_dispatch":
        distress_level = "high"
        recommended_priority = 1
    elif recommended_action == "operator_callback":
        distress_level = "medium"
        recommended_priority = 2
    else:
        distress_level = "low"
        recommended_priority = 3

    ranked_factors = sorted(factors, key=lambda factor: factor.weight, reverse=True)
    top_reasons = [factor.evidence for factor in ranked_factors[:3]]

    score_result = ScoreResult(
        score=score,
        recommended_priority=recommended_priority,
        recommended_action=recommended_action,  # type: ignore[arg-type]
        confidence=confidence,
        factors=factors,
    )

    return {
        "confidence": confidence,
        "distress_level": distress_level,
        "recommended_action": recommended_action,
        "top_contributing_reasons": top_reasons,
        "emergency_type": inferred_emergency_type,
        "score_result": score_result,
    }
