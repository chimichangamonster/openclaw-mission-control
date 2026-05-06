"use client";

/**
 * Regulatory task detail side panel (item 101 v2 Phase 2b).
 *
 * Mounted as a fixed right-side drawer when a task body is clicked. Holds
 * assignee + due-date editors, the threaded notes list (load + add + delete),
 * and the tag pill add/remove combobox. Every mutation invalidates the
 * "regulatory", "snapshot" query family on the parent so the page rerenders
 * authoritative state once the network round-trip completes.
 */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addTaskTag,
  createTaskNote,
  deleteTaskNote,
  listTaskNotes,
  removeTaskTag,
  updateTask,
  type RegulatoryTaskNote,
} from "@/lib/regulatory-api";

import styles from "./regulatory.module.css";

// ---------------------------------------------------------------------------
// Types — kept local. The page passes the visible-in-snapshot subset down,
// not the full RegulatoryTask DB row.
// ---------------------------------------------------------------------------

export interface DetailPanelTaskTag {
  id: string;
  slug: string;
  label: string;
  color_token: string;
}

export interface DetailPanelTask {
  id: string;
  body: string;
  note: string | null;
  completed: boolean;
  assignee_user_id: string | null;
  due_date: string | null;
  tags: DetailPanelTaskTag[];
}

export interface DetailPanelOrgMember {
  user_id: string;
  name: string;
  email: string;
}

export interface DetailPanelOptionTag {
  id: string;
  slug: string;
  label: string;
  color_token: string;
}

