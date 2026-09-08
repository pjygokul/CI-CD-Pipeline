"""Pytest Fixtures for Data Engineering Test Suite.

Provides synthetic data, mock storage clients, and standard schema contracts for automated testing.
"""

import pytest
import pandas as pd
from src.pipeline.config import LoyaltyTiers, TransformConfig
from src.pipeline.extract import MockS3Client


@pytest.fixture
def sample_valid_raw_df() -> pd.DataFrame:
    """Fixture providing clean, valid raw transaction data."""
    return pd.DataFrame(
        [
            {
                "transaction_id": "TXN-10001",
                "customer_id": "CUST-101",
                "amount": 100.0,
                "currency": "USD",
                "timestamp": "2026-03-01T10:00:00Z",
                "status": "COMPLETED",
                "item_count": 2,
            },
            {
                "transaction_id": "TXN-10002",
                "customer_id": "CUST-102",
                "amount": 200.0,
                "currency": "EUR",
                "timestamp": "2026-03-01T12:30:00Z",
                "status": "COMPLETED",
                "item_count": 1,
            },
            {
                "transaction_id": "TXN-10003",
                "customer_id": "CUST-101",
                "amount": 2500.0,
                "currency": "USD",
                "timestamp": "2026-03-02T15:00:00Z",
                "status": "COMPLETED",
                "item_count": 4,
            },
        ]
    )


@pytest.fixture
def sample_multi_currency_df() -> pd.DataFrame:
    """Fixture providing transactions across various currencies."""
    return pd.DataFrame(
        [
            {"transaction_id": "TXN-20001", "currency": "USD", "amount": 100.0},
            {"transaction_id": "TXN-20002", "currency": "EUR", "amount": 100.0},
            {"transaction_id": "TXN-20003", "currency": "GBP", "amount": 100.0},
            {"transaction_id": "TXN-20004", "currency": "INR", "amount": 10000.0},
            {
                "transaction_id": "TXN-20005",
                "currency": "XYZ",
                "amount": 50.0,
            },  # Unknown currency fallback
        ]
    )


@pytest.fixture
def sample_schema_contracts() -> dict:
    """Fixture providing schema contracts for testing validation rules."""
    return {
        "version": "1.0.0",
        "fields": {
            "transaction_id": {
                "type": "string",
                "nullable": False,
                "unique": True,
                "regex": r"^TXN-[0-9]{5,}$",
            },
            "customer_id": {
                "type": "string",
                "nullable": False,
                "unique": False,
                "regex": r"^CUST-[0-9]{3,}$",
            },
            "amount": {
                "type": "float",
                "nullable": False,
                "min_value": 0.01,
                "max_value": 100000.0,
            },
            "currency": {
                "type": "string",
                "nullable": False,
                "allowed_values": ["USD", "EUR", "GBP", "CAD", "INR"],
            },
            "timestamp": {
                "type": "datetime",
                "nullable": False,
            },
            "status": {
                "type": "string",
                "nullable": False,
                "allowed_values": ["COMPLETED", "PENDING", "FAILED", "REFUNDED"],
            },
        },
    }


@pytest.fixture
def sample_transform_config() -> TransformConfig:
    """Fixture providing transformation parameters."""
    return TransformConfig(
        base_currency="USD",
        fx_rates={"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CAD": 0.74, "INR": 0.012},
        anomaly_std_threshold=2.5,
        loyalty_tiers=LoyaltyTiers(bronze_max=500, silver_max=2000, gold_min=2000),
    )


@pytest.fixture
def mock_s3_storage() -> MockS3Client:
    """Fixture providing in-memory mock S3 client preloaded with test payload."""
    test_json = """[
        {"transaction_id": "TXN-90001", "customer_id": "CUST-901", "amount": 500.0,
         "currency": "USD", "timestamp": "2026-03-01T08:00:00Z", "status": "COMPLETED"},
        {"transaction_id": "TXN-90002", "customer_id": "CUST-902", "amount": 750.0,
         "currency": "EUR", "timestamp": "2026-03-01T09:30:00Z", "status": "COMPLETED"}
    ]"""
    return MockS3Client(
        in_memory_store={"s3://mock-bucket/transactions.json": test_json}
    )
