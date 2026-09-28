from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from radio_parser.config import PROJECT_ROOT, get_settings
from radio_parser.pipeline import parse_transcript


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse 警廣 transcripts into map bounding-box JSON."
    )
    parser.add_argument("input", nargs="?", help="Transcript .txt path. Omit to read stdin.")
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
    args = parser.parse_args(argv)
    settings = get_settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    if args.input:
        path = Path(args.input)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        text = path.read_text(encoding="utf-8")
        transcript_path = str(path)
    else:
        text = sys.stdin.read()
        transcript_path = None

    use_llm = False if args.no_llm else None
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
    payload = json.dumps(report.model_dump(), ensure_ascii=False, indent=2) + "\n"
    out_path.write_text(payload, encoding="utf-8")

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
