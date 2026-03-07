"""CLI demo for the audio intelligence pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from app.pipeline import analyze_audio
from server import PAB_CONFIG, SENIORS, compute_final_urgency


def _resolve_audio_path(raw_path: str) -> str:
    path = Path(raw_path)
    if path.exists():
        return str(path)

    sample_audio_path = Path("sample_audio") / raw_path
    if sample_audio_path.exists():
        return str(sample_audio_path)

    return raw_path


def main() -> int:
    audio_path = sys.argv[1] if len(sys.argv) > 1 else "sample.wav"
    senior_id = sys.argv[2] if len(sys.argv) > 2 else "S001"
    senior = SENIORS.get(senior_id, SENIORS["S001"])

    result = analyze_audio(_resolve_audio_path(audio_path), config=PAB_CONFIG)
    urgency = compute_final_urgency(result, senior)
    result_with_triage = {
        **result,
        "senior": {"id": senior["id"], "name": senior["name"], "unit": senior["unit"]},
        "urgency": urgency,
    }
    print(json.dumps(result_with_triage, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
