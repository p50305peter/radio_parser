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
      "kilometer_end": 路段終點樁號或 null,
      "span_km": 回堵或受影響長度公里或 null,
      "city": "縣市名或 null",
      "landmark": "交流道或地標或 null",
      "landmark_end": "路段另一端地標或 null",
      "severity": "low|medium|high|unknown",
      "confidence": 0到1,
      "raw_span": "原文片段"
    }
  ]
}
沒有交通事件就回 {"incidents": []}。不要編造座標。"""

COMMENT_SYSTEM_PROMPT = """你是台灣警廣即時路況 comment 剖析器。
每筆已有 API 欄位：UID、road、direction、roadtype、areaNm、x1（經度）、y1（緯度）。
x1/y1 常常只是粗定位（縣市或交流道），真正樁號、回堵長度、A到B 路段在 comment。
依 comment 抽出更精確地點來重調地圖方形區塊。不要編造座標數字。
只輸出 JSON：
{
  "incidents": [
    {
      "uid": "對應原 UID",
      "type": "accident|congestion|breakdown|construction|weather|other",
      "summary": "一句話",
      "location_text": "精煉後的地點文字",
      "direction": "南下|北上|東向|西向 或 null",
      "road": "道路名或 null",
      "kilometer": 數字或 null,
      "kilometer_end": 數字或 null,
      "span_km": 回堵/占用路段公里或 null,
      "city": "縣市或 null",
      "landmark": "交流道或地標或 null",
      "landmark_end": "另一端地標或 null",
      "severity": "low|medium|high|unknown",
      "confidence": 0到1,
      "prefer_comment_over_api": true
    }
  ]
}
comment 沒有更精確地點時 prefer_comment_over_api 設 false。"""


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
                kilometer_end=_optional_float(item.get("kilometer_end")),
                span_km=_optional_float(item.get("span_km")),
                city=_optional_str(item.get("city")),
                landmark=_optional_str(item.get("landmark")),
                landmark_end=_optional_str(item.get("landmark_end")),
                severity=_enum(Severity, item.get("severity"), Severity.UNKNOWN),
                confidence=_clamp_conf(item.get("confidence")),
                raw_span=_optional_str(item.get("raw_span")),
                prefer_comment_over_api=bool(
                    item.get("prefer_comment_over_api", True)
                ),
            )
        )
    return mentions


def refine_comments_with_openai(
    records: list[dict[str, Any]],
    settings: Settings,
) -> dict[str, ExtractedMention]:
    """records: compact dicts with uid + structured fields + comment."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": COMMENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(records, ensure_ascii=False),
            },
        ],
    )
    content = response.choices[0].message.content or "{}"
    payload: dict[str, Any] = json.loads(content)
    items = payload.get("incidents") or payload.get("events") or []
    by_uid: dict[str, ExtractedMention] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        uid = _optional_str(item.get("uid") or item.get("UID"))
        mentions = _mentions_from_items([item])
        if uid and mentions:
            by_uid[uid] = mentions[0]
    return by_uid


def _mentions_from_items(items: list[Any]) -> list[ExtractedMention]:
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
                kilometer_end=_optional_float(item.get("kilometer_end")),
                span_km=_optional_float(item.get("span_km")),
                city=_optional_str(item.get("city")),
                landmark=_optional_str(item.get("landmark")),
                landmark_end=_optional_str(item.get("landmark_end")),
                severity=_enum(Severity, item.get("severity"), Severity.UNKNOWN),
                confidence=_clamp_conf(item.get("confidence")),
                raw_span=_optional_str(item.get("raw_span")),
                prefer_comment_over_api=bool(item.get("prefer_comment_over_api", True)),
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
