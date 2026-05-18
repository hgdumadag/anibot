from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

import anibot.main as main_module
from anibot.main import app
from anibot.planning.generator import generate_farming_plan
from anibot.planning.repository import FarmingPlanRepository
from anibot.planning.schema import FarmingPlanRequest
from anibot.rag.ingest import ingest_knowledge


ROOT = Path(__file__).resolve().parents[1]


def _db(tmp_path: Path) -> Path:
    db_path = tmp_path / "knowledge.db"
    ingest_knowledge(ROOT, db_path=db_path, chroma_dir=tmp_path / "chroma")
    return db_path


def _rice_request(**overrides) -> FarmingPlanRequest:
    data = {
        "province": "Nueva Ecija",
        "municipality": "Munoz",
        "barangay": "Demo Barangay",
        "crop": "rice",
        "farming_type": "conventional",
        "planning_mode": "planning_to_plant",
        "target_planting_date": "June",
        "water_source": "irrigated",
        "rice_ecosystem": "lowland",
        "soil_condition": "moist",
        "concerns": ["fertilizer_nutrient"],
        "observation_notes": "Farmer wants basic soil and fertilizer guidance.",
    }
    data.update(overrides)
    return FarmingPlanRequest(**data)


def test_rice_plan_generation_has_source_backed_sections(tmp_path: Path) -> None:
    plan = generate_farming_plan(_rice_request(), _db(tmp_path))

    assert plan.status == "generated"
    assert plan.source_count > 0
    assert len(plan.sections) >= 10
    assert all(section.citations or section.fallback_reason for section in plan.sections)
    assert plan.timeline
    assert plan.glossary
    assert plan.decision_rows
    assert plan.material_checklist
    assert plan.record_templates
    assert plan.mao_questions


def test_date_specific_timeline_uses_target_planting_date(tmp_path: Path) -> None:
    plan = generate_farming_plan(_rice_request(target_planting_date="2026-06-15"), _db(tmp_path))
    rendered = plan.model_dump_json()

    assert "May 4-18, 2026" in rendered
    assert "May 18-25, 2026" in rendered
    assert "June 15, 2026" in rendered


def test_timeline_falls_back_for_vague_target_date(tmp_path: Path) -> None:
    plan = generate_farming_plan(_rice_request(target_planting_date="June"), _db(tmp_path))

    assert plan.timeline
    assert plan.timeline[0].approximate_date == "Relative to target planting date"
    assert any(item.period == "Planting week" for item in plan.timeline)


def test_organic_plan_blocks_chemical_pesticide_for_stored_organic_rice(tmp_path: Path) -> None:
    request = _rice_request(farming_type="organic_traditional", concerns=["pests"])

    plan = generate_farming_plan(request, _db(tmp_path))
    rendered = plan.model_dump_json().lower()

    assert "chemical pesticides for stored organic rice" in rendered
    assert "ask mao" in rendered
    assert "product-specific" not in rendered


def test_conventional_plan_keeps_pesticide_guidance_general(tmp_path: Path) -> None:
    request = _rice_request(farming_type="conventional", concerns=["pests"])

    plan = generate_farming_plan(request, _db(tmp_path))
    rendered = plan.model_dump_json().lower()

    assert "registered-pesticide" not in rendered
    assert "registered" in rendered
    assert "pesticide selection" in rendered
    assert "glyphosate" not in rendered
    assert "insecticide brand" not in rendered


def test_fertility_section_does_not_invent_exact_rates(tmp_path: Path) -> None:
    plan = generate_farming_plan(_rice_request(concerns=["fertilizer_nutrient", "poor_growth"]), _db(tmp_path))
    fertility = next(section for section in plan.sections if section.key == "soil_fertility")
    text = " ".join(fertility.guidance).lower()

    assert "soil" in text
    assert "analysis" in text
    assert "kg/ha" not in text
    assert "bags per hectare" not in text


