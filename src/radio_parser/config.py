from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATHS = (
    PROJECT_ROOT / "config.env",
    PROJECT_ROOT / ".env",
)


def load_config_files() -> None:
    for path in CONFIG_PATHS:
        if path.exists():
            load_dotenv(path, override=False)


load_config_files()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    geocoder_provider: str
    output_dir: Path
    default_bbox_half_deg: float

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key.strip())

    @classmethod
    def from_env(cls) -> Settings:
        load_config_files()
        output = os.getenv("OUTPUT_DIR", "output")
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
            geocoder_provider=os.getenv("GEOCODER_PROVIDER", "local").strip() or "local",
            output_dir=output_path,
            default_bbox_half_deg=float(os.getenv("DEFAULT_BBOX_HALF_DEG", "0.008")),
        )


def get_settings() -> Settings:
    return Settings.from_env()
