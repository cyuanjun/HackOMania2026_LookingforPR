"""
PAB Emergency Response API
──────────────────────────
Uses the user's existing pipeline.analyze_audio() exactly as-is.
Adds only:
  1. Fusion urgency scoring (_compute_final_urgency)
  2. GPT-4o operator summary (_build_llm_summary)
  3. Senior DB + REST endpoints

Project layout expected:
  server.py          ← this file
  app/
    __init__.py
    config.py
    env.py
    pipeline.py
    explanations.py
    audio/
      __init__.py
      event_detection.py
      features.py
      loader.py
      quality.py
      silence.py
    speech/
      __init__.py
      asr_openai.py
      keywords.py
      language.py
      translation.py
      urgency.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent))

from app.config import AppConfig
from app.pipeline import analyze_audio

# ── PAB-tuned config ──────────────────────────────────────────────────────────
PAB_CONFIG = AppConfig(
    min_duration_sec=0.60,                     # skip button-press artifact (~0.5 s)
    silence_top_db=25.0,                       # lower threshold -> more sensitive to pause/silence after impact
    peak_threshold=0.85,                       # 0.72 -> ignore button clicks as impact
    silence_after_impact_gate_threshold=0.50,  # allow moderate impacts to enter silence-after-impact check
    silence_after_impact_sec=1.2,              # tolerate shorter but meaningful post-impact pause
    silence_after_impact_detect_threshold=0.45,
    fall_sound_detect_threshold=0.45,
    crying_detect_threshold=0.38,              # 0.20 -> reduce elderly vocal texture noise
    breathing_irregularity_detect_threshold=0.45,  # 0.40 -> reduce elderly breathiness false positives
    use_llm_explanations=True,
    use_optional_yamnet=True,
)

# ── Senior database ───────────────────────────────────────────────────────────
SENIORS: dict[str, dict[str, Any]] = {
    "S001": {
        "id": "S001", "name": "Tan Ah Kow", "age": 78, "gender": "Male",
        "address": "Blk 123 Toa Payoh Lor 4 #05-21", "phone": "+65 9123 4567",
        "unit": "PAB-TPA-0523",
        "emergency_contact": {"name": "Tan Wei Ming (Son)", "phone": "+65 9876 5432"},
        "languages": ["Hokkien", "Mandarin", "basic English"],
        "medical_history": ["Hypertension", "Type 2 Diabetes", "Mild Dementia"],
        "medications": ["Metformin 500mg", "Amlodipine 5mg"],
        "mobility": "Uses walking stick",
        "past_alerts": [
            {"date": "2025-11-12", "type": "False Alarm", "note": "Accidentally pressed button"},
            {"date": "2025-08-03", "type": "Urgent", "note": "Fall in bathroom — ambulance dispatched"},
            {"date": "2025-05-21", "type": "Non-urgent", "note": "Felt dizzy, no medical attention needed"},
        ],
    },
    "S002": {
        "id": "S002", "name": "Madam Wong Siew Lan", "age": 82, "gender": "Female",
        "address": "Blk 45 Bukit Merah View #10-05", "phone": "+65 9234 5678",
        "unit": "PAB-BMV-0105",
        "emergency_contact": {"name": "Wong Li Ling (Daughter)", "phone": "+65 8765 4321"},
        "languages": ["Cantonese", "Mandarin"],
        "medical_history": ["Osteoporosis", "Heart Failure (Stage 2)", "Depression"],
        "medications": ["Furosemide 40mg", "Carvedilol 6.25mg", "Sertraline 50mg"],
        "mobility": "Wheelchair-bound",
        "past_alerts": [
            {"date": "2026-01-15", "type": "Non-urgent", "note": "Loneliness — wanted to talk"},
            {"date": "2025-12-24", "type": "Urgent", "note": "Chest pain — ambulance dispatched"},
            {"date": "2025-10-08", "type": "Uncertain", "note": "Audio unclear, welfare check sent"},
        ],
    },
    "S003": {
        "id": "S003", "name": "Mr Rajan Pillai", "age": 71, "gender": "Male",
        "address": "Blk 88 Geylang Bahru #03-12", "phone": "+65 9345 6789",
        "unit": "PAB-GLB-0312",
        "emergency_contact": {"name": "Priya Pillai (Daughter)", "phone": "+65 8234 5678"},
        "languages": ["Tamil", "English", "Malay"],
        "medical_history": ["Chronic Kidney Disease (Stage 3)", "Gout"],
        "medications": ["Allopurinol 100mg", "Calcium carbonate"],
        "mobility": "Independent",
        "past_alerts": [
            {"date": "2025-09-30", "type": "False Alarm", "note": "Button pressed during cleaning"},
        ],
    },
    "S004": {
        "id": "S004", "name": "Mdm Siti Rahimah", "age": 75, "gender": "Female",
        "address": "Blk 201 Tampines St 21 #08-33", "phone": "+65 9456 7890",
        "unit": "PAB-TMP-0833",
        "emergency_contact": {"name": "Noor Azman (Son)", "phone": "+65 8345 6789"},
        "languages": ["Malay", "basic English"],
        "medical_history": ["Asthma", "Hypertension", "Cataract (post-op)"],
        "medications": ["Salbutamol inhaler", "Amlodipine 10mg"],
        "mobility": "Slow walker, no aids",
        "past_alerts": [
            {"date": "2026-02-10", "type": "Urgent", "note": "Asthma attack — paramedic dispatched"},
            {"date": "2025-07-18", "type": "Non-urgent", "note": "Ran out of medication"},
        ],
    },
}

_HIGH_RISK = {
    "heart failure", "cardiac", "copd", "asthma", "stroke",
    "parkinson", "dementia", "diabetes", "kidney disease",
    "osteoporosis", "hypertension",
}


def compute_final_urgency(pipeline_result: dict[str, Any], senior: dict[str, Any]) -> dict[str, Any]:
    """Fuse pipeline signals + senior medical profile to produce urgency."""
    nse = pipeline_result.get("non_speech_events", {})
    sf = pipeline_result.get("speech_features", {})
    tx = pipeline_result.get("transcript", {})
    transcript_text = tx.get("translated_text", "") or tx.get("text", "")

    speech_urgency = float(sf.get("speech_urgency_score", 0.0))
    fall_conf = float(nse.get("fall_sound_confidence", 0.0))
    impact_conf = float(nse.get("impact_confidence", 0.0))
    crying_conf = float(nse.get("crying_confidence", 0.0))
    breathing_conf = float(nse.get("breathing_irregularity_confidence", 0.0))
    shouting_conf = float(nse.get("shouting_confidence", 0.0))
    silence_conf = float(nse.get("silence_after_impact_confidence", 0.0))

    help_kw = bool(sf.get("help_keyword_detected", False))
    fall_kw = bool(sf.get("fall_keyword_detected", False))
    breathe_kw = bool(sf.get("cannot_breathe_keyword_detected", False))
    keyword_hits = list(sf.get("keyword_hits", []))

    med_lower = " ".join(senior.get("medical_history", [])).lower()
    risk_hits = [c for c in _HIGH_RISK if c in med_lower]
    medical_boost = min(len(risk_hits) * 0.04, 0.15)

    prior_urgent = sum(1 for p in senior.get("past_alerts", []) if p.get("type") == "Urgent")
    recency_boost = 0.05 if prior_urgent >= 2 else 0.0

    acoustic = max(
        (0.55 * fall_conf) + (0.20 * impact_conf) + (0.15 * silence_conf) + (0.10 * crying_conf),
        (0.60 * impact_conf) + (0.25 * silence_conf),
        breathing_conf * 0.85,
        shouting_conf * 0.75,
    )

    base = max(speech_urgency, acoustic)
    fused = min(base + medical_boost + recency_boost, 1.0)
    score = round(fused * 100, 1)

    if fused >= 0.62 or (breathe_kw and fused >= 0.40) or (fall_kw and fall_conf >= 0.50):
        level = "urgent"
    elif fused >= 0.38 or (help_kw and fused >= 0.25):
        level = "uncertain"
    elif fused >= 0.15:
        level = "non-urgent"
    else:
        level = "false_alarm"

    if not transcript_text.strip() and not keyword_hits and acoustic < 0.25:
        level = "false_alarm"
        score = min(score, 15.0)

    return {
        "urgency_level": level,
        "urgency_score": score,
        "fused_score": round(fused, 3),
        "speech_score": round(speech_urgency, 3),
        "acoustic_score": round(acoustic, 3),
        "medical_risk_boost": round(medical_boost, 3),
        "risk_conditions": risk_hits,
    }


def _normalize_suggested_actions(raw: Any) -> list[str]:
    """Normalize LLM output to a stable list of action strings."""
    if isinstance(raw, list):
        return [str(a).strip() for a in raw if str(a).strip()][:4]

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        # Handle newline/comma/bullet/numbered formats from free-form outputs.
        parts = [
            p.strip(" \t-•0123456789.)(")
            for p in text.replace("\r", "\n").replace(",", "\n").split("\n")
        ]
        cleaned = [p for p in parts if p]
        return cleaned[:4]

    return []


def _build_llm_summary(pipeline_result: dict[str, Any], senior: dict[str, Any], urgency: dict[str, Any]) -> dict[str, Any]:
    """Call GPT-4o to generate operator-facing recommendation from pipeline dict."""
    from app.env import ensure_dotenv_loaded
    ensure_dotenv_loaded()

    if not os.getenv("OPENAI_API_KEY"):
        return {"summary": "", "recommendation": "OpenAI API key not configured.", "suggested_actions": []}

    try:
        import openai
        client = openai.OpenAI()
    except Exception:
        return {"summary": "", "recommendation": "openai package unavailable.", "suggested_actions": []}

    nse = pipeline_result.get("non_speech_events", {})
    sf  = pipeline_result.get("speech_features", {})
    tx  = pipeline_result.get("transcript", {})
    lang = pipeline_result.get("language", {})

    system = (
        "You are an AI triage assistant for Singapore's PAB (Personal Alert Button) hotline. "
        "Operators monitor elderly seniors living alone in HDB flats. "
        "Given structured audio analysis + senior profile, produce a concise operator-facing report. "
        "Be clinical and non-alarmist. Use cautious language when evidence is weak. "
        "Return ONLY valid JSON: {summary, recommendation, suggested_actions: string[] (max 4)}."
    )

    payload = {
        "senior": {
            "name": senior["name"], "age": senior["age"],
            "address": senior["address"],
            "medical_history": senior["medical_history"],
            "medications": senior["medications"],
            "mobility": senior["mobility"],
            "languages": senior["languages"],
            "emergency_contact": senior["emergency_contact"],
            "past_alerts_summary": (
                f"{len(senior['past_alerts'])} past alerts, "
                f"{sum(1 for p in senior['past_alerts'] if p['type']=='Urgent')} urgent"
            ),
        },
        "audio_analysis": {
            "detected_language":       lang.get("detected_language", "unknown"),
            "transcript_original":     tx.get("text", ""),
            "transcript_english":      tx.get("translated_text", ""),
            "asr_confidence":          tx.get("asr_confidence"),
            "keyword_hits":            sf.get("keyword_hits", []),
            "help_detected":           sf.get("help_keyword_detected"),
            "fall_detected":           sf.get("fall_keyword_detected"),
            "breathing_distress":      sf.get("cannot_breathe_keyword_detected"),
            "non_speech_confidences": {
                "fall_sound":              round(float(nse.get("fall_sound_confidence", 0)), 3),
                "impact":                  round(float(nse.get("impact_confidence", 0)), 3),
                "crying":                  round(float(nse.get("crying_confidence", 0)), 3),
                "shouting":                round(float(nse.get("shouting_confidence", 0)), 3),
                "breathing_irregularity":  round(float(nse.get("breathing_irregularity_confidence", 0)), 3),
                "silence_after_impact":    round(float(nse.get("silence_after_impact_confidence", 0)), 3),
            },
            "pipeline_explanations": pipeline_result.get("explanations", []),
        },
        "urgency": {
            "level":               urgency["urgency_level"],
            "score_0_to_100":      urgency["urgency_score"],
            "risk_conditions":     urgency["risk_conditions"],
        },
    }

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.15,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return {
            "summary":           str(data.get("summary", "")),
            "recommendation":    str(data.get("recommendation", "")),
            "suggested_actions": _normalize_suggested_actions(data.get("suggested_actions", [])),
        }
    except Exception as exc:
        return {"summary": "", "recommendation": f"LLM error: {exc}", "suggested_actions": []}


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="PAB Emergency Response API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/seniors")
def list_seniors():
    return [
        {"id": v["id"], "name": v["name"], "age": v["age"],
         "address": v["address"], "unit": v["unit"], "languages": v["languages"]}
        for v in SENIORS.values()
    ]


@app.get("/api/seniors/{senior_id}")
def get_senior(senior_id: str):
    if senior_id not in SENIORS:
        raise HTTPException(404, "Senior not found")
    return SENIORS[senior_id]


@app.post("/api/analyze")
async def analyze(
    senior_id: str = Form(...),
    audio_file: UploadFile = File(...),
):
    if senior_id not in SENIORS:
        raise HTTPException(404, f"Senior '{senior_id}' not found")

    senior      = SENIORS[senior_id]
    suffix      = Path(audio_file.filename or "audio.wav").suffix or ".wav"
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(400, "Empty audio file uploaded")

    # Save to temp file → run user's pipeline as-is
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        pipeline_result = analyze_audio(tmp_path, config=PAB_CONFIG)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Add fusion urgency + LLM summary on top of pipeline dict
    urgency     = compute_final_urgency(pipeline_result, senior)
    llm_summary = _build_llm_summary(pipeline_result, senior, urgency)

    # Return pipeline dict intact + extra keys the frontend needs
    return {
        **pipeline_result,          # audio_meta, non_speech_events, acoustic_features,
                                    # language, transcript, speech_features,
                                    # explanations, model_info  — all original keys
        "senior":      senior,      # full senior profile
        "urgency":     urgency,     # fusion score
        "llm_summary": llm_summary, # operator recommendation
    }


@app.get("/api/health")
def health():
    import datetime
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}
