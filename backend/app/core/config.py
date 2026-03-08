from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    csv_dir: Path
    cases_dir: Path
    uploads_dir: Path
    app_name: str = "HackOMania 2026 PAB Triage API"
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    emergency_min_actions: dict[str, str] = field(
        default_factory=lambda: {
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
    )

    @classmethod
    def default(cls) -> "Settings":
        backend_root = Path(__file__).resolve().parents[2]
        data_dir = backend_root / "data"
        return cls(
            csv_dir=data_dir / "csv",
            cases_dir=data_dir / "cases",
            uploads_dir=data_dir / "uploads",
        )

    def ensure_directories(self) -> None:
        self.csv_dir.mkdir(parents=True, exist_ok=True)
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
