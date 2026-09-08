"""Unit Tests for Data Contract & Quality Validation.

Tests schema contract enforcement, missing column detection, nullability, uniqueness,
allowed enum sets, numeric range bounds, and regex constraints.
"""

import pandas as pd
from src.pipeline.config import ValidationConfig
from src.pipeline.validate import (
    validate_allowed_values,
    validate_dataframe,
    validate_nullability,
    validate_numeric_ranges,
    validate_regex_patterns,
    validate_required_columns,
    validate_uniqueness,
)


class TestValidationRules:
    """Test individual validation rules."""

    def test_validate_required_columns_success(self, sample_valid_raw_df):
        is_valid, issues = validate_required_columns(
            sample_valid_raw_df, ["transaction_id", "customer_id", "amount"]
        )
        assert is_valid is True
        assert len(issues) == 0

    def test_validate_required_columns_missing(self, sample_valid_raw_df):
        is_valid, issues = validate_required_columns(
            sample_valid_raw_df, ["transaction_id", "non_existent_column"]
        )
        assert is_valid is False
        assert len(issues) == 1
        assert "non_existent_column" in issues[0].message

    def test_validate_nullability_failure(self, sample_schema_contracts):
        df_with_null = pd.DataFrame(
            [{"transaction_id": "TXN-10001", "customer_id": None, "amount": 100.0}]
        )
        is_valid, issues = validate_nullability(
            df_with_null, sample_schema_contracts["fields"]
        )
        assert is_valid is False
        assert any(i.column == "customer_id" for i in issues)

    def test_validate_uniqueness_failure(self, sample_schema_contracts):
        df_duplicates = pd.DataFrame(
            [
                {"transaction_id": "TXN-10001", "customer_id": "CUST-101"},
                {"transaction_id": "TXN-10001", "customer_id": "CUST-102"},
            ]
        )
        is_valid, issues = validate_uniqueness(
            df_duplicates, sample_schema_contracts["fields"]
        )
        assert is_valid is False
        assert any(i.column == "transaction_id" for i in issues)

    def test_validate_allowed_values_failure(self, sample_schema_contracts):
        df_bad_currency = pd.DataFrame(
            [
                {"currency": "BITCOIN"},
                {"currency": "USD"},
            ]
        )
        is_valid, issues = validate_allowed_values(
            df_bad_currency, sample_schema_contracts["fields"]
        )
        assert is_valid is False
        assert any(i.column == "currency" for i in issues)

    def test_validate_numeric_ranges_violation(self, sample_schema_contracts):
        df_invalid_amounts = pd.DataFrame(
            [
                {"amount": -50.0},  # below min 0.01
                {"amount": 5000000.0},  # above max 100000.0
            ]
        )
        is_valid, issues = validate_numeric_ranges(
            df_invalid_amounts, sample_schema_contracts["fields"]
        )
        assert is_valid is False
        assert len(issues) == 2

    def test_validate_regex_patterns(self, sample_schema_contracts):
        df_regex = pd.DataFrame(
            [
                {"transaction_id": "TXN-12345", "customer_id": "INVALID-CUST"},
            ]
        )
        is_valid, issues = validate_regex_patterns(
            df_regex, sample_schema_contracts["fields"]
        )
        assert is_valid is False
        assert any(i.column == "customer_id" for i in issues)


class TestFullContractValidation:
    """Test end-to-end data contract validation reporting."""

    def test_full_contract_valid_dataframe(
        self, sample_valid_raw_df, sample_schema_contracts
    ):
        config = ValidationConfig(strict_mode=True, max_error_percentage=0.0)
        report = validate_dataframe(
            sample_valid_raw_df, sample_schema_contracts, config
        )
        assert report.is_valid is True
        assert report.error_count() == 0

    def test_full_contract_empty_dataframe(self, sample_schema_contracts):
        empty_df = pd.DataFrame()
        report = validate_dataframe(empty_df, sample_schema_contracts)
        assert report.is_valid is False
        assert report.error_count() == 1

    def test_full_contract_relaxed_threshold(self, sample_schema_contracts):
        # 10 rows, 1 row has invalid enum
        data = [
            {
                "transaction_id": f"TXN-{10000+i}",
                "customer_id": f"CUST-{100+i}",
                "amount": 100.0,
                "currency": "USD",
                "timestamp": "2026-03-01",
                "status": "COMPLETED",
            }
            for i in range(10)
        ]
        data[0]["currency"] = "INVALID"
        df = pd.DataFrame(data)

        # In strict mode, should fail
        strict_report = validate_dataframe(
            df, sample_schema_contracts, ValidationConfig(strict_mode=True)
        )
        assert strict_report.is_valid is False

        # In relaxed mode (allow up to 10% errors), should pass
        relaxed_report = validate_dataframe(
            df,
            sample_schema_contracts,
            ValidationConfig(strict_mode=False, max_error_percentage=10.0),
        )
        assert relaxed_report.is_valid is True
