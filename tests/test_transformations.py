"""Unit Tests for Data Transformations.

Tests pure transformation functions across edge cases, data types, business logic,
and outlier detection algorithms.
"""

import pandas as pd
from src.pipeline.config import LoyaltyTiers
from src.pipeline.transform import (
    assign_loyalty_tiers,
    clean_and_cast_types,
    compute_customer_lifetime_metrics,
    deduplicate_records,
    detect_anomalies_zscore,
    extract_temporal_features,
    normalize_currencies,
    run_all_transformations,
)


class TestDataCleaningAndCasting:
    """Test string standardization and type casting."""

    def test_clean_and_cast_valid_data(self):
        df = pd.DataFrame(
            [
                {
                    "transaction_id": " txn-101 ",
                    "customer_id": "cust-202",
                    "amount": "150.75",
                    "currency": " usd ",
                    "timestamp": "2026-03-01 10:00:00",
                    "status": "completed",
                }
            ]
        )
        cleaned = clean_and_cast_types(df)
        assert cleaned["transaction_id"].iloc[0] == "TXN-101"
        assert cleaned["customer_id"].iloc[0] == "CUST-202"
        assert cleaned["currency"].iloc[0] == "USD"
        assert cleaned["status"].iloc[0] == "COMPLETED"
        assert cleaned["amount"].iloc[0] == 150.75
        assert pd.api.types.is_datetime64_any_dtype(cleaned["timestamp"])

    def test_clean_and_cast_with_invalid_amounts(self):
        df = pd.DataFrame(
            [{"transaction_id": "TXN-1", "amount": "invalid_num", "item_count": "5"}]
        )
        cleaned = clean_and_cast_types(df)
        assert pd.isna(cleaned["amount"].iloc[0])
        assert cleaned["item_count"].iloc[0] == 5


class TestCurrencyNormalization:
    """Test multi-currency exchange rate conversions."""

    def test_normalize_known_currencies(
        self, sample_multi_currency_df, sample_transform_config
    ):
        normalized = normalize_currencies(
            sample_multi_currency_df,
            base_currency=sample_transform_config.base_currency,
            fx_rates=sample_transform_config.fx_rates,
        )
        assert "amount_normalized_usd" in normalized.columns
        # USD: 100 * 1.0 = 100.0
        assert (
            normalized.loc[
                normalized["currency"] == "USD", "amount_normalized_usd"
            ].iloc[0]
            == 100.0
        )
        # EUR: 100 * 1.08 = 108.0
        assert (
            normalized.loc[
                normalized["currency"] == "EUR", "amount_normalized_usd"
            ].iloc[0]
            == 108.0
        )
        # GBP: 100 * 1.27 = 127.0
        assert (
            normalized.loc[
                normalized["currency"] == "GBP", "amount_normalized_usd"
            ].iloc[0]
            == 127.0
        )
        # INR: 10000 * 0.012 = 120.0
        assert (
            normalized.loc[
                normalized["currency"] == "INR", "amount_normalized_usd"
            ].iloc[0]
            == 120.0
        )

    def test_normalize_fallback_unlisted_currency(
        self, sample_multi_currency_df, sample_transform_config
    ):
        normalized = normalize_currencies(
            sample_multi_currency_df,
            base_currency="USD",
            fx_rates=sample_transform_config.fx_rates,
        )
        # XYZ fallback fx_rate is 1.0 -> 50.0
        assert (
            normalized.loc[
                normalized["currency"] == "XYZ", "amount_normalized_usd"
            ].iloc[0]
            == 50.0
        )


class TestLoyaltyTierAssignment:
    """Test business logic tier categorization based on thresholds."""

    def test_loyalty_tier_boundaries(self):
        tiers = LoyaltyTiers(bronze_max=500.0, silver_max=2000.0, gold_min=2000.0)
        df = pd.DataFrame(
            [
                {"transaction_id": "T1", "amount_normalized_usd": 150.0},
                {"transaction_id": "T2", "amount_normalized_usd": 500.0},
                {"transaction_id": "T3", "amount_normalized_usd": 500.01},
                {"transaction_id": "T4", "amount_normalized_usd": 1999.99},
                {"transaction_id": "T5", "amount_normalized_usd": 2000.0},
                {"transaction_id": "T6", "amount_normalized_usd": 50000.0},
            ]
        )
        res = assign_loyalty_tiers(df, tiers=tiers)
        tier_list = res["loyalty_tier"].tolist()
        assert tier_list == ["BRONZE", "BRONZE", "SILVER", "SILVER", "GOLD", "GOLD"]


