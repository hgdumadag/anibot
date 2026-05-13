from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


VALID_TIERS = {"reviewed_advisory", "context_reference", "future_crop"}
VALID_ALLOWED_USE = {"advisory_evidence", "context_only", "future_only"}


@dataclass(frozen=True)
class DocumentSpec:
    id: str
    filename: str
    title: str
    source_agency: str
    document_type: str
    year: int
    crops: tuple[str, ...]
    advisory_tier: str
    allowed_use: str
    reviewed: bool

    @property
    def supports_advisory(self) -> bool:
        return (
            self.reviewed
            and self.advisory_tier == "reviewed_advisory"
            and self.allowed_use == "advisory_evidence"
        )


def load_manifest(path: Path) -> list[DocumentSpec]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        raise ValueError(f"Unsupported manifest version in {path}")

    docs: list[DocumentSpec] = []
    seen: set[str] = set()
    for item in raw.get("documents", []):
        spec = DocumentSpec(
            id=_required_str(item, "id"),
            filename=_required_str(item, "filename"),
            title=_required_str(item, "title"),
            source_agency=_required_str(item, "source_agency"),
            document_type=_required_str(item, "document_type"),
            year=int(item["year"]),
            crops=tuple(str(crop).lower() for crop in item.get("crops", [])),
            advisory_tier=_required_str(item, "advisory_tier"),
            allowed_use=_required_str(item, "allowed_use"),
            reviewed=bool(item.get("reviewed", False)),
        )
        if spec.id in seen:
            raise ValueError(f"Duplicate document id: {spec.id}")
        if not spec.crops:
            raise ValueError(f"{spec.id} must declare at least one crop")
        if spec.advisory_tier not in VALID_TIERS:
            raise ValueError(f"{spec.id} has invalid advisory_tier: {spec.advisory_tier}")
        if spec.allowed_use not in VALID_ALLOWED_USE:
            raise ValueError(f"{spec.id} has invalid allowed_use: {spec.allowed_use}")
        seen.add(spec.id)
        docs.append(spec)
    return docs


def _required_str(item: dict, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Manifest item missing required string field: {key}")
    return value.strip()
