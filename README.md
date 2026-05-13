# AniBot Farming Plan Recommendation App

This repository contains an offline-first farming plan recommendation app for AniBot. Phase 1 showcases Gemma 4 through Ollama as the required local AI planner for beginner-friendly rice and corn plans, grounded in local PDF standards and context references.

The intended deployment is a Raspberry Pi kiosk in a municipal agriculture hub. Farmers or Municipal Agriculture Office staff can use the browser-based form, generate a local Gemma-powered plan, reopen saved plans, and print the result or save it as a PDF from the browser print dialog.

## Ingest the PDF Corpus

```powershell
python scripts/ingest_knowledge.py
```

The ingest command reads `knowledge/manifest.toml`, extracts text from PDFs in `docs/`, chunks the pages with citation metadata, and writes the local SQLite database to `data/anibot_knowledge.db`.

SQLite FTS5 is always enabled. Chroma indexing is also attempted when `chromadb` is installed, but the system works without it.

## Run the App

```powershell
.\scripts\run_app.ps1
```

Open `http://127.0.0.1:8000`.

The form asks for location, plan language, crop, farming type, planning mode, field condition, water source, soil condition, and current concerns. It does not ask for available capital, budget, prices, or input costs.

Supported plan languages:

- English
- Filipino
- Cebuano

## Municipal Kiosk Deployment

AniBot is designed for a municipal hub kiosk deployment, such as a Raspberry Pi installed at a Municipal Agriculture Office or farmer assistance desk.

The kiosk-oriented runtime is:

- Browser UI for walk-up use
- FastAPI/Jinja local web app
- SQLite knowledge database built from local PDF standards
- SQLite saved-plan database
- Ollama runtime with the configured Gemma 4 model
- Optional printer connected through the operating system/browser

Plan generation does not require internet once the PDF corpus has been ingested and the Gemma model is installed locally. The kiosk can therefore support farmers in areas with weak or intermittent connectivity.

Generated plans are saved locally and can be reopened by id. The plan page includes a print button. The browser print flow can print a paper copy or use "Save as PDF" for digital handoff, recordkeeping, or later sharing.

## Ollama-First Local AI Planning

AniBot treats Ollama as the required local AI engine for the web app. On every plan request, the app checks the configured Ollama host and asks the configured Gemma model to generate beginner calendar wording from a compact packet of retrieved source-backed guidelines.

The deterministic template path remains as a safety control inside the planner. If Gemma is reachable but returns invalid JSON or validation blocks unsafe content, AniBot saves the source-backed template plan and records the LLM rejection. If Ollama is unreachable or the configured Gemma model is not installed, the web app rejects plan creation until the local AI engine is ready.

Defaults:

- Host: `http://127.0.0.1:11434`
- Model: `gemma4:e2b`
- Timeout: `45` seconds

Override with:

```powershell
$env:ANIBOT_OLLAMA_HOST = "http://127.0.0.1:11434"
$env:ANIBOT_OLLAMA_MODEL = "gemma4:e2b"
$env:ANIBOT_OLLAMA_TIMEOUT_SECONDS = "120"
```

Check connection:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/ollama/status
```

The home page shows the current Ollama connection status before the plan form and disables plan creation until the local Gemma model is active.

## Query Evidence From Python

```python
from pathlib import Path
from anibot.rag.retriever import retrieve_evidence

result = retrieve_evidence(
    query="water management seed preparation",
    crop="rice",
    db_path=Path("data/anibot_knowledge.db"),
)

for chunk in result.chunks:
    print(chunk.citation, chunk.chunk_id)
```

Phase 1 supports rice and corn farming plans. Corn standards are indexed as reviewed advisory evidence for corn-specific retrieval and source-backed recommendations.

Generated plans include a Current Concern Response near the top. It reflects the selected concerns and observation notes with immediate checks, actions to avoid until verified, records/photos to collect, and MAO escalation triggers.

## What Is Passed to Ollama

Ollama receives a JSON-only evidence-planner prompt containing:

- the farmer request fields
- compact retrieved guideline snippets with source labels
- draft calendar rows with period, approximate date, task, how-to steps, observation guidance, and escalation triggers
- the required structured output shape for the beginner timeline
- safety rules prohibiting new technical claims, exact fertilizer rates, pesticide products, chemical dosages, brands, money advice, and unsupported crop advice

Ollama is expected to return only a structured beginner timeline. AniBot keeps deterministic source-cited technical sections, validates the LLM timeline, and falls back to the template timeline if validation fails after Gemma was attempted.

## Generate a Plan From Python

```python
from pathlib import Path
from anibot.planning import FarmingPlanRequest, generate_farming_plan

request = FarmingPlanRequest(
    province="Nueva Ecija",
    municipality="Munoz",
    crop="corn",
    language="filipino",
    farming_type="conventional",
    planning_mode="planning_to_plant",
    target_planting_date="June",
    water_source="irrigated",
    soil_condition="moist",
    concerns=["fertilizer_nutrient"],
)

plan = generate_farming_plan(request, Path("data/anibot_knowledge.db"))
print(plan.model_dump_json(indent=2))
```

## Tests

```powershell
python -m pytest
```
