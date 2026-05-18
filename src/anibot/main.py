from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from anibot.llm.ollama import OllamaClient
from anibot.llm.vertex import VertexClient
from anibot.planning.generator import generate_farming_plan
from anibot.planning.repository import FarmingPlanRepository
from anibot.planning.schema import Concern, FarmingPlanRequest


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
KNOWLEDGE_DB = DATA_DIR / "anibot_knowledge.db"
APP_DB = DATA_DIR / "anibot_app.db"
TEMPLATE_DIR = Path(__file__).resolve().parent / "web" / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"
LOGGER = logging.getLogger(__name__)

app = FastAPI(title="AniBot Farming Plan")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


VERCEL_JUDGING_MODE = "vercel_judging"


@app.get("/", response_class=HTMLResponse)
def new_plan(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "concerns": _concern_options(),
            "latest": _latest_plans(),
            "engine": _engine_status(),
            "demo_mode": _is_vercel_judging_mode(),
        },
    )


@app.get("/ollama/status")
def ollama_status() -> dict:
    status = _ollama_status()
    return {
        "available": status.available,
        "host": status.host,
        "model": status.model,
        "models": status.models,
        "message": status.message,
    }


@app.post("/plans")
def create_plan(
    request: Request,
    province: Annotated[str, Form()],
    municipality: Annotated[str, Form()],
    barangay: Annotated[str, Form()] = "",
    field_notes: Annotated[str, Form()] = "",
    language: Annotated[str, Form()] = "english",
    crop: Annotated[str, Form()] = "rice",
    farming_type: Annotated[str, Form()] = "unknown",
    planning_mode: Annotated[str, Form()] = "planning_to_plant",
    target_planting_date: Annotated[str, Form()] = "",
    current_stage: Annotated[str, Form()] = "",
    water_source: Annotated[str, Form()] = "unknown",
    rice_ecosystem: Annotated[str, Form()] = "unknown",
    soil_condition: Annotated[str, Form()] = "unknown",
    concerns: Annotated[list[Concern], Form()] = ["none"],
    observation_notes: Annotated[str, Form()] = "",
):
    if not KNOWLEDGE_DB.exists():
        raise HTTPException(status_code=503, detail="Knowledge database not found. Run scripts/ingest_knowledge.py first.")
    plan_request = FarmingPlanRequest(
        province=province,
        municipality=municipality,
        barangay=barangay,
        field_notes=field_notes,
        language=language,
        crop=crop,
        farming_type=farming_type,
        planning_mode=planning_mode,
        target_planting_date=target_planting_date,
        current_stage=current_stage,
        water_source=water_source,
        rice_ecosystem=rice_ecosystem,
        soil_condition=soil_condition,
        concerns=concerns,
        observation_notes=observation_notes,
    )
    if _is_vercel_judging_mode():
        try:
            llm_client = _required_vertex_client()
            plan = generate_farming_plan(plan_request, KNOWLEDGE_DB, _chroma_dir(), llm_client=llm_client)
            return templates.TemplateResponse(
                request,
                "plan.html",
                {
                    "plan_request": plan_request,
                    "plan": plan,
                    "plan_id": None,
                    "demo_mode": True,
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            LOGGER.exception("Vercel judging plan generation failed")
            raise HTTPException(
                status_code=503,
                detail=f"Vercel judging plan generation failed: {_safe_runtime_error(exc)}",
            ) from exc
    llm_client = _required_ollama_client()
    plan = generate_farming_plan(plan_request, KNOWLEDGE_DB, _chroma_dir(), llm_client=llm_client)
    repo = FarmingPlanRepository(APP_DB)
    try:
        plan_id = repo.save(plan_request, plan)
    finally:
        repo.close()
    return RedirectResponse(url=f"/plans/{plan_id}", status_code=303)


@app.get("/plans/{plan_id}", response_class=HTMLResponse)
def show_plan(plan_id: int, request: Request) -> HTMLResponse:
    if _is_vercel_judging_mode():
        raise HTTPException(status_code=404, detail="Online judging plans are rendered immediately and are not persisted.")
    repo = FarmingPlanRepository(APP_DB)
    try:
        result = repo.get(plan_id)
    finally:
        repo.close()
    if result is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan_request, plan = result
    return templates.TemplateResponse(
        request,
        "plan.html",
        {
            "plan_request": plan_request,
            "plan": plan,
            "plan_id": plan_id,
        },
    )


def _latest_plans() -> list:
    if _is_vercel_judging_mode():
        return []
    if not APP_DB.exists():
        return []
    repo = FarmingPlanRepository(APP_DB)
    try:
        return repo.latest(limit=5)
    finally:
        repo.close()


def _concern_options() -> list[tuple[str, str]]:
    return [
        ("none", "None yet"),
        ("pests", "Pests"),
        ("weeds", "Weeds"),
        ("poor_growth", "Poor growth"),
        ("fertilizer_nutrient", "Fertilizer or nutrient concern"),
        ("water_shortage", "Water shortage"),
        ("heavy_rain_flooding", "Heavy rain or flooding"),
        ("harvest_post_harvest", "Harvest or post-harvest concern"),
    ]


def _ollama_status():
    return OllamaClient().status(timeout_seconds=0.8)


def _vertex_status():
    return VertexClient().status()


def _engine_status():
    if _is_vercel_judging_mode():
        return _vertex_status()
    return _ollama_status()


def _is_vercel_judging_mode() -> bool:
    return os.getenv("ANIBOT_RUNTIME_MODE", "").strip().lower() == VERCEL_JUDGING_MODE


def _chroma_dir() -> Path | None:
    if _is_vercel_judging_mode():
        return None
    return DATA_DIR / "chroma"


def _required_llm_client():
    if _is_vercel_judging_mode():
        return _required_vertex_client()
    return _required_ollama_client()


def _required_vertex_client() -> VertexClient:
    candidate = VertexClient()
    status = candidate.status()
    if not status.available:
        raise HTTPException(status_code=503, detail=status.message)
    return candidate


def _required_ollama_client() -> OllamaClient:
    candidate = OllamaClient()
    status = candidate.status(timeout_seconds=0.8)
    if not status.available:
        raise HTTPException(
            status_code=503,
            detail=f"Gemma via Ollama is required to generate a plan. {status.message}",
        )
    return candidate


def _safe_runtime_error(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    for key in ("GOOGLE_APPLICATION_CREDENTIALS_JSON", "private_key", "client_email", "token"):
        text = text.replace(key, "[redacted]")
    if not text:
        text = exc.__class__.__name__
    return f"{exc.__class__.__name__}: {text[:700]}"
