from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from radio_parser.config import PROJECT_ROOT, get_settings
from radio_parser.pipeline import parse_pbs_api, parse_transcript


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse 警廣 transcripts or PBS open data into map bounding-box JSON."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Transcript .txt path. Omit with --from-api, or read stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write incidents JSON here. Default: OUTPUT_DIR/incidents.json",
    )
    parser.add_argument(
        "--geojson",
        help="Also write a GeoJSON FeatureCollection for map layers.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Force heuristic parser even if OPENAI_API_KEY is set.",
    )
    parser.add_argument(
        "--from-api",
        action="store_true",
        help="Fetch 警廣即時路況 JSON（data.gov.tw/dataset/15221）then parse comments.",
    )
    parser.add_argument(
        "--from-pbs-json",
        help="Parse a saved PBS opendata JSON file instead of fetching.",
    )
    parser.add_argument(
        "--pbs-url",
        help="Override PBS_API_URL for --from-api.",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    use_llm = False if args.no_llm else None

    if args.from_api or args.from_pbs_json:
        payload = None
        url = args.pbs_url
        if args.from_pbs_json:
            path = Path(args.from_pbs_json)
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            payload = json.loads(path.read_text(encoding="utf-8"))
            url = url or str(path)
        report = parse_pbs_api(
            settings=settings,
            url=url,
            payload=payload,
            use_llm=use_llm,
        )
    else:
        if args.input:
            path = Path(args.input)
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            text = path.read_text(encoding="utf-8")
            transcript_path = str(path)
        else:
            text = sys.stdin.read()
            transcript_path = None
        report = parse_transcript(
            text,
            settings=settings,
            transcript_path=transcript_path,
            use_llm=use_llm,
        )

    out_path = Path(args.output) if args.output else settings.output_dir / "incidents.json"
    if not out_path.is_absolute():
        out_path = PROJECT_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload_text = json.dumps(report.model_dump(), ensure_ascii=False, indent=2) + "\n"
    out_path.write_text(payload_text, encoding="utf-8")

    if args.geojson:
        geojson_path = Path(args.geojson)
        if not geojson_path.is_absolute():
            geojson_path = PROJECT_ROOT / geojson_path
    else:
        geojson_path = out_path.with_suffix(".geojson")
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    geojson_path.write_text(
        json.dumps(report.to_geojson(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"parser={report.parser}")
    print(f"incidents={len(report.incidents)}")
    print(f"wrote {out_path}")
    print(f"wrote {geojson_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
