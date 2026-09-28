from __future__ import annotations

from pathlib import Path
from typing import Any

from radio_parser.config import Settings, get_settings
from radio_parser.geocode import mention_to_incident
from radio_parser.heuristic import extract_mentions
from radio_parser.models import ExtractedMention, IncidentReport
from radio_parser.pbs import PbsRecord, load_pbs_records
from radio_parser.refine import record_to_incident


def parse_transcript(
    transcript: str,
    *,
    settings: Settings | None = None,
    transcript_path: str | None = None,
    use_llm: bool | None = None,
) -> IncidentReport:
    settings = settings or get_settings()
    parser_name = "heuristic"
    mentions = []
    should_llm = settings.openai_enabled if use_llm is None else use_llm
    if should_llm:
        from radio_parser.llm import extract_with_openai

        mentions = extract_with_openai(transcript, settings)
        parser_name = f"openai:{settings.openai_model}"
    if not mentions:
        mentions = extract_mentions(transcript)
        if parser_name.startswith("openai"):
            parser_name = f"{parser_name}+heuristic_fallback"
        else:
            parser_name = "heuristic"
    incidents = [
        mention_to_incident(mention, settings, raw_text=transcript)
        for mention in mentions
    ]
    return IncidentReport(
        parser=parser_name,
        transcript_path=transcript_path,
        incidents=incidents,
    )


def parse_file(path: Path, *, settings: Settings | None = None) -> IncidentReport:
    text = path.read_text(encoding="utf-8")
    return parse_transcript(text, settings=settings, transcript_path=str(path))


def parse_pbs_records(
    records: list[PbsRecord],
    *,
    settings: Settings | None = None,
    use_llm: bool | None = None,
    pbs_url: str | None = None,
) -> IncidentReport:
    settings = settings or get_settings()
    parser_name = "pbs+heuristic"
    llm_by_uid: dict[str, ExtractedMention] = {}
    should_llm = settings.openai_enabled if use_llm is None else use_llm
    if should_llm and records:
        from radio_parser.llm import refine_comments_with_openai

        payload = [
            {
                "uid": rec.uid,
                "road": rec.road,
                "direction": rec.direction,
                "roadtype": rec.roadtype,
                "areaNm": rec.area_nm,
                "x1": rec.lng,
                "y1": rec.lat,
                "comment": rec.comment,
            }
            for rec in records
        ]
        llm_by_uid = refine_comments_with_openai(payload, settings)
        parser_name = f"pbs+openai:{settings.openai_model}"
        if not llm_by_uid:
            parser_name = f"{parser_name}+heuristic_fallback"
    incidents = [
        record_to_incident(rec, settings, mention=llm_by_uid.get(rec.uid))
        for rec in records
        if rec.comment or rec.road or rec.area_nm
    ]
    return IncidentReport(
        source="pbs_opendata",
        parser=parser_name,
        pbs_url=pbs_url,
        incidents=incidents,
    )


def parse_pbs_api(
    *,
    settings: Settings | None = None,
    url: str | None = None,
    payload: Any | None = None,
    use_llm: bool | None = None,
) -> IncidentReport:
    settings = settings or get_settings()
    target = url or settings.pbs_api_url
    records = load_pbs_records(settings=settings, url=url, payload=payload)
    return parse_pbs_records(
        records,
        settings=settings,
        use_llm=use_llm,
        pbs_url=None if payload is not None and url is None else target,
    )
