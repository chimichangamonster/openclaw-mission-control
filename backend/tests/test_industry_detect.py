# ruff: noqa: INP001
"""Tests for industry auto-detection and enhanced template listing."""

from __future__ import annotations

import pytest

from app.services.industry_templates import detect_industry, list_templates


class TestDetectIndustry:
    def test_construction_keywords(self):
        result = detect_industry("Elite Construction Group")
        assert result["template_id"] == "construction"
        assert result["confidence"] >= 0.4

    def test_construction_trades(self):
        result = detect_industry("ABC Plumbing & Electrical")
        assert result["template_id"] == "construction"

    def test_waste_management(self):
        result = detect_industry("Waste Gurus")
        assert result["template_id"] == "waste_management"
        assert result["confidence"] >= 0.4

    def test_waste_disposal(self):
        result = detect_industry("Green Disposal Inc")
        assert result["template_id"] == "waste_management"

    def test_staffing_agency(self):
        result = detect_industry("King Staffing Solutions")
        assert result["template_id"] == "staffing"
        assert result["confidence"] >= 0.4

    def test_staffing_recruitment(self):
        result = detect_industry("TopTalent Recruitment Agency")
        assert result["template_id"] == "staffing"

    def test_trading_company(self):
        result = detect_industry("Apex Capital Trading")
        assert result["template_id"] == "day_trading"

    def test_betting_company(self):
        result = detect_industry("Pro Sports Betting Analytics")
        assert result["template_id"] == "sports_betting"

    def test_no_match_returns_none(self):
        result = detect_industry("Acme Corporation")
        assert result["template_id"] is None
        assert result["confidence"] == 0.0

    def test_empty_name(self):
        result = detect_industry("")
        assert result["template_id"] is None

    def test_case_insensitive(self):
        result = detect_industry("CONSTRUCTION BUILDERS INC")
        assert result["template_id"] == "construction"

    def test_description_helps_detection(self):
        result = detect_industry(
            "GreenTech Solutions",
            org_description="waste recycling and environmental cleanup services",
        )
        assert result["template_id"] == "waste_management"

    def test_domain_helps_detection(self):
        result = detect_industry("ECS Ltd", domain="eliteconstruction.ca")
        assert result["template_id"] == "construction"

    def test_multiple_matches_picks_best(self):
        """When org name has keywords from multiple templates, pick highest score."""
        result = detect_industry("Construction Staffing & Labour Solutions")
        assert result["template_id"] in ("construction", "staffing")
        assert result["confidence"] >= 0.4
        assert len(result["all_scores"]) >= 2

    def test_higher_confidence_with_more_keywords(self):
        low = detect_industry("Builder Co")
        high = detect_industry("Construction Contracting & Building Renovation")
        assert high["confidence"] > low["confidence"]

    def test_biomedical_maps_to_waste(self):
        """Biomedical disposal maps to waste management template."""
        result = detect_industry("Gient Biomedical Disposal")
        assert result["template_id"] == "waste_management"

    def test_all_scores_included(self):
        result = detect_industry("Construction and Waste Removal")
        assert "all_scores" in result
        assert "construction" in result["all_scores"]
        assert "waste_management" in result["all_scores"]


    # ── New vertical detection tests ────────────────────────────────────────

    def test_manufacturing(self):
        result = detect_industry("Precision Manufacturing Corp")
        assert result["template_id"] == "manufacturing"
        assert result["confidence"] >= 0.4

    def test_oil_gas(self):
        result = detect_industry("Northern Pipeline Services")
        assert result["template_id"] == "oil_gas"

    def test_oil_gas_drilling(self):
        result = detect_industry("Apex Drilling & Well Servicing")
        assert result["template_id"] == "oil_gas"

    def test_mining(self):
        result = detect_industry("Goldfield Mining Corp")
        assert result["template_id"] == "mining"

    def test_agriculture(self):
        result = detect_industry("Prairie Grain Farms")
        assert result["template_id"] == "agriculture"

    def test_logistics(self):
        result = detect_industry("FastTrack Logistics & Warehousing")
        assert result["template_id"] == "logistics"

    def test_energy_utilities(self):
        result = detect_industry("SunPeak Solar Energy")
        assert result["template_id"] == "energy_utilities"

    def test_healthcare_pharma(self):
        result = detect_industry("BioGenix Pharmaceutical Lab")
        assert result["template_id"] == "healthcare_pharma"

    def test_food_beverage(self):
        result = detect_industry("Mountain Brewery & Distillery")
        assert result["template_id"] == "food_beverage"

    def test_smart_buildings(self):
        result = detect_industry("SmartSpace Facilities BMS Services")
        assert result["template_id"] == "smart_buildings"

    def test_telecom(self):
        result = detect_industry("NorthLink Telecommunications")
        assert result["template_id"] == "telecom"

    def test_water_wastewater(self):
        result = detect_industry("ClearWater Treatment Plant Services")
        assert result["template_id"] == "water_wastewater"

    def test_professional_services(self):
        result = detect_industry("Vantage Consulting Advisory")
        assert result["template_id"] == "professional_services"


class TestListTemplatesEnhanced:
    def test_includes_skills_list(self):
        templates = list_templates()
        for t in templates:
            assert "skills" in t
            assert isinstance(t["skills"], list)

    def test_includes_onboarding_step_count(self):
        templates = list_templates()
        for t in templates:
            assert "onboarding_step_count" in t
            assert isinstance(t["onboarding_step_count"], int)
            assert t["onboarding_step_count"] > 0

    def test_includes_feature_flags(self):
        templates = list_templates()
        for t in templates:
            assert "feature_flags" in t
            assert isinstance(t["feature_flags"], list)

    def test_construction_has_expected_skills(self):
        templates = list_templates()
        construction = next(t for t in templates if t["id"] == "construction")
        assert "bookkeeping" in construction["skills"]
        assert "job-costing" in construction["skills"]
