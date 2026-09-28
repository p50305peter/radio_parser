# radio_parser

把台灣警廣（警察廣播電台）路況解析成地圖可用的 JSON：每筆事件含**方形區塊座標**，以及這區發生了什麼（交通事故、回堵／塞車、拋錨、施工等）。

主要資料來源是政府開放資料 [警廣即時路況（dataset 15221）](https://data.gov.tw/dataset/15221)。API 已有 `road`、`direction`、`roadtype`、`x1`/`y1`，但座標常是粗定位；**真正的樁號、回堵長度、A 到 B 路段在 `comment`**，所以仍用規則／OpenAI 剖析 comment，再重調 bbox。

沒有 key 時走規則解析。也可以繼續丟逐字稿 `.txt`。

## 快速開始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.env.example config.env   # 已有空白 config.env 可直接改

# 線上 API（每次約最近 1000 筆）
python -m radio_parser.cli --from-api --no-llm

# 離線樣本（本機驗證用）
python -m radio_parser.cli --from-pbs-json samples/pbs/opendata_sample.json --no-llm
```

JSON 端點（資料集「資料資源下載網址」）：

`https://rtr.pbs.gov.tw/NMP103_PbsWS/resources/roadData/opendata`

區域代碼：`A` 全 / `N` 北 / `M` 中 / `S` 南 / `E` 東。

輸出：

- `output/incidents.json`：給地圖用的事件列表（bbox 方形區塊）
- `output/incidents.geojson`：GeoJSON Polygon

看地圖（需本機 HTTP，避免 `file://` 讀不到 JSON）：

```bash
python -m http.server 8080 --directory web
cp output/incidents.json web/incidents.json
# 瀏覽器開 http://127.0.0.1:8080
```

測試：

```bash
pytest
```

## 設定（config.env）

從 `config.env.example` 複製。真實金鑰不要 commit（`config.env` 已在 `.gitignore`）。

| 變數 | 說明 |
| --- | --- |
| `OPENAI_API_KEY` | 填了才會用 LLM 剖析 comment／逐字稿 |
| `OPENAI_MODEL` | 預設 `gpt-4o-mini` |
| `OPENAI_BASE_URL` | 預設官方 API；相容 proxy 可改 |
| `PBS_API_URL` | 警廣 JSON。可用 `--pbs-url` 覆蓋 |
| `PBS_TIMEOUT_SEC` | 預設 30 |
| `GEOCODER_PROVIDER` | 目前只有 `local`（內建國道公里／交流道／縣市） |
| `OUTPUT_DIR` | 預設 `output` |
| `DEFAULT_BBOX_HALF_DEG` | 方形半邊長度（度）。`0.008` 大約 ±800–900 公尺 |

`GOOGLE_MAPS_API_KEY` / Nominatim 也在 example 裡預留，之後要接線上 geocoding 再用。

## JSON 格式

```json
{
  "source": "pbs_opendata",
  "parser": "pbs+heuristic",
  "generated_at": "2026-09-28T03:00:00+00:00",
  "pbs_url": "https://rtr.pbs.gov.tw/NMP103_PbsWS/resources/roadData/opendata",
  "incidents": [
    {
      "id": "N20260928001",
      "uid": "N20260928001",
      "type": "accident",
      "title": "交通事故｜國道1號 南下 25.3k",
      "summary": "兩輛小客車追撞，內線車道占用",
      "severity": "medium",
      "location_text": "國道1號 南下 25.3k 台北交流道",
      "bbox": {
        "min_lat": 25.06,
        "min_lng": 121.50,
        "max_lat": 25.08,
        "max_lng": 121.56
      },
      "original_bbox": {
        "min_lat": 25.068,
        "min_lng": 121.540,
        "max_lat": 25.084,
        "max_lng": 121.556
      },
      "bbox_source": "comment_span",
      "center": { "lat": 25.07, "lng": 121.53 },
      "road": "國道1號",
      "direction": "南下",
      "kilometer": 25.3,
      "span_km": 3.0,
      "confidence": 0.55
    }
  ]
}
```

`type`：`accident` | `congestion` | `breakdown` | `construction` | `weather` | `other`

`bbox_source`：`api`（只用 x1/y1）｜`comment` / `comment_span`（依 comment 重調）｜`hybrid`｜`gazetteer`

地圖上實線是重調後區塊，虛線是 API 原始點。

## 流程

1. 拉 PBS JSON（或讀已存檔／逐字稿）
2. 結構化欄位當種子：`UID`、`road`、`direction`、`roadtype`、`x1`/`y1`、`region`
3. 若有 `OPENAI_API_KEY`：把每筆 comment 交給模型抽樁號／交流道／回堵長度；否則用中文規則
4. 用 comment 算出真正中心與路段，重寫 bbox（有回堵就拉長方形）
5. 寫 JSON / GeoJSON；`web/index.html` 用 Leaflet 畫矩形

國道座標是概略內插，不是公路總局精準樁號，地圖上先用來標示「這一帶」。

## CLI

```bash
python -m radio_parser.cli --from-api
python -m radio_parser.cli --from-api --no-llm -o output/incidents.json
python -m radio_parser.cli --from-pbs-json samples/pbs/opendata_sample.json --no-llm
python -m radio_parser.cli path/to/transcript.txt -o output/incidents.json
python -m radio_parser.cli --no-llm samples/transcripts/sample_police_radio.txt
cat transcript.txt | python -m radio_parser.cli --no-llm
```
