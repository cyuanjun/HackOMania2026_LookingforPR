import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

DEFAULT_REPO_SEED_DIR = REPO_ROOT / "data" / "seed"
DEFAULT_BACKEND_SEED_DIR = BACKEND_ROOT / "data" / "seed"
DEFAULT_SEED_DIR = (
    DEFAULT_REPO_SEED_DIR if DEFAULT_REPO_SEED_DIR.exists() else DEFAULT_BACKEND_SEED_DIR
)
SEED_DIR = Path(os.getenv("SEED_DIR", DEFAULT_SEED_DIR.as_posix()))

DEFAULT_REPO_TRAINING_DIR = REPO_ROOT / "data" / "training"
DEFAULT_BACKEND_TRAINING_DIR = BACKEND_ROOT / "data" / "training"
DEFAULT_TRAINING_DIR = (
    DEFAULT_REPO_TRAINING_DIR
    if DEFAULT_REPO_TRAINING_DIR.exists()
    else DEFAULT_BACKEND_TRAINING_DIR
)
TRAINING_DIR = Path(os.getenv("TRAINING_DIR", DEFAULT_TRAINING_DIR.as_posix()))

DEFAULT_REPO_DB_DIR = REPO_ROOT / "data" / "db"
DEFAULT_BACKEND_DB_DIR = BACKEND_ROOT / "data" / "db"
DEFAULT_DB_DIR = DEFAULT_REPO_DB_DIR if DEFAULT_REPO_DB_DIR.exists() else DEFAULT_BACKEND_DB_DIR
DB_DIR = Path(os.getenv("DB_DIR", DEFAULT_DB_DIR.as_posix()))
UNIT_INFORMATION_SEED_PATH = SEED_DIR / "unit_information.csv"
MEDICAL_HISTORY_SEED_PATH = SEED_DIR / "medical_history.csv"
CALL_HISTORY_SEED_PATH = SEED_DIR / "call_history.csv"
TRAINING_RECORDS_CSV_PATH = TRAINING_DIR / "case_training_records.csv"
DEFAULT_DB_PATH = (DB_DIR / "app.db").as_posix()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")
EXPORT_TRAINING_CSV = os.getenv("EXPORT_TRAINING_CSV", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
}
