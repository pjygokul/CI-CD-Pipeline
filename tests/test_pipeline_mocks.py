"""Mock Testing for Data Pipelines.

Tests pipeline components by mocking external dependencies (S3 storage, database connectors,
and filesystem writes) using dependency injection and unittest.mock / pytest-mock.
"""

import json
from unittest.mock import MagicMock
import pandas as pd
import pytest
from src.pipeline.config import (
    ExtractConfig,
    LoadConfig,
    PipelineConfig,
    TransformConfig,
    ValidationConfig,
)
from src.pipeline.extract import (
    LocalStorageClient,
    MockS3Client,
    extract_data,
    parse_raw_records_to_df,
)
from src.pipeline.load import load_data
from src.pipeline.runner import PipelineRunner


class TestExtractWithMocks:
    """Test data extraction with mock storage clients."""

    def test_extract_from_mock_s3(self, mock_s3_storage):
        config = ExtractConfig(
            source_type="s3", raw_data_path="s3://mock-bucket/transactions.json"
        )
        df = extract_data(config, storage_client=mock_s3_storage)
        assert len(df) == 2
        assert "TXN-90001" in df["transaction_id"].values

    def test_extract_missing_s3_object_raises(self, mock_s3_storage):
        config = ExtractConfig(
            source_type="s3", raw_data_path="s3://mock-bucket/non_existent.json"
        )
        with pytest.raises(FileNotFoundError):
            extract_data(config, storage_client=mock_s3_storage)

    def test_extract_with_patched_client(self):
        mock_client = MagicMock()
        mock_client.read_file.return_value = json.dumps(
            [
                {
                    "transaction_id": "TXN-777",
                    "customer_id": "CUST-777",
                    "amount": 99.0,
                    "currency": "USD",
                }
            ]
        )
        config = ExtractConfig(source_type="s3", raw_data_path="s3://bucket/test.json")
        df = extract_data(config, storage_client=mock_client)
        assert len(df) == 1
        assert df["transaction_id"].iloc[0] == "TXN-777"
        mock_client.read_file.assert_called_once_with("s3://bucket/test.json")


class TestLoadWithMocks:
    """Test data loading with mock storage destinations."""

    def test_load_to_mock_storage(self):
        mock_client = MockS3Client()
        df = pd.DataFrame([{"transaction_id": "TXN-1", "amount": 100.0}])
        config = LoadConfig(
            target_type="json", output_path="s3://target-bucket/output.json"
        )
        dest = load_data(df, config, storage_client=mock_client)
        assert dest == "s3://target-bucket/output.json"
        assert "s3://target-bucket/output.json" in mock_client._store

    def test_load_handles_datetime_serialization(self):
        mock_client = MagicMock()
        df = pd.DataFrame(
            [
                {
                    "transaction_id": "TXN-1",
                    "timestamp": pd.to_datetime("2026-03-01 12:00:00"),
                }
            ]
        )
        config = LoadConfig(target_type="json", output_path="s3://bucket/out.json")
        load_data(df, config, storage_client=mock_client)
        mock_client.write_file.assert_called_once()
        written_content = mock_client.write_file.call_args[0][1]
        assert "2026-03-01 12:00:00" in written_content


class TestPipelineRunnerWithMocks:
    """Test full pipeline execution with injected mocks."""

    def test_pipeline_runner_success(self, sample_schema_contracts):
        mock_storage = MockS3Client(
            {
                "s3://test-bucket/raw.json": json.dumps(
                    [
                        {
                            "transaction_id": "TXN-10001",
                            "customer_id": "CUST-101",
                            "amount": 250.0,
                            "currency": "USD",
                            "timestamp": "2026-03-01T10:00:00Z",
                            "status": "COMPLETED",
                        }
                    ]
                )
            }
        )

        custom_config = PipelineConfig(
            environment="test",
            app_name="TestPipeline",
            extract=ExtractConfig(
                source_type="s3", raw_data_path="s3://test-bucket/raw.json"
            ),
            transform=TransformConfig(),
            validation=ValidationConfig(strict_mode=True),
            load=LoadConfig(
                target_type="json", output_path="s3://test-bucket/out.json"
            ),
        )

        runner = PipelineRunner(
            config=custom_config,
            schema_contracts=sample_schema_contracts,
            storage_client=mock_storage,
        )

        result = runner.run(env="test")
        assert result.status == "SUCCESS"
        assert result.records_extracted == 1
        assert result.records_transformed == 1
        assert "s3://test-bucket/out.json" in mock_storage._store

    def test_pipeline_runner_validation_failure_halts(self, sample_schema_contracts):
        # Missing required transaction_id
        mock_storage = MockS3Client(
            {
                "s3://test-bucket/corrupt.json": json.dumps(
                    [
                        {
                            "customer_id": "CUST-101",
                            "amount": 250.0,
                            "currency": "USD",
                        }
                    ]
                )
            }
        )

        custom_config = PipelineConfig(
            environment="test",
            extract=ExtractConfig(
                source_type="s3", raw_data_path="s3://test-bucket/corrupt.json"
            ),
            transform=TransformConfig(),
            validation=ValidationConfig(strict_mode=True),
            load=LoadConfig(output_path="s3://test-bucket/out.json"),
        )

        runner = PipelineRunner(
            config=custom_config,
            schema_contracts=sample_schema_contracts,
            storage_client=mock_storage,
        )

        result = runner.run(env="test")
        assert result.status == "VALIDATION_FAILED"
        assert result.raw_validation_report.error_count() > 0
        assert "s3://test-bucket/out.json" not in mock_storage._store

    def test_pipeline_runner_unexpected_exception(self, sample_schema_contracts):
        mock_storage = MagicMock()
        mock_storage.read_file.side_effect = RuntimeError(
            "Network timeout connecting to storage"
        )

        custom_config = PipelineConfig(
            environment="test",
            extract=ExtractConfig(
                source_type="s3", raw_data_path="s3://test-bucket/raw.json"
            ),
            transform=TransformConfig(),
            validation=ValidationConfig(),
            load=LoadConfig(output_path="s3://test-bucket/out.json"),
        )

        runner = PipelineRunner(
            config=custom_config,
            schema_contracts=sample_schema_contracts,
            storage_client=mock_storage,
        )

        result = runner.run(env="test")
        assert result.status == "ERROR"
        assert "Network timeout" in result.error_message


class TestLocalStorageClientAndParsers:
    """Test local storage client and json parsing logic."""

    def test_local_storage_read_and_write(self, tmp_path):
        client = LocalStorageClient()
        test_file = tmp_path / "test_data" / "sample.json"
        content = '{"key": "value"}'

        success = client.write_file(str(test_file), content)
        assert success is True
        assert test_file.exists()

        read_back = client.read_file(str(test_file))
        assert read_back == content

    def test_local_storage_missing_file(self, tmp_path):
        client = LocalStorageClient()
        with pytest.raises(FileNotFoundError):
            client.read_file(str(tmp_path / "missing.json"))

    def test_parse_json_lines_and_dict_records(self):
        # Dict with records wrapper
        dict_wrapper = json.dumps({"records": [{"id": 1}, {"id": 2}]})
        df1 = parse_raw_records_to_df(dict_wrapper)
        assert len(df1) == 2

        # JSON lines format
        json_lines = '{"id": 10}\n{"id": 20}\n'
        df2 = parse_raw_records_to_df(json_lines)
        assert len(df2) == 2
        assert df2["id"].tolist() == [10, 20]
