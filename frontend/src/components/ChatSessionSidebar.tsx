"use client";

import { useState } from "react";
import {
  Plus,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Trash2,
  Check,
  X,
  PanelLeftClose,
  Loader2,
  Search,
  ChevronDown,
  ChevronRight,
  FolderPlus,
  Archive,
  FolderInput,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SessionItem {
  key: string;
  displayName?: string;
  groupChannel?: string;
  totalTokens?: number;
  model?: string;
}

interface SidebarProject {
  id: string;
  name: string;
  color: string | null;
  session_count: number;
}

interface ChatSessionSidebarProps {
  sessions: SessionItem[];
  projects: SidebarProject[];
  assignments: Record<string, string>;
  activeSessionKey: string | null;
  mainSessionKey: string | null;
  unreadSessions?: Set<string>;
  onSelectSession: (key: string) => void;
  onCreateSession: (label: string) => Promise<unknown>;
  onCreateSessionInProject?: (label: string, projectId: string) => Promise<void>;
  onRenameSession: (key: string, label: string) => Promise<void>;
  onDeleteSession: (key: string) => Promise<void>;
  onAssignToProject: (sessionKey: string, projectId: string | null) => Promise<void>;
  onCreateProject: (name: string, color: string | null) => Promise<void>;
  onRenameProject: (projectId: string, name: string) => Promise<void>;
  onArchiveProject: (projectId: string) => Promise<void>;
  onClose: () => void;
  isLoading: boolean;
}

// Fixed palette — 10 muted colors for projects. No free-form hex.
const PROJECT_COLORS: { name: string; hex: string }[] = [
  { name: "slate", hex: "#64748b" },
  { name: "red", hex: "#ef4444" },
  { name: "orange", hex: "#f97316" },
  { name: "amber", hex: "#f59e0b" },
  { name: "green", hex: "#10b981" },
  { name: "teal", hex: "#14b8a6" },
  { name: "blue", hex: "#3b82f6" },
  { name: "indigo", hex: "#6366f1" },
  { name: "purple", hex: "#a855f7" },
  { name: "pink", hex: "#ec4899" },
];

// Generate a collision-proof default label. Gateway rejects label reuse
// (INVALID_REQUEST "label already in use"), so we avoid sequential numbering.
// Format: "New chat 14:32:07" — unique per second. Auto-titler will rename
// to something meaningful ~2s after first response lands.
function defaultSessionLabel(): string {
  const d = new Date();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `New chat ${hh}:${mm}:${ss}`;
}

function formatTokens(tokens: number | undefined): string {
  if (!tokens) return "";
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}K`;
  return `${tokens}`;
}

function sessionLabel(session: SessionItem, mainKey: string | null): string {
  if (session.displayName) return session.displayName;
  if (session.key === mainKey) return "The Claw";
  const parts = session.key.split(":");
  const last = parts[parts.length - 1];
  if (last.startsWith("chat-")) return `Conversation ${last.slice(5, 9)}`;
  if (session.groupChannel) return `#${session.groupChannel}`;
  return last;
}

