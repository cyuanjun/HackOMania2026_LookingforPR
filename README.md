# HackOMania 2026 - PAB Triage MVP

![Dashboard Preview](./docs/images/dashboard.png)

AI-assisted triage dashboard for **Personal Alert Button (PAB)** alerts, built for **HackOMania 2026**.

This project is a monorepo MVP that helps operators monitor incoming alert cases, review AI-assisted triage outputs, and make faster response decisions using resident context, call history, and audio-derived signals.

---

## Overview

When a PAB alert is triggered, operators often need to make decisions quickly with incomplete information. This project aims to support that workflow by combining:

- **Resident context** from structured records
- **Audio analysis** from prerecorded or uploaded clips
- **Language / dialect handling**
- **Rule-based triage fusion**
- **Operator review and final action tracking**

The current implementation is designed as a **modular MVP**, with clean separation between frontend, backend, and persistence so it can evolve into a production-ready system later.

---

## Key Features

- **Operator dashboard** for viewing and managing alert cases
- **FastAPI backend** for case handling and API services
- **Next.js frontend** for a clean web-based interface
- **Resident context lookup** from CSV-backed repositories
- **Case persistence** using JSON files
- **Audio upload pipeline scaffold**
- **Language detection, transcription, and translation hooks**
- **Derived medical / history flags**
- **Fusion-based triage engine**
- **Case workflow state transitions**
- Future-ready repository abstraction for **Supabase or database migration**

---

## Repository Structure

```text
.
├── backend/     # FastAPI service, repositories, tests, local data storage
├── frontend/    # Next.js + TypeScript + Tailwind dashboard
├── docs/        # Architecture notes
└── EXTRA/       # Extra materials / supporting files
```

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
