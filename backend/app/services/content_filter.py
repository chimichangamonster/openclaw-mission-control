"""CAC-compliant content filtering for LLM outputs in regulated regions.

Filters generative AI output before it reaches end users in regions that
require content moderation (primarily China under CAC regulation).

Pipeline: LLM response → content_filter() → filtered response → user

Usage:
    from app.services.content_filter import filter_content, ContentFilterResult
    result = filter_content(text, region="cn")

Design:
- Keyword-based filtering with category tracking
- Per-region rule sets (currently: China)
- Replacement is "[内容已过滤]" (content filtered) for Chinese users
- Audit-friendly: returns filter count and categories for logging
- Non-destructive default: regions without rules pass through unchanged
"""

from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple

from app.core.logging import get_logger

logger = get_logger(__name__)


class ContentFilterRegion(str, Enum):
    """Regions with content filtering requirements."""

    NONE = "none"  # No filtering (default)
    CN = "cn"  # China — CAC compliance


class ContentFilterResult(NamedTuple):
    """Result of content filtering with audit metadata."""

    text: str
    filtered_count: int
    categories: set[str]
    region: str


# ---------------------------------------------------------------------------
# China (CAC) filter rules
#
# Categories follow CAC's "Provisions on the Management of Generative AI
# Services" (生成式人工智能服务管理暂行办法, 2023):
#
# 1. State power subversion / national unity
# 2. State security / national interests
# 3. National image
# 4. Territorial integrity
# 5. Ethnic / religious incitement
# 6. Discriminatory content
# 7. Violence / terror
# 8. False / harmful information
#
# This is a baseline keyword filter. Production China deployments should
# integrate a dedicated content moderation API (Alibaba Green, Baidu AI,
# or Tencent TMR) for comprehensive coverage.
# ---------------------------------------------------------------------------

_CN_REPLACEMENT = "[内容已过滤]"

# Each entry: (compiled regex, category label)
# Patterns target content that an AI *generates* — not user input (that's sanitize.py)
_CN_FILTER_RULES: list[tuple[re.Pattern[str], str]] = [
    # Territorial integrity — Taiwan, Tibet, Xinjiang sovereignty claims
    (re.compile(
        r"台湾(?:是|为|属于)(?:一个)?(?:独立|主权)(?:的)?(?:国家|政治实体)",
        re.IGNORECASE,
    ), "territorial_integrity"),
    (re.compile(r"台湾独立|台独", re.IGNORECASE), "territorial_integrity"),
    (re.compile(r"西藏独立|藏独", re.IGNORECASE), "territorial_integrity"),
    (re.compile(r"东突厥斯坦", re.IGNORECASE), "territorial_integrity"),
    (re.compile(
        r"Taiwan\s+(?:is|as)\s+(?:an?\s+)?independent\s+(?:country|nation|state)",
        re.IGNORECASE,
    ), "territorial_integrity"),
    (re.compile(r"Free\s+Tibet", re.IGNORECASE), "territorial_integrity"),
    (re.compile(r"East\s+Turkestan", re.IGNORECASE), "territorial_integrity"),

    # State security — subversion, overthrow references
    (re.compile(r"颠覆国家政权|分裂国家", re.IGNORECASE), "state_security"),
    (re.compile(r"overthrow\s+(?:the\s+)?(?:Chinese|PRC)\s+(?:government|state|regime)", re.IGNORECASE), "state_security"),

    # Sensitive historical events
    (re.compile(r"天安门(?:事件|屠杀|大屠杀|镇压)", re.IGNORECASE), "sensitive_history"),
    (re.compile(r"六四(?:事件|屠杀|运动)", re.IGNORECASE), "sensitive_history"),
    (re.compile(r"Tiananmen\s+(?:Square\s+)?(?:massacre|protest|crackdown)", re.IGNORECASE), "sensitive_history"),
    (re.compile(r"June\s+(?:4th|Fourth)\s+(?:incident|massacre|crackdown)", re.IGNORECASE), "sensitive_history"),

    # Political leadership criticism (direct insults/attacks)
    (re.compile(r"习近平.*(?:独裁|暴君|下台)", re.IGNORECASE), "political_leadership"),
    (re.compile(r"Xi\s+Jinping\s+.*(?:dictator|tyrant|step\s+down|resign)", re.IGNORECASE), "political_leadership"),

    # Ethnic / religious incitement
    (re.compile(r"(?:维吾尔|藏|回|蒙)族.*(?:劣等|消灭|清洗)", re.IGNORECASE), "ethnic_incitement"),
    (re.compile(r"(?:Uyghur|Tibetan|Hui)\s+.*(?:inferior|eliminate|cleanse)", re.IGNORECASE), "ethnic_incitement"),

    # Falun Gong / banned organizations
    (re.compile(r"法轮功|法轮大法", re.IGNORECASE), "banned_organization"),
    (re.compile(r"Falun\s+(?:Gong|Dafa)", re.IGNORECASE), "banned_organization"),

    # Violence / terrorism promotion
    (re.compile(r"(?:制造|制作|组装)(?:炸弹|爆炸物|武器)", re.IGNORECASE), "violence"),
    (re.compile(r"(?:how\s+to\s+)?(?:make|build|assemble)\s+(?:a\s+)?(?:bomb|explosive|weapon)", re.IGNORECASE), "violence"),

    # VPN / circumvention promotion (regulated under CSL)
    (re.compile(r"(?:翻墙|科学上网).*(?:教程|方法|工具|软件)", re.IGNORECASE), "circumvention"),
    (re.compile(r"(?:bypass|circumvent)\s+(?:the\s+)?(?:Great\s+)?Firewall", re.IGNORECASE), "circumvention"),
]

# Region → rules mapping
_REGION_RULES: dict[ContentFilterRegion, list[tuple[re.Pattern[str], str]]] = {
    ContentFilterRegion.CN: _CN_FILTER_RULES,
}

# Region → replacement string
_REGION_REPLACEMENTS: dict[ContentFilterRegion, str] = {
    ContentFilterRegion.CN: _CN_REPLACEMENT,
}


def filter_content(
    text: str | None,
    *,
    region: str = "none",
) -> ContentFilterResult:
    """Filter LLM output for regulatory compliance.

    Args:
        text: LLM-generated text to filter.
        region: Region code ("none", "cn").

    Returns:
        ContentFilterResult with filtered text, count, and categories.
    """
    if text is None:
        return ContentFilterResult(text="", filtered_count=0, categories=set(), region=region)

    try:
        filter_region = ContentFilterRegion(region.lower())
    except ValueError:
        filter_region = ContentFilterRegion.NONE

    if filter_region == ContentFilterRegion.NONE:
        return ContentFilterResult(text=text, filtered_count=0, categories=set(), region=region)

    rules = _REGION_RULES.get(filter_region, [])
    replacement = _REGION_REPLACEMENTS.get(filter_region, "[filtered]")

    count = 0
    categories: set[str] = set()

    for pattern, category in rules:
        matches = pattern.findall(text)
        if matches:
            text = pattern.sub(replacement, text)
            count += len(matches)
            categories.add(category)

    if count > 0:
        logger.warning(
            "content_filter.applied region=%s count=%d categories=%s",
            region,
            count,
            ",".join(sorted(categories)),
        )

    return ContentFilterResult(
        text=text,
        filtered_count=count,
        categories=categories,
        region=region,
    )


def get_org_filter_region(data_policy: dict) -> str:
    """Extract the content filter region from an org's data policy.

    data_policy_json supports:
        {"content_filter_region": "cn", ...}

    Defaults to "none" if not set.
    """
    return data_policy.get("content_filter_region", "none")