def test_current_concerns_section_addresses_selected_concerns(tmp_path: Path) -> None:
    request = _rice_request(
        concerns=["pests", "water_shortage"],
        observation_notes="Leaf holes near the dry edge of the field.",
    )

    plan = generate_farming_plan(request, _db(tmp_path))
    concern_section = next(section for section in plan.sections if section.key == "current_concerns")
    rendered = concern_section.model_dump_json().lower()

    assert plan.sections[1].key == "current_concerns"
    assert concern_section.title == "Current Concern Response"
    assert "submitted concern: pests, water shortage" in rendered
    assert "leaf holes near the dry edge" in rendered
    assert "identify the pest first" in rendered
    assert "check the water source" in rendered
    assert "do not spray immediately" in rendered
    assert len(concern_section.actions) == 2
    assert concern_section.citations


def test_current_concerns_section_sanitizes_money_terms(tmp_path: Path) -> None:
    request = _rice_request(
        concerns=["poor_growth"],
        observation_notes="The farmer mentioned budget and cost but plants are yellow.",
    )

    plan = generate_farming_plan(request, _db(tmp_path))
    rendered = plan.model_dump_json().lower()

    assert "budget" not in rendered
    assert "cost" not in rendered
    assert "[removed money term]" in rendered


def test_filipino_current_concerns_section_addresses_selected_concerns(tmp_path: Path) -> None:
    request = _rice_request(
        language="filipino",
        concerns=["pests", "heavy_rain_flooding"],
        observation_notes="May sira sa dahon pagkatapos ng baha.",
    )

    plan = generate_farming_plan(request, _db(tmp_path))
    concern_section = next(section for section in plan.sections if section.key == "current_concerns")
    rendered = concern_section.model_dump_json().lower()

    assert concern_section.title == "Tugon sa Kasalukuyang Alalahanin"
    assert "ipinasang alalahanin: peste, malakas na ulan o baha" in rendered
    assert "may sira sa dahon pagkatapos ng baha" in rendered
    assert "huwag agad mag-spray" in rendered
    assert "suriin ang daluyan" in rendered


def test_beginner_artifacts_keep_safety_boundaries(tmp_path: Path) -> None:
    plan = generate_farming_plan(_rice_request(target_planting_date="2026-06-15", concerns=["pests", "fertilizer_nutrient"]), _db(tmp_path))
    rendered = plan.model_dump_json().lower()

    blocked = [
        "kg/ha",
        "bags per hectare",
        "glyphosate",
        "insecticide brand",
        "product-specific advice",
        "guarantee yield",
        "guaranteed yield",
    ]
    for term in blocked:
        assert term not in rendered


def test_corn_plan_generation_has_source_backed_sections(tmp_path: Path) -> None:
    request = _rice_request(crop="corn")

    plan = generate_farming_plan(request, _db(tmp_path))

    assert plan.status == "generated"
    assert plan.crop == "corn"
    assert plan.source_count > 0
    assert any(citation.chunk_id.startswith("pns_bafs_20_2018_corn_gap") for section in plan.sections for citation in section.citations)
    assert "corn" in plan.model_dump_json().lower()


def test_corn_planting_week_gives_practical_planting_workflow(tmp_path: Path) -> None:
    request = _rice_request(crop="corn", target_planting_date="2026-06-08")

    plan = generate_farming_plan(request, _db(tmp_path))
    planting_week = next(item for item in plan.timeline if item.period == "Planting week")
    rendered_steps = " ".join(planting_week.how_to_steps).lower()

    assert "planting distance" in rendered_steps
    assert "seeding rate" in rendered_steps
    assert "mark rows or hills" in rendered_steps
    assert "furrows or holes" in rendered_steps
    assert "irrigate or wait for rain" in rendered_steps
    assert "actual spacing or seeding rate used" in rendered_steps
    assert "recommended spacing or seeding rate is unknown" in planting_week.ask_for_help_if.lower()


def test_plan_output_has_no_budget_or_capital_terms(tmp_path: Path) -> None:
    plan = generate_farming_plan(_rice_request(), _db(tmp_path))
    rendered = plan.model_dump_json().lower()

    assert "budget" not in rendered
    assert "capital" not in rendered
    assert "cost" not in rendered
    assert "price" not in rendered


