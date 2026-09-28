from __future__ import annotations

import re

from radio_parser.models import ExtractedMention, IncidentType, Severity

TYPE_KEYWORDS: list[tuple[IncidentType, tuple[str, ...]]] = [
    (IncidentType.ACCIDENT, ("交通事故", "車禍", "追撞", "事故", "擦撞", "翻覆", "撞")),
    (IncidentType.CONGESTION, ("回堵", "車多", "壅塞", "塞車", "車潮", "緩慢", "車速偏低")),
    (IncidentType.BREAKDOWN, ("拋錨", "故障", "停等", "占用內線")),
    (IncidentType.CONSTRUCTION, ("施工", "養護", "封閉", "改道")),
    (IncidentType.WEATHER, ("積水", "濃霧", "坍方", "落石", "路樹")),
]

SEVERITY_KEYWORDS: list[tuple[Severity, tuple[str, ...]]] = [
    (Severity.HIGH, ("多車", "翻覆", "傷亡", "嚴重回堵", "回堵超過", "封閉")),
    (Severity.MEDIUM, ("回堵", "占用", "追撞")),
]

ROAD_RE = re.compile(
    r"(國道[一二三四五1-5]號|國[1-5]|中山高(?:速公路)?|福[爾尔]摩沙|福高|北宜高|"
    r"台[1-9]\d?線|台[1-9]\d?甲|市道\d+|快速道路|環東大道|環河快速|"
    r"新生高架|建國高架|市民大道|麥帥公路)"
)
DIGIT_KM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:k|K|公里)")
CN_KM_RE = re.compile(
    r"([零一二三四五六七八九十百兩]+(?:點[零一二三四五六七八九]+)?)\s*(?:k|K|公里)"
)
_CN_DIGIT = {
    "零": 0,
    "一": 1,
    "二": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def chinese_number_to_float(text: str) -> float | None:
    if "點" in text:
        whole, frac = text.split("點", 1)
        base = _chinese_int(whole)
        if base is None or not frac:
            return None
        scale = 0.1
        value = float(base)
        for ch in frac:
            if ch not in _CN_DIGIT:
                return None
            value += _CN_DIGIT[ch] * scale
            scale /= 10
        return value
    parsed = _chinese_int(text)
    return None if parsed is None else float(parsed)


def _chinese_int(text: str) -> int | None:
    if not text:
        return 0
    if text == "十":
        return 10
    if "百" in text:
        left, right = text.split("百", 1)
        hundreds = 1 if not left else _CN_DIGIT.get(left)
        if hundreds is None:
            return None
        rest = 0 if not right else _chinese_int(right)
        if rest is None:
            return None
        return hundreds * 100 + rest
    if "十" in text:
        left, right = text.split("十", 1)
        tens = 1 if not left else _CN_DIGIT.get(left)
        if tens is None:
            return None
        ones = 0 if not right else _CN_DIGIT.get(right)
        if ones is None:
            return None
        return tens * 10 + ones
    return _CN_DIGIT.get(text)


def extract_kilometer(text: str) -> float | None:
    """Prefer a km post near the road name, not '回堵約三公里'."""
    candidates: list[tuple[int, float]] = []
    for match in DIGIT_KM_RE.finditer(text):
        candidates.append((match.start(), float(match.group(1))))
    for match in CN_KM_RE.finditer(text):
        value = chinese_number_to_float(match.group(1))
        if value is not None:
            candidates.append((match.start(), value))
    if not candidates:
        return None
    cutoff = len(text)
    for marker in ("回堵", "後方", "車多"):
        idx = text.find(marker)
        if idx != -1:
            cutoff = min(cutoff, idx)
    preferred = [item for item in candidates if item[0] < cutoff]
    return (preferred or candidates)[0][1]
DIR_RE = re.compile(r"(南下|北上|東向|西向|往南|往北|往東|往西)")
CITY_RE = re.compile(
    r"(基隆|台北|臺北|新北|桃園|新竹|苗栗|台中|臺中|彰化|南投|雲林|嘉義|"
    r"台南|臺南|高雄|屏東|宜蘭|花蓮|台東|臺東)"
)
LANDMARK_RE = re.compile(
    r"(圓山|五股|林口|中壢|內壢|楊梅|頭份|中港|員林|斗南|新營|岡山|鼎金|五甲|"
    r"木柵|深坑|新店|安坑|土城|中和|板橋|汐止|南港|忠孝橋|中興橋|華江橋|"
    r"[^\s，。、]{2,6}交流道)"
)

SENTENCE_SPLIT = re.compile(r"[。！？\n；]+")


def _classify(text: str) -> tuple[IncidentType, Severity]:
    incident_type = IncidentType.OTHER
    for itype, words in TYPE_KEYWORDS:
        if any(word in text for word in words):
            incident_type = itype
            break
    severity = Severity.UNKNOWN
    for sev, words in SEVERITY_KEYWORDS:
        if any(word in text for word in words):
            severity = sev
            break
    if incident_type == IncidentType.ACCIDENT and severity == Severity.UNKNOWN:
        severity = Severity.MEDIUM
    if incident_type == IncidentType.CONGESTION and severity == Severity.UNKNOWN:
        severity = Severity.LOW
    return incident_type, severity


def extract_mentions(transcript: str) -> list[ExtractedMention]:
    mentions: list[ExtractedMention] = []
    seen: set[tuple[str, str]] = set()
    for chunk in SENTENCE_SPLIT.split(transcript):
        text = chunk.strip(" ，、")
        if len(text) < 6:
            continue
        itype, severity = _classify(text)
        if itype == IncidentType.OTHER and not ROAD_RE.search(text):
            continue
        road_m = ROAD_RE.search(text)
        kilometer = extract_kilometer(text)
        dir_m = DIR_RE.search(text)
        city_m = CITY_RE.search(text)
        landmark_m = LANDMARK_RE.search(text)
        location_parts = [
            part
            for part in (
                city_m.group(0) if city_m else None,
                road_m.group(0) if road_m else None,
                dir_m.group(0) if dir_m else None,
                f"{kilometer:g}k" if kilometer is not None else None,
                landmark_m.group(0) if landmark_m else None,
            )
            if part
        ]
        location_text = " ".join(location_parts) or text[:40]
        key = (itype.value, location_text)
        if key in seen:
            continue
        seen.add(key)
        mentions.append(
            ExtractedMention(
                type=itype,
                summary=text,
                location_text=location_text,
                direction=dir_m.group(0) if dir_m else None,
                road=road_m.group(0) if road_m else None,
                kilometer=kilometer,
                city=city_m.group(0) if city_m else None,
                landmark=landmark_m.group(0) if landmark_m else None,
                severity=severity,
                confidence=0.55 if itype != IncidentType.OTHER else 0.35,
                raw_span=text,
            )
        )
    return mentions
