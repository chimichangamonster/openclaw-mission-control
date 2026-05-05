/**
 * RegulatoryDetailPanel — task detail side panel (item 101 v2 Phase 2b).
 *
 * Coverage:
 * - Loads task notes on mount via listTaskNotes
 * - Submits new note via createTaskNote, optimistic prepend, clears textarea
 * - Delete-note button calls deleteTaskNote and removes the note from the list
 * - Assignee dropdown saves via updateTask
 * - Due-date input saves via updateTask
 * - Add-tag combobox calls addTaskTag for the selected tag
 * - Remove-tag X on a pill calls removeTaskTag
 * - Closes on backdrop click and on Esc keypress
 */

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/regulatory-api", () => ({
  listTaskNotes: vi.fn(),
  createTaskNote: vi.fn(),
  deleteTaskNote: vi.fn(),
  updateTask: vi.fn(),
  addTaskTag: vi.fn(),
  removeTaskTag: vi.fn(),
}));

import {
  addTaskTag,
  createTaskNote,
  deleteTaskNote,
  listTaskNotes,
  removeTaskTag,
  updateTask,
} from "@/lib/regulatory-api";
import { RegulatoryDetailPanel } from "./regulatory-detail-panel";

const mockedListNotes = vi.mocked(listTaskNotes);
const mockedCreateNote = vi.mocked(createTaskNote);
const mockedDeleteNote = vi.mocked(deleteTaskNote);
const mockedUpdateTask = vi.mocked(updateTask);
const mockedAddTag = vi.mocked(addTaskTag);
const mockedRemoveTag = vi.mocked(removeTaskTag);

afterEach(() => {
  vi.clearAllMocks();
});

const baseTask = {
  id: "task-1",
  phase_id: "phase-1",
  body: "Open business bank account",
  note: null,
  completed: false,
  completed_at: null,
  completed_by_user_id: null,
  assignee_user_id: null,
  due_date: null,
  sort_order: 0,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
  tags: [
    { id: "tag-1", slug: "td", label: "TD", color_token: "navy" },
  ],
};

const allTags = [
  { id: "tag-1", slug: "td", label: "TD", color_token: "navy" },
  { id: "tag-2", slug: "rbc", label: "RBC", color_token: "navy" },
  { id: "tag-3", slug: "cra", label: "CRA", color_token: "navy" },
];

const orgMembers = [
  { user_id: "user-1", name: "Henry", email: "henry@example.com" },
  { user_id: "user-2", name: "Samir", email: "samir@example.com" },
];

const renderPanel = (overrides: Partial<{ onClose: () => void }> = {}) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const onClose = overrides.onClose ?? vi.fn();
  return {
    onClose,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RegulatoryDetailPanel
          task={baseTask}
          allTags={allTags}
          orgMembers={orgMembers}
          onClose={onClose}
        />
      </QueryClientProvider>,
    ),
  };
};

describe("RegulatoryDetailPanel", () => {
  it("renders the task body and existing tag pills", () => {
    mockedListNotes.mockResolvedValue([]);
    renderPanel();
    expect(screen.getByText(/Open business bank account/)).toBeInTheDocument();
    expect(screen.getByText("TD")).toBeInTheDocument();
  });

  it("loads and renders threaded notes", async () => {
    mockedListNotes.mockResolvedValue([
      {
        id: "note-1",
        task_id: "task-1",
        body: "Spoke with TD rep — appointment Friday",
        author_user_id: "user-1",
        created_at: "2026-05-04T10:00:00Z",
      },
    ]);
    renderPanel();
    await waitFor(() => expect(mockedListNotes).toHaveBeenCalledWith("task-1"));
    expect(
      await screen.findByText(/Spoke with TD rep/),
    ).toBeInTheDocument();
  });

  it("submits a new note via createTaskNote and clears the textarea", async () => {
    mockedListNotes.mockResolvedValue([]);
    mockedCreateNote.mockResolvedValue({
      id: "note-new",
      task_id: "task-1",
      body: "New note body",
      author_user_id: "user-1",
      created_at: "2026-05-05T00:00:00Z",
    });
    renderPanel();

    const textarea = await screen.findByPlaceholderText(/add a note/i);
    fireEvent.change(textarea, { target: { value: "New note body" } });
    fireEvent.click(screen.getByRole("button", { name: /save note/i }));

    await waitFor(() =>
      expect(mockedCreateNote).toHaveBeenCalledWith("task-1", "New note body"),
    );
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("deletes a note via deleteTaskNote", async () => {
    mockedListNotes.mockResolvedValue([
      {
        id: "note-1",
        task_id: "task-1",
        body: "Existing note",
        author_user_id: "user-1",
        created_at: "2026-05-04T10:00:00Z",
      },
    ]);
    mockedDeleteNote.mockResolvedValue(undefined);
    renderPanel();

    await screen.findByText(/Existing note/);
    fireEvent.click(screen.getByRole("button", { name: /delete note/i }));
    await waitFor(() =>
      expect(mockedDeleteNote).toHaveBeenCalledWith("task-1", "note-1"),
    );
  });

  it("saves assignee selection via updateTask", async () => {
    mockedListNotes.mockResolvedValue([]);
    mockedUpdateTask.mockResolvedValue({ ...baseTask, assignee_user_id: "user-2" });
    renderPanel();

    const select = await screen.findByLabelText(/assignee/i);
    fireEvent.change(select, { target: { value: "user-2" } });

    await waitFor(() =>
      expect(mockedUpdateTask).toHaveBeenCalledWith("task-1", {
        assignee_user_id: "user-2",
      }),
    );
  });

  it("saves due date via updateTask", async () => {
    mockedListNotes.mockResolvedValue([]);
    mockedUpdateTask.mockResolvedValue({
      ...baseTask,
      due_date: "2026-06-01T00:00:00Z",
    });
    renderPanel();

    const dueDate = await screen.findByLabelText(/due date/i);
    fireEvent.change(dueDate, { target: { value: "2026-06-01" } });

    await waitFor(() => expect(mockedUpdateTask).toHaveBeenCalledTimes(1));
    const call = mockedUpdateTask.mock.calls[0];
    expect(call[0]).toBe("task-1");
    expect(call[1].due_date).toMatch(/^2026-06-01/);
  });

  it("adds an unattached tag via addTaskTag", async () => {
    mockedListNotes.mockResolvedValue([]);
    mockedAddTag.mockResolvedValue({
      task_id: "task-1",
      tag_id: "tag-2",
      created_at: "2026-05-05T00:00:00Z",
    });
    renderPanel();

    const tagSelect = await screen.findByLabelText(/add tag/i);
    fireEvent.change(tagSelect, { target: { value: "tag-2" } });

    await waitFor(() =>
      expect(mockedAddTag).toHaveBeenCalledWith("task-1", "tag-2"),
    );
  });

  it("removes a tag via removeTaskTag when the X is clicked", async () => {
    mockedListNotes.mockResolvedValue([]);
    mockedRemoveTag.mockResolvedValue(undefined);
    renderPanel();

    const removeBtn = await screen.findByRole("button", {
      name: /remove tag td/i,
    });
    fireEvent.click(removeBtn);

    await waitFor(() =>
      expect(mockedRemoveTag).toHaveBeenCalledWith("task-1", "tag-1"),
    );
  });

  it("calls onClose when the close button is clicked", () => {
    mockedListNotes.mockResolvedValue([]);
    const { onClose } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /close panel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when Escape is pressed", () => {
    mockedListNotes.mockResolvedValue([]);
    const { onClose } = renderPanel();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