def test_repository_saves_and_loads_plan(tmp_path: Path) -> None:
    request = _rice_request()
    plan = generate_farming_plan(request, _db(tmp_path))
    repo = FarmingPlanRepository(tmp_path / "app.db")
    try:
        plan_id = repo.save(request, plan)
        loaded = repo.get(plan_id)
    finally:
        repo.close()

    assert loaded is not None
    loaded_request, loaded_plan = loaded
    assert loaded_request.location_label == request.location_label
    assert loaded_request.language == request.language
    assert loaded_plan.language == plan.language
    assert loaded_plan.source_count == plan.source_count


def test_filipino_plan_generation_uses_selected_language(tmp_path: Path) -> None:
    request = _rice_request(language="filipino", target_planting_date="2026-06-15")

    plan = generate_farming_plan(request, _db(tmp_path))
    rendered = plan.model_dump_json().lower()

    assert plan.language == "filipino"
    assert plan.planning_basis.startswith("nagpaplanong magtanim")
    assert plan.sections[0].title == "Buod ng Plano"
    assert any(item.period == "Linggo ng pagtatanim" for item in plan.timeline)
    assert "plano sa lupa at sustansiya" in rendered


def test_cebuano_plan_generation_uses_selected_language(tmp_path: Path) -> None:
    request = _rice_request(
        language="cebuano",
        concerns=["pests", "water_shortage"],
        observation_notes="Naay buslot sa dahon ug uga ang kilid sa uma.",
        target_planting_date="2026-06-15",
    )

    plan = generate_farming_plan(request, _db(tmp_path))
    concern_section = next(section for section in plan.sections if section.key == "current_concerns")
    rendered = plan.model_dump_json().lower()

    assert plan.language == "cebuano"
    assert plan.planning_basis.startswith("nagplano nga magtanom")
    assert plan.sections[0].title == "Kinatibuk-ang Plano"
    assert concern_section.title == "Tubag sa Kasamtangang Kabalaka"
    assert "gisumiter nga kabalaka: peste, kakulang sa tubig" in rendered
    assert "naay buslot sa dahon ug uga ang kilid sa uma" in rendered
    assert any(item.period == "Semana sa pagtanom" for item in plan.timeline)
    assert "plano sa yuta ug sustansiya" in rendered


def test_form_does_not_ask_for_available_capital() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text.lower()
    assert "available capital" not in html
    assert 'name="capital"' not in html
    assert "budget" not in html
    assert 'name="language"' in html
    assert "filipino" in html
    assert "cebuano" in html
    assert "primary local ai engine" in html
    assert "local gemma" in html
    assert "all data stays on this device" in html
    assert "vertex ai" not in html
    assert 'name="use_ollama"' not in html


def test_plan_page_renders_beginner_tables(tmp_path: Path) -> None:
    plan = generate_farming_plan(_rice_request(target_planting_date="2026-06-15"), _db(tmp_path))
    repo = FarmingPlanRepository(tmp_path / "app.db")
    try:
        plan_id = repo.save(_rice_request(target_planting_date="2026-06-15"), plan)
    finally:
        repo.close()

    original_app_db = main_module.APP_DB
    main_module.APP_DB = tmp_path / "app.db"
    try:
        client = TestClient(app)
        response = client.get(f"/plans/{plan_id}")
    finally:
        main_module.APP_DB = original_app_db

    assert response.status_code == 200
    html = response.text
    assert "Beginner Calendar" in html
    assert "What To Do Next" in html
    assert "Materials Checklist" in html
    assert "Recordkeeping Templates" in html
    assert "MAO Visit Checklist" in html
    assert "Field Activity Record" in html
    assert "Print farming plan" in html
    assert "window.print()" in html


def test_plan_page_renders_filipino_labels(tmp_path: Path) -> None:
    request = _rice_request(language="filipino", target_planting_date="2026-06-15")
    plan = generate_farming_plan(request, _db(tmp_path))
    repo = FarmingPlanRepository(tmp_path / "app.db")
    try:
        plan_id = repo.save(request, plan)
    finally:
        repo.close()

    original_app_db = main_module.APP_DB
    main_module.APP_DB = tmp_path / "app.db"
    try:
        client = TestClient(app)
        response = client.get(f"/plans/{plan_id}")
    finally:
        main_module.APP_DB = original_app_db

    assert response.status_code == 200
    html = response.text
    assert "Kalendaryo para sa Baguhan" in html
    assert "Checklist sa Pagbisita sa MAO" in html
    assert "I-print ang plano" in html
    assert "Buod ng Plano" in html


