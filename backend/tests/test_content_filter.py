# ruff: noqa: INP001
"""Tests for CAC-compliant content filtering service."""

from __future__ import annotations

import pytest

from app.services.content_filter import (
    ContentFilterRegion,
    ContentFilterResult,
    filter_content,
    get_org_filter_region,
)


# ---------------------------------------------------------------------------
# Basic behavior
# ---------------------------------------------------------------------------


class TestFilterContentBasic:
    def test_none_input(self) -> None:
        result = filter_content(None, region="cn")
        assert result.text == ""
        assert result.filtered_count == 0
        assert result.categories == set()

    def test_no_region(self) -> None:
        text = "This is normal text about Taiwan independence"
        result = filter_content(text, region="none")
        assert result.text == text
        assert result.filtered_count == 0

    def test_unknown_region(self) -> None:
        text = "台湾独立"
        result = filter_content(text, region="xx")
        assert result.text == text
        assert result.filtered_count == 0

    def test_empty_text(self) -> None:
        result = filter_content("", region="cn")
        assert result.text == ""
        assert result.filtered_count == 0

    def test_clean_text_passes_through(self) -> None:
        text = "Today's weather in Beijing is sunny. 今天北京天气晴朗。"
        result = filter_content(text, region="cn")
        assert result.text == text
        assert result.filtered_count == 0
        assert result.categories == set()


# ---------------------------------------------------------------------------
# Chinese (CN) territorial integrity filters
# ---------------------------------------------------------------------------


class TestCNTerritorialIntegrity:
    def test_taiwan_independence_chinese(self) -> None:
        result = filter_content("台湾独立运动", region="cn")
        assert result.filtered_count > 0
        assert "territorial_integrity" in result.categories
        assert "台湾独立" not in result.text
        assert "[内容已过滤]" in result.text

    def test_taiwan_independence_english(self) -> None:
        result = filter_content("Taiwan is an independent country", region="cn")
        assert result.filtered_count > 0
        assert "territorial_integrity" in result.categories

    def test_free_tibet(self) -> None:
        result = filter_content("Support Free Tibet movement", region="cn")
        assert result.filtered_count > 0
        assert "territorial_integrity" in result.categories

    def test_tibet_independence_chinese(self) -> None:
        result = filter_content("支持西藏独立", region="cn")
        assert result.filtered_count > 0
        assert "territorial_integrity" in result.categories

    def test_east_turkestan(self) -> None:
        result = filter_content("East Turkestan independence", region="cn")
        assert result.filtered_count > 0
        assert "territorial_integrity" in result.categories

    def test_east_turkestan_chinese(self) -> None:
        result = filter_content("东突厥斯坦独立", region="cn")
        assert result.filtered_count > 0
        assert "territorial_integrity" in result.categories


# ---------------------------------------------------------------------------
# State security
# ---------------------------------------------------------------------------


class TestCNStateSecurity:
    def test_subversion_chinese(self) -> None:
        result = filter_content("颠覆国家政权的行为", region="cn")
        assert result.filtered_count > 0
        assert "state_security" in result.categories

    def test_overthrow_english(self) -> None:
        result = filter_content("plans to overthrow the Chinese government", region="cn")
        assert result.filtered_count > 0
        assert "state_security" in result.categories


# ---------------------------------------------------------------------------
# Sensitive history
# ---------------------------------------------------------------------------


class TestCNSensitiveHistory:
    def test_tiananmen_chinese(self) -> None:
        result = filter_content("天安门事件的历史", region="cn")
        assert result.filtered_count > 0
        assert "sensitive_history" in result.categories

    def test_tiananmen_english(self) -> None:
        result = filter_content("Tiananmen Square massacre in 1989", region="cn")
        assert result.filtered_count > 0
        assert "sensitive_history" in result.categories

    def test_june_fourth(self) -> None:
        result = filter_content("June Fourth incident details", region="cn")
        assert result.filtered_count > 0
        assert "sensitive_history" in result.categories

    def test_june_fourth_chinese(self) -> None:
        result = filter_content("六四事件的真相", region="cn")
        assert result.filtered_count > 0
        assert "sensitive_history" in result.categories


# ---------------------------------------------------------------------------
# Political leadership
# ---------------------------------------------------------------------------


class TestCNPoliticalLeadership:
    def test_xi_dictator_english(self) -> None:
        result = filter_content("Xi Jinping is a dictator who should step down", region="cn")
        assert result.filtered_count > 0
        assert "political_leadership" in result.categories

    def test_xi_dictator_chinese(self) -> None:
        result = filter_content("习近平是独裁者", region="cn")
        assert result.filtered_count > 0
        assert "political_leadership" in result.categories


