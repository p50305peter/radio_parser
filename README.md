# radio_parser

把台灣警廣（警察廣播電台）路況廣播解析成地圖可用的 JSON：每筆事件含**方形區塊座標**，以及這區發生了什麼（交通事故、回堵／塞車、拋錨、施工等）。

目前還沒有正式的廣播 API，先吃**逐字稿文字檔**。OpenAI API 已預留在 `config.env`，沒有 key 時會走規則解析。

## 快速開始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.env.example config.env   # 已有空白 config.env 可直接改
python -m radio_parser.cli samples/transcripts/sample_police_radio.txt
```

輸出：

- `output/incidents.json`：給地圖用的事件列表（bbox 方形區塊）
- `output/incidents.geojson`：GeoJSON Polygon，方便丟進 GIS / Leaflet

看地圖（需本機 HTTP，避免 `file://` 讀不到 JSON）：

```bash
python -m http.server 8080 --directory web
# 另開一個 terminal，把最新 JSON 拷到 web/
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
| `OPENAI_API_KEY` | 預留。填了才會用 LLM 判斷事件類型與地點文字 |
| `OPENAI_MODEL` | 預設 `gpt-4o-mini` |
| `OPENAI_BASE_URL` | 預設官方 API；相容 proxy 可改 |
| `GEOCODER_PROVIDER` | 目前只有 `local`（內建國道公里／交流道／縣市） |
| `OUTPUT_DIR` | 預設 `output` |
| `DEFAULT_BBOX_HALF_DEG` | 方形半邊長度（度）。`0.008` 大約 ±800–900 公尺 |

`GOOGLE_MAPS_API_KEY` / Nominatim 也在 example 裡預留，之後要接線上 geocoding 再用。

## JSON 格式

```json
{
  "source": "police_radio",
  "parser": "heuristic",
  "generated_at": "2026-09-28T03:00:00+00:00",
  "incidents": [
    {
      "id": "a1b2c3d4e5f6",
      "type": "accident",
      "title": "交通事故｜國道1號 南下 25.3k",
      "summary": "兩輛小客車追撞，內線車道占用",
      "severity": "medium",
      "location_text": "國道1號 南下 25.3k 台北交流道",
      "bbox": {
        "min_lat": 25.06,
        "min_lng": 121.53,
        "max_lat": 25.08,
        "max_lng": 121.55
      },
      "center": { "lat": 25.07, "lng": 121.54 },
      "road": "國道1號",
      "direction": "南下",
      "kilometer": 25.3,
      "confidence": 0.55
    }
  ]
}
```

`type`：`accident` | `congestion` | `breakdown` | `construction` | `weather` | `other`

## 流程

1. 讀取警廣逐字稿
2. 若有 `OPENAI_API_KEY`：請模型抽出事件；失敗或沒 key 則用中文規則（事故／回堵／公里數／交流道）
3. 用地名表把「國道＋公里／交流道／縣市」轉成中心點，再擴成方形 bbox
4. 寫 JSON / GeoJSON，前端 `web/index.html` 用 Leaflet 畫矩形

國道座標是概略內插，不是公路總局精準樁號，地圖上先用來標示「這一帶」。

## CLI

```bash
python -m radio_parser.cli path/to/transcript.txt -o output/incidents.json
python -m radio_parser.cli --no-llm samples/transcripts/sample_police_radio.txt
cat transcript.txt | python -m radio_parser.cli --no-llm
```
