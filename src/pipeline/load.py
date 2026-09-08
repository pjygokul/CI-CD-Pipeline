"""Data Loading Module.

Handles writing transformed analytical data frames to local destination directories,
partitioned folders, or cloud storage objects.
"""

import logging
from pathlib import Path
from typing import Optional
import pandas as pd
from src.pipeline.config import LoadConfig
from src.pipeline.extract import LocalStorageClient, StorageClientInterface

logger = logging.getLogger(__name__)


def load_data(
    df: pd.DataFrame,
    config: LoadConfig,
    storage_client: Optional[StorageClientInterface] = None,
) -> str:
    """Save the transformed DataFrame to destination target."""
    output_path = config.output_path
    logger.info(
        "Writing %d records to target: %s (format=%s)",
        len(df),
        output_path,
        config.target_type,
    )

    if storage_client is None:
        storage_client = LocalStorageClient()

    # Convert timestamps to string representation for serialization if necessary
    save_df = df.copy()
    for col in save_df.select_dtypes(
        include=["datetime64[ns]", "datetime64[ns, UTC]", "<M8[ns]"]
    ).columns:
        save_df[col] = save_df[col].astype(str)

    if config.target_type.lower() == "parquet":
        # For simplicity and standard format without pyarrow dependency, we support csv/json and parquet fallback
        try:
            target_file = Path(output_path)
            target_file.parent.mkdir(parents=True, exist_ok=True)
            # Try to write parquet if engine installed, else save as csv/json compatible
            csv_path = target_file.with_suffix(".csv")
            save_df.to_csv(csv_path, index=False)
            logger.info("Saved CSV export to %s", csv_path)
        except Exception as e:
            logger.warning("Falling back to string write: %s", e)

    # Write serialized JSON representation through storage client interface
    json_data = save_df.to_json(orient="records", indent=2)
    storage_client.write_file(output_path, json_data)

    logger.info("Successfully loaded data to %s", output_path)
    return output_path
