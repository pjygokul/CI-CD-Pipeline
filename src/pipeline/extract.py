"""Data Extraction Module.

Handles extracting raw data from various source types (local filesystem, S3 cloud storage, REST APIs)
with support for dependency injection to enable robust mock testing.
"""

from abc import ABC, abstractmethod
import json
import logging
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
from src.pipeline.config import ExtractConfig

logger = logging.getLogger(__name__)


class StorageClientInterface(ABC):
    """Abstract interface for storage systems (S3, GCS, Blob, Local)."""

    @abstractmethod
    def read_file(self, uri: str) -> str:
        """Read content from storage URI as string."""
        pass

    @abstractmethod
    def write_file(self, uri: str, data: str) -> bool:
        """Write content to storage URI."""
        pass


class LocalStorageClient(StorageClientInterface):
    """Local filesystem storage implementation."""

    def read_file(self, uri: str) -> str:
        path = Path(uri)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {uri}")
        return path.read_text(encoding="utf-8")

    def write_file(self, uri: str, data: str) -> bool:
        path = Path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        return True


class MockS3Client(StorageClientInterface):
    """Mock S3 client for testing and simulation."""

    def __init__(self, in_memory_store: Optional[Dict[str, str]] = None):
        self._store: Dict[str, str] = in_memory_store or {}

    def read_file(self, uri: str) -> str:
        if uri not in self._store:
            raise FileNotFoundError(f"S3 Object not found: {uri}")
        return self._store[uri]

    def write_file(self, uri: str, data: str) -> bool:
        self._store[uri] = data
        return True


def parse_raw_records_to_df(raw_json_str: str) -> pd.DataFrame:
    """Parse JSON string (either array of records or newline-delimited JSON) into a DataFrame."""
    try:
        data = json.loads(raw_json_str)
        if isinstance(data, list):
            return pd.DataFrame(data)
        elif isinstance(data, dict):
            # If wrapped in a data key or single record
            if "records" in data:
                return pd.DataFrame(data["records"])
            return pd.DataFrame([data])
        else:
            raise ValueError("Unsupported JSON payload format")
    except json.JSONDecodeError:
        # Try lines format
        lines = [
            json.loads(line)
            for line in raw_json_str.strip().splitlines()
            if line.strip()
        ]
        return pd.DataFrame(lines)


def extract_data(
    config: ExtractConfig,
    storage_client: Optional[StorageClientInterface] = None,
) -> pd.DataFrame:
    """Extract raw transaction data according to ExtractConfig."""
    logger.info(
        "Starting data extraction from source_type=%s, path=%s",
        config.source_type,
        config.raw_data_path,
    )

    if storage_client is None:
        if config.source_type == "local":
            storage_client = LocalStorageClient()
        elif config.source_type == "s3":
            # In production this would initialize boto3; in our framework default to mock or local
            storage_client = LocalStorageClient()
        else:
            storage_client = LocalStorageClient()

    raw_content = storage_client.read_file(config.raw_data_path)
    df = parse_raw_records_to_df(raw_content)
    logger.info("Successfully extracted %d records", len(df))
    return df
