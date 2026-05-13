from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Crop = Literal["rice", "corn"]
PlanLanguage = Literal["english", "filipino", "cebuano"]
FarmingType = Literal["conventional", "organic_traditional", "unknown"]
PlanningMode = Literal["planning_to_plant", "already_planted"]
WaterSource = Literal["irrigated", "rainfed", "unknown"]
RiceEcosystem = Literal["lowland", "upland", "unknown"]
SoilCondition = Literal["dry", "moist", "flooded", "unknown"]
Concern = Literal[
    "pests",
    "weeds",
    "poor_growth",
    "fertilizer_nutrient",
    "water_shortage",
    "heavy_rain_flooding",
    "harvest_post_harvest",
    "none",
]


class FarmingPlanRequest(BaseModel):
    province: str = Field(min_length=1, max_length=80)
    municipality: str = Field(min_length=1, max_length=80)
    barangay: str = Field(default="", max_length=80)
    field_notes: str = Field(default="", max_length=500)
    crop: str = Field(default="rice", max_length=40)
    farming_type: FarmingType = "unknown"
    planning_mode: PlanningMode = "planning_to_plant"
    target_planting_date: str = Field(default="", max_length=40)
    current_stage: str = Field(default="", max_length=80)
    water_source: WaterSource = "unknown"
    rice_ecosystem: RiceEcosystem = "unknown"
    soil_condition: SoilCondition = "unknown"
    concerns: list[Concern] = Field(default_factory=lambda: ["none"])
    observation_notes: str = Field(default="", max_length=800)
    language: PlanLanguage = "english"

    @field_validator("crop")
    @classmethod
    def normalize_crop(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("concerns")
    @classmethod
    def normalize_concerns(cls, value: list[Concern]) -> list[Concern]:
        if not value:
            return ["none"]
        if "none" in value and len(value) > 1:
            return [item for item in value if item != "none"]
        return value

    @model_validator(mode="after")
    def validate_date_or_stage(self) -> "FarmingPlanRequest":
        if self.planning_mode == "planning_to_plant" and not self.target_planting_date.strip():
            self.target_planting_date = "not specified"
        if self.planning_mode == "already_planted" and not self.current_stage.strip():
            self.current_stage = "not specified"
        return self

    @property
    def location_label(self) -> str:
        parts = [self.barangay.strip(), self.municipality.strip(), self.province.strip()]
        return ", ".join(part for part in parts if part)


class Citation(BaseModel):
    chunk_id: str
    title: str
    page_number: int
    heading: str

    @property
    def label(self) -> str:
        return f"{self.title}, page {self.page_number}"


class PlanAction(BaseModel):
    task: str
    observe: str
    ask_for_help_if: str


class PlanSection(BaseModel):
    key: str
    title: str
    guidance: list[str]
    actions: list[PlanAction] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def require_source_or_fallback(self) -> "PlanSection":
        if not self.citations and not self.fallback_reason:
            raise ValueError(f"{self.key} must include citations or a fallback reason")
        return self


class TimelineItem(BaseModel):
    period: str
    approximate_date: str
    task: str
    how_to_steps: list[str] = Field(default_factory=list)
    observe: str
    ask_for_help_if: str


class GlossaryItem(BaseModel):
    term: str
    explanation: str


class DecisionRow(BaseModel):
    situation: str
    first_check: str
    what_to_do_next: str
    contact_mao_if: str


class MaterialChecklistGroup(BaseModel):
    category: str
    items: list[str]


class RecordTemplate(BaseModel):
    title: str
    columns: list[str]
    sample_row: list[str]


class MaoQuestion(BaseModel):
    topic: str
    question: str


class FarmingPlan(BaseModel):
    crop: str
    location: str
    language: PlanLanguage = "english"
    farming_type: FarmingType
    planning_basis: str
    status: Literal["generated", "unsupported_crop", "insufficient_evidence"]
    generation_method: Literal["template", "ollama", "fallback"] = "template"
    llm_model: str | None = None
    llm_error: str | None = None
    warnings: list[str]
    sections: list[PlanSection]
    timeline: list[TimelineItem] = Field(default_factory=list)
    glossary: list[GlossaryItem] = Field(default_factory=list)
    decision_rows: list[DecisionRow] = Field(default_factory=list)
    material_checklist: list[MaterialChecklistGroup] = Field(default_factory=list)
    record_templates: list[RecordTemplate] = Field(default_factory=list)
    mao_questions: list[MaoQuestion] = Field(default_factory=list)
    source_count: int

    @model_validator(mode="after")
    def reject_budget_fields_in_output(self) -> "FarmingPlan":
        rendered = self.model_dump_json().lower()
        blocked_terms = ("capital", "budget", "cost", "price")
        found = [term for term in blocked_terms if term in rendered]
        if found:
            raise ValueError(f"FarmingPlan output must not include budget terms: {found}")
        return self
