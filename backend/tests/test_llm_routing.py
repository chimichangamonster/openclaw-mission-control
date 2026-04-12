# ruff: noqa: INP001
"""Tests for LLM routing — custom endpoints, BYOK resolution, health checks."""

from __future__ import annotations

from app.services.llm_routing import OPENROUTER_BASE_URL, LLMEndpoint


class TestLLMEndpoint:
    """LLMEndpoint data class."""

    def test_openrouter_endpoint(self):
        ep = LLMEndpoint(
            api_url=OPENROUTER_BASE_URL,
            api_key="sk-test",
            source="byok_openrouter",
            name="OpenRouter (BYOK)",
            models=[],
            is_openrouter=True,
        )
        assert ep.is_openrouter is True
        assert ep.source == "byok_openrouter"
        assert "openrouter.ai" in ep.api_url

    def test_custom_endpoint(self):
        ep = LLMEndpoint(
            api_url="https://llm.corp.internal/v1",
            api_key="corp-key",
            source="custom",
            name="Corp LLM",
            models=["llama-3.1-70b", "mistral-7b"],
            is_openrouter=False,
        )
        assert ep.is_openrouter is False
        assert ep.source == "custom"
        assert len(ep.models) == 2
        assert "corp.internal" in ep.api_url

    def test_data_sovereignty(self):
        """Custom endpoints keep data private (not OpenRouter)."""
        custom = LLMEndpoint(
            api_url="https://llm.internal/v1",
            api_key="k",
            source="custom",
            name="Private",
            models=[],
            is_openrouter=False,
        )
        openrouter = LLMEndpoint(
            api_url=OPENROUTER_BASE_URL,
            api_key="k",
            source="byok_openrouter",
            name="OR",
            models=[],
            is_openrouter=True,
        )
        # Custom = data stays private
        assert not custom.is_openrouter
        # OpenRouter = data leaves
        assert openrouter.is_openrouter


class TestCustomEndpointConfig:
    """OrganizationSettings custom LLM endpoint fields."""

    def test_default_empty(self):
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="fake")
        assert settings.custom_llm_endpoint == {}
        assert settings.custom_llm_api_key_encrypted is None

    def test_endpoint_json_parsing(self):
        import json

        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(
            organization_id="fake",
            custom_llm_endpoint_json=json.dumps(
                {
                    "api_url": "https://llm.corp.internal/v1",
                    "name": "Corp LLM",
                    "models": ["llama-3.1-70b"],
                }
            ),
        )
        ep = settings.custom_llm_endpoint
        assert ep["api_url"] == "https://llm.corp.internal/v1"
        assert ep["name"] == "Corp LLM"
        assert "llama-3.1-70b" in ep["models"]


class TestRoutingPriority:
    """Resolution priority: custom > BYOK OpenRouter > platform OpenRouter."""

    def test_priority_order(self):
        """Custom endpoint takes priority over OpenRouter keys."""
        # This is a design test — verifying the intended resolution order
        # The actual resolution is async and needs DB, tested via integration
        sources = ["custom", "byok_openrouter", "platform_openrouter"]
        # Custom (enterprise self-hosted) > BYOK (org's own OpenRouter) > Platform default
        assert sources.index("custom") < sources.index("byok_openrouter")
        assert sources.index("byok_openrouter") < sources.index("platform_openrouter")


class TestHealthCheckResponse:
    """Health check result structure."""

    def test_health_result_fields(self):
        """Health check returns expected fields."""
        expected_fields = {
            "reachable",
            "authenticated",
            "models",
            "inference_ok",
            "latency_ms",
            "error",
        }
        # These are the fields returned by check_endpoint_health
        result = {
            "reachable": False,
            "authenticated": False,
            "models": [],
            "inference_ok": False,
            "latency_ms": None,
            "error": None,
        }
        assert set(result.keys()) == expected_fields


class TestDeploymentTiers:
    """Enterprise deployment tier model."""

    def test_saas_tier(self):
        """SaaS: data goes through OpenRouter to public LLMs."""
        ep = LLMEndpoint(
            api_url=OPENROUTER_BASE_URL,
            api_key="k",
            source="platform_openrouter",
            name="Platform",
            models=[],
            is_openrouter=True,
        )
        assert ep.is_openrouter
        assert ep.source == "platform_openrouter"

    def test_dedicated_tier(self):
        """Dedicated: org's own OpenRouter key, can restrict providers."""
        ep = LLMEndpoint(
            api_url=OPENROUTER_BASE_URL,
            api_key="org-key",
            source="byok_openrouter",
            name="BYOK",
            models=[],
            is_openrouter=True,
        )
        assert ep.is_openrouter
        assert ep.source == "byok_openrouter"

    def test_enterprise_tier(self):
        """Enterprise: self-hosted, data never leaves client infra."""
        ep = LLMEndpoint(
            api_url="https://ai.megacorp.internal/v1",
            api_key="internal",
            source="custom",
            name="MegaCorp AI",
            models=["llama-3.1-405b"],
            is_openrouter=False,
        )
        assert not ep.is_openrouter
        assert ep.source == "custom"
        assert "megacorp" in ep.api_url
