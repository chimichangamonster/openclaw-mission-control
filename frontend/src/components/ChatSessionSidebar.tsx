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
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SessionItem {
  key: string;
  displayName?: string;
  groupChannel?: string;
  totalTokens?: number;
  model?: string;
}

interface ChatSessionSidebarProps {
  sessions: SessionItem[];
  activeSessionKey: string | null;
  mainSessionKey: string | null;
  onSelectSession: (key: string) => void;
  onCreateSession: (label: string) => Promise<void>;
  onRenameSession: (key: string, label: string) => Promise<void>;
  onDeleteSession: (key: string) => Promise<void>;
  onClose: () => void;
  isLoading: boolean;
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
  // Extract a readable name from key like "agent:mc-gateway-xxx:chat-abc12345"
  const parts = session.key.split(":");
  const last = parts[parts.length - 1];
  if (last.startsWith("chat-")) return `Conversation ${last.slice(5, 9)}`;
  if (session.groupChannel) return `#${session.groupChannel}`;
  return last;
}

export function ChatSessionSidebar({
  sessions,
  activeSessionKey,
  mainSessionKey,
  onSelectSession,
  onCreateSession,
  onRenameSession,
  onDeleteSession,
  onClose,
  isLoading,
}: ChatSessionSidebarProps) {
  const [creating, setCreating] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [menuKey, setMenuKey] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const handleCreate = async () => {
    const label = newLabel.trim() || `Conversation ${sessions.length + 1}`;
    setActionLoading(true);
    try {
      await onCreateSession(label);
      setNewLabel("");
      setCreating(false);
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

  const handleDelete = async (key: string) => {
    setActionLoading(true);
    try {
      await onDeleteSession(key);
      setMenuKey(null);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="flex h-full w-[260px] shrink-0 flex-col border-r border-[color:var(--border)] bg-[color:var(--surface)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[color:var(--border)] px-3 py-3">
        <h3 className="text-sm font-medium text-[color:var(--text)]">Conversations</h3>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setCreating(true)}
            className="rounded-md p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)] transition"
            title="New conversation"
          >
            <Plus className="h-4 w-4" />
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
            <button
              onClick={() => setCreating(false)}
              className="rounded p-1 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] transition"
            >
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

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-1">
        {isLoading && sessions.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-[color:var(--text-muted)]" />
          </div>
        ) : sessions.length === 0 ? (
          <p className="px-3 py-4 text-xs text-[color:var(--text-quiet)] text-center">
            No conversations yet
          </p>
        ) : (
          sessions.map((session) => {
            const isActive = session.key === activeSessionKey;
            const isMain = session.key === mainSessionKey;
            const label = sessionLabel(session, mainSessionKey);

            return (
              <div key={session.key} className="relative px-1.5 py-0.5">
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
                  <button
                    onClick={() => onSelectSession(session.key)}
                    className={cn(
                      "group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-xs transition",
                      isActive
                        ? "bg-[color:var(--accent)]/10 text-[color:var(--text)]"
                        : "text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)]",
                    )}
                  >
                    <MessageSquare className={cn("h-3.5 w-3.5 shrink-0", isActive ? "text-[color:var(--accent)]" : "")} />
                    <span className="flex-1 truncate">{label}</span>
                    {session.totalTokens ? (
                      <span className="shrink-0 text-[10px] tabular-nums text-[color:var(--text-quiet)] opacity-60">
                        {formatTokens(session.totalTokens)}
                      </span>
                    ) : null}
                    {!isMain && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuKey(menuKey === session.key ? null : session.key);
                        }}
                        className="shrink-0 rounded p-0.5 opacity-0 group-hover:opacity-100 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] transition"
                      >
                        <MoreHorizontal className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </button>
                )}

                {/* Context menu */}
                {menuKey === session.key && !isMain && (
                  <div className="absolute right-2 top-full z-20 mt-0.5 rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] py-1 shadow-lg">
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
                      onClick={() => void handleDelete(session.key)}
                      disabled={actionLoading}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-rose-500 hover:bg-[color:var(--surface-muted)] transition disabled:opacity-40"
                    >
                      <Trash2 className="h-3 w-3" /> Delete
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
