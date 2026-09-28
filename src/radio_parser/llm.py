from __future__ import annotations

import json
from typing import Any

from radio_parser.config import Settings
from radio_parser.models import ExtractedMention, IncidentType, Severity

SYSTEM_PROMPT = """你是台灣交通廣播（警廣）逐字稿分析器。
從廣播內容抽出交通事故、塞車/回堵、拋錨、施工、天候路況等事件。
只輸出 JSON，格式如下：
{
  "incidents": [
    {
      "type": "accident|congestion|breakdown|construction|weather|other",
      "summary": "一句話描述發生什麼",
      "location_text": "盡量保留原廣播地名/路名",
      "direction": "南下|北上|東向|西向 或 null",
      "road": "國道1號/台64線 等或 null",
      "kilometer": 數字或 null,
      "city": "縣市名或 null",
      "landmark": "交流道或地標或 null",
      "severity": "low|medium|high|unknown",
      "confidence": 0到1,
      "raw_span": "原文片段"
    }
  ]
}
沒有交通事件就回 {"incidents": []}。不要編造座標。"""


def extract_with_openai(transcript: str, settings: Settings) -> list[ExtractedMention]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    )
    content = response.choices[0].message.content or "{}"
    payload: dict[str, Any] = json.loads(content)
    items = payload.get("incidents") or payload.get("events") or []
    mentions: list[ExtractedMention] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mentions.append(
            ExtractedMention(
                type=_enum(IncidentType, item.get("type"), IncidentType.OTHER),
                summary=str(item.get("summary") or "").strip() or "未提供摘要",
                location_text=str(item.get("location_text") or item.get("location") or "").strip()
                or "未知地點",
                direction=_optional_str(item.get("direction")),
                road=_optional_str(item.get("road")),
                kilometer=_optional_float(item.get("kilometer")),
                city=_optional_str(item.get("city")),
                landmark=_optional_str(item.get("landmark")),
                severity=_enum(Severity, item.get("severity"), Severity.UNKNOWN),
                confidence=_clamp_conf(item.get("confidence")),
                raw_span=_optional_str(item.get("raw_span")),
            )
        )
    return mentions


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "未知"}:
        return None
    return text


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp_conf(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.6
    return max(0.0, min(1.0, number))


def _enum(enum_cls, value: Any, default):
    if value is None:
        return default
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return default
