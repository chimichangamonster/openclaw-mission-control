"""Industry template definitions — bundled configurations for rapid client onboarding.

Templates define default feature flags, skills, config categories, and onboarding
steps for a given industry. When applied to an org, they seed OrgConfigData and
OrgOnboardingStep records with sensible defaults the client can then customize.

Templates are defined in code (not DB) — they're platform operator knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ConfigItem:
    key: str
    label: str
    value: dict[str, Any]


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
        skills=[
            "bookkeeping",
            "job-costing",
            "staffing",
            "expense-capture",
            "doc-gen",
            "competitor-intel",
        ],
        default_config={
            "cost_codes": [
                ConfigItem("labour", "Labour", {"code": "CC-100", "unit": "hour"}),
                ConfigItem("materials", "Materials", {"code": "CC-200", "unit": "each"}),
                ConfigItem(
                    "equipment_rental", "Equipment Rental", {"code": "CC-300", "unit": "day"}
                ),
                ConfigItem(
                    "subcontractor", "Subcontractor", {"code": "CC-400", "unit": "lump_sum"}
                ),
                ConfigItem("fuel", "Fuel & Transport", {"code": "CC-500", "unit": "litre"}),
                ConfigItem("ppe", "Safety & PPE", {"code": "CC-600", "unit": "each"}),
                ConfigItem("permits", "Permits & Fees", {"code": "CC-700", "unit": "each"}),
                ConfigItem("overhead", "Overhead", {"code": "CC-800", "unit": "percent"}),
            ],
            "crew_roles": [
                ConfigItem(
                    "labourer",
                    "General Labourer",
                    {"default_pay_rate": 22.00, "default_bill_rate": 32.00},
                ),
                ConfigItem(
                    "skilled_labourer",
                    "Skilled Labourer",
                    {"default_pay_rate": 28.00, "default_bill_rate": 42.00},
                ),
                ConfigItem(
                    "foreman", "Foreman", {"default_pay_rate": 35.00, "default_bill_rate": 52.00}
                ),
                ConfigItem(
                    "operator",
                    "Equipment Operator",
                    {"default_pay_rate": 32.00, "default_bill_rate": 48.00},
                ),
                ConfigItem(
                    "carpenter",
                    "Carpenter",
                    {"default_pay_rate": 30.00, "default_bill_rate": 45.00},
                ),
                ConfigItem(
                    "electrician",
                    "Electrician",
                    {"default_pay_rate": 38.00, "default_bill_rate": 58.00},
                ),
            ],
            "equipment": [
                ConfigItem(
                    "excavator", "Excavator", {"rate_per_hour": 150.00, "rate_per_day": 1000.00}
                ),
                ConfigItem(
                    "bobcat",
                    "Bobcat / Skid Steer",
                    {"rate_per_hour": 85.00, "rate_per_day": 550.00},
                ),
                ConfigItem(
                    "dump_truck", "Dump Truck", {"rate_per_hour": 95.00, "rate_per_day": 650.00}
                ),
                ConfigItem("crane", "Crane", {"rate_per_hour": 250.00, "rate_per_day": 1800.00}),
            ],
            "brand_voice": [
                ConfigItem("tone", "Tone", {"value": "Professional, confident, results-driven"}),
                ConfigItem(
                    "voice",
                    "Voice",
                    {"value": "We're the experts who get it done right the first time"},
                ),
                ConfigItem(
                    "audience",
                    "Audience",
                    {"value": "Project managers, general contractors, property developers"},
                ),
                ConfigItem(
                    "avoid",
                    "Avoid",
                    {"value": "Jargon overload, salesy language, exclamation marks"},
                ),
                ConfigItem(
                    "keywords",
                    "Keywords",
                    {"value": "quality, precision, on-time, on-budget, trusted partner"},
                ),
                ConfigItem("location", "Location", {"value": "Calgary, AB"}),
            ],
            "chat_suggestions": [
                ConfigItem("job_costs", "Today's job costs", {"prompt": "What did today's jobs cost to run?"}),
                ConfigItem("invoice_status", "Invoice status", {"prompt": "Which invoices are still outstanding?"}),
                ConfigItem("crew_schedule", "Crew schedule", {"prompt": "Who's on which site this week?"}),
                ConfigItem("weekly_report", "Weekly report", {"prompt": "Generate this week's project status report"}),
            ],
        },
        onboarding_steps=[
            OnboardingStep(
                "review_cost_codes",
                "Review and customize cost codes",
                "Default construction cost codes have been added. Modify codes, rates, and categories to match your accounting.",
                1,
            ),
            OnboardingStep(
                "add_first_client",
                "Add your first client",
                "Create a client record for the company you bill.",
                2,
            ),
            OnboardingStep(
                "add_first_job",
                "Create your first job/project",
                "Set up a project with budget, site address, and client.",
                3,
            ),
            OnboardingStep(
                "add_workers",
                "Add your crew members",
                "Register workers with roles, rates, and safety certifications.",
                4,
            ),
            OnboardingStep(
                "configure_rates",
                "Set your bill and pay rates",
                "Review default rates for each crew role and adjust to your market.",
                5,
            ),
            OnboardingStep(
                "test_invoice",
                "Generate a test invoice",
                "Create a timesheet entry and generate an invoice to verify the workflow.",
                6,
            ),
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
        skills=["bookkeeping", "expense-capture", "doc-gen", "competitor-intel", "email-triage"],
        default_config={
            "service_catalog": [
                ConfigItem(
                    "bin_rental_20yd",
                    "20 Yard Bin Rental",
                    {"price": 350.00, "unit": "per_haul", "description": "20 yard roll-off bin"},
                ),
                ConfigItem(
                    "bin_rental_30yd",
                    "30 Yard Bin Rental",
                    {"price": 425.00, "unit": "per_haul", "description": "30 yard roll-off bin"},
                ),
                ConfigItem(
                    "bin_rental_40yd",
                    "40 Yard Bin Rental",
                    {"price": 500.00, "unit": "per_haul", "description": "40 yard roll-off bin"},
                ),
                ConfigItem(
                    "junk_removal",
                    "Junk Removal",
                    {"price": 0, "unit": "quote", "description": "Priced per job"},
                ),
                ConfigItem(
                    "recycling_pickup",
                    "Recycling Pickup",
                    {
                        "price": 175.00,
                        "unit": "per_pickup",
                        "description": "Scheduled recycling collection",
                    },
                ),
            ],
            "cost_codes": [
                ConfigItem("disposal_fees", "Disposal Fees", {"code": "WM-100", "unit": "tonne"}),
                ConfigItem("fuel", "Fuel", {"code": "WM-200", "unit": "litre"}),
                ConfigItem(
                    "vehicle_maintenance", "Vehicle Maintenance", {"code": "WM-300", "unit": "each"}
                ),
                ConfigItem(
                    "bin_repair", "Bin Repair/Replacement", {"code": "WM-400", "unit": "each"}
                ),
                ConfigItem("labour", "Labour", {"code": "WM-500", "unit": "hour"}),
            ],
            "competitors": [
                ConfigItem(
                    "example_competitor",
                    "Example Competitor",
                    {
                        "name": "Example Waste Co",
                        "website": "https://example.com",
                        "blog_url": "",
                        "keywords": ["junk removal", "waste management", "bin rental"],
                        "location": "Edmonton, AB",
                    },
                ),
            ],
            "brand_voice": [
                ConfigItem(
                    "tone",
                    "Tone",
                    {"value": "Practical, community-focused, environmentally conscious"},
                ),
                ConfigItem(
                    "voice",
                    "Voice",
                    {"value": "Straightforward experts who care about doing it right"},
                ),
                ConfigItem(
                    "audience",
                    "Audience",
                    {
                        "value": "Municipalities, commercial property managers, construction companies"
                    },
                ),
                ConfigItem(
                    "avoid", "Avoid", {"value": "Preachy environmentalism, corporate speak"}
                ),
                ConfigItem(
                    "keywords",
                    "Keywords",
                    {"value": "reliable, clean, efficient, sustainable, local"},
                ),
                ConfigItem("location", "Location", {"value": "Edmonton, AB"}),
            ],
            "chat_suggestions": [
                ConfigItem("triage_emails", "Triage emails", {"prompt": "Triage my inbox for today"}),
                ConfigItem("overdue_pickups", "Overdue pickups", {"prompt": "Any overdue pickups or missed routes?"}),
                ConfigItem("quote_job", "Quote a job", {"prompt": "Draft a quote for a new junk removal job"}),
                ConfigItem("competitor_scan", "Competitor summary", {"prompt": "What did this week's competitor scan find?"}),
            ],
        },
        onboarding_steps=[
            OnboardingStep(
                "review_services",
                "Review service catalog",
                "Default services and pricing have been added. Adjust to your rates.",
                1,
            ),
            OnboardingStep(
                "add_first_client", "Add your first client", "Create a client record.", 2
            ),
            OnboardingStep(
                "configure_pricing",
                "Set your pricing",
                "Review bin rental, hauling, and service rates.",
                3,
            ),
            OnboardingStep(
                "test_invoice", "Generate a test invoice", "Create and review a sample invoice.", 4
            ),
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
                ConfigItem(
                    "labourer",
                    "General Labourer",
                    {"default_pay_rate": 18.00, "default_bill_rate": 28.00},
                ),
                ConfigItem(
                    "warehouse",
                    "Warehouse Worker",
                    {"default_pay_rate": 19.00, "default_bill_rate": 29.00},
                ),
                ConfigItem(
                    "forklift",
                    "Forklift Operator",
                    {"default_pay_rate": 22.00, "default_bill_rate": 34.00},
                ),
                ConfigItem(
                    "admin",
                    "Administrative",
                    {"default_pay_rate": 20.00, "default_bill_rate": 32.00},
                ),
                ConfigItem(
                    "skilled_trade",
                    "Skilled Trade",
                    {"default_pay_rate": 30.00, "default_bill_rate": 48.00},
                ),
            ],
            "billing_terms": [
                ConfigItem("net15", "Net 15", {"days": 15}),
                ConfigItem("net30", "Net 30", {"days": 30}),
                ConfigItem("net45", "Net 45", {"days": 45}),
            ],
            "brand_voice": [
                ConfigItem("tone", "Tone", {"value": "Approachable, reliable, energetic"}),
                ConfigItem("voice", "Voice", {"value": "We connect great people with great work"}),
                ConfigItem(
                    "audience",
                    "Audience",
                    {"value": "Job seekers, hiring managers, HR departments"},
                ),
                ConfigItem(
                    "avoid", "Avoid", {"value": "Generic recruiter language, overpromising"}
                ),
                ConfigItem(
                    "keywords",
                    "Keywords",
                    {"value": "opportunity, team, growth, flexible, skilled"},
                ),
                ConfigItem("location", "Location", {"value": "Calgary, AB"}),
            ],
            "chat_suggestions": [
                ConfigItem("open_roles", "Open roles", {"prompt": "What roles are we trying to fill this week?"}),
                ConfigItem("timesheets_due", "Timesheets due", {"prompt": "Which timesheets are outstanding?"}),
                ConfigItem("candidate_shortlist", "Candidate shortlist", {"prompt": "Shortlist candidates for the latest role"}),
                ConfigItem("margin_check", "Margin check", {"prompt": "What are my margins on active placements?"}),
            ],
        },
        onboarding_steps=[
            OnboardingStep(
                "add_first_client",
                "Add your first client company",
                "The company you place workers at.",
                1,
            ),
            OnboardingStep(
                "configure_rates",
                "Set your bill and pay rates",
                "Default rates by role. Adjust to your market.",
                2,
            ),
            OnboardingStep(
                "add_workers",
                "Add your worker pool",
                "Register candidates with skills and availability.",
                3,
            ),
            OnboardingStep(
                "create_placement",
                "Create your first placement",
                "Assign a worker to a client site.",
                4,
            ),
            OnboardingStep(
                "log_timesheet", "Log a timesheet", "Record hours for a placed worker.", 5
            ),
            OnboardingStep(
                "generate_invoice",
                "Generate an invoice from timesheets",
                "Bill the client for approved hours.",
                6,
            ),
        ],
    ),
    # ── Service Verticals ────────────────────────────────────────────────────
    "professional_services": IndustryTemplate(
        id="professional_services",
        name="Professional Services",
        description="Client pipeline, proposal building, project tracking, hour logging, budget burn alerts, and status reporting.",
        icon="💼",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=[
            "bookkeeping",
            "expense-capture",
            "doc-gen",
            "competitor-intel",
            "lead-qualifier",
            "client-pipeline",
            "discovery-prep",
            "proposal-builder",
            "project-tracker",
        ],
        default_config={
            "service_catalog": [
                ConfigItem("consulting", "Consulting", {"rate_per_hour": 175.00, "unit": "hour"}),
                ConfigItem(
                    "implementation", "Implementation", {"rate_per_hour": 150.00, "unit": "hour"}
                ),
                ConfigItem(
                    "managed_service",
                    "Managed Service",
                    {"rate_per_month": 2500.00, "unit": "month"},
                ),
                ConfigItem(
                    "training", "Training & Workshops", {"rate_per_day": 1200.00, "unit": "day"}
                ),
            ],
            "project_stages": [
                ConfigItem("discovery", "Discovery", {"typical_days": 5}),
                ConfigItem("proposal", "Proposal", {"typical_days": 3}),
                ConfigItem("implementation", "Implementation", {"typical_days": 30}),
                ConfigItem("review", "Review & Handoff", {"typical_days": 5}),
            ],
            "chat_suggestions": [
                ConfigItem("pipeline_status", "Pipeline status", {"prompt": "What's in my client pipeline this week?"}),
                ConfigItem("project_burn", "Project burn", {"prompt": "Which projects are over 75% of budget?"}),
                ConfigItem("discovery_prep", "Discovery prep", {"prompt": "Prep me for my next discovery call"}),
                ConfigItem("proposal_draft", "Proposal draft", {"prompt": "Draft a proposal for the latest qualified lead"}),
            ],
        },
        onboarding_steps=[
            OnboardingStep(
                "configure_services",
                "Set up service catalog",
                "Define your service types and rates.",
                1,
            ),
            OnboardingStep(
                "add_first_client", "Add your first client", "Create a client record.", 2
            ),
            OnboardingStep(
                "create_project", "Create a project", "Set up milestones, budget, and timeline.", 3
            ),
            OnboardingStep(
                "log_hours", "Log your first hours", "Record time against a project.", 4
            ),
            OnboardingStep(
                "generate_invoice", "Generate an invoice", "Bill a client for logged hours.", 5
            ),
        ],
    ),
    "clean_technology": IndustryTemplate(
        id="clean_technology",
        name="Clean Technology & Equipment Sales",
        description="Capital equipment sales pipeline, waste treatment operations, regulatory compliance tracking, ROI modeling, and global market prospecting.",
        icon="🔬",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=[
            "bookkeeping",
            "invoicing",
            "expense-capture",
            "doc-gen",
            "competitor-intel",
            "lead-qualifier",
            "client-pipeline",
            "discovery-prep",
            "proposal-builder",
            "project-tracker",
            "social-media",
            "news-intelligence",
            "scheduling",
            "notifications",
            "document-intake",
            "roi-calculator",
            "regulatory-tracker",
            "waste-market-intel",
            "email-triage",
        ],
        default_config={
            "product_catalog": [
                ConfigItem(
                    "magnetgas", "MagnetGas Treatment System", {"price": "TBD", "unit": "system"}
                ),
                ConfigItem(
                    "eboiler", "Eboiler Steam/Hot Water", {"price": "TBD", "unit": "system"}
                ),
                ConfigItem(
                    "autoclave_shredder",
                    "Autoclave-Shredder MWI Series",
                    {"price": "TBD", "unit": "system"},
                ),
                ConfigItem(
                    "steam_microwave",
                    "Steam-Microwave Sterilizer",
                    {"price": "TBD", "unit": "system"},
                ),
                ConfigItem(
                    "medical_autoclave",
                    "Medical Waste Autoclave MWC Series",
                    {"price": "TBD", "unit": "system"},
                ),
                ConfigItem(
                    "container_washer",
                    "Container Washer QX1000",
                    {"price": "TBD", "unit": "system"},
                ),
            ],
            "sales_stages": [
                ConfigItem("lead", "Lead", {"typical_days": 14}),
                ConfigItem("qualification", "Qualification", {"typical_days": 21}),
                ConfigItem("site_assessment", "Site Assessment", {"typical_days": 30}),
                ConfigItem("proposal", "Proposal", {"typical_days": 14}),
                ConfigItem("negotiation", "Negotiation", {"typical_days": 30}),
                ConfigItem("purchase_order", "Purchase Order", {"typical_days": 14}),
                ConfigItem("installation", "Installation", {"typical_days": 90}),
                ConfigItem("commissioning", "Commissioning", {"typical_days": 30}),
            ],
            "cost_codes": [
                ConfigItem("equipment", "Equipment Purchase", {"code": "CT-100", "unit": "each"}),
                ConfigItem(
                    "installation",
                    "Installation & Integration",
                    {"code": "CT-200", "unit": "lump_sum"},
                ),
                ConfigItem(
                    "shipping", "Shipping & Logistics", {"code": "CT-300", "unit": "shipment"}
                ),
                ConfigItem(
                    "regulatory", "Regulatory & Certification", {"code": "CT-400", "unit": "each"}
                ),
                ConfigItem(
                    "training", "Training & Commissioning", {"code": "CT-500", "unit": "day"}
                ),
                ConfigItem(
                    "maintenance", "Maintenance & Spare Parts", {"code": "CT-600", "unit": "annual"}
                ),
                ConfigItem(
                    "consulting", "Consulting & Engineering", {"code": "CT-700", "unit": "hour"}
                ),
            ],
            "brand_voice": [
                ConfigItem(
                    "tone",
                    "Tone",
                    {"value": "Professional, technical, environmentally authoritative"},
                ),
                ConfigItem(
                    "voice",
                    "Voice",
                    {"value": "We engineer solutions that eliminate the problem at its source"},
                ),
                ConfigItem(
                    "audience",
                    "Audience",
                    {
                        "value": "Hospital administrators, government procurement, industrial facility managers, waste management directors"
                    },
                ),
                ConfigItem(
                    "avoid",
                    "Avoid",
                    {
                        "value": "Greenwashing, unsubstantiated claims, competitor bashing, oversimplifying regulatory requirements"
                    },
                ),
                ConfigItem(
                    "keywords",
                    "Keywords",
                    {
                        "value": "near-zero emissions, on-site treatment, proven technology, regulatory compliance, ROI, MagnetGas"
                    },
                ),
                ConfigItem(
                    "location",
                    "Location",
                    {"value": "Edmonton, AB — with offices in Montreal, Paris, Chongqing"},
                ),
            ],
            "regulatory_bodies": [
                ConfigItem(
                    "aepa",
                    "Alberta Environment and Protected Areas",
                    {
                        "jurisdiction": "Alberta",
                        "governs": "EPEA facility approvals for waste treatment",
                    },
                ),
                ConfigItem(
                    "absa",
                    "Alberta Boilers Safety Association",
                    {"jurisdiction": "Alberta", "governs": "CRN for pressure vessels and boilers"},
                ),
                ConfigItem(
                    "csa",
                    "Canadian Standards Association",
                    {
                        "jurisdiction": "Canada",
                        "governs": "electrical and gas appliance certification",
                    },
                ),
                ConfigItem(
                    "epa",
                    "Environmental Protection Agency",
                    {
                        "jurisdiction": "United States",
                        "governs": "medical waste treatment facility permits",
                    },
                ),
                ConfigItem(
                    "health_canada",
                    "Health Canada",
                    {
                        "jurisdiction": "Canada",
                        "governs": "biomedical waste classification and handling",
                    },
                ),
                ConfigItem(
                    "who",
                    "World Health Organization",
                    {
                        "jurisdiction": "International",
                        "governs": "medical waste management guidelines",
                    },
                ),
            ],
            "chat_suggestions": [
                ConfigItem("pipeline_status", "Sales pipeline", {"prompt": "What's in the sales pipeline this week?"}),
                ConfigItem("regulatory_updates", "Regulatory updates", {"prompt": "Any regulatory updates I should know about?"}),
                ConfigItem("market_intel", "Market intel", {"prompt": "Summarize this week's waste market intel scan"}),
                ConfigItem("roi_model", "ROI model", {"prompt": "Model ROI for a new prospect"}),
            ],
        },
        onboarding_steps=[
            OnboardingStep(
                "review_products",
                "Review product catalog",
                "Default Magnetik product catalog loaded. Add pricing and customize specs.",
                1,
            ),
            OnboardingStep(
                "configure_sales_stages",
                "Configure sales pipeline stages",
                "Review the 8-stage pipeline from Lead to Commissioning.",
                2,
            ),
            OnboardingStep(
                "add_first_client",
                "Add your first prospect",
                "Create a prospect record in the pipeline.",
                3,
            ),
            OnboardingStep(
                "upload_regulatory_docs",
                "Upload regulatory documentation",
                "Add certification docs, emission test reports, and compliance evidence.",
                4,
            ),
            OnboardingStep(
                "connect_email",
                "Connect email account",
                "Link your info@magnetiksolutions.com mailbox.",
                5,
            ),
            OnboardingStep(
                "test_proposal",
                "Generate a test proposal",
                "Create a proposal with ROI modeling for a sample prospect.",
                6,
            ),
        ],
    ),
}


def get_template(template_id: str) -> IndustryTemplate | None:
    return TEMPLATES.get(template_id)


# Human-readable labels for config categories
CATEGORY_LABELS: dict[str, str] = {
    "cost_codes": "Cost Codes",
    "crew_roles": "Crew Roles & Rates",
    "equipment": "Equipment Tracking",
    "brand_voice": "Brand Voice & Tone",
    "service_catalog": "Service Catalog",
    "billing_terms": "Billing Terms",
    "competitors": "Competitors",
    "project_stages": "Project Stages",
    "product_catalog": "Product Catalog",
    "sales_stages": "Sales Pipeline Stages",
    "regulatory_bodies": "Regulatory Bodies",
    "chat_suggestions": "Chat Suggestions",
}


def list_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "icon": t.icon,
            "skill_count": len(t.skills),
            "skills": t.skills,
            "config_categories": [
                {
                    "key": cat,
                    "label": CATEGORY_LABELS.get(cat, cat.replace("_", " ").title()),
                    "item_count": len(items),
                }
                for cat, items in t.default_config.items()
            ],
            "onboarding_step_count": len(t.onboarding_steps),
            "feature_flags": list(t.feature_flags.keys()),
        }
        for t in TEMPLATES.values()
    ]


# ---------------------------------------------------------------------------
# Industry auto-detection from org name / description
# ---------------------------------------------------------------------------

_INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "construction": [
        "construction",
        "contracting",
        "contractor",
        "building",
        "builder",
        "trades",
        "plumbing",
        "plumber",
        "electrical",
        "electrician",
        "hvac",
        "roofing",
        "roofer",
        "framing",
        "drywall",
        "concrete",
        "excavation",
        "excavating",
        "demolition",
        "renovation",
        "remodel",
        "carpentry",
        "carpenter",
        "masonry",
        "paving",
        "landscape",
        "general contractor",
        "gc",
        "infrastructure",
        "civil",
    ],
    "waste_management": [
        "waste",
        "recycling",
        "disposal",
        "hauling",
        "garbage",
        "trash",
        "junk",
        "removal",
        "sanitation",
        "environmental",
        "cleanup",
        "clean-up",
        "compost",
        "landfill",
        "dumpster",
        "bin",
        "biomedical",
        "hazardous",
        "remediation",
    ],
    "staffing": [
        "staffing",
        "recruitment",
        "recruiting",
        "temp",
        "temporary",
        "placement",
        "hiring",
        "hr",
        "human resources",
        "workforce",
        "employment",
        "agency",
        "personnel",
        "labour",
        "labor",
        "manpower",
        "talent",
    ],
    "professional_services": [
        "consulting",
        "consultant",
        "advisory",
        "professional services",
        "accounting",
        "accountant",
        "legal",
        "law firm",
        "engineering",
        "architecture",
        "architect",
        "it services",
        "managed services",
        "marketing agency",
        "design agency",
        "creative agency",
    ],
    "clean_technology": [
        "clean tech",
        "clean technology",
        "cleantech",
        "waste treatment",
        "medical waste",
        "biomedical waste",
        "gasification",
        "sterilization",
        "autoclave",
        "emissions reduction",
        "environmental technology",
        "waste-to-energy",
        "thermal treatment",
        "magnetgas",
        "eboiler",
        "incineration alternative",
        "on-site treatment",
    ],
}


def detect_industry(
    org_name: str,
    org_description: str = "",
    domain: str = "",
) -> dict[str, Any]:
    """Detect the most likely industry template from org context.

    Returns ``{"template_id": str | None, "confidence": float, "all_scores": dict}``.
    Confidence is 0.0–1.0. Returns None if no match above threshold.
    """
    text = f"{org_name} {org_description} {domain}".lower()
    scores: dict[str, int] = {}

    for template_id, keywords in _INDUSTRY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[template_id] = score

    if not scores:
        return {"template_id": None, "confidence": 0.0, "all_scores": {}}

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_score = scores[best]
    # Normalize: 1 keyword match = 0.4, 2 = 0.6, 3+ = 0.8+
    confidence = min(1.0, 0.2 + best_score * 0.2)

    return {
        "template_id": best,
        "confidence": round(confidence, 2),
        "all_scores": {k: round(min(1.0, 0.2 + v * 0.2), 2) for k, v in scores.items()},
    }
