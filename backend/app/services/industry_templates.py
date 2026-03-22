"""Industry template definitions — bundled configurations for rapid client onboarding.

Templates define default feature flags, skills, config categories, and onboarding
steps for a given industry. When applied to an org, they seed OrgConfigData and
OrgOnboardingStep records with sensible defaults the client can then customize.

Templates are defined in code (not DB) — they're platform operator knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConfigItem:
    key: str
    label: str
    value: dict


@dataclass
class OnboardingStep:
    key: str
    label: str
    description: str = ""
    sort_order: int = 0


@dataclass
class IndustryTemplate:
    id: str
    name: str
    description: str
    icon: str  # emoji
    feature_flags: dict[str, bool]
    skills: list[str]
    default_config: dict[str, list[ConfigItem]]  # category -> items
    onboarding_steps: list[OnboardingStep]


TEMPLATES: dict[str, IndustryTemplate] = {
    "construction": IndustryTemplate(
        id="construction",
        name="Construction & Trades",
        description="Job costing, crew management, safety compliance, equipment tracking, and project-based invoicing.",
        icon="🏗️",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["bookkeeping", "job-costing", "staffing", "expense-capture", "doc-gen", "competitor-intel"],
        default_config={
            "cost_codes": [
                ConfigItem("labour", "Labour", {"code": "CC-100", "unit": "hour"}),
                ConfigItem("materials", "Materials", {"code": "CC-200", "unit": "each"}),
                ConfigItem("equipment_rental", "Equipment Rental", {"code": "CC-300", "unit": "day"}),
                ConfigItem("subcontractor", "Subcontractor", {"code": "CC-400", "unit": "lump_sum"}),
                ConfigItem("fuel", "Fuel & Transport", {"code": "CC-500", "unit": "litre"}),
                ConfigItem("ppe", "Safety & PPE", {"code": "CC-600", "unit": "each"}),
                ConfigItem("permits", "Permits & Fees", {"code": "CC-700", "unit": "each"}),
                ConfigItem("overhead", "Overhead", {"code": "CC-800", "unit": "percent"}),
            ],
            "crew_roles": [
                ConfigItem("labourer", "General Labourer", {"default_pay_rate": 22.00, "default_bill_rate": 32.00}),
                ConfigItem("skilled_labourer", "Skilled Labourer", {"default_pay_rate": 28.00, "default_bill_rate": 42.00}),
                ConfigItem("foreman", "Foreman", {"default_pay_rate": 35.00, "default_bill_rate": 52.00}),
                ConfigItem("operator", "Equipment Operator", {"default_pay_rate": 32.00, "default_bill_rate": 48.00}),
                ConfigItem("carpenter", "Carpenter", {"default_pay_rate": 30.00, "default_bill_rate": 45.00}),
                ConfigItem("electrician", "Electrician", {"default_pay_rate": 38.00, "default_bill_rate": 58.00}),
            ],
            "equipment": [
                ConfigItem("excavator", "Excavator", {"rate_per_hour": 150.00, "rate_per_day": 1000.00}),
                ConfigItem("bobcat", "Bobcat / Skid Steer", {"rate_per_hour": 85.00, "rate_per_day": 550.00}),
                ConfigItem("dump_truck", "Dump Truck", {"rate_per_hour": 95.00, "rate_per_day": 650.00}),
                ConfigItem("crane", "Crane", {"rate_per_hour": 250.00, "rate_per_day": 1800.00}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("review_cost_codes", "Review and customize cost codes", "Default construction cost codes have been added. Modify codes, rates, and categories to match your accounting.", 1),
            OnboardingStep("add_first_client", "Add your first client", "Create a client record for the company you bill.", 2),
            OnboardingStep("add_first_job", "Create your first job/project", "Set up a project with budget, site address, and client.", 3),
            OnboardingStep("add_workers", "Add your crew members", "Register workers with roles, rates, and safety certifications.", 4),
            OnboardingStep("configure_rates", "Set your bill and pay rates", "Review default rates for each crew role and adjust to your market.", 5),
            OnboardingStep("test_invoice", "Generate a test invoice", "Create a timesheet entry and generate an invoice to verify the workflow.", 6),
        ],
    ),

    "waste_management": IndustryTemplate(
        id="waste_management",
        name="Waste Management",
        description="Route scheduling, client communications, bin tracking, hauling invoicing, and compliance docs.",
        icon="♻️",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
        },
        skills=["bookkeeping", "expense-capture", "doc-gen", "competitor-intel"],
        default_config={
            "service_catalog": [
                ConfigItem("bin_rental_20yd", "20 Yard Bin Rental", {"price": 350.00, "unit": "per_haul", "description": "20 yard roll-off bin"}),
                ConfigItem("bin_rental_30yd", "30 Yard Bin Rental", {"price": 425.00, "unit": "per_haul", "description": "30 yard roll-off bin"}),
                ConfigItem("bin_rental_40yd", "40 Yard Bin Rental", {"price": 500.00, "unit": "per_haul", "description": "40 yard roll-off bin"}),
                ConfigItem("junk_removal", "Junk Removal", {"price": 0, "unit": "quote", "description": "Priced per job"}),
                ConfigItem("recycling_pickup", "Recycling Pickup", {"price": 175.00, "unit": "per_pickup", "description": "Scheduled recycling collection"}),
            ],
            "cost_codes": [
                ConfigItem("disposal_fees", "Disposal Fees", {"code": "WM-100", "unit": "tonne"}),
                ConfigItem("fuel", "Fuel", {"code": "WM-200", "unit": "litre"}),
                ConfigItem("vehicle_maintenance", "Vehicle Maintenance", {"code": "WM-300", "unit": "each"}),
                ConfigItem("bin_repair", "Bin Repair/Replacement", {"code": "WM-400", "unit": "each"}),
                ConfigItem("labour", "Labour", {"code": "WM-500", "unit": "hour"}),
            ],
            "competitors": [
                ConfigItem("example_competitor", "Example Competitor", {
                    "name": "Example Waste Co",
                    "website": "https://example.com",
                    "blog_url": "",
                    "keywords": ["junk removal", "waste management", "bin rental"],
                    "location": "Edmonton, AB",
                }),
            ],
        },
        onboarding_steps=[
            OnboardingStep("review_services", "Review service catalog", "Default services and pricing have been added. Adjust to your rates.", 1),
            OnboardingStep("add_first_client", "Add your first client", "Create a client record.", 2),
            OnboardingStep("configure_pricing", "Set your pricing", "Review bin rental, hauling, and service rates.", 3),
            OnboardingStep("test_invoice", "Generate a test invoice", "Create and review a sample invoice.", 4),
        ],
    ),

    "staffing": IndustryTemplate(
        id="staffing",
        name="Staffing Agency",
        description="Candidate tracking, shift scheduling, timesheet processing, margin analysis, and client invoicing.",
        icon="👥",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["bookkeeping", "staffing", "expense-capture", "doc-gen"],
        default_config={
            "crew_roles": [
                ConfigItem("labourer", "General Labourer", {"default_pay_rate": 18.00, "default_bill_rate": 28.00}),
                ConfigItem("warehouse", "Warehouse Worker", {"default_pay_rate": 19.00, "default_bill_rate": 29.00}),
                ConfigItem("forklift", "Forklift Operator", {"default_pay_rate": 22.00, "default_bill_rate": 34.00}),
                ConfigItem("admin", "Administrative", {"default_pay_rate": 20.00, "default_bill_rate": 32.00}),
                ConfigItem("skilled_trade", "Skilled Trade", {"default_pay_rate": 30.00, "default_bill_rate": 48.00}),
            ],
            "billing_terms": [
                ConfigItem("net15", "Net 15", {"days": 15}),
                ConfigItem("net30", "Net 30", {"days": 30}),
                ConfigItem("net45", "Net 45", {"days": 45}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_first_client", "Add your first client company", "The company you place workers at.", 1),
            OnboardingStep("configure_rates", "Set your bill and pay rates", "Default rates by role. Adjust to your market.", 2),
            OnboardingStep("add_workers", "Add your worker pool", "Register candidates with skills and availability.", 3),
            OnboardingStep("create_placement", "Create your first placement", "Assign a worker to a client site.", 4),
            OnboardingStep("log_timesheet", "Log a timesheet", "Record hours for a placed worker.", 5),
            OnboardingStep("generate_invoice", "Generate an invoice from timesheets", "Bill the client for approved hours.", 6),
        ],
    ),

    "day_trading": IndustryTemplate(
        id="day_trading",
        name="Day Trading & Investing",
        description="Portfolio monitoring, technical analysis, risk management, morning scans, and automated trade execution.",
        icon="📈",
        feature_flags={
            "paper_trading": True,
            "watchlist": True,
            "cost_tracker": True,
            "cron_jobs": True,
        },
        skills=["technical-analysis", "social-sentiment", "earnings-calendar", "portfolio-monitor", "stock-watchlist", "morning-scan", "market-research", "news-intelligence"],
        default_config={
            "trading_config": [
                ConfigItem("commission", "Commission per Trade", {"amount": 9.99, "currency": "CAD"}),
                ConfigItem("max_position_pct", "Max Position Size", {"percent": 5, "description": "Max % of portfolio per trade"}),
                ConfigItem("starting_balance", "Starting Balance", {"amount": 10000.00, "currency": "CAD"}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("configure_portfolio", "Set up your paper trading portfolio", "Choose starting balance and commission rates.", 1),
            OnboardingStep("add_watchlist", "Add stocks to your watchlist", "Start tracking tickers you're interested in.", 2),
            OnboardingStep("run_morning_scan", "Run your first morning scan", "Get a pre-market briefing from the Stock Analyst.", 3),
        ],
    ),

    "sports_betting": IndustryTemplate(
        id="sports_betting",
        name="Sports Betting",
        description="Odds comparison, bankroll management, bet tracking, post-game analysis, and automated resolution.",
        icon="🏒",
        feature_flags={
            "paper_bets": True,
            "cost_tracker": True,
            "cron_jobs": True,
        },
        skills=["odds-comparison", "bankroll-management", "resolve-bets", "nhl-edge"],
        default_config={
            "betting_config": [
                ConfigItem("bankroll", "Starting Bankroll", {"amount": 1000.00, "currency": "CAD"}),
                ConfigItem("max_bet_pct", "Max Bet Size", {"percent": 5, "description": "Max % of bankroll per bet"}),
                ConfigItem("sportsbook", "Primary Sportsbook", {"name": "Bet365", "region": "Alberta"}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("configure_bankroll", "Set your bankroll", "Choose starting amount and max bet size.", 1),
            OnboardingStep("place_first_bet", "Place your first paper bet", "Try a bet through the Sports Analyst.", 2),
        ],
    ),
}


def get_template(template_id: str) -> IndustryTemplate | None:
    return TEMPLATES.get(template_id)


def list_templates() -> list[dict]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "icon": t.icon,
            "skill_count": len(t.skills),
            "config_categories": list(t.default_config.keys()),
        }
        for t in TEMPLATES.values()
    ]
