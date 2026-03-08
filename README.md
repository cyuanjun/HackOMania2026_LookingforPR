# HackOMania 2026 - PAB Triage MVP

Monorepo scaffold for an AI-assisted triage dashboard for Personal Alert Button (PAB) alerts.

## Structure

- `frontend/`: Next.js + TypeScript + Tailwind dashboard
- `backend/`: FastAPI service with CSV repositories and JSON case store
- `docs/`: architecture notes

## Quickstart

### 1) Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Optional (enables real transcript + language detection + translation):

```powershell
$env:OPENAI_API_KEY = "sk-..."
# Optional model overrides
$env:OPENAI_WHISPER_MODEL = "whisper-1"
$env:OPENAI_TRANSLATION_MODEL = "gpt-4o-mini"
$env:OPENAI_SUMMARY_MODEL = "gpt-4o-mini"
```

### 2) Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend now calls a built-in same-origin proxy route by default (`/api/proxy/*`), which forwards to backend origin.

Optional backend origin override for the frontend proxy route:

```powershell
$env:BACKEND_API_ORIGIN = "http://127.0.0.1:8000"
```

Optional direct API base override (skip proxy):

```powershell
$env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000/api/v1"
```

## Tests

```powershell
cd backend
pytest
```
