"""警廣即時路況 open data（data.gov.tw dataset 15221）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from radio_parser.config import Settings

DEFAULT_PBS_URL = (
    "https://rtr.pbs.gov.tw/NMP103_PbsWS/resources/roadData/opendata"
)
USER_AGENT = "radio_parser/0.1 (+https://data.gov.tw/dataset/15221)"

TAIWAN_LAT = (21.5, 25.4)
TAIWAN_LNG = (118.0, 122.2)


@dataclass(frozen=True)
class PbsRecord:
    uid: str
    region: str | None
    srcdetail: str | None
    area_nm: str | None
    direction: str | None
    roadtype: str | None
    road: str | None
    comment: str
    happen_date: str | None
    happen_time: str | None
    mod_dttm: str | None
    lng: float | None
    lat: float | None
    raw: dict[str, Any]


def fetch_pbs_payload(
    url: str | None = None,
    *,
    timeout: float = 30.0,
) -> Any:
    target = url or DEFAULT_PBS_URL
    request = urllib.request.Request(
        target,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"無法讀取警廣 API {target}: {exc}") from exc
    text = body.decode("utf-8-sig")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"警廣 API 不是 JSON: {exc}") from exc


def parse_pbs_payload(payload: Any) -> list[PbsRecord]:
    rows = _rows_from_payload(payload)
    records: list[PbsRecord] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        comment = _pick(row, "comment", "路況說明") or ""
        uid = str(_pick(row, "UID", "uid", "UniqueId", "唯一編號") or f"row-{index}")
        records.append(
            PbsRecord(
                uid=uid,
                region=_pick(row, "region", "路況區域"),
                srcdetail=_pick(row, "srcdetail", "資料來源"),
                area_nm=_pick(row, "areaNm", "area_nm", "地區區分說明"),
                direction=_pick(row, "direction", "方向"),
                roadtype=_pick(row, "roadtype", "路況類別"),
                road=_pick(row, "road", "道路名稱"),
                comment=comment.strip(),
                happen_date=_pick(row, "happendate", "發生日期"),
                happen_time=_pick(row, "happentime", "發生時間"),
                mod_dttm=_pick(row, "modDttm", "修改時間"),
                lng=_coord(_pick(row, "x1", "lng", "經度")),
                lat=_coord(_pick(row, "y1", "lat", "緯度")),
                raw=row,
            )
        )
    return records


def load_pbs_records(
    *,
    settings: Settings | None = None,
    url: str | None = None,
    payload: Any | None = None,
) -> list[PbsRecord]:
    if payload is not None:
        return parse_pbs_payload(payload)
    settings = settings
    target = url or (settings.pbs_api_url if settings else DEFAULT_PBS_URL)
    timeout = settings.pbs_timeout_sec if settings else 30.0
    return parse_pbs_payload(fetch_pbs_payload(target, timeout=timeout))


def _rows_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("result", "data", "records", "datas", "roadData"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = value.get("records") or value.get("data")
            if isinstance(nested, list):
                return nested
    return []


def _pick(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            text = str(row[key]).strip()
            if text:
                return text
    lower = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        value = lower.get(key.lower())
        if value not in (None, ""):
            text = str(value).strip()
            if text:
                return text
    return None


def _coord(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number == 0:
        return None
    return number


def taiwan_point(lat: float | None, lng: float | None) -> tuple[float, float] | None:
    if lat is None or lng is None:
        return None
    if not (TAIWAN_LAT[0] <= lat <= TAIWAN_LAT[1]):
        return None
    if not (TAIWAN_LNG[0] <= lng <= TAIWAN_LNG[1]):
        return None
    return (lat, lng)
