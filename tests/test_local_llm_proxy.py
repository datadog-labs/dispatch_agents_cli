"""Tests for the local router LLM proxy endpoint (/llm/proxy).

Validates that the router derives the wire format from the endpoint path when
the SDK omits ``provider_format`` (SDK PR #384 dropped it from /llm/proxy
payloads), mirroring the production backend's _format_from_endpoint fallback.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """Create a test client for the router service."""
    from fastapi import FastAPI

    from dispatch_cli.router.service import api_router

    app = FastAPI()
    app.include_router(api_router)
    return TestClient(app)


@pytest.fixture
def mock_get_api_key():
    """Mock API key retrieval so no real credentials are needed."""
    with patch(
        "dispatch_cli.router.local_llm.get_api_key",
        return_value="sk-test-key",
    ) as mock:
        yield mock


@pytest.fixture
def capture_provider_post():
    """Mock httpx.AsyncClient and capture the URL the proxy forwards to."""
    posted = {}

    async def fake_post(url, json=None, headers=None):
        posted["url"] = url
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b'{"ok": true}'
        resp.json.return_value = {"ok": True}
        return resp

    client = MagicMock()
    client.post = AsyncMock(side_effect=fake_post)

    @asynccontextmanager
    async def fake_client(*args, **kwargs):
        yield client

    with patch("dispatch_cli.router.service.httpx.AsyncClient", fake_client):
        yield posted


class TestProxyFormatResolution:
    """The router must accept payloads that omit provider_format."""

    def test_responses_endpoint_routes_to_openai_without_provider_format(
        self, test_client, mock_get_api_key, capture_provider_post
    ):
        """An OpenAI Responses call with no provider_format routes to OpenAI (no 422)."""
        response = test_client.post(
            "/llm/proxy",
            json={
                "body": {"model": "gpt-5.4", "input": []},
                "endpoint": "/v1/responses",
            },
        )
        assert response.status_code == 200
        assert capture_provider_post["url"].startswith("https://api.openai.com")

    def test_messages_endpoint_routes_to_anthropic_without_provider_format(
        self, test_client, mock_get_api_key, capture_provider_post
    ):
        """An Anthropic Messages call with no provider_format routes to Anthropic."""
        response = test_client.post(
            "/llm/proxy",
            json={
                "body": {"model": "claude-3", "messages": []},
                "endpoint": "/v1/messages",
            },
        )
        assert response.status_code == 200
        assert capture_provider_post["url"].startswith("https://api.anthropic.com")

    def test_explicit_provider_format_still_honored(
        self, test_client, mock_get_api_key, capture_provider_post
    ):
        """An explicit provider_format takes precedence (passthrough SDKs still send it)."""
        response = test_client.post(
            "/llm/proxy",
            json={
                "provider_format": "openai",
                "body": {"model": "gpt-5.4", "input": []},
                "endpoint": "/v1/responses",
            },
        )
        assert response.status_code == 200
        assert capture_provider_post["url"].startswith("https://api.openai.com")

    def test_unknown_endpoint_without_provider_format_returns_400(
        self, test_client, mock_get_api_key
    ):
        """An unresolvable endpoint yields the clear 400, not a misroute or 422."""
        response = test_client.post(
            "/llm/proxy",
            json={
                "body": {"model": "whatever"},
                "endpoint": "/v1/unknown",
            },
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "Cannot resolve provider" in detail
        assert "/v1/unknown" in detail
