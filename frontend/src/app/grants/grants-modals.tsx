"use client";

/**
 * Grants tracker modals (item 118 sub-B Phase 2b.1).
 *
 * Two modals share the backdrop + frame substrate: CreateGrantModal,
 * EditGrantModal. Single file mirroring `regulatory-modals.tsx`.
 *
 * Determinism posture per `feedback_determinism_first_for_high_liability.md`:
 * zero LLM in path. No template-prefill, no URL-scrape, no status auto-advance.
 * Operator-typed only.
 */

import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  createGrant,
  updateGrant,
  type Grant,
  type GrantCreate,
  type GrantUpdate,
} from "@/lib/grants-api";

import { amountLabel } from "./page";
import styles from "./grants.module.css";

const STATUS_OPTIONS: ReadonlyArray<string> = [
  "planned",
  "drafting",
  "submitted",
  "under_review",
  "awarded",
  "declined",
  "withdrawn",
  "completed",
];

const TEMPLATE_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "(none)" },
  { value: "era-industrial-transformation", label: "ERA Industrial Transformation" },
  { value: "alberta-innovates", label: "Alberta Innovates" },
  { value: "sred", label: "SR&ED" },
  { value: "custom", label: "Custom" },
];

const CURRENCY_OPTIONS: ReadonlyArray<string> = ["CAD", "USD"];

interface FormState {
  granting_body: string;
  program_name: string;
  application_template_slug: string;
  application_status: string;
  awarded_amount: string;
  matched_funding_amount: string;
  total_project_value: string;
  currency: string;
  cash_coinvestment_required_pct: string;
  cash_coinvestment_source: string;
  project_start_date: string;
  project_end_date: string;
  incorporation_required_entity: string;
  contact_person: string;
  contact_email: string;
  program_url: string;
  notes_md: string;
}

const emptyForm: FormState = {
  granting_body: "",
  program_name: "",
  application_template_slug: "",
  application_status: "planned",
  awarded_amount: "",
  matched_funding_amount: "",
  total_project_value: "",
  currency: "CAD",
  cash_coinvestment_required_pct: "",
  cash_coinvestment_source: "",
  project_start_date: "",
  project_end_date: "",
  incorporation_required_entity: "",
  contact_person: "",
  contact_email: "",
  program_url: "",
  notes_md: "",
};

function fromGrant(grant: Grant): FormState {
  return {
    granting_body: grant.granting_body ?? "",
    program_name: grant.program_name ?? "",
    application_template_slug: grant.application_template_slug ?? "",
    application_status: grant.application_status ?? "planned",
    awarded_amount: grant.awarded_amount ?? "",
    matched_funding_amount: grant.matched_funding_amount ?? "",
    total_project_value: grant.total_project_value ?? "",
    currency: grant.currency ?? "CAD",
    cash_coinvestment_required_pct: grant.cash_coinvestment_required_pct ?? "",
    cash_coinvestment_source: grant.cash_coinvestment_source ?? "",
    project_start_date: grant.project_start_date ?? "",
    project_end_date: grant.project_end_date ?? "",
    incorporation_required_entity: grant.incorporation_required_entity ?? "",
    contact_person: grant.contact_person ?? "",
    contact_email: grant.contact_email ?? "",
    program_url: grant.program_url ?? "",
    notes_md: grant.notes_md ?? "",
  };
}

function toCreatePayload(f: FormState): GrantCreate {
  // Empty strings become null; required fields stay as strings.
  const opt = (s: string): string | null => (s.trim() === "" ? null : s);
  return {
    granting_body: f.granting_body.trim(),
    program_name: f.program_name.trim(),
    application_template_slug: opt(f.application_template_slug),
    application_status: f.application_status,
    awarded_amount: opt(f.awarded_amount),
    matched_funding_amount: opt(f.matched_funding_amount),
    total_project_value: opt(f.total_project_value),
    currency: f.currency,
    project_start_date: opt(f.project_start_date),
    project_end_date: opt(f.project_end_date),
    incorporation_required_entity: opt(f.incorporation_required_entity),
    cash_coinvestment_required_pct: opt(f.cash_coinvestment_required_pct),
    cash_coinvestment_source: opt(f.cash_coinvestment_source),
    contact_person: opt(f.contact_person),
    contact_email: opt(f.contact_email),
    program_url: opt(f.program_url),
    notes_md: opt(f.notes_md),
  };
}

function diffPatch(initial: FormState, current: FormState): GrantUpdate {
  const opt = (s: string): string | null => (s.trim() === "" ? null : s);
  const patch: GrantUpdate = {};
  const keys = Object.keys(current) as (keyof FormState)[];
  for (const k of keys) {
    if (initial[k] === current[k]) continue;
    if (k === "granting_body" || k === "program_name") {
      patch[k] = current[k].trim();
    } else if (k === "application_status" || k === "currency") {
      patch[k] = current[k];
    } else {
      (patch as Record<string, string | null>)[k] = opt(current[k]);
    }
  }
  return patch;
}

function isValidUrl(s: string): boolean {
  if (s.trim() === "") return true;
  return /^https?:\/\//i.test(s.trim());
}

function isValidPercent(s: string): boolean {
  if (s.trim() === "") return true;
  const n = Number(s);
  return Number.isFinite(n) && n >= 0 && n <= 100;
}

function isValidDateOrder(start: string, end: string): boolean {
  if (start === "" || end === "") return true;
  return start <= end;
}

function isValidNonNegativeNumber(s: string): boolean {
  if (s.trim() === "") return true;
  const n = Number(s);
  return Number.isFinite(n) && n >= 0;
}

