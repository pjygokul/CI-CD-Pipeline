"""Data Contract and Quality Validation Module.

Provides declarative data validation against schema contracts, ensuring pipeline reliability and
failing fast in CI/CD environments upon contract violations.
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from src.pipeline.config import ValidationConfig

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    check_name: str
    column: Optional[str]
    severity: str  # "ERROR" or "WARNING"
    message: str
    failed_rows_count: int = 0


@dataclass
class ValidationReport:
    is_valid: bool
    total_records: int
    issues: List[ValidationIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "ERROR")

    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "WARNING")

    def summary(self) -> str:
        status = "PASSED" if self.is_valid else "FAILED"
        return (
            f"Validation Report: Status={status} | Records={self.total_records} | "
            f"Errors={self.error_count()} | Warnings={self.warning_count()}"
        )


def validate_required_columns(
    df: pd.DataFrame, required_columns: List[str]
) -> Tuple[bool, List[ValidationIssue]]:
    """Validate that all required columns are present in the DataFrame."""
    issues = []
    missing_cols = [col for col in required_columns if col not in df.columns]

    if missing_cols:
        for col in missing_cols:
            issues.append(
                ValidationIssue(
                    check_name="required_columns",
                    column=col,
                    severity="ERROR",
                    message=f"Missing mandatory column: '{col}'",
                    failed_rows_count=len(df),
                )
            )
        return False, issues
    return True, []


def validate_nullability(
    df: pd.DataFrame, schema_fields: Dict[str, dict]
) -> Tuple[bool, List[ValidationIssue]]:
    """Validate non-nullable columns have 0 null values."""
    issues = []
    all_valid = True

    for col, rules in schema_fields.items():
        if col in df.columns and not rules.get("nullable", True):
            null_count = int(df[col].isna().sum())
            if null_count > 0:
                all_valid = False
                issues.append(
                    ValidationIssue(
                        check_name="nullability",
                        column=col,
                        severity="ERROR",
                        message=f"Column '{col}' has {null_count} null values but is marked non-nullable.",
                        failed_rows_count=null_count,
                    )
                )
    return all_valid, issues


def validate_uniqueness(
    df: pd.DataFrame, schema_fields: Dict[str, dict]
) -> Tuple[bool, List[ValidationIssue]]:
    """Validate uniqueness constraints on designated primary / unique columns."""
    issues = []
    all_valid = True

    for col, rules in schema_fields.items():
        if col in df.columns and rules.get("unique", False):
            # Non-null values uniqueness
            non_null_series = df[col].dropna()
            duplicates = int(non_null_series.duplicated().sum())
            if duplicates > 0:
                all_valid = False
                issues.append(
                    ValidationIssue(
                        check_name="uniqueness",
                        column=col,
                        severity="ERROR",
                        message=f"Column '{col}' has {duplicates} duplicate values violates uniqueness constraint.",
                        failed_rows_count=duplicates,
                    )
                )
    return all_valid, issues


def validate_allowed_values(
    df: pd.DataFrame, schema_fields: Dict[str, dict]
) -> Tuple[bool, List[ValidationIssue]]:
    """Validate categorical columns against allowed values enumeration."""
    issues = []
    all_valid = True

    for col, rules in schema_fields.items():
        allowed = rules.get("allowed_values")
        if col in df.columns and allowed is not None:
            invalid_mask = ~df[col].dropna().isin(allowed)
            invalid_count = int(invalid_mask.sum())
            if invalid_count > 0:
                all_valid = False
                issues.append(
                    ValidationIssue(
                        check_name="allowed_values",
                        column=col,
                        severity="ERROR",
                        message=f"Column '{col}' contains {invalid_count} values outside allowed set: {allowed}.",
                        failed_rows_count=invalid_count,
                    )
                )
    return all_valid, issues


def validate_numeric_ranges(
    df: pd.DataFrame, schema_fields: Dict[str, dict]
) -> Tuple[bool, List[ValidationIssue]]:
    """Validate numeric columns conform to min_value and max_value bounds."""
    issues = []
    all_valid = True

    for col, rules in schema_fields.items():
        if col in df.columns:
            min_val = rules.get("min_value")
            max_val = rules.get("max_value")

            if min_val is not None or max_val is not None:
                numeric_series = pd.to_numeric(df[col], errors="coerce")
                if min_val is not None:
                    viol_min = int((numeric_series < min_val).sum())
                    if viol_min > 0:
                        all_valid = False
                        issues.append(
                            ValidationIssue(
                                check_name="numeric_range_min",
                                column=col,
                                severity="ERROR",
                                message=f"Column '{col}' has {viol_min} values less than minimum {min_val}.",
                                failed_rows_count=viol_min,
                            )
                        )
                if max_val is not None:
                    viol_max = int((numeric_series > max_val).sum())
                    if viol_max > 0:
                        all_valid = False
                        issues.append(
                            ValidationIssue(
                                check_name="numeric_range_max",
                                column=col,
                                severity="ERROR",
                                message=f"Column '{col}' has {viol_max} values exceeding maximum {max_val}.",
                                failed_rows_count=viol_max,
                            )
                        )
    return all_valid, issues


def validate_regex_patterns(
    df: pd.DataFrame, schema_fields: Dict[str, dict]
) -> Tuple[bool, List[ValidationIssue]]:
    """Validate string columns conform to regex pattern format."""
    issues = []
    all_valid = True

    for col, rules in schema_fields.items():
        pattern = rules.get("regex")
        if col in df.columns and pattern:
            str_series = df[col].dropna().astype(str)
            invalid_mask = ~str_series.str.match(pattern)
            invalid_count = int(invalid_mask.sum())
            if invalid_count > 0:
                all_valid = False
                issues.append(
                    ValidationIssue(
                        check_name="regex_format",
                        column=col,
                        severity="WARNING",
                        message=f"Column '{col}' has {invalid_count} records not matching regex pattern '{pattern}'.",
                        failed_rows_count=invalid_count,
                    )
                )
    return all_valid, issues


def validate_dataframe(
    df: pd.DataFrame,
    schema_contracts: dict,
    validation_config: Optional[ValidationConfig] = None,
) -> ValidationReport:
    """Run full suite of data quality & schema contract checks."""
    if df.empty:
        return ValidationReport(
            is_valid=False,
            total_records=0,
            issues=[
                ValidationIssue(
                    check_name="empty_dataset",
                    column=None,
                    severity="ERROR",
                    message="Dataset is empty (0 records).",
                )
            ],
        )

    fields = schema_contracts.get("fields", {})
    all_issues: List[ValidationIssue] = []

    # 1. Required columns
    req_cols = (
        validation_config.required_columns
        if validation_config and validation_config.required_columns
        else list(fields.keys())
    )
    _, req_issues = validate_required_columns(df, req_cols)
    all_issues.extend(req_issues)

    # If critical required columns are missing, cannot perform field-level validations safely
    if any(issue.severity == "ERROR" for issue in req_issues):
        return ValidationReport(
            is_valid=False, total_records=len(df), issues=all_issues
        )

    # 2. Nullability
    _, null_issues = validate_nullability(df, fields)
    all_issues.extend(null_issues)

    # 3. Uniqueness
    _, uniq_issues = validate_uniqueness(df, fields)
    all_issues.extend(uniq_issues)

    # 4. Allowed enum values
    _, enum_issues = validate_allowed_values(df, fields)
    all_issues.extend(enum_issues)

    # 5. Numeric ranges
    _, range_issues = validate_numeric_ranges(df, fields)
    all_issues.extend(range_issues)

    # 6. Regex format
    _, regex_issues = validate_regex_patterns(df, fields)
    all_issues.extend(regex_issues)

    # Evaluate overall status based on strict mode and error tolerance
    total_records = len(df)
    total_errors = sum(
        issue.failed_rows_count for issue in all_issues if issue.severity == "ERROR"
    )
    error_percentage = (total_errors / (total_records * max(1, len(fields)))) * 100

    strict_mode = validation_config.strict_mode if validation_config else True
    max_error_pct = validation_config.max_error_percentage if validation_config else 0.0

    if strict_mode:
        is_valid = len([i for i in all_issues if i.severity == "ERROR"]) == 0
    else:
        is_valid = error_percentage <= max_error_pct

    metrics = {
        "total_records": total_records,
        "error_count": sum(1 for i in all_issues if i.severity == "ERROR"),
        "warning_count": sum(1 for i in all_issues if i.severity == "WARNING"),
        "error_percentage": round(error_percentage, 2),
    }

    report = ValidationReport(
        is_valid=is_valid,
        total_records=total_records,
        issues=all_issues,
        metrics=metrics,
    )
    logger.info(report.summary())
    return report
