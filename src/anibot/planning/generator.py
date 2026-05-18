from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import re
from typing import Protocol

from anibot.planning.schema import (
    Citation,
    DecisionRow,
    FarmingPlan,
    FarmingPlanRequest,
    GlossaryItem,
    MaoQuestion,
    MaterialChecklistGroup,
    PlanAction,
    PlanSection,
    RecordTemplate,
    TimelineItem,
)
from anibot.planning.localization import localize_plan
from anibot.rag.retriever import retrieve_evidence
from anibot.rag.store import StoredChunk


class PlanLlmClient(Protocol):
    model: str

    def generate_json(self, prompt: str) -> dict:
        ...


TECHNICAL_SECTIONS = {
    "before_planting": "{crop} farm location soil analysis land preparation seedbed water source drainage",
    "planting_establishment": "{crop} land preparation planting seed material seedbed crop establishment",
    "soil_fertility": "{crop} soil nutrients fertilizer organic soil amendments nutrient management soil analysis",
    "water_management": "{crop} water management irrigation drainage dry flooded rainfall",
    "pest_weed": "{crop} integrated pest management pesticide weed management monitoring registered pesticides",
    "harvest_post_harvest": "{crop} harvest post-harvest drying storage contamination pesticide fertilizer storage",
}

CONTEXT_QUERY = "PAGASA rainfall soil moisture water shortage heavy rain flooding farm operations"


@dataclass(frozen=True)
class EvidenceBundle:
    section_key: str
    chunks: list[StoredChunk]
    fallback_reason: str | None

    @property
    def advisory_chunks(self) -> list[StoredChunk]:
        return [chunk for chunk in self.chunks if chunk.allowed_use == "advisory_evidence"]

    @property
    def context_chunks(self) -> list[StoredChunk]:
        return [chunk for chunk in self.chunks if chunk.allowed_use == "context_only"]


def generate_farming_plan(
    request: FarmingPlanRequest,
    db_path: Path,
    chroma_dir: Path | None = None,
    llm_client: PlanLlmClient | None = None,
) -> FarmingPlan:
    if request.crop not in {"rice", "corn"}:
        return _unsupported_crop_plan(request)

    bundles = {
        key: _retrieve_section_evidence(key, query.format(crop=request.crop), request, db_path, chroma_dir)
        for key, query in TECHNICAL_SECTIONS.items()
    }
    context_bundle = _retrieve_context_evidence(request, db_path, chroma_dir)
    sections = [
        _summary_section(request, bundles, context_bundle),
        _current_concerns_section(request, bundles, context_bundle),
        _before_planting_section(request, bundles["before_planting"]),
        _planting_section(request, bundles["planting_establishment"]),
        _soil_fertility_section(request, bundles["soil_fertility"]),
        _water_section(request, bundles["water_management"], context_bundle),
        _pest_weed_section(request, bundles["pest_weed"]),
        _stage_checklist_section(request, bundles),
        _harvest_section(request, bundles["harvest_post_harvest"]),
        _records_section(request, bundles),
        _warning_section(request, bundles),
    ]
    warnings = _warnings_for_request(request, bundles)
    citations = {citation.chunk_id for section in sections for citation in section.citations}
    status = "generated" if citations else "insufficient_evidence"
    draft = FarmingPlan(
        crop=request.crop,
        location=request.location_label,
        language=request.language,
        farming_type=request.farming_type,
        planning_basis=_planning_basis(request),
        status=status,
        generation_method="template",
        warnings=warnings,
        sections=sections,
        timeline=_timeline_for_request(request),
        glossary=_glossary_items(),
        decision_rows=_decision_rows_for_request(request),
        material_checklist=_material_checklist(request),
        record_templates=_record_templates(),
        mao_questions=_mao_questions_for_request(request),
        source_count=len(citations),
    )
    if llm_client is None or status != "generated":
        return localize_plan(request, draft)
    return localize_plan(request, _plan_artifacts_with_llm(request, draft, bundles, context_bundle, llm_client))


def _retrieve_section_evidence(
    key: str,
    query: str,
    request: FarmingPlanRequest,
    db_path: Path,
    chroma_dir: Path | None,
) -> EvidenceBundle:
    terms = [
        query,
        request.farming_type.replace("_", " "),
        request.water_source,
        request.rice_ecosystem,
        request.soil_condition,
        " ".join(request.concerns),
        request.observation_notes,
    ]
    result = retrieve_evidence(" ".join(terms), request.crop, db_path, chroma_dir=chroma_dir, limit=5)
    return EvidenceBundle(section_key=key, chunks=result.chunks, fallback_reason=result.fallback_reason)


def _retrieve_context_evidence(
    request: FarmingPlanRequest,
    db_path: Path,
    chroma_dir: Path | None,
) -> EvidenceBundle:
    result = retrieve_evidence(
        f"{CONTEXT_QUERY} {request.province} {request.municipality} {' '.join(request.concerns)}",
        request.crop,
        db_path,
        chroma_dir=chroma_dir,
        include_context=True,
        limit=5,
    )
    context = [chunk for chunk in result.chunks if chunk.allowed_use == "context_only"]
    return EvidenceBundle(section_key="context", chunks=context, fallback_reason=result.fallback_reason if not context else None)


def _summary_section(
    request: FarmingPlanRequest,
    bundles: dict[str, EvidenceBundle],
    context_bundle: EvidenceBundle,
) -> PlanSection:
    citations = _citations_from([*bundles["before_planting"].advisory_chunks[:1], *context_bundle.context_chunks[:1]])
    guidance = [
        f"Prepare a {_crop_label(request)} farming plan for {request.location_label} using {request.farming_type.replace('_', ' ')} guidance where available.",
        f"Planning basis: {_planning_basis(request)}.",
        "Use this as decision support and confirm unusual field conditions with the Municipal Agriculture Office.",
    ]
    if request.field_notes:
        guidance.append(f"Field note considered: {request.field_notes}.")
    if _is_surigao_area(request):
        guidance.append("For Marga or nearby Surigao City fields, confirm with MAO or local farmers that the target date matches local rainfall, irrigation, and drainage conditions.")
    return PlanSection(
        key="plan_summary",
        title="Plan Summary",
        guidance=guidance,
        citations=citations,
        fallback_reason=None if citations else "No reviewed source was found for the summary context.",
    )


