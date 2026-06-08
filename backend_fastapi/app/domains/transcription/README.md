# Transcription domain

## Structured output

The canonical transcription shape is `chunks[].turns[]` stored on the recording session (`transcript_json`). Each audio section stores its worker result in `turns_json`.

Shared parsing, consolidation and rendering live in `shared/transcription_contract/`.

## Speakers

`MEDICO | PACIENTE | ACOMPANANTE | DESCONOCIDO`

## Turn merging

A turn represents one continuous utterance until another speaker intervenes. After Gemini returns JSON, `transcription_worker` merges consecutive turns from the same speaker when `overlaps_next` and `overlaps_previous` are both false on the boundary. Overlapping speech and speaker changes are never merged.

The debug transcription page keeps raw Gemini turns in the JSON view; the Text view and `rendered_text` use merged turns.

## Deduplication

Adjacent chunk deduplication runs only at session consolidation time in FastAPI. It removes duplicated suffix/prefix text between neighboring chunks when the speaker matches. It does not merge different speakers or rewrite `overlaps_previous` / `overlaps_next`.

## VAD ownership

- **Primary path:** browser Silero VAD segments the encounter and uploads the clipped artifact. `transcription_worker` transcribes that GCS object directly with Gemini.
- **Fallback path:** only when the clipped transcript is empty and an original artifact exists, the worker downloads the original audio, applies worker Silero VAD trim, and re-transcribes.
- **Debug Gemini:** same as the primary path — transcribe the frontend-clipped section blob without an extra worker trim.

## Legacy coexistence

Older sessions may only have `raw_transcript` / `consolidated_transcript`. Read paths tolerate null structured fields and fall back to flat text.
