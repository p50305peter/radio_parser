from __future__ import annotations

from radio_parser.config import Settings
from radio_parser.gazetteer import (
    CITIES,
    LANDMARKS,
    GeoPoint,
    canonical_road,
    interpolate_freeway,
)
from radio_parser.models import BoundingBox, ExtractedMention, Incident

TAIWAN_FALLBACK = GeoPoint(23.9739, 120.9820, "台灣", half_deg=1.5)


def mention_to_incident(
    mention: ExtractedMention,
    settings: Settings,
    raw_text: str | None = None,
) -> Incident:
    point = resolve_point(mention)
    half = point.half_deg if point.half_deg is not None else settings.default_bbox_half_deg
    bbox = BoundingBox(
        min_lat=round(point.lat - half, 6),
        min_lng=round(point.lng - half, 6),
        max_lat=round(point.lat + half, 6),
        max_lng=round(point.lng + half, 6),
    )
    title = _title(mention)
    return Incident(
        type=mention.type,
        title=title,
        summary=mention.summary,
        severity=mention.severity,
        location_text=mention.location_text,
        bbox=bbox,
        center={"lat": round(point.lat, 6), "lng": round(point.lng, 6)},
        road=canonical_road(mention.road) or mention.road,
        direction=mention.direction,
        kilometer=mention.kilometer,
        city=mention.city,
        confidence=mention.confidence,
        raw_text=mention.raw_span or raw_text,
    )


def resolve_point(mention: ExtractedMention) -> GeoPoint:
    road = canonical_road(mention.road) or mention.road
    if road and mention.kilometer is not None:
        freeway = interpolate_freeway(road, mention.kilometer)
        if freeway:
            return freeway
    if mention.landmark:
        for key, point in LANDMARKS.items():
            if key in mention.landmark or key in mention.location_text:
                return point
    if mention.city:
        for key, point in CITIES.items():
            if key in mention.city:
                return GeoPoint(point.lat, point.lng, point.label, half_deg=0.04)
    blob = " ".join(
        part
        for part in (mention.location_text, mention.landmark, mention.city, mention.summary)
        if part
    )
    for key, point in LANDMARKS.items():
        if key in blob:
            return point
    for key, point in CITIES.items():
        if key in blob:
            return GeoPoint(point.lat, point.lng, point.label, half_deg=0.04)
    if road:
        freeway = interpolate_freeway(road, mention.kilometer or 0)
        if freeway:
            return freeway
    return TAIWAN_FALLBACK


def _title(mention: ExtractedMention) -> str:
    type_zh = {
        "accident": "交通事故",
        "congestion": "塞車/回堵",
        "breakdown": "車輛拋錨",
        "construction": "施工",
        "weather": "天候路況",
        "other": "路況",
    }[mention.type.value]
    where = mention.location_text or "未定位"
    return f"{type_zh}｜{where}"
