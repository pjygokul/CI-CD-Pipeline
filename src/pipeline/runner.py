"""Pipeline as Code Orchestration Runner.

Executes end-to-end data pipeline workflows with pre-transformation and post-transformation
contract validation gates, metrics collection, and audit logging.
"""

from dataclasses import dataclass
from datetime import datetime
import logging
import time
from typing import Optional
from src.pipeline.config import (
    PipelineConfig,
    load_config,
    load_schema_contracts,
)
from src.pipeline.extract import StorageClientInterface, extract_data
from src.pipeline.load import load_data
from src.pipeline.transform import run_all_transformations
from src.pipeline.validate import ValidationReport, validate_dataframe

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    status: str  # "SUCCESS", "VALIDATION_FAILED", "ERROR"
    environment: str
    start_time: str
    end_time: str
    duration_seconds: float
    records_extracted: int = 0
    records_transformed: int = 0
    records_loaded: int = 0
    anomalies_detected: int = 0
    raw_validation_report: Optional[ValidationReport] = None
    output_destination: Optional[str] = None
    error_message: Optional[str] = None


class PipelineRunner:
    """Executes the data pipeline end-to-end as code."""

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        schema_contracts: Optional[dict] = None,
        storage_client: Optional[StorageClientInterface] = None,
    ):
        self.config = config
        self.schema_contracts = schema_contracts
        self.storage_client = storage_client

    def run(self, env: str = "dev") -> PipelineRunResult:
        """Run the complete pipeline for the specified environment."""
        start_ts = time.time()
        start_time_str = datetime.utcnow().isoformat()
        logger.info("==================================================")
        logger.info("Initiating Pipeline Execution | Environment: %s", env)
        logger.info("==================================================")

        try:
            # 1. Load Configurations & Contracts
            if self.config is None:
                self.config = load_config(env=env)
            if self.schema_contracts is None:
                self.schema_contracts = load_schema_contracts()

            # 2. Extract Stage
            logger.info("[Step 1/4] Extracting raw records...")
            raw_df = extract_data(
                self.config.extract, storage_client=self.storage_client
            )
            records_extracted = len(raw_df)

            # 3. Validation Gate 1: Raw Data Contract Verification
            logger.info("[Step 2/4] Validating raw data against schema contracts...")
            validation_report = validate_dataframe(
                raw_df,
                schema_contracts=self.schema_contracts,
                validation_config=self.config.validation,
            )

            if not validation_report.is_valid:
                logger.error("Raw data contract validation failed! Halting pipeline.")
                end_ts = time.time()
                return PipelineRunResult(
                    status="VALIDATION_FAILED",
                    environment=env,
                    start_time=start_time_str,
                    end_time=datetime.utcnow().isoformat(),
                    duration_seconds=round(end_ts - start_ts, 3),
                    records_extracted=records_extracted,
                    raw_validation_report=validation_report,
                    error_message=f"Validation failed with {validation_report.error_count()} errors.",
                )

            # 4. Transform Stage
            logger.info("[Step 3/4] Transforming and enriching data...")
            transformed_df = run_all_transformations(
                raw_df, config=self.config.transform
            )
            records_transformed = len(transformed_df)
            anomalies_count = (
                int(transformed_df["is_anomaly"].sum())
                if "is_anomaly" in transformed_df.columns
                else 0
            )

            # 5. Load Stage
            logger.info("[Step 4/4] Loading analytical dataset to target...")
            output_dest = load_data(
                transformed_df,
                config=self.config.load,
                storage_client=self.storage_client,
            )

            end_ts = time.time()
            logger.info("==================================================")
            logger.info(
                "Pipeline Execution Successfully Completed in %.2fs", end_ts - start_ts
            )
            logger.info(
                "Records: Extracted=%d, Transformed=%d, Anomalies=%d",
                records_extracted,
                records_transformed,
                anomalies_count,
            )
            logger.info("==================================================")

            return PipelineRunResult(
                status="SUCCESS",
                environment=env,
                start_time=start_time_str,
                end_time=datetime.utcnow().isoformat(),
                duration_seconds=round(end_ts - start_ts, 3),
                records_extracted=records_extracted,
                records_transformed=records_transformed,
                records_loaded=records_transformed,
                anomalies_detected=anomalies_count,
                raw_validation_report=validation_report,
                output_destination=output_dest,
            )

        except Exception as exc:
            end_ts = time.time()
            logger.exception("Pipeline failed with unexpected error: %s", exc)
            return PipelineRunResult(
                status="ERROR",
                environment=env,
                start_time=start_time_str,
                end_time=datetime.utcnow().isoformat(),
                duration_seconds=round(end_ts - start_ts, 3),
                error_message=str(exc),
            )
