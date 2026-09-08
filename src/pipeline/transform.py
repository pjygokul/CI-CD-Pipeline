"""Data Transformation Engine.

Contains pure, deterministic, and modular data transformations suitable for unit testing,
mock testing, and CI/CD validation.
"""

import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from src.pipeline.config import LoyaltyTiers, TransformConfig

logger = logging.getLogger(__name__)


def clean_and_cast_types(df: pd.DataFrame) -> pd.DataFrame:
    """Clean raw fields: strip whitespace, parse datetime, and cast numeric fields."""
    result_df = df.copy()

    # Clean string columns
    for col in ["transaction_id", "customer_id", "currency", "status"]:
        if col in result_df.columns:
            result_df[col] = result_df[col].astype(str).str.strip().str.upper()

    # Cast numeric
    if "amount" in result_df.columns:
        result_df["amount"] = pd.to_numeric(result_df["amount"], errors="coerce")

    if "item_count" in result_df.columns:
        result_df["item_count"] = (
            pd.to_numeric(result_df["item_count"], errors="coerce")
            .fillna(1)
            .astype(int)
        )

    # Parse timestamps
    if "timestamp" in result_df.columns:
        result_df["timestamp"] = pd.to_datetime(result_df["timestamp"], errors="coerce")

    return result_df


def normalize_currencies(
    df: pd.DataFrame,
    base_currency: str = "USD",
    fx_rates: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Convert transaction amounts to a standardized base currency using fx rates."""
    result_df = df.copy()
    rates = fx_rates or {
        "USD": 1.0,
        "EUR": 1.08,
        "GBP": 1.27,
        "CAD": 0.74,
        "INR": 0.012,
    }

    if "amount" not in result_df.columns or "currency" not in result_df.columns:
        return result_df

    # Map exchange rate; fallback to 1.0 if not found
    result_df["fx_rate_to_base"] = result_df["currency"].map(rates).fillna(1.0)
    result_df["amount_normalized_usd"] = (
        result_df["amount"] * result_df["fx_rate_to_base"]
    ).round(2)

    return result_df


def extract_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract partition and analytical date/time features."""
    result_df = df.copy()

    if "timestamp" in result_df.columns and pd.api.types.is_datetime64_any_dtype(
        result_df["timestamp"]
    ):
        result_df["transaction_year"] = (
            result_df["timestamp"].dt.year.fillna(1970).astype(int)
        )
        result_df["transaction_month"] = (
            result_df["timestamp"].dt.month.fillna(1).astype(int)
        )
        result_df["transaction_day"] = (
            result_df["timestamp"].dt.day.fillna(1).astype(int)
        )
        result_df["transaction_hour"] = (
            result_df["timestamp"].dt.hour.fillna(0).astype(int)
        )
        result_df["day_of_week"] = (
            result_df["timestamp"].dt.day_name().fillna("Unknown")
        )
        result_df["is_weekend"] = result_df["timestamp"].dt.dayofweek.isin([5, 6])
    else:
        result_df["transaction_year"] = 1970
        result_df["transaction_month"] = 1
        result_df["transaction_day"] = 1
        result_df["transaction_hour"] = 0
        result_df["day_of_week"] = "Unknown"
        result_df["is_weekend"] = False

    return result_df


def assign_loyalty_tiers(
    df: pd.DataFrame,
    tiers: Optional[LoyaltyTiers] = None,
) -> pd.DataFrame:
    """Classify transactions/customers into loyalty tiers based on normalized spend amount."""
    result_df = df.copy()
    tier_config = tiers or LoyaltyTiers()

    amount_col = (
        "amount_normalized_usd"
        if "amount_normalized_usd" in result_df.columns
        else "amount"
    )

    if amount_col not in result_df.columns:
        result_df["loyalty_tier"] = "BRONZE"
        return result_df

    conditions = [
        result_df[amount_col] >= tier_config.gold_min,
        (result_df[amount_col] > tier_config.bronze_max)
        & (result_df[amount_col] < tier_config.gold_min),
        result_df[amount_col] <= tier_config.bronze_max,
    ]
    choices = ["GOLD", "SILVER", "BRONZE"]

    result_df["loyalty_tier"] = np.select(conditions, choices, default="BRONZE")
    return result_df


def compute_customer_lifetime_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute aggregate metrics per customer (order count, total spend, average order value)."""
    result_df = df.copy()
    amount_col = (
        "amount_normalized_usd"
        if "amount_normalized_usd" in result_df.columns
        else "amount"
    )

    if "customer_id" not in result_df.columns or amount_col not in result_df.columns:
        return result_df

    # Groupby customer
    cust_stats = (
        result_df.groupby("customer_id")
        .agg(
            cust_total_orders=("transaction_id", "count"),
            cust_total_spend_usd=(amount_col, "sum"),
            cust_avg_order_value_usd=(amount_col, "mean"),
        )
        .reset_index()
    )

    cust_stats["cust_total_spend_usd"] = cust_stats["cust_total_spend_usd"].round(2)
    cust_stats["cust_avg_order_value_usd"] = cust_stats[
        "cust_avg_order_value_usd"
    ].round(2)

    # Merge back
    merged = result_df.merge(cust_stats, on="customer_id", how="left")
    return merged


def detect_anomalies_zscore(
    df: pd.DataFrame,
    column: str = "amount_normalized_usd",
    threshold: float = 3.0,
) -> pd.DataFrame:
    """Flag anomalous transactions using Z-score statistical outlier detection."""
    result_df = df.copy()

    if column not in result_df.columns or len(result_df) < 3:
        result_df["is_anomaly"] = False
        result_df["z_score"] = 0.0
        return result_df

    series = pd.to_numeric(result_df[column], errors="coerce").fillna(0)
    std_dev = series.std(ddof=0)

    if std_dev == 0 or np.isnan(std_dev):
        result_df["z_score"] = 0.0
        result_df["is_anomaly"] = False
        return result_df

    mean_val = series.mean()
    z_scores = ((series - mean_val) / std_dev).abs()

    result_df["z_score"] = z_scores.round(3)
    result_df["is_anomaly"] = z_scores > threshold

    return result_df


def deduplicate_records(
    df: pd.DataFrame,
    subset: Optional[List[str]] = None,
    order_by: str = "timestamp",
) -> pd.DataFrame:
    """Deduplicate records by primary key, keeping the latest record by timestamp."""
    result_df = df.copy()
    keys = subset or ["transaction_id"]

    if all(k in result_df.columns for k in keys):
        if order_by in result_df.columns:
            result_df = result_df.sort_values(by=order_by, ascending=True)
        result_df = result_df.drop_duplicates(subset=keys, keep="last").reset_index(
            drop=True
        )

    return result_df


def run_all_transformations(df: pd.DataFrame, config: TransformConfig) -> pd.DataFrame:
    """Execute complete transformation pipeline sequence."""
    logger.info("Starting transformation sequence on %d records", len(df))

    cleaned = clean_and_cast_types(df)
    deduped = deduplicate_records(cleaned)
    fx_normalized = normalize_currencies(
        deduped, base_currency=config.base_currency, fx_rates=config.fx_rates
    )
    temporal = extract_temporal_features(fx_normalized)
    loyalty = assign_loyalty_tiers(temporal, tiers=config.loyalty_tiers)
    enriched = compute_customer_lifetime_metrics(loyalty)
    final_transformed = detect_anomalies_zscore(
        enriched,
        column="amount_normalized_usd",
        threshold=config.anomaly_std_threshold,
    )

    logger.info(
        "Transformation sequence completed. Final shape: %s", final_transformed.shape
    )
    return final_transformed
