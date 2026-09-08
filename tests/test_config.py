"""Unit Tests for Configuration Loader.

Verifies loading dev and prod configurations, schema contracts, and fallback behaviors.
"""

import pytest
from src.pipeline.config import PipelineConfig, load_config, load_schema_contracts


class TestConfigLoading:
    """Test environment configuration loading."""

    def test_load_dev_config(self):
        config = load_config(env="dev")
        assert isinstance(config, PipelineConfig)
        assert config.environment == "dev"
        assert config.extract.source_type == "local"
        assert config.transform.base_currency == "USD"
        assert "USD" in config.transform.fx_rates

    def test_load_prod_config(self):
        config = load_config(env="prod")
        assert isinstance(config, PipelineConfig)
        assert config.environment == "prod"
        assert config.validation.strict_mode is True
        assert config.extract.source_type == "s3"

    def test_load_schema_contracts(self):
        contracts = load_schema_contracts()
        assert "fields" in contracts
        assert "transaction_id" in contracts["fields"]
        assert contracts["fields"]["transaction_id"]["nullable"] is False

    def test_non_existent_config_falls_back_or_raises(self, tmp_path):
        # When given an empty directory without configs
        with pytest.raises(FileNotFoundError):
            load_config(env="unknown_env", config_dir=str(tmp_path))
