from __future__ import annotations

from pathlib import Path

from radio_parser.config import Settings, get_settings
from radio_parser.geocode import mention_to_incident
from radio_parser.heuristic import extract_mentions
from radio_parser.models import IncidentReport


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