def _current_concerns_section(
    request: FarmingPlanRequest,
    bundles: dict[str, EvidenceBundle],
    context_bundle: EvidenceBundle,
) -> PlanSection:
    selected = [concern for concern in request.concerns if concern != "none"]
    if not selected:
        selected = ["none"]

    guidance = [
        f"Submitted concern: {_concern_summary(selected)}.",
        "Start with field observation and records before applying fertilizer, pesticide, or other irreversible action.",
    ]
    if request.observation_notes.strip():
        guidance.append(f"Farmer observation note: {_safe_user_text(request.observation_notes)}.")
    for concern in selected:
        guidance.extend(_concern_guidance(request, concern))

    citations = _citations_from(_concern_citation_chunks(selected, bundles, context_bundle))
    return PlanSection(
        key="current_concerns",
        title="Current Concern Response",
        guidance=guidance,
        actions=[_concern_action(request, concern) for concern in selected],
        citations=citations,
        fallback_reason=None if citations else "No source-backed concern evidence found; use this as a safety triage and confirm with MAO.",
    )


def _before_planting_section(request: FarmingPlanRequest, bundle: EvidenceBundle) -> PlanSection:
    guidance = [
        "Check whether the site is suitable before land preparation. Look for nearby chemical, industrial, waste, or contamination hazards.",
        "Gather soil samples before land preparation and use the result for nutrient or organic soil amendment decisions.",
        "For a simple soil sample: walk in a zigzag path, collect small samples from several normal spots, avoid unusual spots, mix the soil in a clean container, then bring it to MAO or the recommended lab.",
        "Prepare the field according to contour, soil type, rainfall pattern, water source, and drainage condition.",
        "Repair bunds, canals, and drainage paths before planting, especially if the field is flooded or rainfall is expected.",
    ]
    if request.soil_condition == "dry":
        guidance.append("If the soil is too dry, prioritize water availability before final land preparation.")
    if request.soil_condition == "flooded":
        guidance.append("If the field is flooded, drain or stabilize the area before seedbed or planting work.")
    return _section(
        "before_planting",
        "Before Planting",
        guidance,
        [
            PlanAction(task="Inspect the field and nearby land uses.", observe="Contamination hazards, poor drainage, or flooding.", ask_for_help_if="The field is near a suspected chemical or waste hazard."),
            PlanAction(task="Arrange soil testing before applying nutrients.", observe="Soil test availability, sample date, and previous crop problems.", ask_for_help_if="No soil test is available and plants previously showed poor growth."),
            PlanAction(task="Prepare bunds, canals, and field leveling.", observe="Uneven water depth and blocked water flow.", ask_for_help_if="Water cannot be drained or retained properly."),
        ],
        bundle,
    )


def _planting_section(request: FarmingPlanRequest, bundle: EvidenceBundle) -> PlanSection:
    guidance = [
        "Use clean and suitable seed material and prepare the seedbed or field before crop establishment.",
        "Aim for healthy, uniform plant growth by leveling the field and avoiding high and low soil spots.",
    ]
    if request.water_source == "rainfed":
        guidance.append("For rainfed fields, align planting work with actual field moisture and local weather conditions.")
    else:
        guidance.append("Confirm actual field moisture, drainage, and water control before planting work.")
    if request.planning_mode == "planning_to_plant":
        guidance.append("Do not plant only by calendar date; confirm the field has workable moisture and drainage.")
    else:
        guidance.append("Because the crop is already planted, focus on checking stand uniformity, water condition, weeds, and early pest signs.")
    return _section(
        "planting_establishment",
        "Planting and Crop Establishment",
        guidance,
        [
            PlanAction(task="Check seed or seedling condition.", observe="Weak, uneven, or contaminated planting material.", ask_for_help_if="Seed quality is uncertain."),
            PlanAction(task="Confirm field leveling and water control.", observe="Mounds, low spots, standing water, or dry patches.", ask_for_help_if="The field cannot maintain an even water level."),
        ],
        bundle,
    )


def _soil_fertility_section(request: FarmingPlanRequest, bundle: EvidenceBundle) -> PlanSection:
    amendment = "organic soil amendments" if request.farming_type == "organic_traditional" else "fertilizer or registered organic soil amendment"
    guidance = [
        "Base nutrient decisions on soil or plant-based analysis rather than guesswork.",
        f"Use the recommended combination and timing of {amendment} only after analysis or local technician guidance.",
        f"Store nutrient materials in a clean, dry, slightly elevated area and away from pesticide storage and {_stored_crop_label(request)} drying or storage areas.",
        "Keep records of source, preparation, date, amount, application method, and person responsible.",
    ]
    if request.farming_type == "organic_traditional":
        guidance.append(f"For organic/traditional {_crop_label(request)}, use permitted and properly decomposed organic materials or registered organic soil amendments.")
    else:
        guidance.append(f"For conventional {_crop_label(request)}, use only registered chemical fertilizers or registered organic soil amendments as applicable.")
    return _section(
        "soil_fertility",
        "Soil and Fertility Plan",
        guidance,
        [
            PlanAction(task="Request or schedule soil testing.", observe="Soil test date and lab result.", ask_for_help_if="You need nutrient advice without a soil test."),
            PlanAction(task="Store nutrient materials safely.", observe=f"Moisture, leaks, mixed storage, or proximity to {_stored_crop_label(request)}.", ask_for_help_if=f"Materials are wet, unlabeled, or stored near drying {_crop_label(request)}."),
        ],
        bundle,
    )


def _water_section(request: FarmingPlanRequest, bundle: EvidenceBundle, context_bundle: EvidenceBundle) -> PlanSection:
    guidance = [
        "Plan water management by field condition, water source, crop stage, and local rainfall pattern.",
        "Maintain canals, bunds, and drainage so the field can hold or release water when needed.",
        "Monitor the field after heavy rain and during dry periods; water stress and flooding both require quick local action.",
    ]
    if request.water_source == "rainfed":
        guidance.append("Because the field is rainfed, treat local rainfall timing as a key planting and water-risk factor.")
    if request.water_source in {"rainfed", "unknown"}:
        guidance.append("Before final land preparation, ask MAO or nearby farmers whether expected rainfall is enough for the planned planting week.")
    if request.soil_condition == "dry" or "water_shortage" in request.concerns:
        guidance.append("For dry conditions, avoid irreversible field operations until water availability is realistic.")
    if request.soil_condition == "flooded" or "heavy_rain_flooding" in request.concerns:
        guidance.append("For flooding risk, prioritize drainage checks and ask for local help if seedlings or standing crop are submerged.")
    citations = _citations_from([*bundle.advisory_chunks[:2], *context_bundle.context_chunks[:1]])
    return PlanSection(
        key="water_management",
        title="Water Management Plan",
        guidance=guidance,
        actions=[
            PlanAction(task="Inspect water entry and drainage points.", observe="Blocked canals, broken bunds, dry cracks, or stagnant floodwater.", ask_for_help_if="The field cannot drain after heavy rain or cannot receive irrigation."),
            PlanAction(task="Check field condition weekly.", observe="Dry, moist, or flooded areas.", ask_for_help_if="The field condition changes quickly or crop stress appears."),
        ],
        citations=citations,
        fallback_reason=None if citations else bundle.fallback_reason or context_bundle.fallback_reason or "No water management evidence found.",
    )


