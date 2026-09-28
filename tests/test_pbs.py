from __future__ import annotations

import json
from pathlib import Path

from radio_parser.config import Settings
from radio_parser.heuristic import extract_span_km
from radio_parser.pbs import parse_pbs_payload, taiwan_point
from radio_parser.pipeline import parse_pbs_api
from radio_parser.refine import record_to_incident


def _settings() -> Settings:
    return Settings(
        openai_api_key="",
        openai_model="gpt-4o-mini",
        openai_base_url="https://api.openai.com/v1",
        geocoder_provider="local",
        output_dir=Path("output"),
        default_bbox_half_deg=0.008,
    )


def test_span_km_from_comment():
    assert extract_span_km("後方回堵約三公里") == 3.0
    assert extract_span_km("回堵大約 4 公里") == 4.0


def test_parse_pbs_payload_and_zero_coords():
    rows = parse_pbs_payload(
        {
            "result": [
                {
                    "UID": "X1",
                    "comment": "濃霧",
                    "x1": "0",
                    "y1": "0",
                    "road": "台9線",
                }
            ]
        }
    )
    assert rows[0].lng is None
    assert taiwan_point(22.6, 120.3) is not None
    assert taiwan_point(0, 0) is None


def test_comment_km_moves_bbox_off_api_point():
    settings = _settings()
    sample = json.loads(
        Path("samples/pbs/opendata_sample.json").read_text(encoding="utf-8")
    )
    records = parse_pbs_payload(sample)
    accident = next(r for r in records if r.uid.endswith("001"))
    incident = record_to_incident(accident, settings)
    assert incident.type.value == "accident"
    assert incident.kilometer == 25.3
    assert incident.span_km == 3.0
    assert "台北交流道" in incident.location_text
    assert "公里台北" not in incident.location_text
    assert incident.original_bbox is not None
    settings = _settings()
    sample = json.loads(
        Path("samples/pbs/opendata_sample.json").read_text(encoding="utf-8")
    )
    records = parse_pbs_payload(sample)
    accident = next(r for r in records if r.uid.endswith("001"))
    incident = record_to_incident(accident, settings)
    assert incident.type.value == "accident"
    assert incident.kilometer == 25.3
    assert incident.span_km == 3.0
    assert incident.original_bbox is not None
    # API 點在台北交流道約 121.548；comment 25.3k 應把區塊往西移，並拉長回堵。
    assert incident.bbox.min_lng < incident.original_bbox.min_lng
    assert incident.bbox_source in {"comment", "comment_span"}
    width = incident.bbox.max_lng - incident.bbox.min_lng
    api_width = incident.original_bbox.max_lng - incident.original_bbox.min_lng
    assert width > api_width


def test_pipeline_from_sample_json():
    sample = json.loads(
        Path("samples/pbs/opendata_sample.json").read_text(encoding="utf-8")
    )
    report = parse_pbs_api(payload=sample, use_llm=False)
    assert report.source == "pbs_opendata"
    assert report.parser == "pbs+heuristic"
    assert len(report.incidents) == 5
    types = {item.type.value for item in report.incidents}
    assert {"accident", "congestion", "breakdown", "construction", "weather"} <= types
    dingjin = next(i for i in report.incidents if "鼎金" in (i.summary or "") or (i.location_text and "鼎金" in i.location_text))
    assert dingjin.bbox_source != "api"
    muxin = next(i for i in report.incidents if i.uid.endswith("002"))
    assert "木柵" in muxin.location_text
    assert "新店" in muxin.location_text
    assert "三號北上木柵" not in muxin.location_text
    fog = next(i for i in report.incidents if i.uid.endswith("005"))
    assert fog.original_bbox is None
