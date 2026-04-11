# ruff: noqa: INP001
"""Tests for bookkeeping models, categorization, and export services."""

from __future__ import annotations

import json
from datetime import date

import pytest

# --- Model Tests ---


class TestBookkeepingModels:
    """Test model defaults and JSON properties."""

    def test_worker_defaults(self):
        from app.models.bookkeeping import BkWorker

        w = BkWorker(organization_id="00000000-0000-0000-0000-000000000001", name="John")
        assert w.status == "available"
        assert w.safety_certs == []

    def test_worker_safety_certs_roundtrip(self):
        from app.models.bookkeeping import BkWorker

        certs = [{"name": "CSTS", "expiry_date": "2026-06-01", "certificate_number": "123"}]
        w = BkWorker(
            organization_id="00000000-0000-0000-0000-000000000001",
            name="John",
            safety_certs_json=json.dumps(certs),
        )
        assert w.safety_certs == certs
        assert w.safety_certs[0]["name"] == "CSTS"

    def test_client_defaults(self):
        from app.models.bookkeeping import BkClient

        c = BkClient(organization_id="00000000-0000-0000-0000-000000000001", name="Acme Corp")
        assert c.billing_terms == "net30"

    def test_job_defaults(self):
        from app.models.bookkeeping import BkJob

        j = BkJob(organization_id="00000000-0000-0000-0000-000000000001", name="Site A")
        assert j.status == "active"

    def test_placement_rates(self):
        from app.models.bookkeeping import BkPlacement

        p = BkPlacement(
            organization_id="00000000-0000-0000-0000-000000000001",
            worker_id="00000000-0000-0000-0000-000000000002",
            job_id="00000000-0000-0000-0000-000000000003",
            start_date=date(2026, 3, 1),
            bill_rate=55.0,
            pay_rate=35.0,
        )
        assert p.bill_rate - p.pay_rate == 20.0
        assert p.status == "active"

    def test_timesheet_defaults(self):
        from app.models.bookkeeping import BkTimesheet

        ts = BkTimesheet(
            organization_id="00000000-0000-0000-0000-000000000001",
            worker_id="00000000-0000-0000-0000-000000000002",
            job_id="00000000-0000-0000-0000-000000000003",
            work_date=date(2026, 3, 22),
        )
        assert ts.status == "pending"
        assert ts.regular_hours == 0.0
        assert ts.overtime_hours == 0.0

    def test_expense_ocr_data_roundtrip(self):
        from app.models.bookkeeping import BkExpense

        ocr = {"vendor": "Home Depot", "total": 152.50, "items": []}
        e = BkExpense(
            organization_id="00000000-0000-0000-0000-000000000001",
            amount=152.50,
            ocr_data_json=json.dumps(ocr),
        )
        assert e.ocr_data["vendor"] == "Home Depot"

    def test_invoice_defaults(self):
        from app.models.bookkeeping import BkInvoice

        inv = BkInvoice(
            organization_id="00000000-0000-0000-0000-000000000001",
            client_id="00000000-0000-0000-0000-000000000002",
        )
        assert inv.status == "draft"
        assert inv.subtotal == 0.0

    def test_transaction_types(self):
        from app.models.bookkeeping import BkTransaction

        t = BkTransaction(
            organization_id="00000000-0000-0000-0000-000000000001",
            type="income",
            amount=1000.0,
            gst_amount=50.0,
        )
        assert t.type == "income"
        assert t.amount == 1000.0


# --- Categorization Tests ---