export interface RegulatoryDetailPanelProps {
  task: DetailPanelTask;
  allTags: DetailPanelOptionTag[];
  orgMembers: DetailPanelOrgMember[];
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RegulatoryDetailPanel({
  task,
  allTags,
  orgMembers,
  onClose,
}: RegulatoryDetailPanelProps) {
  const queryClient = useQueryClient();
  const [noteDraft, setNoteDraft] = useState("");

  // Optimistic deltas layered over `task.tags`. When the parent re-fetches
  // and pushes new tags down the tree we automatically re-derive the
  // effective list — no setState-in-effect cascade needed.
  const [optimisticAdds, setOptimisticAdds] = useState<DetailPanelTaskTag[]>([]);
  const [optimisticRemoves, setOptimisticRemoves] = useState<string[]>([]);
  const tags: DetailPanelTaskTag[] = [
    ...task.tags.filter((t) => !optimisticRemoves.includes(t.id)),
    ...optimisticAdds.filter(
      (t) => !task.tags.some((existing) => existing.id === t.id),
    ),
  ];

  // Esc closes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // ---- notes
  const notesQuery = useQuery({
    queryKey: ["regulatory", "task-notes", task.id],
    queryFn: () => listTaskNotes(task.id),
  });

  const createNote = useMutation({
    mutationFn: (body: string) => createTaskNote(task.id, body),
    onSuccess: () => {
      setNoteDraft("");
      queryClient.invalidateQueries({
        queryKey: ["regulatory", "task-notes", task.id],
      });
    },
  });

  const deleteNote = useMutation({
    mutationFn: (noteId: string) => deleteTaskNote(task.id, noteId),
    onMutate: async (noteId) => {
      await queryClient.cancelQueries({
        queryKey: ["regulatory", "task-notes", task.id],
      });
      const previous = queryClient.getQueryData<RegulatoryTaskNote[]>([
        "regulatory",
        "task-notes",
        task.id,
      ]);
      if (previous) {
        queryClient.setQueryData<RegulatoryTaskNote[]>(
          ["regulatory", "task-notes", task.id],
          previous.filter((n) => n.id !== noteId),
        );
      }
      return { previous };
    },
    onError: (_err, _noteId, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(
          ["regulatory", "task-notes", task.id],
          context.previous,
        );
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["regulatory", "task-notes", task.id],
      });
    },
  });

  // ---- task fields
  const saveTask = useMutation({
    mutationFn: (patch: {
      body?: string;
      assignee_user_id?: string | null;
      due_date?: string | null;
    }) => updateTask(task.id, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["regulatory", "snapshot"] });
    },
  });

  // ---- inline body edit (item 114)
  // The panel is mounted with key={task.id} from the page, so a different
  // task always remounts and re-initialises the draft. The remaining concern
  // is server-side mutation of the same task — `task.body` updates in props
  // after a save, but the user's draft is already what was saved, so no sync
  // is needed in practice.
  const [bodyDraft, setBodyDraft] = useState(task.body);
  const handleBodyBlur = () => {
    const next = bodyDraft.trim();
    if (!next || next === task.body) return;
    saveTask.mutate({ body: next });
  };
  const handleBodyKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setBodyDraft(task.body);
      e.currentTarget.blur();
    } else if (e.key === "Enter") {
      e.preventDefault();
      e.currentTarget.blur();
    }
  };

  // ---- tags
  const addTag = useMutation({
    mutationFn: (tagId: string) => addTaskTag(task.id, tagId),
    onMutate: (tagId) => {
      const tagDef = allTags.find((t) => t.id === tagId);
      if (tagDef) setOptimisticAdds((prev) => [...prev, tagDef]);
      setOptimisticRemoves((prev) => prev.filter((id) => id !== tagId));
      return { tagId };
    },
    onError: (_err, _tagId, context) => {
      if (context?.tagId)
        setOptimisticAdds((prev) => prev.filter((t) => t.id !== context.tagId));
    },
    onSettled: () => {
      // Authoritative refetch wins; clear local deltas so they don't double up.
      setOptimisticAdds([]);
      setOptimisticRemoves([]);
      queryClient.invalidateQueries({ queryKey: ["regulatory", "snapshot"] });
    },
  });

  const removeTag = useMutation({
    mutationFn: (tagId: string) => removeTaskTag(task.id, tagId),
    onMutate: (tagId) => {
      setOptimisticRemoves((prev) => [...prev, tagId]);
      setOptimisticAdds((prev) => prev.filter((t) => t.id !== tagId));
      return { tagId };
    },
    onError: (_err, _tagId, context) => {
      if (context?.tagId)
        setOptimisticRemoves((prev) =>
          prev.filter((id) => id !== context.tagId),
        );
    },
    onSettled: () => {
      setOptimisticAdds([]);
      setOptimisticRemoves([]);
      queryClient.invalidateQueries({ queryKey: ["regulatory", "snapshot"] });
    },
  });

  const availableTags = allTags.filter(
    (t) => !tags.some((existing) => existing.id === t.id),
  );

  return (
    <div className={styles.detailPanelBackdrop} onClick={onClose}>
      <div
        className={styles.detailPanel}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className={styles.detailPanelHeader}>
          <input
            type="text"
            aria-label="Task body"
            className={styles.detailPanelTitleInput}
            value={bodyDraft}
            onChange={(e) => setBodyDraft(e.target.value)}
            onBlur={handleBodyBlur}
            onKeyDown={handleBodyKeyDown}
          />
          <button
            type="button"
            aria-label="close panel"
            className={styles.detailPanelClose}
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <div className={styles.detailPanelBody}>
          {/* ---- tag pills + add ---- */}
          <section className={styles.detailSection}>
            <div className={styles.detailLabel}>Tags</div>
            <div className={styles.detailTagRow}>
              {tags.map((t) => (
                <span key={t.id} className={styles.detailTagPill}>
                  {t.label}
                  <button
                    type="button"
                    aria-label={`remove tag ${t.label}`}
                    onClick={() => removeTag.mutate(t.id)}
                    className={styles.detailTagRemove}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            {availableTags.length > 0 && (
              <label className={styles.detailField}>
                <span className={styles.detailLabel}>Add tag</span>
                <select
                  defaultValue=""
                  onChange={(e) => {
                    const v = e.target.value;
                    if (!v) return;
                    addTag.mutate(v);
                    e.target.value = "";
                  }}
                >
                  <option value="">Select…</option>
                  {availableTags.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </section>

          {/* ---- assignee + due date ---- */}
          <section className={styles.detailSection}>
            <label className={styles.detailField}>
              <span className={styles.detailLabel}>Assignee</span>
              <select
                value={task.assignee_user_id ?? ""}
                onChange={(e) =>
                  saveTask.mutate({
                    assignee_user_id: e.target.value || null,
                  })
                }
              >
                <option value="">Unassigned</option>
                {orgMembers.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.detailField}>
              <span className={styles.detailLabel}>Due date</span>
              <input
                type="date"
                value={task.due_date ? task.due_date.slice(0, 10) : ""}
                onChange={(e) => {
                  const v = e.target.value;
                  saveTask.mutate({
                    due_date: v ? `${v}T00:00:00Z` : null,
                  });
                }}
              />
            </label>
          </section>

          {/* ---- notes ---- */}
          <section className={styles.detailSection}>
            <div className={styles.detailLabel}>Notes</div>
            <ul className={styles.detailNoteList}>
              {(notesQuery.data ?? []).map((n) => (
                <li key={n.id} className={styles.detailNoteItem}>
                  <div className={styles.detailNoteBody}>{n.body}</div>
                  <button
                    type="button"
                    aria-label="delete note"
                    onClick={() => deleteNote.mutate(n.id)}
                    className={styles.detailNoteDelete}
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ul>
            <textarea
              placeholder="Add a note…"
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              className={styles.detailNoteInput}
            />
            <button
              type="button"
              onClick={() => {
                if (noteDraft.trim()) createNote.mutate(noteDraft.trim());
              }}
              disabled={!noteDraft.trim() || createNote.isPending}
              className={styles.detailNoteSave}
            >
              Save note
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}