# ---------------------------------------------------------------------------
# Banned organizations
# ---------------------------------------------------------------------------


class TestCNBannedOrganizations:
    def test_falun_gong_chinese(self) -> None:
        result = filter_content("法轮功的修炼方法", region="cn")
        assert result.filtered_count > 0
        assert "banned_organization" in result.categories

    def test_falun_gong_english(self) -> None:
        result = filter_content("Falun Gong practitioners", region="cn")
        assert result.filtered_count > 0
        assert "banned_organization" in result.categories


# ---------------------------------------------------------------------------
# Violence
# ---------------------------------------------------------------------------


class TestCNViolence:
    def test_bomb_making_chinese(self) -> None:
        result = filter_content("如何制造炸弹", region="cn")
        assert result.filtered_count > 0
        assert "violence" in result.categories

    def test_bomb_making_english(self) -> None:
        result = filter_content("how to make a bomb at home", region="cn")
        assert result.filtered_count > 0
        assert "violence" in result.categories


# ---------------------------------------------------------------------------
# Circumvention
# ---------------------------------------------------------------------------


class TestCNCircumvention:
    def test_vpn_tutorial_chinese(self) -> None:
        result = filter_content("翻墙教程和工具推荐", region="cn")
        assert result.filtered_count > 0
        assert "circumvention" in result.categories

    def test_bypass_firewall_english(self) -> None:
        result = filter_content("How to bypass the Great Firewall", region="cn")
        assert result.filtered_count > 0
        assert "circumvention" in result.categories


# ---------------------------------------------------------------------------
# Multiple categories in one text
# ---------------------------------------------------------------------------


class TestCNMultipleCategories:
    def test_multiple_violations(self) -> None:
        text = "台湾独立和天安门事件以及法轮功"
        result = filter_content(text, region="cn")
        assert result.filtered_count >= 3
        assert "territorial_integrity" in result.categories
        assert "sensitive_history" in result.categories
        assert "banned_organization" in result.categories

    def test_mixed_language_violations(self) -> None:
        text = "Free Tibet and 法轮功 and how to bypass the Great Firewall"
        result = filter_content(text, region="cn")
        assert result.filtered_count >= 3
        assert len(result.categories) >= 3


# ---------------------------------------------------------------------------
# False positive avoidance
# ---------------------------------------------------------------------------


class TestCNFalsePositives:
    def test_taiwan_neutral_mention(self) -> None:
        """Mentioning Taiwan in business context should be fine."""
        result = filter_content("We have a supplier in Taiwan.", region="cn")
        assert result.filtered_count == 0

    def test_tiananmen_square_tourism(self) -> None:
        """Neutral mention of Tiananmen Square without 'massacre' should pass."""
        result = filter_content("Tiananmen Square is a famous landmark in Beijing.", region="cn")
        assert result.filtered_count == 0

    def test_normal_business_chinese(self) -> None:
        result = filter_content("今天的股票市场表现良好，上涨了2%。", region="cn")
        assert result.filtered_count == 0

    def test_normal_business_english(self) -> None:
        result = filter_content("Revenue increased 15% in Q3 2025. The manufacturing line ran at 92% OEE.", region="cn")
        assert result.filtered_count == 0


# ---------------------------------------------------------------------------
# Org data policy integration
# ---------------------------------------------------------------------------


class TestGetOrgFilterRegion:
    def test_default_is_none(self) -> None:
        assert get_org_filter_region({}) == "none"

    def test_explicit_none(self) -> None:
        assert get_org_filter_region({"content_filter_region": "none"}) == "none"

    def test_china_region(self) -> None:
        assert get_org_filter_region({"content_filter_region": "cn"}) == "cn"

    def test_with_other_policy_fields(self) -> None:
        policy = {
            "redaction_level": "strict",
            "allow_email_content_to_llm": False,
            "log_llm_inputs": True,
            "content_filter_region": "cn",
        }
        assert get_org_filter_region(policy) == "cn"


# ---------------------------------------------------------------------------
# ContentFilterResult
# ---------------------------------------------------------------------------


class TestContentFilterResult:
    def test_result_is_namedtuple(self) -> None:
        result = filter_content("test", region="none")
        assert isinstance(result, ContentFilterResult)
        assert result.region == "none"

    def test_result_fields(self) -> None:
        result = filter_content("台湾独立", region="cn")
        assert isinstance(result.text, str)
        assert isinstance(result.filtered_count, int)
        assert isinstance(result.categories, set)
        assert isinstance(result.region, str)