def _pest_weed_section(request: FarmingPlanRequest, bundle: EvidenceBundle) -> PlanSection:
    guidance = [
        "Use Integrated Pest Management first: good crop establishment, field sanitation, regular monitoring, and timely non-chemical interventions.",
        "Monitor weeds, insects, disease symptoms, and unusual crop damage throughout the season.",
        "Use pesticide only when justified and only according to competent-authority registration, label directions, PPE, and pre-harvest interval.",
        "Keep purchase, application, storage, and disposal records for all pesticides or agricultural chemicals.",
    ]
    if request.farming_type == "organic_traditional":
        guidance.append(f"For organic/traditional {_crop_label(request)}, do not use chemical pesticides for stored organic {_crop_label(request)}; ask MAO before any pest control measure that could affect organic status.")
    else:
        guidance.append(f"For conventional {_crop_label(request)}, do not choose pesticide products from this app; ask a certified applicator or MAO before any pesticide selection.")
    return _section(
        "pest_weed",
        "Pest, Disease, and Weed Management",
        guidance,
        [
            PlanAction(task="Scout the field every week.", observe="Insects, leaf damage, disease spots, weeds, or poor crop stand.", ask_for_help_if="Damage spreads or the pest is unknown."),
            PlanAction(task="Follow the safe pesticide workflow before any pesticide use.", observe="Pest identity, damage spread, label, registration, PPE, storage, and pre-harvest interval.", ask_for_help_if="The pest is unknown, damage is spreading, the label is missing, or correct use is uncertain."),
        ],
        bundle,
    )


def _stage_checklist_section(request: FarmingPlanRequest, bundles: dict[str, EvidenceBundle]) -> PlanSection:
    guidance = [
        "Before planting: inspect field hazards, test soil, repair water control, and prepare clean seed or seedbed.",
        "Planting to early growth: check uniform establishment, water condition, weeds, yellowing, holes or leaf damage, snails, insects, disease spots, and weak seedlings.",
        "Active growth: monitor nutrients, water, pest pressure, weed competition, lodging, and spreading damage regularly.",
        "Before harvest: check maturity, avoid contamination, and prepare clean drying and storage areas.",
    ]
    if request.planning_mode == "already_planted":
        guidance.insert(0, f"Start from the current stage: {request.current_stage}. Do not repeat earlier operations unless a technician recommends it.")
    citations = _citations_from(_first_advisory_chunks(bundles, per_section=1))
    return PlanSection(
        key="stage_checklist",
        title="Stage-by-Stage Checklist",
        guidance=guidance,
        actions=[
            PlanAction(task="Review the checklist once a week.", observe="Missed field tasks or new risks.", ask_for_help_if="A problem is worsening or outside the checklist."),
            PlanAction(task="Update records after each field activity.", observe="Date, material used, field condition, and crop response.", ask_for_help_if="You are unsure what was applied or when."),
        ],
        citations=citations,
        fallback_reason=None if citations else "No source-backed checklist evidence found.",
    )


def _harvest_section(request: FarmingPlanRequest, bundle: EvidenceBundle) -> PlanSection:
    guidance = [
        f"Before harvest and post-harvest handling, keep {_stored_crop_label(request)} away from soil, dirty tools, animals, chemicals, and other contamination sources.",
        "Use clean hauling, drying, and storage materials.",
        f"Store {_crop_label(request)} separately from fertilizer, pesticides, treated pallets, or other possible contamination sources.",
        "Clean storage facilities before use, especially if pesticide traces are suspected.",
    ]
    return _section(
        "harvest_post_harvest",
        "Harvest and Post-Harvest",
        guidance,
        [
            PlanAction(task="Prepare clean drying and storage areas.", observe="Dirt, leaks, pests, chemical containers, or treated pallets.", ask_for_help_if="The storage area may have pesticide residue or contamination."),
            PlanAction(task=f"Handle harvested {_crop_label(request)} with clean materials.", observe="Direct soil contact or mixed hauling with contaminants.", ask_for_help_if="Clean drying or hauling materials are not available."),
        ],
        bundle,
    )


def _records_section(request: FarmingPlanRequest, bundles: dict[str, EvidenceBundle]) -> PlanSection:
    citations = _citations_from(_first_advisory_chunks({"soil_fertility": bundles["soil_fertility"], "pest_weed": bundles["pest_weed"]}, 2))
    return PlanSection(
        key="records",
        title="Records to Keep",
        guidance=[
            "Record planting date, seed source, soil test result, nutrient material used, pesticide or agrochemical use, pest observations, weather problems, and harvest result.",
            "For fertilizer or organic soil amendments, record source, preparation details, application date, amount, method, and responsible person.",
            "For pesticides or agricultural chemicals, record purchase, application, storage, disposal, label instructions followed, and pre-harvest interval.",
        ],
        actions=[
            PlanAction(task="Write records on the same day as field work.", observe="Missing dates, materials, or observations.", ask_for_help_if="You cannot identify what input was used."),
        ],
        citations=citations,
        fallback_reason=None if citations else "No source-backed recordkeeping evidence found.",
    )


def _warning_section(request: FarmingPlanRequest, bundles: dict[str, EvidenceBundle]) -> PlanSection:
    warnings = _warnings_for_request(request, bundles)
    citations = _citations_from(_first_advisory_chunks({"pest_weed": bundles["pest_weed"], "before_planting": bundles["before_planting"]}, 1))
    return PlanSection(
        key="warnings_escalation",
        title="Warnings and Escalation",
        guidance=warnings
        or [
            "Ask the Municipal Agriculture Office if the field condition is unusual, evidence is missing, a pest is unknown, or chemical use is uncertain.",
        "This app does not diagnose disease, guarantee yield, or select pesticide products.",
        ],
        actions=[
            PlanAction(task="Escalate severe or uncertain problems.", observe="Fast-spreading pest or disease, suspected chemical contamination, flooding, drought stress, or unsafe pesticide uncertainty.", ask_for_help_if="Any warning condition is present."),
        ],
        citations=citations,
        fallback_reason=None if citations else "Escalation guidance is a safety fallback.",
    )


