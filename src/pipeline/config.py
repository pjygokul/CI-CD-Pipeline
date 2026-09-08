"""Pipeline Configuration as Code.

Manages environment-specific configurations and schema contracts with Pydantic validation.
"""

from pathlib import Path
from typing import Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


class ExtractConfig(BaseModel):
    source_type: str = Field(
        default="local", description="Source type: local, s3, gcs, db"
    )
    raw_data_path: str = Field(..., description="Path to raw source data")
    s3_bucket: Optional[str] = None
    batch_size: int = Field(default=1000, ge=1)


class LoyaltyTiers(BaseModel):
    bronze_max: float = 500.0
    silver_max: float = 2000.0
    gold_min: float = 2000.0


class TransformConfig(BaseModel):
    base_currency: str = Field(default="USD")
    fx_rates: Dict[str, float] = Field(default_factory=lambda: {"USD": 1.0})
    anomaly_std_threshold: float = Field(default=3.0, gt=0)
    loyalty_tiers: LoyaltyTiers = Field(default_factory=LoyaltyTiers)


class ValidationConfig(BaseModel):
    strict_mode: bool = False
    max_error_percentage: float = Field(default=5.0, ge=0.0, le=100.0)
    required_columns: List[str] = Field(default_factory=list)


class LoadConfig(BaseModel):
    target_type: str = Field(default="parquet")
    output_path: str = Field(...)
    partition_cols: List[str] = Field(default_factory=list)


class PipelineConfig(BaseModel):
    environment: str = Field(..., description="dev, staging, or prod")
    app_name: str = Field(default="DataPipeline")
    version: str = Field(default="1.0.0")
    extract: ExtractConfig
    transform: TransformConfig
    validation: ValidationConfig
    load: LoadConfig


def load_config(env: str = "dev", config_dir: Optional[str] = None) -> PipelineConfig:
    """Load configuration YAML for the specified environment."""
    base_dir = (
        Path(config_dir)
        if config_dir
        else Path(__file__).resolve().parents[2] / "config"
    )
    config_file = base_dir / f"pipeline_config.{env}.yaml"

    if not config_file.exists():
        fallback = base_dir / "pipeline_config.dev.yaml"
        if fallback.exists():
            config_file = fallback
        else:
            raise FileNotFoundError(
                f"Configuration file not found for env '{env}' at {config_file}"
            )

    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return PipelineConfig(**data)


def load_schema_contracts(contract_path: Optional[str] = None) -> dict:
    """Load schema contract specifications from YAML."""
    if contract_path:
        path = Path(contract_path)
    else:
        path = Path(__file__).resolve().parents[2] / "config" / "schema_contracts.yaml"

    if not path.exists():
        raise FileNotFoundError(f"Schema contracts file not found at {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