class TestCategorization:
    """Test regex-based expense categorization."""

    def test_home_depot(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("Home Depot #5432") == "materials"

    def test_shell_gas(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("Shell Canada") == "fuel"

    def test_canadian_tire(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("Canadian Tire Store") == "tools"

    def test_marks_work(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("Marks Work Warehouse") == "ppe"

    def test_tim_hortons(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("Tim Hortons #1234") == "food"

    def test_napa_auto(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("NAPA Auto Parts") == "vehicle"

    def test_staples(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("Staples Business") == "office"

    def test_sunbelt_rentals(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("Sunbelt Rentals") == "equipment"

    def test_impark(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("Impark") == "parking"

    def test_unknown_vendor_fallback_to_items(self):
        from app.services.bookkeeping_categorization import categorize_expense

        items = [{"description": "2x4 lumber 8ft"}]
        assert categorize_expense("Random Store", items) == "materials"

    def test_item_fuel(self):
        from app.services.bookkeeping_categorization import categorize_expense

        items = [{"description": "diesel fuel 50L"}]
        assert categorize_expense(None, items) == "fuel"

    def test_item_ppe(self):
        from app.services.bookkeeping_categorization import categorize_expense

        items = [{"description": "hard hat with visor"}]
        assert categorize_expense(None, items) == "ppe"

    def test_no_match(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("Unknown Vendor LLC") == "other"

    def test_none_vendor_no_items(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense(None) == "other"

    def test_case_insensitive(self):
        from app.services.bookkeeping_categorization import categorize_expense

        assert categorize_expense("HOME DEPOT") == "materials"
        assert categorize_expense("shell") == "fuel"


# --- Export Tests ---


class TestQuickBooksExports:
    """Test CSV and IIF export generation."""

    def _sample_transactions(self):
        return [
            {
                "date": "2026-03-15",
                "type": "expense",
                "amount": 105.0,
                "gst_amount": 5.0,
                "description": "Lumber purchase",
                "job_id": "job-1",
                "category": "materials",
            },
            {
                "date": "2026-03-16",
                "type": "income",
                "amount": 2100.0,
                "gst_amount": 100.0,
                "description": "Invoice #001 payment",
                "job_id": "job-1",
                "category": None,
            },
        ]

    def test_csv_has_headers(self):
        from app.services.bookkeeping_exports import generate_csv

        csv = generate_csv(self._sample_transactions())
        first_line = csv.split("\n")[0]
        assert "Date" in first_line
        assert "Transaction Type" in first_line
        assert "GST Amount" in first_line

    def test_csv_row_count(self):
        from app.services.bookkeeping_exports import generate_csv

        csv = generate_csv(self._sample_transactions())
        lines = csv.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows

    def test_csv_expense_account(self):
        from app.services.bookkeeping_exports import generate_csv

        csv = generate_csv(self._sample_transactions())
        assert "Expenses" in csv
        assert "Revenue" in csv

    def test_iif_has_headers(self):
        from app.services.bookkeeping_exports import generate_iif

        iif = generate_iif(self._sample_transactions())
        assert "!TRNS" in iif
        assert "!SPL" in iif
        assert "!ENDTRNS" in iif

    def test_iif_expense_block(self):
        from app.services.bookkeeping_exports import generate_iif

        iif = generate_iif(self._sample_transactions())
        assert "CHECK" in iif
        assert "Construction Materials" in iif
        assert "GST Input Tax Credits" in iif

    def test_iif_income_block(self):
        from app.services.bookkeeping_exports import generate_iif

        iif = generate_iif(self._sample_transactions())
        assert "INVOICE" in iif
        assert "Accounts Receivable" in iif
        assert "GST Collected" in iif

    def test_iif_date_format(self):
        from app.services.bookkeeping_exports import _format_iif_date

        assert _format_iif_date("2026-03-15") == "3/15/2026"
        assert _format_iif_date(date(2026, 1, 5)) == "1/5/2026"

    def test_expense_summary(self):
        from app.services.bookkeeping_exports import generate_expense_summary

        expenses = [
            {"amount": 100.0, "gst_amount": 5.0, "category": "fuel", "job_id": "j1"},
            {"amount": 200.0, "gst_amount": 10.0, "category": "materials", "job_id": "j1"},
            {"amount": 50.0, "gst_amount": 2.50, "category": "fuel", "job_id": "j2"},
        ]
        summary = generate_expense_summary(expenses)
        assert summary["total"] == 350.0
        assert summary["total_gst"] == 17.5
        assert summary["by_category"]["fuel"]["count"] == 2
        assert summary["by_category"]["fuel"]["total"] == 150.0
        assert summary["by_category"]["materials"]["count"] == 1
        assert summary["by_job"]["j1"]["count"] == 2
        assert summary["by_job"]["j2"]["count"] == 1

    def test_expense_summary_uncategorized(self):
        from app.services.bookkeeping_exports import generate_expense_summary

        expenses = [{"amount": 25.0, "gst_amount": 1.25, "category": None, "job_id": None}]
        summary = generate_expense_summary(expenses)
        assert "uncategorized" in summary["by_category"]
        assert "unassigned" in summary["by_job"]


# --- Feature Flag Tests ---


class TestBookkeepingFeatureFlag:
    """Verify bookkeeping is in default feature flags."""

    def test_flag_exists(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert "bookkeeping" in DEFAULT_FEATURE_FLAGS
        assert DEFAULT_FEATURE_FLAGS["bookkeeping"] is True