function isFormValid(f: FormState): boolean {
  if (!f.granting_body.trim()) return false;
  if (!f.program_name.trim()) return false;
  if (!isValidUrl(f.program_url)) return false;
  if (!isValidPercent(f.cash_coinvestment_required_pct)) return false;
  if (!isValidDateOrder(f.project_start_date, f.project_end_date)) return false;
  if (!isValidNonNegativeNumber(f.awarded_amount)) return false;
  if (!isValidNonNegativeNumber(f.matched_funding_amount)) return false;
  if (!isValidNonNegativeNumber(f.total_project_value)) return false;
  return true;
}

interface FormBodyProps {
  form: FormState;
  setForm: (next: FormState) => void;
}

function FormBody({ form, setForm }: FormBodyProps) {
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm({ ...form, [k]: v });

  return (
    <>
      <label className={styles.modalField}>
        Granting body
        <input
          type="text"
          value={form.granting_body}
          onChange={(e) => set("granting_body", e.target.value)}
          autoFocus
        />
      </label>

      <label className={styles.modalField}>
        Program name
        <input
          type="text"
          value={form.program_name}
          onChange={(e) => set("program_name", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Application template
        <select
          value={form.application_template_slug}
          onChange={(e) => set("application_template_slug", e.target.value)}
        >
          {TEMPLATE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label className={styles.modalField}>
        Application status
        <select
          value={form.application_status}
          onChange={(e) => set("application_status", e.target.value)}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </label>

      <label className={styles.modalField}>
        {amountLabel(form.application_status)} amount
        <input
          type="number"
          min={0}
          step="0.01"
          value={form.awarded_amount}
          onChange={(e) => set("awarded_amount", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Currency
        <select
          value={form.currency}
          onChange={(e) => set("currency", e.target.value)}
        >
          {CURRENCY_OPTIONS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>

      <label className={styles.modalField}>
        Matched funding amount
        <input
          type="number"
          min={0}
          step="0.01"
          value={form.matched_funding_amount}
          onChange={(e) => set("matched_funding_amount", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Total project value
        <input
          type="number"
          min={0}
          step="0.01"
          value={form.total_project_value}
          onChange={(e) => set("total_project_value", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Cash co-investment required (%)
        <input
          type="number"
          min={0}
          max={100}
          step="0.01"
          value={form.cash_coinvestment_required_pct}
          onChange={(e) => set("cash_coinvestment_required_pct", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Cash co-investment source
        <input
          type="text"
          value={form.cash_coinvestment_source}
          onChange={(e) => set("cash_coinvestment_source", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Project start date
        <input
          type="date"
          value={form.project_start_date}
          onChange={(e) => set("project_start_date", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Project end date
        <input
          type="date"
          value={form.project_end_date}
          onChange={(e) => set("project_end_date", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Required incorporated entity
        <input
          type="text"
          value={form.incorporation_required_entity}
          onChange={(e) => set("incorporation_required_entity", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Contact person
        <input
          type="text"
          value={form.contact_person}
          onChange={(e) => set("contact_person", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Contact email
        <input
          type="email"
          value={form.contact_email}
          onChange={(e) => set("contact_email", e.target.value)}
        />
      </label>

      <label className={styles.modalField}>
        Program URL
        <input
          type="url"
          value={form.program_url}
          onChange={(e) => set("program_url", e.target.value)}
          placeholder="https://example.org/funding/program"
        />
      </label>

      <label className={styles.modalField}>
        Notes
        <textarea
          rows={4}
          value={form.notes_md}
          onChange={(e) => set("notes_md", e.target.value)}
        />
      </label>
    </>
  );
}

// ---------------------------------------------------------------------------
// CreateGrantModal (operator+)
// ---------------------------------------------------------------------------

export function CreateGrantModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(emptyForm);

  const mutation = useMutation({
    mutationFn: () => createGrant(toCreatePayload(form)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["grants", "list"] });
      onClose();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (isFormValid(form)) mutation.mutate();
  };

  return (
    <div className={styles.modalBackdrop} onClick={onClose}>
      <div
        className={`${styles.modal} ${styles.modalWide}`}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className={styles.modalTitle}>Create grant</h2>
        <form onSubmit={onSubmit}>
          <FormBody form={form} setForm={setForm} />
          <div className={styles.modalActions}>
            <button
              type="button"
              className={styles.toolbarBtn}
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className={styles.detailNoteSave}
              disabled={!isFormValid(form) || mutation.isPending}
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EditGrantModal (operator+)
// ---------------------------------------------------------------------------

export function EditGrantModal({
  grant,
  onClose,
}: {
  grant: Grant;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const initial = fromGrant(grant);
  const [form, setForm] = useState<FormState>(initial);

  const mutation = useMutation({
    mutationFn: () => updateGrant(grant.id, diffPatch(initial, form)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["grants", "list"] });
      queryClient.invalidateQueries({
        queryKey: ["grants", "detail", grant.id],
      });
      onClose();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (isFormValid(form)) mutation.mutate();
  };

  return (
    <div className={styles.modalBackdrop} onClick={onClose}>
      <div
        className={`${styles.modal} ${styles.modalWide}`}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className={styles.modalTitle}>Edit grant</h2>
        <form onSubmit={onSubmit}>
          <FormBody form={form} setForm={setForm} />
          <div className={styles.modalActions}>
            <button
              type="button"
              className={styles.toolbarBtn}
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className={styles.detailNoteSave}
              disabled={!isFormValid(form) || mutation.isPending}
            >
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