def _section(
    key: str,
    title: str,
    guidance: list[str],
    actions: list[PlanAction],
    bundle: EvidenceBundle,
) -> PlanSection:
    citations = _citations_from(bundle.advisory_chunks[:3])
    return PlanSection(
        key=key,
        title=title,
        guidance=guidance,
        actions=actions,
        citations=citations,
        fallback_reason=None if citations else bundle.fallback_reason or f"No reviewed crop advisory evidence found for {title}.",
    )


def _unsupported_crop_plan(request: FarmingPlanRequest) -> FarmingPlan:
    section = PlanSection(
        key="warnings_escalation",
        title="Warnings and Escalation",
        guidance=[
            f"{request.crop} is not supported in Phase 1.",
            "Consult the Municipal Agriculture Office for a crop-specific plan.",
        ],
        fallback_reason="Unsupported crop for Phase 1.",
    )
    return localize_plan(request, FarmingPlan(
        crop=request.crop,
        location=request.location_label,
        language=request.language,
        farming_type=request.farming_type,
        planning_basis=_planning_basis(request),
        status="unsupported_crop",
        generation_method="template",
        warnings=["Unsupported crop for Phase 1. Consult the Municipal Agriculture Office."],
        sections=[section],
        source_count=0,
    ))


def _plan_artifacts_with_llm(
    request: FarmingPlanRequest,
    draft: FarmingPlan,
    bundles: dict[str, EvidenceBundle],
    context_bundle: EvidenceBundle,
    llm_client: PlanLlmClient,
) -> FarmingPlan:
    from anibot.llm.prompt import build_evidence_planner_prompt

    try:
        prompt = build_evidence_planner_prompt(
            request,
            _evidence_guidelines_from(bundles, context_bundle),
            draft.timeline,
        )
        payload = llm_client.generate_json(prompt)
        planned_artifacts = _parse_llm_planned_artifacts(draft, payload)
        return FarmingPlan(
            crop=draft.crop,
            location=draft.location,
            language=draft.language,
            farming_type=draft.farming_type,
            planning_basis=draft.planning_basis,
            status=draft.status,
            generation_method=getattr(llm_client, "generation_method", "ollama"),
            llm_model=llm_client.model,
            llm_error=None,
            warnings=draft.warnings,
            sections=draft.sections,
            timeline=planned_artifacts["timeline"],
            glossary=draft.glossary,
            decision_rows=draft.decision_rows,
            material_checklist=draft.material_checklist,
            record_templates=draft.record_templates,
            mao_questions=draft.mao_questions,
            source_count=draft.source_count,
        )
    except Exception as exc:
        return draft.model_copy(
            update={
                "generation_method": "fallback",
                "llm_model": llm_client.model,
                "llm_error": _safe_llm_error(exc),
            }
        )


def _evidence_guidelines_from(
    bundles: dict[str, EvidenceBundle],
    context_bundle: EvidenceBundle,
) -> list[dict[str, str | int]]:
    guidelines: list[dict[str, str | int]] = []
    seen: set[str] = set()
    for key, bundle in bundles.items():
        for chunk in bundle.advisory_chunks[:2]:
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            guidelines.append(
                {
                    "topic": key,
                    "source": chunk.citation,
                    "page": chunk.page_number,
                    "guideline": _compact_evidence_text(chunk.text),
                }
            )
    for chunk in context_bundle.context_chunks[:1]:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        guidelines.append(
            {
                "topic": "local_context",
                "source": chunk.citation,
                "page": chunk.page_number,
                "guideline": _compact_evidence_text(chunk.text),
            }
        )
    return guidelines[:7]


def _compact_evidence_text(text: str, limit: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


def _parse_llm_planned_artifacts(draft: FarmingPlan, payload: dict) -> dict[str, list]:
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    artifacts = {
        "timeline": _parse_llm_timeline(payload.get("timeline"), draft.timeline),
    }
    _reject_unsafe_artifacts(artifacts)
    return artifacts


def _parse_llm_timeline(value: object, calendar_rows: list[TimelineItem]) -> list[TimelineItem]:
    if not isinstance(value, list) or len(value) != len(calendar_rows):
        raise ValueError("LLM response must contain one timeline item for each calendar row")
    timeline: list[TimelineItem] = []
    for item, original in zip(value, calendar_rows):
        if not isinstance(item, dict):
            raise ValueError("LLM timeline items must be objects")
        if item.get("period") != original.period or item.get("approximate_date") != original.approximate_date:
            raise ValueError("LLM timeline must keep period and approximate_date values unchanged")
        parsed = TimelineItem.model_validate(item)
        if not parsed.task.strip() or not parsed.observe.strip() or not parsed.ask_for_help_if.strip():
            raise ValueError("LLM timeline items must include task, observe, and ask_for_help_if")
        if not 2 <= len(parsed.how_to_steps) <= 6:
            raise ValueError("LLM timeline items must include 2 to 6 how-to steps")
        timeline.append(_merge_timeline_item(original, parsed))
    return timeline


def _merge_timeline_item(original: TimelineItem, candidate: TimelineItem) -> TimelineItem:
    how_to_steps = candidate.how_to_steps
    if _steps_are_weaker(original.how_to_steps, candidate.how_to_steps):
        how_to_steps = original.how_to_steps
    return TimelineItem(
        period=original.period,
        approximate_date=original.approximate_date,
        task=_prefer_specific_text(original.task, candidate.task),
        how_to_steps=how_to_steps,
        observe=_prefer_specific_text(original.observe, candidate.observe),
        ask_for_help_if=_prefer_specific_text(original.ask_for_help_if, candidate.ask_for_help_if),
    )


def _prefer_specific_text(original: str, candidate: str) -> str:
    candidate = candidate.strip()
    if _is_vague_instruction(candidate) or _specificity_score(candidate) < max(4, _specificity_score(original) - 2):
        return original
    return candidate


def _steps_are_weaker(original: list[str], candidate: list[str]) -> bool:
    if any(_is_vague_instruction(step) for step in candidate):
        return True
    original_score = sum(_specificity_score(step) for step in original)
    candidate_score = sum(_specificity_score(step) for step in candidate)
    return candidate_score < max(8, original_score - 3)


def _specificity_score(text: str) -> int:
    lowered = text.lower()
    terms = [
        "soil",
        "sample",
        "zigzag",
        "water",
        "drain",
        "bund",
        "canal",
        "seed",
        "seedling",
        "source",
        "field",
        "record",
        "photo",
        "pest",
        "weed",
        "yellow",
        "disease",
        "dry",
        "flood",
        "level",
        "moisture",
        "mao",
        "technician",
        "pesticide",
        "storage",
        "drying",
    ]
    score = sum(1 for term in terms if term in lowered)
    score += min(len([token for token in re.split(r"\W+", lowered) if token]), 18) // 5
    return score


def _is_vague_instruction(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip().lower()).rstrip(".")
    vague_phrases = {
        "prepare seeds for planting",
        "prepare seed for planting",
        "check field condition",
        "check the field condition",
        "monitor crop growth",
        "monitor crop growth regularly",
        "inspect for pests and weeds",
        "ask mao if unsure",
        "ask for help if unsure",
        "execute the planting plan",
        "finalize planting plan",
    }
    return normalized in vague_phrases


def _parse_llm_decision_rows(value: object) -> list[DecisionRow]:
    if not isinstance(value, list):
        raise ValueError("LLM response must contain decision_rows list")
    if not 4 <= len(value) <= 8:
        raise ValueError("LLM decision_rows must contain 4 to 8 items")
    return [DecisionRow.model_validate(_normalize_decision_row(item)) for item in value]


def _normalize_decision_row(item: object) -> dict:
    if not isinstance(item, dict):
        raise ValueError("LLM decision_rows items must be objects")
    normalized = dict(item)
    _copy_first_present(
        normalized,
        "first_check",
        ["check_first", "initial_check", "field_check", "what_to_check_first"],
    )
    _copy_first_present(
        normalized,
        "what_to_do_next",
        ["action", "next_action", "next_step", "recommendation", "recommended_action", "what_to_do"],
    )
    _copy_first_present(
        normalized,
        "contact_mao_if",
        ["ask_mao_if", "ask_for_help_if", "contact_technician_if", "mao_if", "seek_help_if"],
    )
    if not str(normalized.get("what_to_do_next", "")).strip():
        normalized["what_to_do_next"] = "Record the issue and ask MAO for the safe next step before acting."
    return normalized


def _copy_first_present(target: dict, canonical_key: str, aliases: list[str]) -> None:
    if str(target.get(canonical_key, "")).strip():
        return
    for alias in aliases:
        value = target.get(alias)
        if str(value or "").strip():
            target[canonical_key] = value
            return


def _parse_model_list(value: object, model: type, key: str, min_items: int, max_items: int) -> list:
    if not isinstance(value, list):
        raise ValueError(f"LLM response must contain {key} list")
    if not min_items <= len(value) <= max_items:
        raise ValueError(f"LLM {key} must contain {min_items} to {max_items} items")
    parsed = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"LLM {key} items must be objects")
        parsed.append(model.model_validate(item))
    return parsed


