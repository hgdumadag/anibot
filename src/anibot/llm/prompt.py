from __future__ import annotations

import json

from anibot.planning.schema import FarmingPlanRequest, TimelineItem


def build_evidence_planner_prompt(
    request: FarmingPlanRequest,
    evidence_guidelines: list[dict[str, str | int]],
    calendar_rows: list[TimelineItem],
) -> str:
    payload = {
        "context": request.model_dump(),
        "evidence": evidence_guidelines,
        "calendar": [
            {
                "period": item.period,
                "approximate_date": item.approximate_date,
                "draft_task": item.task,
                "draft_how_to_steps": item.how_to_steps,
                "draft_observe": item.observe,
                "draft_ask_for_help_if": item.ask_for_help_if,
            }
            for item in calendar_rows
        ],
    }
    return (
        "Return only valid compact JSON. Do not include markdown, comments, or extra text. "
        "Top-level key must be exactly: timeline. "
        "Improve the beginner calendar using INPUT evidence and the draft calendar. "
        "Timeline must have one item for every INPUT calendar row and must copy period and approximate_date exactly. "
        "Each timeline item needs: period, approximate_date, task, how_to_steps, observe, ask_for_help_if. "
        "Use 2-4 concrete how_to_steps per row. Keep steps short but specific enough for a beginner to act. "
        "Do not replace a specific draft step with a vague instruction. "
        "Bad vague steps include: prepare seeds for planting, check field condition, monitor crop growth, ask MAO if unsure. "
        "When evidence is thin, keep or lightly improve the draft row instead of inventing. "
        "Never include fertilizer rates, pesticide products, chemical dosages, brands, money advice, or harvest predictions. "
        "Require MAO or technician help for soil-test interpretation, pest identity, pesticide decisions, dry/flooded fields, and contamination.\n\n"
        "INPUT="
        f"{json.dumps(payload, ensure_ascii=True, separators=(',', ':'))}"
    )
