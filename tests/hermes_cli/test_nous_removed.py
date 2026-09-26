"""Guard against restoring the removed Nous provider through old config."""
from unittest.mock import patch
import pytest


def test_stale_primary_nous_provider_fails_clearly():
    from hermes_cli.runtime_provider import resolve_runtime_provider
    with patch("hermes_cli.runtime_provider.resolve_requested_provider", return_value="nous"):
        with pytest.raises(ValueError, match="Nous Portal was removed"):
            resolve_runtime_provider(requested="nous")


def test_stale_auxiliary_nous_provider_returns_no_client():
    from agent.auxiliary_client import resolve_provider_client
    with patch("agent.auxiliary_client._validate_proxy_env_urls"):
        assert resolve_provider_client("nous", model="old") == (None, None)
