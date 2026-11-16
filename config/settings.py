"""
Central application configuration loaded from environment variables / .env file.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    database_url: str = Field(
        default="postgresql://dtuser:dtpassword@localhost:5432/decisiontrace",
        alias="DATABASE_URL",
    )

    # ------------------------------------------------------------------ #
    # Prefect
    # ------------------------------------------------------------------ #
    prefect_api_url: str = Field(
        default="http://localhost:4200/api",
        alias="PREFECT_API_URL",
    )

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # ------------------------------------------------------------------ #
    # Data paths
    # ------------------------------------------------------------------ #
    raw_data_dir: Path = Field(default=Path("data/raw"), alias="RAW_DATA_DIR")
    validated_data_dir: Path = Field(
        default=Path("data/validated"), alias="VALIDATED_DATA_DIR"
    )
    simulated_data_dir: Path = Field(
        default=Path("data/simulated"), alias="SIMULATED_DATA_DIR"
    )

    # ------------------------------------------------------------------ #
    # Data quality thresholds
    # ------------------------------------------------------------------ #
    freshness_threshold_hours: int = Field(
        default=24, alias="FRESHNESS_THRESHOLD_HOURS"
    )

    # Minimum acceptable reliability score (0–100) before a warning is raised
    min_reliability_score: float = Field(default=80.0)

    # Maximum allowed duplicate rate (fraction 0–1)
    max_duplicate_rate: float = Field(default=0.01)


settings = Settings()