def _validate_record_templates(templates: list[RecordTemplate]) -> None:
    for template in templates:
        if len(template.columns) != len(template.sample_row):
            raise ValueError(f"Record template '{template.title}' sample_row must match columns")


def _reject_unsafe_artifacts(artifacts: dict[str, list]) -> None:
    rendered = " ".join(str(item.model_dump()) for values in artifacts.values() for item in values).lower()
    blocked_terms = [
        "kg/ha",
        "bags per hectare",
        "glyphosate",
        "insecticide brand",
        "guarantee yield",
        "guaranteed yield",
    ]
    found = [term for term in blocked_terms if term in rendered]
    if found:
        raise ValueError(f"LLM artifacts contain unsafe terms: {found}")
    rate_patterns = [
        r"\b\d+(\.\d+)?\s*(kg|kilogram|kilograms|bag|bags|sack|sacks)\s*(/|per)\s*(ha|hectare|hectares)\b",
        r"\b\d+(\.\d+)?\s*(ml|liter|liters|l|g|gram|grams)\s*(/|per)\s*(l|liter|liters|ha|hectare|hectares)\b",
    ]
    for pattern in rate_patterns:
        if re.search(pattern, rendered):
            raise ValueError("LLM artifacts contain unsupported input rate or dosage")


def _safe_llm_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}".strip()
    blocked = ("capital", "budget", "cost", "price")
    for term in blocked:
        message = message.replace(term, "[blocked term]")
        message = message.replace(term.title(), "[blocked term]")
        message = message.replace(term.upper(), "[blocked term]")
    if len(message) > 500:
        message = f"{message[:497]}..."
    return message


def _citations_from(chunks: list[StoredChunk]) -> list[Citation]:
    seen: set[str] = set()
    citations: list[Citation] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        citations.append(
            Citation(
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                page_number=chunk.page_number,
                heading=chunk.heading,
            )
        )
    return citations


def _first_advisory_chunks(bundles: dict[str, EvidenceBundle], per_section: int) -> list[StoredChunk]:
    chunks: list[StoredChunk] = []
    for bundle in bundles.values():
        chunks.extend(bundle.advisory_chunks[:per_section])
    return chunks


def _planning_basis(request: FarmingPlanRequest) -> str:
    if request.planning_mode == "planning_to_plant":
        return f"planning to plant; target date: {request.target_planting_date}"
    return f"already planted; current stage: {request.current_stage}"


def _crop_label(request: FarmingPlanRequest) -> str:
    return _crop_label_from_value(request.crop)


def _crop_label_from_value(crop: str) -> str:
    return {"rice": "rice", "corn": "corn"}.get(crop, crop)


def _stored_crop_label(request: FarmingPlanRequest) -> str:
    if request.crop == "corn":
        return "harvested corn, corn ears, or corn grain"
    return "paddy rice"


def _parse_target_date(value: str) -> date | None:
    text = value.strip()
    if not text or text == "not specified":
        return None
    for pattern in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _date_range(start: date, end: date) -> str:
    if start.month == end.month and start.year == end.year:
        return f"{start.strftime('%B')} {start.day}-{end.day}, {start.year}"
    return f"{start.strftime('%B')} {start.day}-{end.strftime('%B')} {end.day}, {end.year}"


def _concern_summary(concerns: list[str]) -> str:
    return ", ".join(_concern_label(concern) for concern in concerns)


def _concern_label(concern: str) -> str:
    return {
        "pests": "pests",
        "weeds": "weeds",
        "poor_growth": "poor growth",
        "fertilizer_nutrient": "fertilizer or nutrient concern",
        "water_shortage": "water shortage",
        "heavy_rain_flooding": "heavy rain or flooding",
        "harvest_post_harvest": "harvest or post-harvest concern",
        "none": "no urgent concern selected",
    }.get(concern, concern.replace("_", " "))


