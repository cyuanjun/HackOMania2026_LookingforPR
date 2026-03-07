# HackOMania 2026 - PAB Operator Dashboard

This repo is scaffolded as a single repo with:

- `backend/` FastAPI API
- `frontend/` Next.js app
- `data/seed/` demo seed data (profiles)

## Run backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend default URL: `http://127.0.0.1:8000`

Backend persistence:

- Uses SQL database storage for profiles/cases/training records.
- Local default DB: `sqlite:///data/db/app.db`
- Override with `DATABASE_URL` (for example Supabase/Postgres).
  - Example: `postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require`

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend default URL: `http://localhost:3000`

Set `NEXT_PUBLIC_API_BASE_URL` if backend is not at `http://127.0.0.1:8000`.

## Deploy On Vercel

Use 2 separate Vercel projects from the same repo:

1. Frontend project
- Root Directory: `frontend`
- Framework Preset: `Next.js` (auto-detected)
- Env var:
  - `NEXT_PUBLIC_API_BASE_URL=https://<your-backend-project>.vercel.app`

2. Backend project
- Root Directory: `backend`
- Uses `backend/vercel.json` and `backend/api/index.py`
- Env vars:
  - `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require`
  - `EXPORT_TRAINING_CSV=false` (recommended on Vercel serverless filesystem)

Optional backend env vars:
- `SEED_DIR=/var/task/data/seed` (usually not needed because defaults are preconfigured)
- `TRAINING_DIR=/tmp` (only if you explicitly want temporary CSV export)

Data unit note:

- `historical_call_history.average_call_duration` is interpreted in **seconds**.
- `historical_call_history.last_call_timestamp` is stored as an ISO-8601 timestamp.

## Outcome Labeling And Training Data

The backend now stores a training snapshot per processed case:

- full feature context (unit/medical/call/audio)
- model predictions (severity/action/confidence/false alarm probability)
- actual outcomes (when provided)

Useful endpoints:

- `GET /cases/training-records`
- `POST /cases/{case_id}/outcome`

CSV export for future model training:

- Appends one row per outcome submission to:
  - `data/training/case_training_records.csv`
- Includes full feature context + predicted outputs + actual labels.

Example payload for outcome labeling:

```json
{
  "actual_severity": "high",
  "actual_action": "ambulance_dispatch",
  "actual_false_alarm": false,
  "actual_emergency_type": "cardiac",
  "notes": "Confirmed by attending team."
}
```
