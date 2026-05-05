"use client";

/**
 * Modal components for the regulatory tracker (item 101 v2 Phase 2b).
 *
 * Three modals share the same backdrop + modal frame: Import HTML, Add Phase,
 * Add Task. Kept in one file to avoid file-noise when each is ~40 lines.
 */

import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  createPhase,
  createTask,
  importTrackerHtml,
  type ImportHtmlSummary,
} from "@/lib/regulatory-api";

import styles from "./regulatory.module.css";

// ---------------------------------------------------------------------------
// Import HTML modal (admin only)
// ---------------------------------------------------------------------------

export function ImportHtmlModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<ImportHtmlSummary | null>(null);

  const mutation = useMutation({
    mutationFn: (f: File) => importTrackerHtml(f),
    onSuccess: (s) => {
      setSummary(s);
      queryClient.invalidateQueries({ queryKey: ["regulatory", "snapshot"] });
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (file) mutation.mutate(file);
  };

  return (
    <div className={styles.modalBackdrop} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.modalTitle}>Import tracker HTML</h2>
        <form onSubmit={onSubmit}>
          <label className={styles.modalField}>
            Tracker HTML file
            <input
              type="file"
              accept=".html,text/html"
              aria-label="Tracker HTML file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          {summary && (
            <div className={styles.modalSummary}>
              Created: {summary.tasks_created} tasks,{" "}
              {summary.phases_created} phases, {summary.streams_created}{" "}
              streams. Skipped duplicates: {summary.tasks_skipped_duplicate}.
            </div>
          )}
          <div className={styles.modalActions}>
            <button
              type="button"
              className={styles.toolbarBtn}
              onClick={onClose}
            >
              Close
            </button>
            <button
              type="submit"
              className={styles.detailNoteSave}
              disabled={!file || mutation.isPending}
            >
              Import
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Phase modal (operator+)
// ---------------------------------------------------------------------------

export function AddPhaseModal({
  streamId,
  countryId,
  onClose,
}: {
  streamId: string;
  countryId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [badgeKind, setBadgeKind] = useState("now");
  const [timingLabel, setTimingLabel] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      createPhase({
        stream_id: streamId,
        country_id: countryId,
        name,
        badge_kind: badgeKind,
        timing_label: timingLabel || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["regulatory", "snapshot"] });
      onClose();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim()) mutation.mutate();
  };

  return (
    <div className={styles.modalBackdrop} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.modalTitle}>Add phase</h2>
        <form onSubmit={onSubmit}>
          <label className={styles.modalField}>
            Phase name
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </label>
          <label className={styles.modalField}>
            Badge
            <select
              value={badgeKind}
              onChange={(e) => setBadgeKind(e.target.value)}
            >
              <option value="now">now</option>
              <option value="pre">pre</option>
              <option value="arrive">arrive</option>
              <option value="post">post</option>
              <option value="concurrent">concurrent</option>
              <option value="corp">corp</option>
              <option value="insurance">insurance</option>
            </select>
          </label>
          <label className={styles.modalField}>
            Timing label (optional)
            <input
              type="text"
              value={timingLabel}
              onChange={(e) => setTimingLabel(e.target.value)}
              placeholder="e.g. Days 1-3"
            />
          </label>
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
              disabled={!name.trim() || mutation.isPending}
            >
              Create phase
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Task modal (operator+)
// ---------------------------------------------------------------------------

export function AddTaskModal({
  phaseId,
  onClose,
}: {
  phaseId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [note, setNote] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      createTask({
        phase_id: phaseId,
        body,
        note: note || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["regulatory", "snapshot"] });
      onClose();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (body.trim()) mutation.mutate();
  };

  return (
    <div className={styles.modalBackdrop} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.modalTitle}>Add task</h2>
        <form onSubmit={onSubmit}>
          <label className={styles.modalField}>
            Task body
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              autoFocus
            />
          </label>
          <label className={styles.modalField}>
            Note (optional)
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
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
              disabled={!body.trim() || mutation.isPending}
            >
              Create task
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