def _concern_guidance(request: FarmingPlanRequest, concern: str) -> list[str]:
    crop = _crop_label(request)
    if concern == "pests":
        return [
            "For pests: identify the pest first, check whether damage is spreading, and take clear photos of affected leaves, stems, or plants.",
            "Do not spray immediately or choose a pesticide from this app; ask MAO or a qualified applicator if pest identity or pesticide use is uncertain.",
        ]
    if concern == "weeds":
        return [
            f"For weeds: check whether weeds are competing with young {crop}, especially in field edges, wet spots, and thin crop stand areas.",
            "Act early using locally advised weed management and keep records of the method used.",
        ]
    if concern == "poor_growth":
        return [
            "For poor growth: compare weak and healthy areas, then check water condition, stand uniformity, yellowing, pest signs, and disease spots.",
            "Do not guess the cause or apply nutrients by trial; bring notes or photos to MAO if weak growth continues.",
        ]
    if concern == "fertilizer_nutrient":
        return [
            "For fertilizer or nutrient concern: use soil or plant-based analysis before deciding the material, timing, or amount.",
            "Record previous fertilizer or amendment use, crop response, and any yellowing or uneven growth before asking for local guidance.",
        ]
    if concern == "water_shortage":
        return [
            "For water shortage: check the water source, canals, bunds, nearby fields, and whether the soil is too dry for the next planned operation.",
            "Delay irreversible field work if water availability is not realistic.",
        ]
    if concern == "heavy_rain_flooding":
        return [
            "For heavy rain or flooding: inspect drainage paths, canals, bund breaks, and whether seedlings or standing crop are submerged.",
            "Ask for local help quickly if water cannot be drained or plants remain underwater.",
        ]
    if concern == "harvest_post_harvest":
        return [
            f"For harvest or post-harvest concern: keep {_stored_crop_label(request)} away from soil, dirty tools, animals, chemical containers, and treated pallets.",
            "Prepare clean drying, hauling, and storage materials before harvest work starts.",
        ]
    return [
        "No urgent concern was selected. Use the weekly checklist to watch water, weeds, pests, yellowing, disease spots, and uneven crop growth.",
    ]


def _concern_action(request: FarmingPlanRequest, concern: str) -> PlanAction:
    crop = _crop_label(request)
    if concern == "pests":
        return PlanAction(task="Respond to pest concern today.", observe="Pest identity, number of affected plants, photos, and whether damage is spreading.", ask_for_help_if="The pest is unknown, damage spreads, or pesticide use is being considered.")
    if concern == "weeds":
        return PlanAction(task="Map weed pressure in the field.", observe=f"Weed type, weed density, young {crop} suppression, and wet or thin stand areas.", ask_for_help_if=f"You are unsure whether the plant is a weed or {crop} growth is being suppressed.")
    if concern == "poor_growth":
        return PlanAction(task="Compare weak and healthy crop areas.", observe="Water condition, yellowing, pest signs, disease spots, stand gaps, and recent field activity.", ask_for_help_if="Weak growth spreads, yellowing worsens, or no soil or plant analysis is available.")
    if concern == "fertilizer_nutrient":
        return PlanAction(task="Prepare for soil or plant-based nutrient guidance.", observe="Soil test status, previous nutrient use, yellowing, uneven growth, and crop response.", ask_for_help_if="You need nutrient advice without a soil test or plant-based analysis.")
    if concern == "water_shortage":
        return PlanAction(task="Check whether water is enough before the next field operation.", observe="Water source reliability, canal flow, dry cracks, nearby field condition, and soil moisture.", ask_for_help_if="No reliable water source is available or dry conditions continue.")
    if concern == "heavy_rain_flooding":
        return PlanAction(task="Check drainage and submerged crop areas.", observe="Blocked drainage, broken bunds, water depth, submerged seedlings, and stagnant water.", ask_for_help_if="Water cannot be drained or plants remain submerged.")
    if concern == "harvest_post_harvest":
        return PlanAction(task="Inspect harvest, drying, and storage areas.", observe="Soil contact, pests, leaks, dirty sacks, chemical containers, or treated pallets.", ask_for_help_if="Clean drying or storage space is not available or contamination is suspected.")
    return PlanAction(task="Use the weekly field check.", observe="Water, weeds, pests, yellowing, disease spots, uneven growth, and field records.", ask_for_help_if="A problem appears, worsens, or is uncertain.")


def _concern_citation_chunks(
    concerns: list[str],
    bundles: dict[str, EvidenceBundle],
    context_bundle: EvidenceBundle,
) -> list[StoredChunk]:
    mapping = {
        "pests": ["pest_weed"],
        "weeds": ["pest_weed"],
        "poor_growth": ["soil_fertility", "water_management", "pest_weed"],
        "fertilizer_nutrient": ["soil_fertility"],
        "water_shortage": ["water_management"],
        "heavy_rain_flooding": ["water_management"],
        "harvest_post_harvest": ["harvest_post_harvest"],
        "none": ["stage_checklist"],
    }
    chunks: list[StoredChunk] = []
    for concern in concerns:
        for key in mapping.get(concern, []):
            if key == "stage_checklist":
                chunks.extend(_first_advisory_chunks(bundles, per_section=1))
            else:
                chunks.extend(bundles[key].advisory_chunks[:2])
    if any(concern in {"water_shortage", "heavy_rain_flooding"} for concern in concerns):
        chunks.extend(context_bundle.context_chunks[:1])
    return chunks


def _safe_user_text(value: str) -> str:
    text = " ".join(value.split())
    for term in ("capital", "budget", "cost", "price"):
        text = re.sub(term, "[removed money term]", text, flags=re.IGNORECASE)
    return text


