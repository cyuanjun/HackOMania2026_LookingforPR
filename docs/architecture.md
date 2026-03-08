# Architecture Notes

## Backend pipeline stages

1. Intake case creation (resident + prerecorded audio upload)
2. Non-verbal audio cue analysis
3. Language and dialect detection
4. Transcript + English translation
5. Resident context lookup from CSV
6. Derived medical flags
7. Derived history flags
8. Fusion engine triage
9. Summary generation
10. Operator review and final action

## Persistence

- Resident context: CSV (`backend/data/csv`)
- Cases: one JSON file per case (`backend/data/cases`)
- Uploaded audio: local files (`backend/data/uploads`)

All persistence access is behind repository interfaces for future Supabase replacement.

## State machine

- `pending_ai_assessment -> ai_assessed -> operator_processed`
- Invalid transitions return HTTP `409`.

