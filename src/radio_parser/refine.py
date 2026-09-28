"""把 PBS 結構化欄位 + comment 剖析結果合成真正的方形區塊。"""

from __future__ import annotations

from radio_parser.config import Settings
from radio_parser.gazetteer import GeoPoint, canonical_road
from radio_parser.geocode import (
    bbox_from_mention,
    box_from_points,
    mention_to_incident,
    union_boxes,
)
from radio_parser.heuristic import extract_mentions
from radio_parser.models import BoundingBox, ExtractedMention, Incident, IncidentType
from radio_parser.pbs import PbsRecord, taiwan_point

ROADTYPE_MAP: list[tuple[tuple[str, ...], IncidentType]] = [
    (("事故", "車禍", "追撞"), IncidentType.ACCIDENT),
    (("障礙", "拋錨", "故障"), IncidentType.BREAKDOWN),
    (("施工", "養護", "封閉"), IncidentType.CONSTRUCTION),
    (("壅塞", "阻塞", "回堵", "車多", "緩慢"), IncidentType.CONGESTION),
    (("災變", "積水", "濃霧", "坍方"), IncidentType.WEATHER),
]


def record_to_incident(
    record: PbsRecord,
    settings: Settings,
    mention: ExtractedMention | None = None,
) -> Incident:
    mention = _merge_structured(record, mention or _heuristic_comment(record))
    incident = mention_to_incident(mention, settings, raw_text=record.comment)
    api_box = _api_bbox(record, settings)
    refined_box, center, source = bbox_from_mention(mention, settings)
    comment_specific = _comment_is_specific(mention)

    if api_box is None:
        bbox, bbox_source = refined_box, source if comment_specific else "gazetteer"
    elif comment_specific and mention.prefer_comment_over_api:
        bbox, bbox_source = refined_box, source
        if mention.kilometer is None and _boxes_overlap_or_near(api_box, refined_box, 0.03):
            bbox = union_boxes(api_box, refined_box)
            bbox_source = "hybrid"
    elif comment_specific:
        bbox = union_boxes(api_box, refined_box)
        bbox_source = "hybrid"
    else:
        bbox, bbox_source = api_box, "api"

    incident.bbox = bbox
    incident.original_bbox = api_box
    incident.bbox_source = bbox_source
    incident.center = {
        "lat": round((bbox.min_lat + bbox.max_lat) / 2, 6),
        "lng": round((bbox.min_lng + bbox.max_lng) / 2, 6),
    }
    incident.id = record.uid[:12]
    incident.uid = record.uid
    incident.region = record.region
    incident.area_nm = record.area_nm
    incident.roadtype = record.roadtype
    incident.source = "pbs_opendata"
    if record.lat is not None and record.lng is not None:
        incident.api_center = {"lat": record.lat, "lng": record.lng}
    return incident


def _heuristic_comment(record: PbsRecord) -> ExtractedMention:
    text = record.comment or " ".join(
        part for part in (record.area_nm, record.road, record.direction, record.roadtype) if part
    )
    mentions = extract_mentions(text) if text else []
    if mentions:
        return mentions[0]
    itype = _type_from_roadtype(record.roadtype) or IncidentType.OTHER
    return ExtractedMention(
        type=itype,
        summary=record.comment or record.roadtype or "路況",
        location_text=record.area_nm or record.road or "未知地點",
        direction=record.direction,
        road=record.road,
        confidence=0.35,
        raw_span=record.comment,
        prefer_comment_over_api=False,
    )


def _merge_structured(record: PbsRecord, mention: ExtractedMention) -> ExtractedMention:
    itype = mention.type
    if itype == IncidentType.OTHER:
        itype = _type_from_roadtype(record.roadtype) or itype
    location = mention.location_text
    if location in {"未知地點", ""} and record.area_nm:
        location = record.area_nm
    return mention.model_copy(
        update={
            "type": itype,
            "location_text": location,
            "direction": mention.direction or record.direction,
            "road": mention.road or record.road,
            "city": mention.city,
            "summary": mention.summary or record.comment or "路況",
            "raw_span": mention.raw_span or record.comment,
        }
    )


def _type_from_roadtype(roadtype: str | None) -> IncidentType | None:
    if not roadtype:
        return None
    for words, itype in ROADTYPE_MAP:
        if any(word in roadtype for word in words):
            return itype
    return None


def _comment_is_specific(mention: ExtractedMention) -> bool:
    return any(
        (
            mention.kilometer is not None,
            mention.kilometer_end is not None,
            mention.span_km is not None,
            mention.landmark,
            mention.landmark_end,
        )
    )


def _api_bbox(record: PbsRecord, settings: Settings) -> BoundingBox | None:
    point = taiwan_point(record.lat, record.lng)
    if not point:
        return None
    lat, lng = point
    return box_from_points(
        [GeoPoint(lat, lng, canonical_road(record.road) or record.road or "api")],
        settings.default_bbox_half_deg,
    )


def _boxes_overlap_or_near(a: BoundingBox, b: BoundingBox, pad: float) -> bool:
    return not (
        a.max_lat + pad < b.min_lat
        or b.max_lat + pad < a.min_lat
        or a.max_lng + pad < b.min_lng
        or b.max_lng + pad < a.min_lng
    )
