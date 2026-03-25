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
            "brand_voice": [
                ConfigItem("tone", "Tone", {"value": "Professional, confident, results-driven"}),
                ConfigItem("voice", "Voice", {"value": "We're the experts who get it done right the first time"}),
                ConfigItem("audience", "Audience", {"value": "Project managers, general contractors, property developers"}),
                ConfigItem("avoid", "Avoid", {"value": "Jargon overload, salesy language, exclamation marks"}),
                ConfigItem("keywords", "Keywords", {"value": "quality, precision, on-time, on-budget, trusted partner"}),
                ConfigItem("location", "Location", {"value": "Calgary, AB"}),
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
            "brand_voice": [
                ConfigItem("tone", "Tone", {"value": "Practical, community-focused, environmentally conscious"}),
                ConfigItem("voice", "Voice", {"value": "Straightforward experts who care about doing it right"}),
                ConfigItem("audience", "Audience", {"value": "Municipalities, commercial property managers, construction companies"}),
                ConfigItem("avoid", "Avoid", {"value": "Preachy environmentalism, corporate speak"}),
                ConfigItem("keywords", "Keywords", {"value": "reliable, clean, efficient, sustainable, local"}),
                ConfigItem("location", "Location", {"value": "Edmonton, AB"}),
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
            "brand_voice": [
                ConfigItem("tone", "Tone", {"value": "Approachable, reliable, energetic"}),
                ConfigItem("voice", "Voice", {"value": "We connect great people with great work"}),
                ConfigItem("audience", "Audience", {"value": "Job seekers, hiring managers, HR departments"}),
                ConfigItem("avoid", "Avoid", {"value": "Generic recruiter language, overpromising"}),
                ConfigItem("keywords", "Keywords", {"value": "opportunity, team, growth, flexible, skilled"}),
                ConfigItem("location", "Location", {"value": "Calgary, AB"}),
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

    # ── IoT / Sensor-Driven Verticals ────────────────────────────────────────

    "manufacturing": IndustryTemplate(
        id="manufacturing",
        name="Manufacturing",
        description="Equipment monitoring, OEE tracking, SPC quality control, work orders, shift reports, and inventory alerts.",
        icon="🏭",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["bookkeeping", "expense-capture", "doc-gen"],
        default_config={
            "equipment_types": [
                ConfigItem("cnc_machine", "CNC Machine", {"oee_target": 85, "maintenance_interval_hours": 500}),
                ConfigItem("press", "Hydraulic Press", {"oee_target": 80, "maintenance_interval_hours": 750}),
                ConfigItem("conveyor", "Conveyor System", {"oee_target": 95, "maintenance_interval_hours": 1000}),
                ConfigItem("packaging", "Packaging Line", {"oee_target": 90, "maintenance_interval_hours": 400}),
            ],
            "shift_schedule": [
                ConfigItem("day", "Day Shift", {"start": "06:00", "end": "14:00"}),
                ConfigItem("afternoon", "Afternoon Shift", {"start": "14:00", "end": "22:00"}),
                ConfigItem("night", "Night Shift", {"start": "22:00", "end": "06:00"}),
            ],
            "quality_params": [
                ConfigItem("temperature", "Temperature", {"unit": "°C", "usl": 200, "lsl": 180, "target": 190}),
                ConfigItem("pressure", "Pressure", {"unit": "PSI", "usl": 105, "lsl": 95, "target": 100}),
                ConfigItem("weight", "Product Weight", {"unit": "g", "usl": 502, "lsl": 498, "target": 500}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_equipment", "Register your equipment", "Add machines with OEE targets and maintenance intervals.", 1),
            OnboardingStep("configure_shifts", "Set up shift schedule", "Define shift times for production tracking.", 2),
            OnboardingStep("set_quality_params", "Define quality parameters", "Set SPC control limits for your products.", 3),
            OnboardingStep("connect_data_source", "Connect your data source", "Configure webhook or MQTT endpoint for sensor data.", 4),
            OnboardingStep("test_alert", "Trigger a test alert", "Send a sample reading to verify the alert pipeline.", 5),
        ],
    ),

    "oil_gas": IndustryTemplate(
        id="oil_gas",
        name="Oil & Gas",
        description="Wellhead monitoring, pipeline pressure tracking, leak detection, safety compliance, and production optimization.",
        icon="🛢️",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["bookkeeping", "expense-capture", "doc-gen"],
        default_config={
            "equipment_types": [
                ConfigItem("wellhead", "Wellhead", {"monitoring": ["pressure", "flow_rate", "temperature"]}),
                ConfigItem("pipeline_segment", "Pipeline Segment", {"monitoring": ["pressure", "flow_rate", "gas_detection"]}),
                ConfigItem("compressor", "Compressor Station", {"monitoring": ["vibration", "temperature", "pressure"]}),
                ConfigItem("separator", "Separator", {"monitoring": ["level", "pressure", "temperature"]}),
            ],
            "safety_thresholds": [
                ConfigItem("h2s", "H2S Gas Level", {"unit": "ppm", "warning": 10, "critical": 20, "evacuate": 50}),
                ConfigItem("pressure_high", "High Pressure", {"unit": "PSI", "warning": 900, "critical": 1000}),
                ConfigItem("leak_rate", "Leak Rate", {"unit": "L/min", "warning": 0.5, "critical": 2.0}),
            ],
            "compliance_docs": [
                ConfigItem("daily_production", "Daily Production Report", {"frequency": "daily"}),
                ConfigItem("safety_inspection", "Safety Inspection", {"frequency": "weekly"}),
                ConfigItem("environmental", "Environmental Compliance", {"frequency": "monthly"}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_assets", "Register wells and pipeline segments", "Add your production assets with monitoring parameters.", 1),
            OnboardingStep("set_safety_thresholds", "Configure safety thresholds", "Set warning and critical levels for gas, pressure, and leaks.", 2),
            OnboardingStep("connect_scada", "Connect SCADA/sensor feed", "Configure webhook or API endpoint for sensor data.", 3),
            OnboardingStep("test_alert", "Verify alert pipeline", "Send a test reading above threshold to confirm alerting works.", 4),
        ],
    ),

    "mining": IndustryTemplate(
        id="mining",
        name="Mining",
        description="Fleet tracking, haul truck telemetry, ore grade monitoring, blast zone safety, and production reporting.",
        icon="⛏️",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["bookkeeping", "expense-capture", "doc-gen"],
        default_config={
            "equipment_types": [
                ConfigItem("haul_truck", "Haul Truck", {"payload_tonnes": 150, "maintenance_interval_hours": 250}),
                ConfigItem("excavator", "Mining Excavator", {"bucket_size_m3": 15, "maintenance_interval_hours": 500}),
                ConfigItem("conveyor", "Conveyor Belt", {"capacity_tph": 2000, "maintenance_interval_hours": 1000}),
                ConfigItem("drill", "Blast Hole Drill", {"depth_m": 15, "maintenance_interval_hours": 300}),
            ],
            "safety_zones": [
                ConfigItem("blast_zone", "Blast Zone", {"radius_m": 500, "clearance_time_min": 30}),
                ConfigItem("pit_edge", "Pit Edge", {"buffer_m": 15}),
                ConfigItem("haul_road", "Haul Road", {"speed_limit_kph": 40}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_fleet", "Register your fleet", "Add haul trucks, excavators, and drills with specs.", 1),
            OnboardingStep("define_zones", "Define safety zones", "Set blast zone radii, pit edge buffers, and speed limits.", 2),
            OnboardingStep("connect_telemetry", "Connect fleet telemetry", "Configure GPS/telemetry webhook for haul truck data.", 3),
            OnboardingStep("test_report", "Generate a test production report", "Verify ore grade and tonnage reporting.", 4),
        ],
    ),

    "agriculture": IndustryTemplate(
        id="agriculture",
        name="Agriculture",
        description="Soil monitoring, irrigation scheduling, weather integration, yield prediction, crop health alerts, and spray timing.",
        icon="🌾",
        feature_flags={
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
        },
        skills=["doc-gen"],
        default_config={
            "sensor_types": [
                ConfigItem("soil_moisture", "Soil Moisture", {"unit": "%", "optimal_min": 25, "optimal_max": 45}),
                ConfigItem("soil_temp", "Soil Temperature", {"unit": "°C", "planting_min": 10}),
                ConfigItem("weather_station", "Weather Station", {"metrics": ["temp", "humidity", "wind", "rain"]}),
                ConfigItem("ndvi", "NDVI / Drone Imagery", {"healthy_min": 0.6, "stress_threshold": 0.3}),
            ],
            "crop_types": [
                ConfigItem("wheat", "Wheat", {"season": "spring", "growth_days": 120}),
                ConfigItem("canola", "Canola", {"season": "spring", "growth_days": 100}),
                ConfigItem("barley", "Barley", {"season": "spring", "growth_days": 90}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_fields", "Register your fields", "Add field names, acreage, and crop assignments.", 1),
            OnboardingStep("connect_sensors", "Connect soil and weather sensors", "Configure webhook or API for sensor readings.", 2),
            OnboardingStep("set_thresholds", "Set irrigation and alert thresholds", "Define moisture levels that trigger irrigation recommendations.", 3),
            OnboardingStep("test_alert", "Verify alert pipeline", "Send a test reading to confirm notifications work.", 4),
        ],
    ),

    "logistics": IndustryTemplate(
        id="logistics",
        name="Logistics & Warehousing",
        description="Inventory tracking, fleet management, route optimization, dock scheduling, ETA prediction, and shipping docs.",
        icon="📦",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["bookkeeping", "expense-capture", "doc-gen"],
        default_config={
            "warehouse_zones": [
                ConfigItem("receiving", "Receiving Dock", {"capacity": "10 bays"}),
                ConfigItem("storage", "Storage Area", {"racks": 200, "sku_capacity": 5000}),
                ConfigItem("picking", "Pick/Pack Zone", {"stations": 8}),
                ConfigItem("shipping", "Shipping Dock", {"capacity": "8 bays"}),
            ],
            "fleet": [
                ConfigItem("truck", "Delivery Truck", {"capacity_kg": 5000}),
                ConfigItem("van", "Cargo Van", {"capacity_kg": 1500}),
                ConfigItem("forklift", "Forklift", {"capacity_kg": 3000}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("configure_warehouse", "Set up warehouse zones", "Define receiving, storage, picking, and shipping areas.", 1),
            OnboardingStep("add_fleet", "Register delivery fleet", "Add vehicles with capacity specs.", 2),
            OnboardingStep("connect_scanning", "Connect barcode/RFID scanning", "Configure webhook for inventory scan events.", 3),
            OnboardingStep("test_shipment", "Process a test shipment", "Create a pick, pack, and ship workflow to verify the pipeline.", 4),
        ],
    ),

    "energy_utilities": IndustryTemplate(
        id="energy_utilities",
        name="Energy & Utilities",
        description="Smart meter monitoring, grid load forecasting, outage detection, demand response, and OEE for generation assets.",
        icon="⚡",
        feature_flags={
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["doc-gen"],
        default_config={
            "asset_types": [
                ConfigItem("smart_meter", "Smart Meter", {"reading_interval_min": 15}),
                ConfigItem("transformer", "Transformer", {"monitoring": ["temperature", "load_pct", "oil_level"]}),
                ConfigItem("solar_array", "Solar Array", {"capacity_kw": 500, "monitoring": ["output_kw", "irradiance"]}),
                ConfigItem("wind_turbine", "Wind Turbine", {"capacity_kw": 2000, "monitoring": ["output_kw", "wind_speed", "vibration"]}),
            ],
            "alert_thresholds": [
                ConfigItem("grid_load", "Grid Load Warning", {"warning_pct": 85, "critical_pct": 95}),
                ConfigItem("transformer_temp", "Transformer Temperature", {"warning_c": 85, "critical_c": 100}),
                ConfigItem("outage", "Outage Detection", {"timeout_seconds": 120}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_assets", "Register generation and grid assets", "Add meters, transformers, solar/wind units.", 1),
            OnboardingStep("set_thresholds", "Configure alert thresholds", "Set load and temperature warning levels.", 2),
            OnboardingStep("connect_telemetry", "Connect meter/SCADA data", "Configure webhook or API for telemetry readings.", 3),
            OnboardingStep("test_alert", "Verify alert pipeline", "Send a test reading above threshold.", 4),
        ],
    ),

    "healthcare_pharma": IndustryTemplate(
        id="healthcare_pharma",
        name="Healthcare & Pharma",
        description="Clean room monitoring, cold chain compliance, equipment calibration tracking, batch records, and regulatory docs.",
        icon="🏥",
        feature_flags={
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["doc-gen"],
        default_config={
            "monitoring_zones": [
                ConfigItem("clean_room", "Clean Room", {"iso_class": 7, "particle_limit": 352000, "temp_range_c": "20-22", "humidity_pct": "45-55"}),
                ConfigItem("cold_storage", "Cold Storage", {"temp_range_c": "2-8", "alert_deviation_c": 1}),
                ConfigItem("freezer", "Ultra-Low Freezer", {"temp_range_c": "-80 to -70", "alert_deviation_c": 2}),
            ],
            "calibration_schedule": [
                ConfigItem("thermometer", "Thermometer", {"interval_days": 90}),
                ConfigItem("pressure_gauge", "Pressure Gauge", {"interval_days": 180}),
                ConfigItem("balance", "Analytical Balance", {"interval_days": 365}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_zones", "Register monitoring zones", "Add clean rooms, cold storage, and freezer units with specs.", 1),
            OnboardingStep("set_calibration", "Set calibration schedules", "Define calibration intervals for each instrument type.", 2),
            OnboardingStep("connect_sensors", "Connect environmental sensors", "Configure webhook for temperature, humidity, and particle data.", 3),
            OnboardingStep("test_compliance", "Generate a test compliance report", "Verify cold chain and clean room documentation.", 4),
        ],
    ),

    "food_beverage": IndustryTemplate(
        id="food_beverage",
        name="Food & Beverage",
        description="HACCP compliance, cold chain monitoring, spoilage prevention, batch tracking, line speed optimization, and CIP cycle logging.",
        icon="🍽️",
        feature_flags={
            "bookkeeping": True,
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["bookkeeping", "expense-capture", "doc-gen"],
        default_config={
            "haccp_checkpoints": [
                ConfigItem("receiving_temp", "Receiving Temperature Check", {"target_c": 4, "max_c": 7, "frequency": "each delivery"}),
                ConfigItem("cooking_temp", "Cooking Temperature", {"target_c": 74, "min_c": 72, "frequency": "each batch"}),
                ConfigItem("cooling", "Cooling Rate", {"max_hours_to_5c": 4, "frequency": "each batch"}),
                ConfigItem("storage_temp", "Storage Temperature", {"target_c": 3, "max_c": 5, "frequency": "continuous"}),
            ],
            "production_lines": [
                ConfigItem("line_1", "Production Line 1", {"product": "Main product", "target_units_hr": 500}),
                ConfigItem("line_2", "Production Line 2", {"product": "Secondary product", "target_units_hr": 300}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_checkpoints", "Set up HACCP checkpoints", "Define critical control points with temperature limits.", 1),
            OnboardingStep("add_lines", "Register production lines", "Add lines with target throughput.", 2),
            OnboardingStep("connect_sensors", "Connect temperature sensors", "Configure webhook for cold chain and cooking temp data.", 3),
            OnboardingStep("test_haccp_report", "Generate a test HACCP report", "Verify compliance documentation pipeline.", 4),
        ],
    ),

    "smart_buildings": IndustryTemplate(
        id="smart_buildings",
        name="Smart Buildings",
        description="HVAC optimization, occupancy monitoring, energy metering, access control events, comfort management, and maintenance scheduling.",
        icon="🏢",
        feature_flags={
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
        },
        skills=["doc-gen"],
        default_config={
            "building_systems": [
                ConfigItem("hvac", "HVAC System", {"zones": 12, "target_temp_c": 22, "tolerance_c": 1.5}),
                ConfigItem("lighting", "Lighting Control", {"zones": 20, "schedule": "occupancy-based"}),
                ConfigItem("energy_meter", "Energy Meter", {"reading_interval_min": 15}),
                ConfigItem("access_control", "Access Control", {"entry_points": 8}),
            ],
            "comfort_targets": [
                ConfigItem("temperature", "Temperature", {"min_c": 21, "max_c": 24}),
                ConfigItem("humidity", "Humidity", {"min_pct": 30, "max_pct": 60}),
                ConfigItem("co2", "CO2 Level", {"max_ppm": 1000, "warning_ppm": 800}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_systems", "Register building systems", "Add HVAC zones, meters, and access points.", 1),
            OnboardingStep("set_comfort", "Set comfort targets", "Define temperature, humidity, and CO2 thresholds.", 2),
            OnboardingStep("connect_bms", "Connect building management system", "Configure webhook or BACnet/Modbus gateway.", 3),
            OnboardingStep("test_report", "Generate a test energy report", "Verify energy consumption and comfort reporting.", 4),
        ],
    ),

    "telecom": IndustryTemplate(
        id="telecom",
        name="Telecom",
        description="Tower health monitoring, network traffic analysis, capacity planning, outage prediction, and power backup tracking.",
        icon="📡",
        feature_flags={
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["doc-gen"],
        default_config={
            "asset_types": [
                ConfigItem("cell_tower", "Cell Tower", {"monitoring": ["signal_strength", "traffic_load", "power_status"]}),
                ConfigItem("fiber_node", "Fiber Node", {"monitoring": ["throughput", "latency", "error_rate"]}),
                ConfigItem("power_backup", "Power Backup (UPS/Generator)", {"monitoring": ["battery_pct", "fuel_level", "runtime_hours"]}),
            ],
            "alert_thresholds": [
                ConfigItem("signal", "Signal Degradation", {"warning_dbm": -90, "critical_dbm": -100}),
                ConfigItem("traffic", "Traffic Overload", {"warning_pct": 80, "critical_pct": 95}),
                ConfigItem("power", "Power Backup Low", {"warning_pct": 30, "critical_pct": 10}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_assets", "Register network assets", "Add towers, fiber nodes, and backup power units.", 1),
            OnboardingStep("set_thresholds", "Configure alert thresholds", "Set signal, traffic, and power warning levels.", 2),
            OnboardingStep("connect_nms", "Connect network management system", "Configure SNMP trap or webhook for network events.", 3),
            OnboardingStep("test_alert", "Verify alert pipeline", "Trigger a test alert to confirm notification delivery.", 4),
        ],
    ),

    "water_wastewater": IndustryTemplate(
        id="water_wastewater",
        name="Water & Wastewater",
        description="Flow monitoring, pH/turbidity tracking, treatment compliance, pump health, regulatory reporting, and chemical dosing alerts.",
        icon="💧",
        feature_flags={
            "document_generation": True,
            "email": True,
            "cron_jobs": True,
            "approvals": True,
        },
        skills=["doc-gen"],
        default_config={
            "monitoring_points": [
                ConfigItem("influent", "Influent", {"metrics": ["flow_rate", "pH", "turbidity", "BOD"]}),
                ConfigItem("effluent", "Effluent", {"metrics": ["flow_rate", "pH", "turbidity", "chlorine_residual"]}),
                ConfigItem("pump_station", "Pump Station", {"metrics": ["pressure", "vibration", "runtime_hours"]}),
            ],
            "compliance_limits": [
                ConfigItem("ph", "pH Range", {"min": 6.5, "max": 8.5}),
                ConfigItem("turbidity", "Turbidity", {"max_ntu": 1.0}),
                ConfigItem("chlorine", "Chlorine Residual", {"min_ppm": 0.2, "max_ppm": 4.0}),
                ConfigItem("bod", "BOD", {"max_mg_l": 25}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("add_points", "Register monitoring points", "Add influent, effluent, and pump station monitoring.", 1),
            OnboardingStep("set_limits", "Set compliance limits", "Define regulatory limits for pH, turbidity, chlorine, and BOD.", 2),
            OnboardingStep("connect_sensors", "Connect water quality sensors", "Configure webhook or SCADA for sensor readings.", 3),
            OnboardingStep("test_report", "Generate a test compliance report", "Verify regulatory reporting pipeline.", 4),
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
        skills=["bookkeeping", "expense-capture", "doc-gen", "competitor-intel"],
        default_config={
            "service_catalog": [
                ConfigItem("consulting", "Consulting", {"rate_per_hour": 175.00, "unit": "hour"}),
                ConfigItem("implementation", "Implementation", {"rate_per_hour": 150.00, "unit": "hour"}),
                ConfigItem("managed_service", "Managed Service", {"rate_per_month": 2500.00, "unit": "month"}),
                ConfigItem("training", "Training & Workshops", {"rate_per_day": 1200.00, "unit": "day"}),
            ],
            "project_stages": [
                ConfigItem("discovery", "Discovery", {"typical_days": 5}),
                ConfigItem("proposal", "Proposal", {"typical_days": 3}),
                ConfigItem("implementation", "Implementation", {"typical_days": 30}),
                ConfigItem("review", "Review & Handoff", {"typical_days": 5}),
            ],
        },
        onboarding_steps=[
            OnboardingStep("configure_services", "Set up service catalog", "Define your service types and rates.", 1),
            OnboardingStep("add_first_client", "Add your first client", "Create a client record.", 2),
            OnboardingStep("create_project", "Create a project", "Set up milestones, budget, and timeline.", 3),
            OnboardingStep("log_hours", "Log your first hours", "Record time against a project.", 4),
            OnboardingStep("generate_invoice", "Generate an invoice", "Bill a client for logged hours.", 5),
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
            "skills": t.skills,
            "config_categories": list(t.default_config.keys()),
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
        "construction", "contracting", "contractor", "building", "builder",
        "trades", "plumbing", "plumber", "electrical", "electrician",
        "hvac", "roofing", "roofer", "framing", "drywall", "concrete",
        "excavation", "excavating", "demolition", "renovation", "remodel",
        "carpentry", "carpenter", "masonry", "paving", "landscape",
        "general contractor", "gc", "infrastructure", "civil",
    ],
    "waste_management": [
        "waste", "recycling", "disposal", "hauling", "garbage", "trash",
        "junk", "removal", "sanitation", "environmental", "cleanup",
        "clean-up", "compost", "landfill", "dumpster", "bin",
        "biomedical", "hazardous", "remediation",
    ],
    "staffing": [
        "staffing", "recruitment", "recruiting", "temp", "temporary",
        "placement", "hiring", "hr", "human resources", "workforce",
        "employment", "agency", "personnel", "labour", "labor",
        "manpower", "talent",
    ],
    "day_trading": [
        "trading", "investing", "investment", "capital", "securities",
        "brokerage", "portfolio", "hedge", "fund", "asset management",
        "fintech", "financial", "wealth", "equity", "stock",
    ],
    "sports_betting": [
        "betting", "wagering", "sportsbook", "handicapping", "odds",
        "gambling", "casino", "sports analytics",
    ],
    "manufacturing": [
        "manufacturing", "manufacturer", "factory", "production", "assembly",
        "fabrication", "machining", "cnc", "injection molding", "stamping",
        "packaging", "industrial", "plant", "oem", "automotive parts",
        "plastics", "metalwork", "welding", "sheet metal",
    ],
    "oil_gas": [
        "oil", "gas", "petroleum", "pipeline", "drilling", "wellhead",
        "upstream", "midstream", "downstream", "refinery", "lng",
        "oilfield", "fracking", "well servicing", "completions",
        "production optimization", "natural gas",
    ],
    "mining": [
        "mining", "mine", "mineral", "quarry", "aggregate", "ore",
        "excavation", "haul", "blast", "tailings", "smelter",
        "gold", "copper", "coal", "potash", "lithium",
    ],
    "agriculture": [
        "agriculture", "farm", "farming", "crop", "grain", "ranch",
        "livestock", "dairy", "poultry", "irrigation", "agri",
        "harvest", "seed", "fertilizer", "agronomist", "agtech",
        "precision agriculture", "greenhouse", "horticulture",
    ],
    "logistics": [
        "logistics", "warehouse", "warehousing", "shipping", "freight",
        "distribution", "supply chain", "3pl", "fulfillment", "courier",
        "trucking", "transport", "cargo", "inventory", "dock",
        "last mile", "cold chain logistics",
    ],
    "energy_utilities": [
        "energy", "utility", "utilities", "power", "electricity", "grid",
        "solar", "wind", "renewable", "generation", "transmission",
        "distribution", "smart grid", "microgrid", "battery storage",
        "electric vehicle", "ev charging",
    ],
    "healthcare_pharma": [
        "healthcare", "hospital", "clinic", "pharma", "pharmaceutical",
        "biotech", "medical", "laboratory", "lab", "diagnostic",
        "clean room", "gmp", "fda", "health canada", "clinical trial",
        "drug", "vaccine", "medical device",
    ],
    "food_beverage": [
        "food", "beverage", "brewery", "bakery", "dairy", "meat",
        "seafood", "catering", "restaurant", "food processing",
        "haccp", "cfia", "fda food", "cold chain", "frozen",
        "snack", "confectionery", "distillery", "winery",
    ],
    "smart_buildings": [
        "smart building", "property management", "facilities",
        "building management", "bms", "hvac", "real estate",
        "commercial property", "office", "coworking", "campus",
        "building automation", "tenant", "occupancy",
    ],
    "telecom": [
        "telecom", "telecommunications", "wireless", "cellular",
        "network", "isp", "internet", "broadband", "fiber",
        "tower", "5g", "lte", "satellite", "cable",
    ],
    "water_wastewater": [
        "water", "wastewater", "sewage", "treatment plant",
        "water utility", "potable", "desalination", "effluent",
        "stormwater", "hydro", "water quality", "drinking water",
        "municipal water",
    ],
    "professional_services": [
        "consulting", "consultant", "advisory", "professional services",
        "accounting", "accountant", "legal", "law firm", "engineering",
        "architecture", "architect", "it services", "managed services",
        "marketing agency", "design agency", "creative agency",
    ],
}


def detect_industry(
    org_name: str,
    org_description: str = "",
    domain: str = "",
) -> dict:
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