def test_plan_page_renders_cebuano_labels(tmp_path: Path) -> None:
    request = _rice_request(language="cebuano", target_planting_date="2026-06-15")
    plan = generate_farming_plan(request, _db(tmp_path))
    repo = FarmingPlanRepository(tmp_path / "app.db")
    try:
        plan_id = repo.save(request, plan)
    finally:
        repo.close()

    original_app_db = main_module.APP_DB
    main_module.APP_DB = tmp_path / "app.db"
    try:
        client = TestClient(app)
        response = client.get(f"/plans/{plan_id}")
    finally:
        main_module.APP_DB = original_app_db

    assert response.status_code == 200
    html = response.text
    assert "Kalendaryo para sa Bag-ohan" in html
    assert "Checklist sa Pagbisita sa MAO" in html
    assert "I-print ang plano" in html
    assert "Kinatibuk-ang Plano" in html
    assert "Pinulongan: Cebuano" in html


def test_ollama_status_endpoint_returns_connection_shape() -> None:
    client = TestClient(app)

    response = client.get("/ollama/status")

    assert response.status_code == 200
    payload = response.json()
    assert {"available", "host", "model", "models", "message"} <= set(payload)


def test_create_plan_uses_ollama_without_form_opt_in(tmp_path: Path, monkeypatch) -> None:
    knowledge_db = _db(tmp_path)
    app_db = tmp_path / "app.db"

    class FakeLlm:
        model = "fake-rice-model"

        def generate_json(self, prompt: str) -> dict:
            payload = json.loads(prompt.split("INPUT=", 1)[1])
            return {
                "timeline": [
                    {
                        "period": item["period"],
                        "approximate_date": item["approximate_date"],
                        "task": f"Confirm readiness for {item['period']}.",
                        "how_to_steps": [
                            "Check soil moisture, water control, and seed readiness before field work.",
                            "Record field condition and water availability.",
                            "Ask MAO if soil, pest, or water observations are unclear.",
                        ],
                        "observe": "Soil moisture, water control, weeds, pests, yellowing, and uneven growth.",
                        "ask_for_help_if": "Soil, water, pest identity, or seed readiness is uncertain.",
                    }
                    for item in payload["calendar"]
                ],
            }

    original_knowledge_db = main_module.KNOWLEDGE_DB
    original_app_db = main_module.APP_DB
    monkeypatch.setattr(main_module, "KNOWLEDGE_DB", knowledge_db)
    monkeypatch.setattr(main_module, "APP_DB", app_db)
    monkeypatch.setattr(main_module, "_required_ollama_client", lambda: FakeLlm())
    try:
        client = TestClient(app)
        response = client.post(
            "/plans",
            data={
                "province": "Nueva Ecija",
                "municipality": "Munoz",
                "barangay": "Demo Barangay",
                "language": "english",
                "crop": "rice",
                "farming_type": "conventional",
                "planning_mode": "planning_to_plant",
                "target_planting_date": "June",
                "water_source": "irrigated",
                "rice_ecosystem": "lowland",
                "soil_condition": "moist",
                "concerns": ["fertilizer_nutrient"],
            },
            follow_redirects=False,
        )
    finally:
        main_module.KNOWLEDGE_DB = original_knowledge_db
        main_module.APP_DB = original_app_db

    assert response.status_code == 303
    repo = FarmingPlanRepository(app_db)
    try:
        saved = repo.get(1)
    finally:
        repo.close()
    assert saved is not None
    _, plan = saved
    assert plan.generation_method == "ollama"
    assert plan.llm_model == "fake-rice-model"


