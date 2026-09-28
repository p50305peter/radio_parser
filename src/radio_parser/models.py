from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class IncidentType(str, Enum):
    ACCIDENT = "accident"
    CONGESTION = "congestion"
    BREAKDOWN = "breakdown"
    CONSTRUCTION = "construction"
    WEATHER = "weather"
    OTHER = "other"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class BoundingBox(BaseModel):
    """Axis-aligned geographic rectangle (WGS84)."""

    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float

    def as_geojson_polygon(self) -> dict[str, Any]:
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [self.min_lng, self.min_lat],
                    [self.max_lng, self.min_lat],
                    [self.max_lng, self.max_lat],
                    [self.min_lng, self.max_lat],
                    [self.min_lng, self.min_lat],
                ]
            ],
        }


class ExtractedMention(BaseModel):
    """LLM / heuristic extraction before geocoding."""

    type: IncidentType = IncidentType.OTHER
    summary: str
    location_text: str
    direction: str | None = None
    road: str | None = None
    kilometer: float | None = None
    kilometer_end: float | None = None
    span_km: float | None = None
    city: str | None = None
    landmark: str | None = None
    landmark_end: str | None = None
    severity: Severity = Severity.UNKNOWN
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    raw_span: str | None = None
    prefer_comment_over_api: bool = True


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    type: IncidentType
    title: str
    summary: str
    severity: Severity = Severity.UNKNOWN
    location_text: str
    bbox: BoundingBox
    original_bbox: BoundingBox | None = None
    bbox_source: str = "gazetteer"
    center: dict[str, float]
    road: str | None = None
    direction: str | None = None
    kilometer: float | None = None
    kilometer_end: float | None = None
    span_km: float | None = None
    city: str | None = None
    confidence: float = 0.5
    raw_text: str | None = None
    source: str = "police_radio"
    uid: str | None = None
    region: str | None = None
    area_nm: str | None = None
    roadtype: str | None = None
    api_center: dict[str, float] | None = None


class IncidentReport(BaseModel):
    source: str = "police_radio"
    parser: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    transcript_path: str | None = None
    pbs_url: str | None = None
    incidents: list[Incident] = Field(default_factory=list)

    def to_geojson(self) -> dict[str, Any]:
        features = []
        for incident in self.incidents:
            features.append(
                {
                    "type": "Feature",
                    "id": incident.id,
                    "geometry": incident.bbox.as_geojson_polygon(),
                    "properties": incident.model_dump(exclude={"bbox"}),
                }
            )
        return {"type": "FeatureCollection", "features": features}
