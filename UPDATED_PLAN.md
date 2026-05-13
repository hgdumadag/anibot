# AniBot Farming Plan Recommendation App

## Summary

AniBot is now focused on an offline-first farming plan recommendation app for non-experienced farmers. The MVP generates practical rice and corn farming plans from location, farming type, planning mode, field conditions, weather-related context, and observed concerns. It uses the local searchable PDF knowledge database for source-backed guidance and page-level citations.

The MVP does not include budget, available capital, cost ranges, ranked capital-aware options, BLE sharing, RFID login, printer integration, voice, camera diagnosis, or market price sync.

## Core Architecture

```text
anibot/
  pyproject.toml
  README.md
  docs/
  knowledge/
    manifest.toml
  data/
    anibot_knowledge.db
    anibot_app.db
    chroma/
  scripts/
    ingest_knowledge.py
    run_app.ps1
  src/anibot/
    main.py
    rag/
      ingest.py
      retriever.py
      store.py
      vector.py
    planning/
      schema.py
      generator.py
      repository.py
    web/
      templates/
      static/
  tests/
```

Primary libraries:

- `fastapi`, `uvicorn`, `jinja2` for the local web app.
- `pydantic` for request and plan validation.
- `sqlite3` and SQLite FTS5 for plan storage and exact-search knowledge retrieval.
- `pypdf` for PDF text extraction.
- Optional `chromadb` for semantic retrieval when installed.
- Ollama local LLM as the primary beginner-friendly wording engine for an already source-backed draft plan.

## Phase 1 - Rice and Corn Farming Plan MVP

### Goal

A user can run AniBot locally on Windows, open a browser form, enter beginner-friendly rice or corn farm context, and receive a practical farming plan with warnings, checklists, and source citations.

### Inputs

- Location: province, municipality/city, optional barangay, optional field notes.
- Plan language: English, Filipino, or Cebuano.
- Crop: rice or corn for Phase 1; unsupported crops return MAO escalation.
- Farming type: conventional, organic/traditional, or unknown.
- Planning mode: planning to plant or already planted.
- Date or stage: target planting date or current crop stage.
- Farm conditions: irrigated/rainfed/unknown, lowland/upland/unknown, dry/moist/flooded/unknown.
- Current concerns: pests, weeds, poor growth, fertilizer/nutrient concern, water shortage, heavy rain/flooding, harvest/post-harvest concern, or none.
- Optional observation notes.

No available capital, budget, cost, or price inputs are collected.

### Outputs

Generated farming plans include:

- Plan Summary
- Current Concern Response
- Before Planting
- Planting and Crop Establishment
- Soil and Fertility Plan
- Water Management Plan
- Pest, Disease, and Weed Management
- Stage-by-Stage Checklist
- Harvest and Post-Harvest
- Records to Keep
- Warnings and Escalation
- Sources with document title, page number, heading, and chunk id

Farmer-facing plan text is generated in the selected language. Source titles, citation metadata, and system identifiers remain as stored in the local evidence database.

Each technical section must include reviewed crop-specific citations or a clear fallback reason. Context-only documents may support weather or location notes but cannot independently support technical recommendations.

## Implementation Rules

- Rice and corn are the supported Phase 1 crops.
- Corn documents are indexed as reviewed advisory evidence and can generate corn plans.
- Templates assemble beginner-friendly guidance from reviewed crop-specific evidence.
- Gemma through Ollama is required for web-app plan creation in the demo, while deterministic templates remain the safety fallback after a model attempt fails validation.
- Ollama integration uses `ANIBOT_OLLAMA_HOST` and `ANIBOT_OLLAMA_MODEL`, defaulting to `http://127.0.0.1:11434` and `gemma4:e2b`.
- `/ollama/status` reports whether Ollama is reachable and whether the configured model is installed.
- For every web-app plan request, AniBot requires a reachable Ollama host with the configured Gemma model installed. Ollama receives the farmer request, local evidence, calendar rows, output shape, and safety rules. It may generate only validated beginner planning artifacts.
- If Ollama is unavailable or the configured Gemma model is missing, the web app rejects plan creation with a setup error. If Gemma is reached but returns invalid JSON, changes protected fields, or fails validation, AniBot saves the deterministic template plan and records the LLM rejection.
- Exact fertilizer rates and pesticide product choices are not generated unless later backed by reviewed structured data.
- Organic/traditional guidance must preserve organic restrictions around chemical pesticide use.
- Plan JSON is validated to reject budget/capital/cost/price fields.
- Generated plans are stored locally in SQLite with request JSON, plan JSON, status, source count, and timestamp.

## Acceptance Criteria

1. `python scripts/ingest_knowledge.py` builds the local knowledge database from `docs/`.
2. `.\scripts\run_app.ps1` starts the local web app.
3. The form does not ask for available capital, budget, prices, or costs.
4. A rice request generates a plan with source-backed sections.
5. A corn request generates a plan with source-backed sections.
6. Pesticide guidance remains general and safety-focused.
7. Fertility guidance recommends soil or plant-based analysis and does not invent exact rates.
8. Every generated plan section has citations or a fallback reason.
9. Generated plans are saved and can be reopened by id.
10. The app shows Ollama/Gemma as the primary local AI engine and reports whether it can connect.
11. Selected current concerns generate a direct response section with what to check, what not to do yet, what to record, and when to contact MAO.
12. English, Filipino, and Cebuano plan requests generate farmer-facing plan content in the selected language.
13. `python -m pytest` passes.
