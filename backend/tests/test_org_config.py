# ruff: noqa: INP001
"""Tests for org config data, industry templates, and onboarding."""

from __future__ import annotations

import json


class TestOrgConfigModel:
    """Test OrgConfigData model."""

    def test_default_value(self):
        from app.models.org_config import OrgConfigData

        item = OrgConfigData(
            organization_id="00000000-0000-0000-0000-000000000001",
            category="cost_codes",
            key="labour",
            label="Labour",
        )
        assert item.value == {}
        assert item.is_active is True
        assert item.sort_order == 0

    def test_value_json_roundtrip(self):
        from app.models.org_config import OrgConfigData

        data = {"code": "CC-100", "unit": "hour", "rate": 35.00}
        item = OrgConfigData(
            organization_id="00000000-0000-0000-0000-000000000001",
            category="cost_codes",
            key="labour",
            label="Labour",
            value_json=json.dumps(data),
        )
        assert item.value == data
        assert item.value["rate"] == 35.00

    def test_category_and_key(self):
        from app.models.org_config import OrgConfigData

        item = OrgConfigData(
            organization_id="00000000-0000-0000-0000-000000000001",
            category="crew_roles",
            key="foreman",
            label="Foreman",
            value_json=json.dumps({"default_pay_rate": 35.00}),
        )
        assert item.category == "crew_roles"
        assert item.key == "foreman"


class TestOrgOnboardingModel:
    """Test OrgOnboardingStep model."""

    def test_defaults(self):
        from app.models.org_config import OrgOnboardingStep

        step = OrgOnboardingStep(
            organization_id="00000000-0000-0000-0000-000000000001",
            template_id="construction",
            step_key="add_first_client",
            label="Add your first client",
        )
        assert step.completed is False
        assert step.completed_at is None
        assert step.sort_order == 0


class TestIndustryTemplates:
    """Test template definitions."""

    def test_construction_template_exists(self):
        from app.services.industry_templates import get_template

        t = get_template("construction")
        assert t is not None
        assert t.name == "Construction & Trades"
        assert "bookkeeping" in t.skills
        assert "cost_codes" in t.default_config
        assert "crew_roles" in t.default_config

    def test_waste_management_template_exists(self):
        from app.services.industry_templates import get_template

        t = get_template("waste_management")
        assert t is not None
        assert "service_catalog" in t.default_config

    def test_staffing_template_exists(self):
        from app.services.industry_templates import get_template

        t = get_template("staffing")
        assert t is not None
        assert "staffing" in t.skills

    def test_clean_technology_template_exists(self):
        from app.services.industry_templates import get_template

        t = get_template("clean_technology")
        assert t is not None

    def test_unknown_template_returns_none(self):
        from app.services.industry_templates import get_template

        assert get_template("nonexistent") is None

    def test_list_templates(self):
        from app.services.industry_templates import list_templates

        templates = list_templates()
        assert len(templates) == 5
        ids = {t["id"] for t in templates}
        assert "construction" in ids
        assert "waste_management" in ids
        assert "staffing" in ids

    def test_construction_cost_codes(self):
        from app.services.industry_templates import get_template

        t = get_template("construction")
        codes = t.default_config["cost_codes"]
        keys = [c.key for c in codes]
        assert "labour" in keys
        assert "materials" in keys
        assert "equipment_rental" in keys

    def test_construction_onboarding_steps(self):
        from app.services.industry_templates import get_template

        t = get_template("construction")
        assert len(t.onboarding_steps) == 6
        step_keys = [s.key for s in t.onboarding_steps]
        assert "review_cost_codes" in step_keys
        assert "add_first_client" in step_keys
        assert "test_invoice" in step_keys

    def test_construction_crew_roles_have_rates(self):
        from app.services.industry_templates import get_template

        t = get_template("construction")
        roles = t.default_config["crew_roles"]
        for role in roles:
            assert "default_pay_rate" in role.value
            assert "default_bill_rate" in role.value
            assert role.value["default_bill_rate"] > role.value["default_pay_rate"]

    def test_waste_management_service_catalog(self):
        from app.services.industry_templates import get_template

        t = get_template("waste_management")
        services = t.default_config["service_catalog"]
        keys = [s.key for s in services]
        assert "bin_rental_20yd" in keys
        assert "junk_removal" in keys

    def test_template_feature_flags_are_bools(self):
        from app.services.industry_templates import TEMPLATES

        for template in TEMPLATES.values():
            for flag, value in template.feature_flags.items():
                assert isinstance(value, bool), f"{template.id}.{flag} is not bool"


class TestOrganizationSettingsTemplateField:
    """Test the industry_template_id field on OrganizationSettings."""

    def test_default_is_none(self):
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        assert settings.industry_template_id is None

    def test_can_set_template_id(self):
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        settings.industry_template_id = "construction"
        assert settings.industry_template_id == "construction"