def _timeline_for_request(request: FarmingPlanRequest) -> list[TimelineItem]:
    if request.planning_mode == "already_planted":
        return [
            TimelineItem(
                period="Current week",
                approximate_date=f"Current stage: {request.current_stage}",
                task="Start with field checking and records.",
                how_to_steps=[
                    "Walk the field edge and center areas.",
                    "Note water condition, weeds, yellowing, leaf damage, disease spots, and uneven growth.",
                    "Write the current stage and problems in the record template.",
                ],
                observe="Water level, weeds, pest signs, yellowing, disease spots, lodging, and spreading damage.",
                ask_for_help_if="Damage is spreading, water cannot be managed, or the crop stage is uncertain.",
            )
        ]

    target = _parse_target_date(request.target_planting_date)
    if target:
        rows = [
            ("4-6 weeks before planting", _date_range(target - timedelta(weeks=6), target - timedelta(weeks=4)), "Visit MAO and confirm the local planting plan."),
            ("3-4 weeks before planting", _date_range(target - timedelta(weeks=4), target - timedelta(weeks=3)), "Collect soil samples and check water control."),
            ("1-2 weeks before planting", _date_range(target - timedelta(weeks=2), target - timedelta(weeks=1)), "Prepare seed, seedbed, tools, field access, and labor."),
            ("Planting week", target.strftime("%B %d, %Y").replace(" 0", " "), "Plant only if the field is workable."),
            ("Weekly after planting", f"{target.strftime('%B')} to {(target + timedelta(weeks=14)).strftime('%B %Y')}", "Scout the field every week."),
            ("Before harvest", f"{(target + timedelta(weeks=14)).strftime('%B')} to {(target + timedelta(weeks=18)).strftime('%B %Y')}", "Prepare clean drying and storage areas."),
        ]
    else:
        rows = [
            ("4-6 weeks before planting", "Relative to target planting date", "Visit MAO and confirm the local planting plan."),
            ("3-4 weeks before planting", "Relative to target planting date", "Collect soil samples and check water control."),
            ("1-2 weeks before planting", "Relative to target planting date", "Prepare seed, seedbed, tools, field access, and labor."),
            ("Planting week", "Target week", "Plant only if the field is workable."),
            ("Weekly after planting", "From planting until harvest", "Scout the field every week."),
            ("Before harvest", "Several weeks before expected harvest", "Prepare clean drying and storage areas."),
        ]

    return [
        TimelineItem(
            period=period,
            approximate_date=approximate_date,
            task=task,
            how_to_steps=_timeline_steps(period, request),
            observe=_timeline_observe(period),
            ask_for_help_if=_timeline_help(period),
        )
        for period, approximate_date, task in rows
    ]


def _timeline_steps(period: str, request: FarmingPlanRequest) -> list[str]:
    if period.startswith("4-6"):
        steps = [
            "Bring your location, target planting date, water source, and field notes to MAO.",
            "Ask whether the timing matches the local cropping calendar and water conditions.",
            f"Confirm the recommended {_crop_label(request)} variety and where soil testing can be done.",
        ]
        if _is_surigao_area(request):
            steps.append("Ask specifically about Marga or Surigao City rainfall, irrigation, drainage, and flood-prone areas.")
        return steps
    if period.startswith("3-4"):
        return [
            "Walk the field in a zigzag pattern and collect small soil samples from several normal spots.",
            "Avoid unusual spots such as compost piles, burnt areas, water channels, or field edges.",
            "Mix the soil in a clean container and bring the sample to MAO or the recommended lab.",
            "Check bunds, canals, and drainage paths while waiting for guidance.",
        ]
    if period.startswith("1-2"):
        return [
            "Prepare clean seed or seedlings from a reliable source.",
            "Prepare the seedbed or field and check that tools and labor are available.",
            "Repair field access, bunds, canals, and drainage before the planting day.",
        ]
    if period == "Planting week":
        if request.crop == "corn":
            return [
                "Use the MAO or technician-recommended corn planting distance and seeding rate; mark rows or hills with string, stakes, or a row marker before opening furrows or holes.",
                "Place clean seed in the marked furrows or holes, cover with fine soil, and keep the row line visible for later weeding and hilling-up work.",
                "Plant only when the soil has workable moisture; if the soil is dry, irrigate or wait for rain, and if water is standing, drain first.",
                "Record the planting date, seed source, actual spacing or seeding rate used, soil moisture, and any dry or flooded spots.",
            ]
        return [
            "Use the MAO or technician-recommended rice establishment method, spacing, and seed or seedling rate for this field before sowing or transplanting.",
            "Plant or transplant in a level field with workable moisture, keeping rows or planting spots even enough for later water, weed, and pest checks.",
            "If the field is too dry, irrigate or wait for rain; if it is deeply flooded or cannot drain, delay planting until water is manageable.",
            "Record the planting date, seed or seedling source, establishment method, field moisture, and any uneven or flooded spots.",
        ]
    if period == "Weekly after planting":
        return [
            "Walk the field once a week, including edges and inner areas.",
            "Check water level, weeds, yellowing, holes or leaf damage, snails, insects, disease spots, weak growth, and lodging.",
            "Take phone photos of unusual symptoms and compare whether damage is spreading.",
        ]
    return [
        "Clean the drying area, sacks, hauling tools, and storage space.",
        f"Keep {_stored_crop_label(request)} away from soil, animals, fertilizer, pesticides, dirty tools, and treated pallets.",
        "Check any pesticide record for the pre-harvest interval before harvest work.",
    ]


def _timeline_observe(period: str) -> str:
    if period.startswith("4-6"):
        return "Local cropping calendar, water source reliability, variety advice, and soil test options."
    if period.startswith("3-4"):
        return "Soil sample readiness, blocked canals, broken bunds, dry cracks, or floodwater."
    if period.startswith("1-2"):
        return "Seed condition, seedbed readiness, tools, field leveling, and water control."
    if period == "Planting week":
        return "Actual spacing or seeding rate used, soil moisture, even rows or planting spots, drainage, and seed or seedling condition."
    if period == "Weekly after planting":
        return "Water level, weeds, yellowing, leaf damage, snails, insects, disease spots, uneven growth, lodging, and spreading damage."
    return "Clean drying area, clean storage, pest traces, chemical containers, dirty sacks, or treated pallets."


def _timeline_help(period: str) -> str:
    if period.startswith("4-6"):
        return "The target date does not match local water or cropping conditions."
    if period.startswith("3-4"):
        return "You cannot get soil testing guidance or the field cannot hold or drain water."
    if period.startswith("1-2"):
        return "Seed quality is uncertain or field preparation cannot be completed."
    if period == "Planting week":
        return "Recommended spacing or seeding rate is unknown, seed quality is uncertain, or the field is too dry, flooded, uneven, or not draining."
    if period == "Weekly after planting":
        return "The pest is unknown, damage spreads, yellowing worsens, or water stress appears."
    return "The drying or storage area may be contaminated or pesticide waiting time is uncertain."


def _glossary_items() -> list[GlossaryItem]:
    return [
        GlossaryItem(term="Bund", explanation="A raised soil wall around the field that helps hold or guide water."),
        GlossaryItem(term="Seedbed", explanation="A small prepared area where seedlings are grown before transplanting."),
        GlossaryItem(term="IPM", explanation="Managing pests by checking the field and preventing problems first, not spraying immediately."),
        GlossaryItem(term="Pre-harvest interval", explanation="The required waiting time after pesticide use before harvest."),
        GlossaryItem(term="Soil amendment", explanation="Material added to improve soil condition, such as compost or lime, only when suitable and advised."),
    ]