def test_create_plan_requires_gemma_ollama_connection(tmp_path: Path, monkeypatch) -> None:
    knowledge_db = _db(tmp_path)
    app_db = tmp_path / "app.db"

    def unavailable_client():
        raise HTTPException(status_code=503, detail="Gemma via Ollama is required to generate a plan.")

    original_knowledge_db = main_module.KNOWLEDGE_DB
    original_app_db = main_module.APP_DB
    monkeypatch.setattr(main_module, "KNOWLEDGE_DB", knowledge_db)
    monkeypatch.setattr(main_module, "APP_DB", app_db)
    monkeypatch.setattr(main_module, "_required_ollama_client", unavailable_client)
    try:
        client = TestClient(app)
        response = client.post(
            "/plans",
            data={
                "province": "Nueva Ecija",
                "municipality": "Munoz",
                "language": "english",
                "crop": "rice",
                "farming_type": "conventional",
                "planning_mode": "planning_to_plant",
                "target_planting_date": "June",
                "water_source": "irrigated",
                "rice_ecosystem": "lowland",
                "soil_condition": "moist",
                "concerns": ["fertilizer_nutrient"],
            },
            follow_redirects=False,
        )
    finally:
        main_module.KNOWLEDGE_DB = original_knowledge_db
        main_module.APP_DB = original_app_db

    assert response.status_code == 503
    assert "Gemma via Ollama is required" in response.text
    assert not app_db.exists()


