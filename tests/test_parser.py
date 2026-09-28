from __future__ import annotations

from radio_parser.gazetteer import interpolate_freeway
from radio_parser.geocode import mention_to_incident, resolve_point
from radio_parser.heuristic import extract_mentions
from radio_parser.models import ExtractedMention, IncidentType
from radio_parser.pipeline import parse_transcript
from radio_parser.config import Settings
from pathlib import Path


def test_chinese_kilometer():
    from radio_parser.heuristic import chinese_number_to_float, extract_kilometer

    assert chinese_number_to_float("二十五點三") == 25.3
    assert extract_kilometer("國道一號南下二十五點三公里，後方回堵大約三公里") == 25.3
    assert extract_kilometer("國道1號 33.2k 追撞") == 33.2


def test_heuristic_extracts_accident_and_congestion():
    text = Path("samples/transcripts/sample_police_radio.txt").read_text(encoding="utf-8")
    mentions = extract_mentions(text)
    types = {m.type for m in mentions}
    assert IncidentType.ACCIDENT in types
    assert IncidentType.CONGESTION in types
    assert IncidentType.BREAKDOWN in types
    assert any(m.road and "國道" in m.road for m in mentions)


def test_freeway_km_interpolation():
    point = interpolate_freeway("國道1號", 25.3)
    assert point is not None
    assert 24.9 < point.lat < 25.2
    assert 121.4 < point.lng < 121.7


def test_bbox_is_rectangle_around_point():
    settings = Settings(
        openai_api_key="",
        openai_model="gpt-4o-mini",
        openai_base_url="https://api.openai.com/v1",
        geocoder_provider="local",
        output_dir=Path("output"),
        default_bbox_half_deg=0.01,
    )
    mention = ExtractedMention(
        type=IncidentType.ACCIDENT,
        summary="追撞",
        location_text="國道1號南下 25.3k",
        road="國道1號",
        kilometer=25.3,
        direction="南下",
    )
    incident = mention_to_incident(mention, settings)
    assert incident.bbox.max_lat > incident.bbox.min_lat
    assert incident.bbox.max_lng > incident.bbox.min_lng
    center = resolve_point(mention)
    assert abs((incident.bbox.min_lat + incident.bbox.max_lat) / 2 - center.lat) < 1e-6


def test_pipeline_without_openai():
    report = parse_transcript(
        "國道三號北上新店交流道附近回堵約兩公里。",
        use_llm=False,
    )
    assert report.parser == "heuristic"
    assert len(report.incidents) >= 1
    geojson = report.to_geojson()
    assert geojson["type"] == "FeatureCollection"
    assert geojson["features"][0]["geometry"]["type"] == "Polygon"
