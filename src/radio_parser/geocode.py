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
    bbox, center, source = bbox_from_mention(mention, settings)
    title = _title(mention)
    return Incident(
        type=mention.type,
        title=title,
        summary=mention.summary,
        severity=mention.severity,
        location_text=mention.location_text,
        bbox=bbox,
        bbox_source=source,
        center=center,
        road=canonical_road(mention.road) or mention.road,
        direction=mention.direction,
        kilometer=mention.kilometer,
        kilometer_end=mention.kilometer_end,
        span_km=mention.span_km,
        city=mention.city,
        confidence=mention.confidence,
        raw_text=mention.raw_span or raw_text,
    )


def bbox_from_mention(
    mention: ExtractedMention,
    settings: Settings,
) -> tuple[BoundingBox, dict[str, float], str]:
    points = collect_points(mention)
    if not points:
        points = [TAIWAN_FALLBACK]
        source = "fallback"
    elif mention.span_km or mention.kilometer_end or mention.landmark_end:
        source = "comment_span"
    else:
        source = "comment"
    half = settings.default_bbox_half_deg
    bbox = box_from_points(points, half)
    center = {
        "lat": round((bbox.min_lat + bbox.max_lat) / 2, 6),
        "lng": round((bbox.min_lng + bbox.max_lng) / 2, 6),
    }
    return bbox, center, source


def collect_points(mention: ExtractedMention) -> list[GeoPoint]:
    points: list[GeoPoint] = []
    road = canonical_road(mention.road) or mention.road
    km_values: list[float] = []
    if mention.kilometer is not None:
        km_values.append(mention.kilometer)
    if mention.kilometer_end is not None:
        km_values.append(mention.kilometer_end)
    if (
        mention.kilometer is not None
        and mention.span_km
        and mention.kilometer_end is None
    ):
        delta = mention.span_km
        direction = mention.direction or ""
        # 回堵在事故後方：南下/東向公里數變小，北上/西向變大（國1 往南遞增）。
        if any(token in direction for token in ("南下", "往南", "東向", "往東")):
            km_values.append(mention.kilometer - delta)
        elif any(token in direction for token in ("北上", "往北", "西向", "往西")):
            km_values.append(mention.kilometer + delta)
        else:
            km_values.append(mention.kilometer - delta)
            km_values.append(mention.kilometer + delta)
    if road:
        for km in km_values:
            freeway = interpolate_freeway(road, km)
            if freeway:
                points.append(freeway)
    for name in (mention.landmark, mention.landmark_end):
        found = lookup_landmark(name)
        if found:
            points.append(found)
    if not points and mention.city:
        city = lookup_city(mention.city)
        if city:
            points.append(city)
    if not points:
        blob = " ".join(
            part
            for part in (
                mention.location_text,
                mention.landmark,
                mention.city,
                mention.summary,
            )
            if part
        )
        for key, point in LANDMARKS.items():
            if key in blob:
                points.append(point)
                break
        else:
            for key, point in CITIES.items():
                if key in blob:
                    points.append(GeoPoint(point.lat, point.lng, point.label, half_deg=0.04))
                    break
    if not points and road:
        freeway = interpolate_freeway(road, mention.kilometer or 0)
        if freeway:
            points.append(freeway)
    return points


def lookup_landmark(name: str | None) -> GeoPoint | None:
    if not name:
        return None
    for key, point in LANDMARKS.items():
        if key in name or name in key:
            return point
    return None


def lookup_city(name: str | None) -> GeoPoint | None:
    if not name:
        return None
    for key, point in CITIES.items():
        if key in name:
            return GeoPoint(point.lat, point.lng, point.label, half_deg=0.04)
    return None


def box_from_points(points: list[GeoPoint], default_half: float) -> BoundingBox:
    lats = [p.lat for p in points]
    lngs = [p.lng for p in points]
    half = default_half
    for point in points:
        if point.half_deg is not None:
            half = max(half, point.half_deg)
    min_lat = min(lats) - half
    max_lat = max(lats) + half
    min_lng = min(lngs) - half
    max_lng = max(lngs) + half
    return BoundingBox(
        min_lat=round(min_lat, 6),
        min_lng=round(min_lng, 6),
        max_lat=round(max_lat, 6),
        max_lng=round(max_lng, 6),
    )


def union_boxes(first: BoundingBox, second: BoundingBox) -> BoundingBox:
    return BoundingBox(
        min_lat=min(first.min_lat, second.min_lat),
        min_lng=min(first.min_lng, second.min_lng),
        max_lat=max(first.max_lat, second.max_lat),
        max_lng=max(first.max_lng, second.max_lng),
    )


def resolve_point(mention: ExtractedMention) -> GeoPoint:
    points = collect_points(mention)
    if not points:
        return TAIWAN_FALLBACK
    lat = sum(p.lat for p in points) / len(points)
    lng = sum(p.lng for p in points) / len(points)
    return GeoPoint(lat, lng, points[0].label)


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