def test_vercel_judging_form_uses_vertex_demo_copy(monkeypatch) -> None:
    monkeypatch.setenv("ANIBOT_RUNTIME_MODE", "vercel_judging")
    monkeypatch.delenv("ANIBOT_VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    html = response.text.lower()
    assert "judging demo: gemma via vertex ai" in html
    assert "temporary vercel judging mode" in html
    assert "plans are not stored permanently in online judging mode" in html
    assert "all data stays on this device" not in html
    assert "recent plans" not in html


def test_vercel_judging_requires_vertex_config(tmp_path: Path, monkeypatch) -> None:
    knowledge_db = _db(tmp_path)
    app_db = tmp_path / "app.db"

    monkeypatch.setenv("ANIBOT_RUNTIME_MODE", "vercel_judging")
    monkeypatch.delenv("ANIBOT_VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(main_module, "KNOWLEDGE_DB", knowledge_db)
    monkeypatch.setattr(main_module, "APP_DB", app_db)

    client = TestClient(app)
    response = client.post(
        "/plans",
        data={
            "province": "Nueva Ecija",
            "municipality": "Munoz",
            "language": "english",
            "crop": "rice",
            "farming_type": "conventional",
            "planning_mode": "planning_to_plant",
            "target_planting_date": "June",
            "water_source": "irrigated",
            "rice_ecosystem": "lowland",
            "soil_condition": "moist",
            "concerns": ["fertilizer_nutrient"],
        },
    )

    assert response.status_code == 503
    assert "Vertex AI judging mode is not configured" in response.text
    assert not app_db.exists()


def test_vercel_judging_renders_plan_without_persistent_app_db(tmp_path: Path, monkeypatch) -> None:
    knowledge_db = _db(tmp_path)
    app_db = tmp_path / "app.db"

    class FakeVertexLlm:
        generation_method = "vertex"
        model = "gemma-4-26b-a4b-it"

        def generate_json(self, prompt: str) -> dict:
            payload = json.loads(prompt.split("INPUT=", 1)[1])
            return {
                "timeline": [
                    {
                        "period": item["period"],
                        "approximate_date": item["approximate_date"],
                        "task": f"Check demo readiness for {item['period']}.",
                        "how_to_steps": [
                            "Check soil moisture, field access, and water control.",
                            "Record field condition and crop observations.",
                            "Ask MAO if local timing or field symptoms are unclear.",
                        ],
                        "observe": "Soil moisture, water control, weeds, pests, and crop growth.",
                        "ask_for_help_if": "Local timing, pest identity, or water control is uncertain.",
                    }
                    for item in payload["calendar"]
                ],
            }

    monkeypatch.setenv("ANIBOT_RUNTIME_MODE", "vercel_judging")
    monkeypatch.setattr(main_module, "KNOWLEDGE_DB", knowledge_db)
    monkeypatch.setattr(main_module, "APP_DB", app_db)
    monkeypatch.setattr(main_module, "_required_vertex_client", lambda: FakeVertexLlm())

    client = TestClient(app)
    response = client.post(
        "/plans",
        data={
            "province": "Nueva Ecija",
            "municipality": "Munoz",
            "barangay": "Demo Barangay",
            "language": "english",
            "crop": "rice",
            "farming_type": "conventional",
            "planning_mode": "planning_to_plant",
            "target_planting_date": "June",
            "water_source": "irrigated",
            "rice_ecosystem": "lowland",
            "soil_condition": "moist",
            "concerns": ["fertilizer_nutrient"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.text
    assert "Temporary online judging mode" in html
    assert "Generated with Vertex AI judging model: gemma-4-26b-a4b-it" in html
    assert "Print farming plan" in html
    assert "Sources" in html
    assert not app_db.exists()


def test_vercel_judging_does_not_use_chroma_dir(tmp_path: Path, monkeypatch) -> None:
    knowledge_db = _db(tmp_path)
    runtime_db = tmp_path / "runtime" / "anibot_knowledge.db"
    captured: dict = {}

    class FakeVertexLlm:
        generation_method = "vertex"
        model = "gemma-4-26b-a4b-it"

    def fake_generator(plan_request, knowledge_path, chroma_dir=None, llm_client=None):
        captured["knowledge_path"] = knowledge_path
        captured["chroma_dir"] = chroma_dir
        return generate_farming_plan(plan_request, knowledge_path, chroma_dir=None)

    monkeypatch.setenv("ANIBOT_RUNTIME_MODE", "vercel_judging")
    monkeypatch.setattr(main_module, "KNOWLEDGE_DB", knowledge_db)
    monkeypatch.setattr(main_module, "RUNTIME_KNOWLEDGE_DB", runtime_db)
    monkeypatch.setattr(main_module, "_required_vertex_client", lambda: FakeVertexLlm())
    monkeypatch.setattr(main_module, "generate_farming_plan", fake_generator)

    client = TestClient(app)
    response = client.post(
        "/plans",
        data={
            "province": "Nueva Ecija",
            "municipality": "Munoz",
            "language": "english",
            "crop": "rice",
            "farming_type": "conventional",
            "planning_mode": "planning_to_plant",
            "target_planting_date": "June",
            "water_source": "irrigated",
            "rice_ecosystem": "lowland",
            "soil_condition": "moist",
            "concerns": ["fertilizer_nutrient"],
        },
    )

    assert response.status_code == 200
    assert captured["knowledge_path"] == runtime_db
    assert captured["chroma_dir"] is None
    assert runtime_db.exists()


def test_vercel_judging_plan_urls_are_not_persisted(monkeypatch) -> None:
    monkeypatch.setenv("ANIBOT_RUNTIME_MODE", "vercel_judging")

    client = TestClient(app)
    response = client.get("/plans/1")

    assert response.status_code == 404
    assert "not persisted" in response.text


def test_vercel_judging_unexpected_errors_return_diagnostic_503(tmp_path: Path, monkeypatch) -> None:
    knowledge_db = _db(tmp_path)

    class BrokenVertexLlm:
        model = "broken-vertex"

        def generate_json(self, prompt: str) -> dict:
            raise RuntimeError("upstream exploded")

    def broken_generator(*args, **kwargs):
        raise RuntimeError("template render setup failed")

    monkeypatch.setenv("ANIBOT_RUNTIME_MODE", "vercel_judging")
    monkeypatch.setattr(main_module, "KNOWLEDGE_DB", knowledge_db)
    monkeypatch.setattr(main_module, "_required_vertex_client", lambda: BrokenVertexLlm())
    monkeypatch.setattr(main_module, "generate_farming_plan", broken_generator)

    client = TestClient(app)
    response = client.post(
        "/plans",
        data={
            "province": "Nueva Ecija",
            "municipality": "Munoz",
            "language": "english",
            "crop": "rice",
            "farming_type": "conventional",
            "planning_mode": "planning_to_plant",
            "target_planting_date": "June",
            "water_source": "irrigated",
            "rice_ecosystem": "lowland",
            "soil_condition": "moist",
            "concerns": ["fertilizer_nutrient"],
        },
    )

    assert response.status_code == 503
    assert "Vercel judging plan generation failed" in response.text
    assert "RuntimeError" in response.text


def test_llm_planner_generates_artifacts_without_changing_citations(tmp_path: Path) -> None:
    request = _rice_request()
    draft = generate_farming_plan(request, _db(tmp_path))

    class FakeLlm:
        model = "fake-rice-model"

        def generate_json(self, prompt: str) -> dict:
            assert '"evidence"' in prompt
            assert "draft_plan" not in prompt
            assert len(prompt) < 12000
            payload = json.loads(prompt.split("INPUT=", 1)[1])
            assert payload["evidence"]
            assert payload["calendar"][0]["draft_how_to_steps"]
            return {
                "timeline": [
                    {
                        "period": item["period"],
                        "approximate_date": item["approximate_date"],
                        "task": f"Confirm soil, water, and seed readiness for {item['period']}.",
                        "how_to_steps": [
                            "Check soil moisture, bunds, canals, and drainage before field work.",
                            "Record seed source, field condition, and water availability.",
                            "Ask MAO to confirm soil test interpretation before nutrient decisions.",
                        ],
                        "observe": "Soil moisture, seed source, water control, weeds, pests, yellowing, and uneven growth.",
                        "ask_for_help_if": "Soil test interpretation, seed quality, drainage, or pest identity is uncertain.",
                    }
                    for item in payload["calendar"]
                ],
            }

    plan = generate_farming_plan(request, _db(tmp_path), llm_client=FakeLlm())

    assert plan.generation_method == "ollama"
    assert plan.llm_model == "fake-rice-model"
    assert plan.llm_error is None
    assert plan.timeline[0].task == "Confirm soil, water, and seed readiness for 4-6 weeks before planting."
    assert "Soil moisture" in plan.timeline[0].observe
    assert plan.decision_rows == draft.decision_rows
    assert plan.material_checklist == draft.material_checklist
    assert plan.source_count == draft.source_count
    assert plan.sections[0].citations == draft.sections[0].citations
    assert plan.sections[0].guidance == draft.sections[0].guidance


def test_llm_timeline_keeps_template_when_ollama_is_vague(tmp_path: Path) -> None:
    request = _rice_request()
    draft = generate_farming_plan(request, _db(tmp_path))

    class VagueTimelineLlm:
        model = "vague-timeline-model"

        def generate_json(self, prompt: str) -> dict:
            payload = json.loads(prompt.split("INPUT=", 1)[1])
            return {
                "timeline": [
                    {
                            "period": item["period"],
                            "approximate_date": item["approximate_date"],
                            "task": "Final Preparations",
                            "how_to_steps": ["Prepare seeds for planting.", "Check field condition."],
                            "observe": "Soil and seed readiness.",
                            "ask_for_help_if": "Need help interpreting soil condition.",
                        }
                        for item in payload["calendar"]
                    ],
                }

    plan = generate_farming_plan(request, _db(tmp_path), llm_client=VagueTimelineLlm())

    assert plan.generation_method == "ollama"
    assert plan.llm_error is None
    assert plan.timeline[1].how_to_steps == draft.timeline[1].how_to_steps
    assert "zigzag" in " ".join(plan.timeline[1].how_to_steps).lower()


def test_llm_invalid_response_falls_back_to_template(tmp_path: Path) -> None:
    request = _rice_request()

    class BadLlm:
        model = "bad-model"

        def generate_json(self, prompt: str) -> dict:
            return {"wrong": []}

    plan = generate_farming_plan(request, _db(tmp_path), llm_client=BadLlm())

    assert plan.generation_method == "fallback"
    assert plan.llm_model == "bad-model"
    assert "LLM response must contain one timeline item" in (plan.llm_error or "")
    assert plan.sections[0].title == "Plan Summary"


def test_llm_fallback_error_is_sanitized(tmp_path: Path) -> None:
    request = _rice_request()

    class UnsafeErrorLlm:
        model = "unsafe-error-model"

        def generate_json(self, prompt: str) -> dict:
            raise ValueError("response mentioned budget and cost")

    plan = generate_farming_plan(request, _db(tmp_path), llm_client=UnsafeErrorLlm())

    assert plan.generation_method == "fallback"
    assert "budget" not in (plan.llm_error or "").lower()
    assert "cost" not in (plan.llm_error or "").lower()
    assert "[blocked term]" in (plan.llm_error or "")