export function ChatSessionSidebar({
  sessions,
  projects,
  assignments,
  activeSessionKey,
  mainSessionKey,
  unreadSessions,
  onSelectSession,
  onCreateSession,
  onCreateSessionInProject,
  onRenameSession,
  onDeleteSession,
  onAssignToProject,
  onCreateProject,
  onRenameProject,
  onArchiveProject,
  onClose,
  isLoading,
}: ChatSessionSidebarProps) {
  const [creating, setCreating] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectColor, setNewProjectColor] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editProjectName, setEditProjectName] = useState("");
  const [menuKey, setMenuKey] = useState<string | null>(null);
  const [moveMenuKey, setMoveMenuKey] = useState<string | null>(null);
  const [projectMenuId, setProjectMenuId] = useState<string | null>(null);
  const [collapsedProjects, setCollapsedProjects] = useState<Set<string>>(new Set());
  const [actionLoading, setActionLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [newSessionProjectId, setNewSessionProjectId] = useState<string | null>(null);
  const [newSessionInProjectLabel, setNewSessionInProjectLabel] = useState("");

  const filterQuery = filter.trim().toLowerCase();
  const matchesFilter = (session: SessionItem) =>
    !filterQuery ||
    sessionLabel(session, mainSessionKey).toLowerCase().includes(filterQuery);

  const unassignedSessions = sessions.filter(
    (s) => !assignments[s.key] && matchesFilter(s),
  );
  const sessionsByProject: Record<string, SessionItem[]> = {};
  for (const project of projects) {
    sessionsByProject[project.id] = sessions.filter(
      (s) => assignments[s.key] === project.id && matchesFilter(s),
    );
  }
  const totalVisible =
    unassignedSessions.length +
    Object.values(sessionsByProject).reduce((a, b) => a + b.length, 0);

  const toggleProjectCollapse = (id: string) => {
    setCollapsedProjects((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCreate = async () => {
    const label = newLabel.trim() || defaultSessionLabel();
    setActionLoading(true);
    try {
      await onCreateSession(label);
      setNewLabel("");
      setCreating(false);
    } finally {
      setActionLoading(false);
    }
  };

  const handleQuickCreate = async () => {
    setActionLoading(true);
    try {
      await onCreateSession(defaultSessionLabel());
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateProject = async () => {
    const name = newProjectName.trim();
    if (!name) {
      setCreatingProject(false);
      return;
    }
    setActionLoading(true);
    try {
      await onCreateProject(name, newProjectColor);
      setNewProjectName("");
      setNewProjectColor(null);
      setCreatingProject(false);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRename = async (key: string) => {
    if (!editLabel.trim()) {
      setEditingKey(null);
      return;
    }
    setActionLoading(true);
    try {
      await onRenameSession(key, editLabel.trim());
      setEditingKey(null);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRenameProject = async (projectId: string) => {
    if (!editProjectName.trim()) {
      setEditingProjectId(null);
      return;
    }
    setActionLoading(true);
    try {
      await onRenameProject(projectId, editProjectName.trim());
      setEditingProjectId(null);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (key: string) => {
    setActionLoading(true);
    try {
      await onDeleteSession(key);
      setMenuKey(null);
    } finally {
      setActionLoading(false);
    }
  };

  const handleArchiveProject = async (projectId: string) => {
    setActionLoading(true);
    try {
      await onArchiveProject(projectId);
      setProjectMenuId(null);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateInProject = async (projectId: string) => {
    if (!onCreateSessionInProject) return;
    const label = newSessionInProjectLabel.trim() || defaultSessionLabel();
    setActionLoading(true);
    try {
      await onCreateSessionInProject(label, projectId);
      setNewSessionInProjectLabel("");
      setNewSessionProjectId(null);
    } finally {
      setActionLoading(false);
    }
  };

  const handleQuickCreateInProject = async (projectId: string) => {
    if (!onCreateSessionInProject) return;
    setActionLoading(true);
    try {
      await onCreateSessionInProject(defaultSessionLabel(), projectId);
    } finally {
      setActionLoading(false);
    }
  };

  const handleMoveToProject = async (sessionKey: string, projectId: string | null) => {
    setActionLoading(true);
    try {
      await onAssignToProject(sessionKey, projectId);
      setMoveMenuKey(null);
      setMenuKey(null);
    } finally {
      setActionLoading(false);
    }
  };

  const renderSession = (session: SessionItem, indent = false) => {
    const isActive = session.key === activeSessionKey;
    const isMain = session.key === mainSessionKey;
    const isUnread = !isActive && (unreadSessions?.has(session.key) ?? false);
    const label = sessionLabel(session, mainSessionKey);

    return (
      <div key={session.key} className={cn("relative px-1.5 py-0.5", indent && "pl-4")}>
        {editingKey === session.key ? (
          <div className="flex items-center gap-1 rounded-lg px-2 py-1.5">
            <input
              autoFocus
              value={editLabel}
              onChange={(e) => setEditLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleRename(session.key);
                if (e.key === "Escape") setEditingKey(null);
              }}
              className="flex-1 rounded border border-[color:var(--border)] bg-[color:var(--surface-muted)] px-2 py-1 text-xs text-[color:var(--text)] focus:border-[color:var(--accent)] focus:outline-none"
            />
            <button onClick={() => void handleRename(session.key)} className="p-0.5 text-[color:var(--accent)]">
              <Check className="h-3.5 w-3.5" />
            </button>
            <button onClick={() => setEditingKey(null)} className="p-0.5 text-[color:var(--text-quiet)]">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : (
          <div
            className={cn(
              "group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs transition min-w-0",
              isActive
                ? "bg-[color:var(--accent)]/10 text-[color:var(--text)]"
                : "text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)]",
            )}
          >
            <button
              onClick={() => onSelectSession(session.key)}
              className="flex flex-1 items-center gap-2.5 text-left min-w-0"
            >
              <MessageSquare className={cn("h-3.5 w-3.5 shrink-0", isActive ? "text-[color:var(--accent)]" : "")} />
              <span className={cn("flex-1 truncate min-w-0", isUnread && "font-semibold text-[color:var(--text)]")}>{label}</span>
              {isUnread && <span className="h-2 w-2 shrink-0 rounded-full bg-blue-500" />}
              {session.totalTokens ? (
                <span className="shrink-0 text-[10px] tabular-nums text-[color:var(--text-quiet)] opacity-60">
                  {formatTokens(session.totalTokens)}
                </span>
              ) : null}
            </button>
            {!isMain && (
              <button
                onClick={() => {
                  setMenuKey(menuKey === session.key ? null : session.key);
                  setMoveMenuKey(null);
                }}
                className="shrink-0 rounded p-0.5 opacity-60 sm:opacity-0 sm:group-hover:opacity-100 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] hover:opacity-100 transition"
                aria-label="Session actions"
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        )}

        {/* Session context menu */}
        {menuKey === session.key && !isMain && (
          <div className="absolute right-2 top-full z-20 mt-0.5 rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] py-1 shadow-lg min-w-[160px]">
            <button
              onClick={() => {
                setEditLabel(label);
                setEditingKey(session.key);
                setMenuKey(null);
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[color:var(--text)] hover:bg-[color:var(--surface-muted)] transition"
            >
              <Pencil className="h-3 w-3" /> Rename
            </button>
            <button
              onClick={() => setMoveMenuKey(moveMenuKey === session.key ? null : session.key)}
              className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-xs text-[color:var(--text)] hover:bg-[color:var(--surface-muted)] transition"
            >
              <span className="flex items-center gap-2">
                <FolderInput className="h-3 w-3" /> Move to project
              </span>
              <ChevronRight className="h-3 w-3" />
            </button>
            <button
              onClick={() => void handleDelete(session.key)}
              disabled={actionLoading}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-rose-500 hover:bg-[color:var(--surface-muted)] transition disabled:opacity-40"
            >
              <Trash2 className="h-3 w-3" /> Delete
            </button>

            {/* Move submenu */}
            {moveMenuKey === session.key && (
              <div className="mt-1 border-t border-[color:var(--border)] pt-1 max-h-48 overflow-y-auto">
                <button
                  onClick={() => void handleMoveToProject(session.key, null)}
                  disabled={actionLoading}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] transition"
                >
                  No project
                </button>
                {projects.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => void handleMoveToProject(session.key, p.id)}
                    disabled={actionLoading || assignments[session.key] === p.id}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[color:var(--text)] hover:bg-[color:var(--surface-muted)] transition disabled:opacity-40"
                  >
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: p.color || "#64748b" }}
                    />
                    <span className="truncate">{p.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-full w-[260px] shrink-0 flex-col min-h-0 border-r border-[color:var(--border)] bg-[color:var(--surface)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[color:var(--border)] px-3 py-3">
        <h3 className="text-sm font-medium text-[color:var(--text)]">Conversations</h3>
        <div className="flex items-center gap-1">
          <button
            onClick={() => {
              setCreatingProject(true);
              setCreating(false);
            }}
            className="rounded-md p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)] transition"
            title="New project"
          >
            <FolderPlus className="h-4 w-4" />
          </button>
          <button
            onClick={() => void handleQuickCreate()}
            disabled={actionLoading}
            className="rounded-md p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)] transition disabled:opacity-40"
            title="New conversation"
          >
            {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          </button>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)] transition md:hidden"
            title="Close sidebar"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Search input */}
      {sessions.length > 0 && (
        <div className="border-b border-[color:var(--border)] px-3 py-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-quiet)]" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search conversations"
              className="w-full rounded-md border border-[color:var(--border)] bg-[color:var(--surface-muted)] pl-7 pr-7 py-1.5 text-xs text-[color:var(--text)] placeholder:text-[color:var(--text-quiet)] focus:border-[color:var(--accent)] focus:outline-none"
            />
            {filter && (
              <button
                onClick={() => setFilter("")}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] transition"
                title="Clear search"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* New conversation input */}
      {creating && (
        <div className="border-b border-[color:var(--border)] px-3 py-2">
          <input
            autoFocus
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleCreate();
              if (e.key === "Escape") setCreating(false);
            }}
            placeholder="Conversation name..."
            className="w-full rounded-md border border-[color:var(--border)] bg-[color:var(--surface-muted)] px-2.5 py-1.5 text-xs text-[color:var(--text)] placeholder:text-[color:var(--text-quiet)] focus:border-[color:var(--accent)] focus:outline-none"
          />
          <div className="mt-1.5 flex justify-end gap-1">
            <button onClick={() => setCreating(false)} className="rounded p-1 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] transition">
              <X className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => void handleCreate()}
              disabled={actionLoading}
              className="rounded p-1 text-[color:var(--accent)] hover:text-[color:var(--accent-strong)] transition disabled:opacity-40"
            >
              {actionLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      )}

      {/* New project input + color picker */}
      {creatingProject && (
        <div className="border-b border-[color:var(--border)] px-3 py-2">
          <input
            autoFocus
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleCreateProject();
              if (e.key === "Escape") setCreatingProject(false);
            }}
            placeholder="Project name..."
            className="w-full rounded-md border border-[color:var(--border)] bg-[color:var(--surface-muted)] px-2.5 py-1.5 text-xs text-[color:var(--text)] placeholder:text-[color:var(--text-quiet)] focus:border-[color:var(--accent)] focus:outline-none"
          />
          <div className="mt-1.5 flex flex-wrap gap-1">
            {PROJECT_COLORS.map((c) => (
              <button
                key={c.hex}
                onClick={() => setNewProjectColor(c.hex)}
                title={c.name}
                className={cn(
                  "h-4 w-4 rounded-full transition",
                  newProjectColor === c.hex
                    ? "ring-2 ring-offset-1 ring-[color:var(--accent)] ring-offset-[color:var(--surface)]"
                    : "opacity-70 hover:opacity-100",
                )}
                style={{ backgroundColor: c.hex }}
              />
            ))}
          </div>
          <div className="mt-1.5 flex justify-end gap-1">
            <button onClick={() => setCreatingProject(false)} className="rounded p-1 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] transition">
              <X className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => void handleCreateProject()}
              disabled={actionLoading || !newProjectName.trim()}
              className="rounded p-1 text-[color:var(--accent)] hover:text-[color:var(--accent-strong)] transition disabled:opacity-40"
            >
              {actionLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      )}

      {/* Session list */}
      <div className="flex-1 min-h-0 overflow-y-auto py-1">
        {isLoading && sessions.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-[color:var(--text-muted)]" />
          </div>
        ) : sessions.length === 0 ? (
          <p className="px-3 py-4 text-xs text-[color:var(--text-quiet)] text-center">
            No conversations yet
          </p>
        ) : totalVisible === 0 ? (
          <p className="px-3 py-4 text-xs text-[color:var(--text-quiet)] text-center">
            No matches
          </p>
        ) : (
          <>
            {/* Project groups */}
            {projects.map((project) => {
              const projectSessions = sessionsByProject[project.id] ?? [];
              if (filterQuery && projectSessions.length === 0) return null;
              const isCollapsed = collapsedProjects.has(project.id);
              return (
                <div key={project.id} className="relative">
                  <div className="flex items-center gap-1 px-2 py-1">
                    {editingProjectId === project.id ? (
                      <>
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: project.color || "#64748b" }}
                        />
                        <input
                          autoFocus
                          value={editProjectName}
                          onChange={(e) => setEditProjectName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void handleRenameProject(project.id);
                            if (e.key === "Escape") setEditingProjectId(null);
                          }}
                          className="flex-1 rounded border border-[color:var(--border)] bg-[color:var(--surface-muted)] px-2 py-0.5 text-xs text-[color:var(--text)] focus:border-[color:var(--accent)] focus:outline-none min-w-0"
                        />
                        <button onClick={() => void handleRenameProject(project.id)} className="p-0.5 text-[color:var(--accent)] shrink-0">
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button onClick={() => setEditingProjectId(null)} className="p-0.5 text-[color:var(--text-quiet)] shrink-0">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </>
                    ) : (
                      <div className="group flex w-full items-center gap-1.5 rounded px-1 py-1 text-[11px] font-medium uppercase tracking-wider text-[color:var(--text-quiet)] min-w-0">
                        <button
                          onClick={() => toggleProjectCollapse(project.id)}
                          className="flex flex-1 items-center gap-1.5 text-left hover:text-[color:var(--text)] transition min-w-0"
                        >
                          {isCollapsed ? (
                            <ChevronRight className="h-3 w-3 shrink-0" />
                          ) : (
                            <ChevronDown className="h-3 w-3 shrink-0" />
                          )}
                          <span
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ backgroundColor: project.color || "#64748b" }}
                          />
                          <span className="flex-1 truncate min-w-0">{project.name}</span>
                          <span className="shrink-0 text-[10px] tabular-nums text-[color:var(--text-quiet)] opacity-60">
                            {projectSessions.length}
                          </span>
                        </button>
                        {onCreateSessionInProject && (
                          <button
                            onClick={() => {
                              if (collapsedProjects.has(project.id)) {
                                toggleProjectCollapse(project.id);
                              }
                              void handleQuickCreateInProject(project.id);
                            }}
                            disabled={actionLoading}
                            className="shrink-0 rounded p-0.5 opacity-60 sm:opacity-0 sm:group-hover:opacity-100 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] hover:opacity-100 transition disabled:opacity-40"
                            title="New conversation in this project"
                            aria-label="New conversation in this project"
                          >
                            <Plus className="h-3 w-3" />
                          </button>
                        )}
                        <button
                          onClick={() =>
                            setProjectMenuId(projectMenuId === project.id ? null : project.id)
                          }
                          className="shrink-0 rounded p-0.5 opacity-60 sm:opacity-0 sm:group-hover:opacity-100 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] hover:opacity-100 transition"
                          aria-label="Project actions"
                        >
                          <MoreHorizontal className="h-3 w-3" />
                        </button>
                      </div>
                    )}

                    {/* Inline new-session input for this project */}
                    {newSessionProjectId === project.id && (
                      <div className="px-3 py-2 border-b border-[color:var(--border)]">
                        <input
                          autoFocus
                          value={newSessionInProjectLabel}
                          onChange={(e) => setNewSessionInProjectLabel(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void handleCreateInProject(project.id);
                            if (e.key === "Escape") setNewSessionProjectId(null);
                          }}
                          placeholder="Conversation name..."
                          className="w-full rounded-md border border-[color:var(--border)] bg-[color:var(--surface-muted)] px-2.5 py-1.5 text-xs text-[color:var(--text)] placeholder:text-[color:var(--text-quiet)] focus:border-[color:var(--accent)] focus:outline-none"
                        />
                        <div className="mt-1.5 flex justify-end gap-1">
                          <button
                            onClick={() => setNewSessionProjectId(null)}
                            className="rounded p-1 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] transition"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => void handleCreateInProject(project.id)}
                            disabled={actionLoading}
                            className="rounded p-1 text-[color:var(--accent)] hover:text-[color:var(--accent-strong)] transition disabled:opacity-40"
                          >
                            {actionLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Project context menu */}
                  {projectMenuId === project.id && (
                    <div className="absolute right-2 top-full z-20 mt-0.5 rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] py-1 shadow-lg min-w-[140px]">
                      <button
                        onClick={() => {
                          setEditProjectName(project.name);
                          setEditingProjectId(project.id);
                          setProjectMenuId(null);
                        }}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[color:var(--text)] hover:bg-[color:var(--surface-muted)] transition"
                      >
                        <Pencil className="h-3 w-3" /> Rename
                      </button>
                      <button
                        onClick={() => void handleArchiveProject(project.id)}
                        disabled={actionLoading}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-rose-500 hover:bg-[color:var(--surface-muted)] transition disabled:opacity-40"
                      >
                        <Archive className="h-3 w-3" /> Archive
                      </button>
                    </div>
                  )}

                  {!isCollapsed && projectSessions.map((s) => renderSession(s, true))}
                </div>
              );
            })}

            {/* Unassigned — "No project" */}
            {unassignedSessions.length > 0 && (
              <div>
                {projects.length > 0 && (
                  <div className="px-2 py-1 mt-2 text-[11px] font-medium uppercase tracking-wider text-[color:var(--text-quiet)] opacity-60">
                    No project
                  </div>
                )}
                {unassignedSessions.map((s) => renderSession(s, projects.length > 0))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