def _decision_rows_for_request(request: FarmingPlanRequest) -> list[DecisionRow]:
    rows = [
        DecisionRow(situation="Field is too dry before planting", first_check="Check water source and nearby fields.", what_to_do_next="Do not proceed with final land preparation until water availability is realistic.", contact_mao_if="Water source is uncertain or dry conditions continue."),
        DecisionRow(situation="Field is flooded and cannot drain", first_check="Check drainage paths, canals, and bund breaks.", what_to_do_next="Clear drainage if safe and delay seedbed or planting work.", contact_mao_if="Water cannot be drained or seedlings are submerged."),
        DecisionRow(situation="Leaves are yellowing", first_check="Check water condition and whether yellowing is spreading.", what_to_do_next="Record the symptom and ask for soil or plant-based guidance before applying nutrients.", contact_mao_if="Yellowing spreads, growth is poor, or no soil test is available."),
        DecisionRow(situation="Insects, snails, or leaf damage are present", first_check="Identify the pest and check whether damage is spreading.", what_to_do_next="Do not spray immediately; take photos and monitor the damage level.", contact_mao_if="The pest is unknown or damage is spreading."),
        DecisionRow(situation="Weeds are increasing", first_check=f"Check whether weeds are competing with young {_crop_label(request)} plants.", what_to_do_next="Act early using locally advised weed management and keep records.", contact_mao_if=f"You are unsure whether the plant is a weed or {_crop_label(request)} growth is being suppressed."),
        DecisionRow(situation="Harvest or storage area is dirty", first_check="Look for soil contact, pests, animals, chemical containers, dirty tools, or treated pallets.", what_to_do_next="Clean or choose another drying and storage area before harvest.", contact_mao_if="Pesticide residue or contamination is suspected."),
    ]
    if request.water_source in {"rainfed", "unknown"}:
        rows.insert(
            0,
            DecisionRow(situation="Rainfall is uncertain before planting", first_check="Ask nearby farmers and MAO about local rainfall timing.", what_to_do_next="Delay irreversible field work until planting moisture is realistic.", contact_mao_if="No reliable water source is available for the planned week."),
        )
    return rows


def _material_checklist(request: FarmingPlanRequest) -> list[MaterialChecklistGroup]:
    return [
        MaterialChecklistGroup(category="Seeds", items=[f"Recommended {_crop_label(request)} variety", "Clean seed source", "Seed or seedling container"]),
        MaterialChecklistGroup(category="Field tools", items=["Plow or hand tractor access", "Leveling tools", "Boots", "Field markers"]),
        MaterialChecklistGroup(category="Water control", items=["Canal clearing tools", "Bund repair materials", "Drainage path access"]),
        MaterialChecklistGroup(category="Records", items=["Notebook", "Pen", "Phone camera for field photos"]),
        MaterialChecklistGroup(category="Safety", items=["Gloves", "Mask or PPE when handling chemicals", "Labels and storage area for inputs"]),
        MaterialChecklistGroup(category="Post-harvest", items=["Clean sacks", "Clean drying mat", "Clean storage area", "Clean hauling materials"]),
    ]


def _record_templates() -> list[RecordTemplate]:
    return [
        RecordTemplate(
            title="Field Activity Record",
            columns=["Date", "Activity", "Field condition", "Input used", "Amount", "Observation", "Person responsible"],
            sample_row=["June 15", "Planting", "Moist, level field", "Seeds", "Write actual amount", "Good or uneven", "Name"],
        ),
        RecordTemplate(
            title="Pesticide or Agricultural Chemical Record",
            columns=["Date", "Pest/problem", "Product used", "Label followed?", "PPE used?", "Pre-harvest interval", "Who advised?"],
            sample_row=["Write date", "Unknown insect", "None until advised", "Yes/No", "Yes/No", "Write label interval", "MAO or technician"],
        ),
        RecordTemplate(
            title="Weekly Field Observation Record",
            columns=["Date", "Water condition", "Weeds", "Pest signs", "Yellowing/disease spots", "Photo taken?", "Next action"],
            sample_row=["Write date", "Dry/moist/flooded", "Low/medium/high", "Describe signs", "Describe symptoms", "Yes/No", "Monitor or ask MAO"],
        ),
    ]


def _mao_questions_for_request(request: FarmingPlanRequest) -> list[MaoQuestion]:
    questions = [
        MaoQuestion(topic="Planting date and water", question=f"Does planting around {request.target_planting_date} fit the local {_crop_label(request)} calendar, rainfall, irrigation, and drainage conditions for {request.location_label}?"),
        MaoQuestion(topic="Soil testing", question="Where should I bring the mixed soil sample, and who can translate the result into a fertilizer or amendment schedule?"),
        MaoQuestion(topic="Seed or variety", question=f"Which {_crop_label(request)} variety and clean seed source are recommended for this field condition and water source?"),
    ]
    if _is_surigao_area(request):
        questions[0] = MaoQuestion(topic="Planting date and water", question=f"For Marga or nearby Surigao City fields, does planting around {request.target_planting_date} fit usual rainfall, irrigation, drainage, and flood risk?")
    if {"pests", "weeds", "poor_growth"} & set(request.concerns):
        questions.append(MaoQuestion(topic="Field problem contact", question="If I see insects, snails, weeds, leaf holes, yellowing, or disease spots, who should identify the problem before any pesticide or nutrient decision?"))
    if "harvest_post_harvest" in request.concerns:
        questions.append(MaoQuestion(topic="Post-harvest handling", question="What local drying and storage practices should I follow to avoid contamination?"))
    return questions


def _is_surigao_area(request: FarmingPlanRequest) -> bool:
    text = f"{request.barangay} {request.municipality} {request.province}".lower()
    return "surigao" in text or "marga" in text


def _warnings_for_request(request: FarmingPlanRequest, bundles: dict[str, EvidenceBundle]) -> list[str]:
    warnings: list[str] = [
        "This plan is decision support. It does not predict harvest results or replace local technician advice.",
    ]
    if "pests" in request.concerns:
        warnings.append("If pest identity is unknown or damage is spreading, consult MAO before applying pesticide.")
    if "fertilizer_nutrient" in request.concerns or "poor_growth" in request.concerns:
        warnings.append("Do not guess nutrient rates. Use soil or plant-based analysis and local technician guidance.")
    if request.soil_condition == "flooded" or "heavy_rain_flooding" in request.concerns:
        warnings.append(f"Flooding can quickly damage {_crop_label(request)}. Ask for local help if water cannot be drained or plants are submerged.")
    if request.soil_condition == "dry" or "water_shortage" in request.concerns:
        warnings.append("Dry conditions require local water planning before irreversible field operations.")
    if not all(bundle.advisory_chunks for bundle in bundles.values()):
        warnings.append("Some plan sections had thin evidence and should be confirmed with MAO.")
    return warnings
