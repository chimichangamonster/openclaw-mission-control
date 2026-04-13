# ruff: noqa: INP001
"""Tests for industry auto-detection and enhanced template listing."""

from __future__ import annotations

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

    def test_clean_technology(self):
        result = detect_industry("Magnetik Biomedical Waste Treatment")
        assert result["template_id"] == "clean_technology"
        assert result["confidence"] >= 0.4

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