class TestTemporalFeatureExtraction:
    """Test date/time decomposition for partitioning and analytics."""

    def test_temporal_features_extraction(self):
        df = pd.DataFrame(
            [
                {"timestamp": pd.to_datetime("2026-03-01 14:30:00")},  # Sunday
                {"timestamp": pd.to_datetime("2026-03-02 09:15:00")},  # Monday
            ]
        )
        res = extract_temporal_features(df)
        assert res["transaction_year"].tolist() == [2026, 2026]
        assert res["transaction_month"].tolist() == [3, 3]
        assert res["transaction_day"].tolist() == [1, 2]
        assert res["transaction_hour"].tolist() == [14, 9]
        assert res["day_of_week"].tolist() == ["Sunday", "Monday"]
        assert res["is_weekend"].tolist() == [True, False]


class TestCustomerMetricsAggregation:
    """Test customer lifetime aggregations and analytics metrics."""

    def test_customer_lifetime_metrics(self):
        df = pd.DataFrame(
            [
                {
                    "transaction_id": "T1",
                    "customer_id": "C1",
                    "amount_normalized_usd": 100.0,
                },
                {
                    "transaction_id": "T2",
                    "customer_id": "C1",
                    "amount_normalized_usd": 300.0,
                },
                {
                    "transaction_id": "T3",
                    "customer_id": "C2",
                    "amount_normalized_usd": 500.0,
                },
            ]
        )
        res = compute_customer_lifetime_metrics(df)
        c1_row = res[res["customer_id"] == "C1"].iloc[0]
        assert c1_row["cust_total_orders"] == 2
        assert c1_row["cust_total_spend_usd"] == 400.0
        assert c1_row["cust_avg_order_value_usd"] == 200.0

        c2_row = res[res["customer_id"] == "C2"].iloc[0]
        assert c2_row["cust_total_orders"] == 1
        assert c2_row["cust_total_spend_usd"] == 500.0
        assert c2_row["cust_avg_order_value_usd"] == 500.0


class TestAnomalyDetection:
    """Test statistical Z-score outlier detection."""

    def test_detect_anomalies_outlier_flagged(self):
        # 10 standard items and 1 extreme outlier
        amounts = [100.0] * 15 + [50000.0]
        df = pd.DataFrame({"amount_normalized_usd": amounts})
        res = detect_anomalies_zscore(df, column="amount_normalized_usd", threshold=3.0)
        assert bool(res["is_anomaly"].iloc[-1]) is True
        assert bool(res["is_anomaly"].iloc[0]) is False

    def test_detect_anomalies_zero_variance(self):
        df = pd.DataFrame({"amount_normalized_usd": [100.0, 100.0, 100.0]})
        res = detect_anomalies_zscore(df, column="amount_normalized_usd", threshold=3.0)
        assert res["is_anomaly"].sum() == 0


class TestDeduplication:
    """Test deduplication logic based on primary keys and latest timestamp."""

    def test_deduplicate_keeps_latest(self):
        df = pd.DataFrame(
            [
                {
                    "transaction_id": "TXN-1",
                    "timestamp": "2026-03-01 10:00:00",
                    "amount": 10.0,
                },
                {
                    "transaction_id": "TXN-1",
                    "timestamp": "2026-03-01 12:00:00",
                    "amount": 20.0,
                },
                {
                    "transaction_id": "TXN-2",
                    "timestamp": "2026-03-01 08:00:00",
                    "amount": 50.0,
                },
            ]
        )
        res = deduplicate_records(df, subset=["transaction_id"], order_by="timestamp")
        assert len(res) == 2
        txn1 = res[res["transaction_id"] == "TXN-1"].iloc[0]
        assert txn1["amount"] == 20.0


class TestEndToEndTransformationSequence:
    """Test full transformation execution pipeline."""

    def test_run_all_transformations(
        self, sample_valid_raw_df, sample_transform_config
    ):
        result = run_all_transformations(sample_valid_raw_df, sample_transform_config)
        expected_cols = [
            "transaction_id",
            "customer_id",
            "amount",
            "currency",
            "amount_normalized_usd",
            "transaction_year",
            "transaction_month",
            "loyalty_tier",
            "cust_total_orders",
            "cust_total_spend_usd",
            "is_anomaly",
        ]
        for col in expected_cols:
            assert col in result.columns
        assert len(result) == len(sample_valid_raw_df)
