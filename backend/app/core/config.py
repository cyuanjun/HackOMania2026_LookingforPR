from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = REPO_ROOT / "data" / "seed"
UNIT_INFORMATION_SEED_PATH = SEED_DIR / "unit_information.csv"
MEDICAL_HISTORY_SEED_PATH = SEED_DIR / "medical_history.csv"
CALL_HISTORY_SEED_PATH = SEED_DIR / "call_history.csv"
