"use client";

export const dynamic = "force-dynamic";

/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  Brain,
  Check,
  ChevronRight,
  Edit3,
  FolderOpen,
  RefreshCw,
  Save,
  X,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { customFetch } from "@/api/mutator";
import { cn } from "@/lib/utils";

interface MemoryFile {
  name: string;
  description: string;
  content: string | null;
}

interface KnowledgeArticle {
  path: string;
  title: string;
  category: string;
}

async function fetchMemoryFiles(): Promise<MemoryFile[]> {
  const res: any = await customFetch("/api/v1/memory/files", { method: "GET" });
  const data = res?.data ?? res;
  return Array.isArray(data) ? data : [];
}

async function fetchMemoryFile(name: string): Promise<MemoryFile> {
  const res: any = await customFetch(
    `/api/v1/memory/files/${encodeURIComponent(name)}`,
    { method: "GET" },
  );
  return res?.data ?? res;
}

async function updateMemoryFile(
  name: string,
  content: string,
): Promise<MemoryFile> {
  const res: any = await customFetch(
    `/api/v1/memory/files/${encodeURIComponent(name)}`,
    { method: "PUT", body: JSON.stringify({ content }) },
  );
  return res?.data ?? res;
}

async function fetchKnowledgeArticles(): Promise<KnowledgeArticle[]> {
  const res: any = await customFetch("/api/v1/memory/knowledge", {
    method: "GET",
  });
  const data = res?.data ?? res;
  return Array.isArray(data) ? data : [];
}

async function fetchKnowledgeArticle(path: string): Promise<MemoryFile> {
  const res: any = await customFetch(`/api/v1/memory/knowledge/${path}`, {
    method: "GET",
  });
  return res?.data ?? res;
}

export default function MemoryPage() {
  const { isSignedIn } = useAuth();
  const [tab, setTab] = useState<"files" | "knowledge">("files");

  // Memory files state
  const [files, setFiles] = useState<MemoryFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingFile, setLoadingFile] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Knowledge base state
  const [articles, setArticles] = useState<KnowledgeArticle[]>([]);
  const [kbLoading, setKbLoading] = useState(false);
  const [selectedArticle, setSelectedArticle] = useState<string | null>(null);
  const [articleContent, setArticleContent] = useState("");
  const [loadingArticle, setLoadingArticle] = useState(false);

  const loadFiles = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchMemoryFiles();
      setFiles(data);
    } catch {
      setFiles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadKnowledge = useCallback(async () => {
    try {
      setKbLoading(true);
      const data = await fetchKnowledgeArticles();
      setArticles(data);
    } catch {
      setArticles([]);
    } finally {
      setKbLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSignedIn) {
      loadFiles();
      loadKnowledge();
    }
  }, [isSignedIn, loadFiles, loadKnowledge]);

  const openFile = async (name: string) => {
    try {
      setLoadingFile(true);
      setSelectedFile(name);
      setEditing(false);
      setSaveSuccess(false);
      const file = await fetchMemoryFile(name);
      setFileContent(file.content || "");
      setEditContent(file.content || "");
    } catch {
      setFileContent("Error loading file");
    } finally {
      setLoadingFile(false);
    }
  };

  const openArticle = async (path: string) => {
    try {
      setLoadingArticle(true);
      setSelectedArticle(path);
      const file = await fetchKnowledgeArticle(path);
      setArticleContent(file.content || "");
    } catch {
      setArticleContent("Error loading article");
    } finally {
      setLoadingArticle(false);
    }
  };

  const saveFile = async () => {
    if (!selectedFile) return;
    try {
      setSaving(true);
      await updateMemoryFile(selectedFile, editContent);
      setFileContent(editContent);
      setEditing(false);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch {
      alert("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  // Group knowledge articles by category
  const categories = articles.reduce<Record<string, KnowledgeArticle[]>>(
    (acc, a) => {
      (acc[a.category] ||= []).push(a);
      return acc;
    },
    {},
  );

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to manage agent memory.",
        forceRedirectUrl: "/memory",
        signUpForceRedirectUrl: "/memory",
      }}
      title="Agent Memory"
      description="View and edit agent memory files, and browse the compiled knowledge base."
    >
      {/* Tabs */}
      <div className="mb-6 flex gap-1 rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-muted)] p-1">
        <button
          onClick={() => setTab("files")}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition",
            tab === "files"
              ? "bg-[color:var(--surface)] text-[color:var(--text)] shadow-sm"
              : "text-[color:var(--text-quiet)] hover:text-[color:var(--text)]",
          )}
        >
          <Brain className="h-3.5 w-3.5" />
          Memory Files
        </button>
        <button
          onClick={() => setTab("knowledge")}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition",
            tab === "knowledge"
              ? "bg-[color:var(--surface)] text-[color:var(--text)] shadow-sm"
              : "text-[color:var(--text-quiet)] hover:text-[color:var(--text)]",
          )}
        >
          <BookOpen className="h-3.5 w-3.5" />
          Knowledge Base
          {articles.length > 0 && (
            <span className="ml-1 rounded-full bg-[color:var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-semibold">
              {articles.length}
            </span>
          )}
        </button>
      </div>

      {tab === "files" ? (
        <div className="flex flex-col gap-6 md:flex-row">
          {/* File list */}
          <div className="w-full md:w-64 md:shrink-0">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[color:var(--text)]">
                Memory Files
              </h3>
              <button
                onClick={loadFiles}
                className="text-[color:var(--text-quiet)] hover:text-[color:var(--text)]"
              >
                <RefreshCw
                  className={cn("h-3.5 w-3.5", loading && "animate-spin")}
                />
              </button>
            </div>
            <div className="space-y-1">
              {files.map((f) => (
                <button
                  key={f.name}
                  onClick={() => openFile(f.name)}
                  className={cn(
                    "w-full rounded-lg px-3 py-2.5 text-left text-sm transition",
                    selectedFile === f.name
                      ? "bg-blue-100 font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                      : "text-[color:var(--text)] hover:bg-[color:var(--surface-muted)]",
                  )}
                >
                  <div className="font-medium">{f.name}</div>
                  <div className="mt-0.5 text-xs text-[color:var(--text-quiet)]">
                    {f.description}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* File content */}
          <div className="min-w-0 flex-1">
            {!selectedFile ? (
              <div className="flex flex-col items-center justify-center py-16 text-[color:var(--text-quiet)]">
                <Brain className="mb-3 h-10 w-10 opacity-30" />
                <p>Select a memory file to view or edit</p>
                <p className="mt-1 text-xs">
                  These files define who The Claw is and what it knows.
                </p>
              </div>
            ) : loadingFile ? (
              <div className="flex items-center justify-center py-16 text-[color:var(--text-quiet)]">
                Loading...
              </div>
            ) : (
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-[color:var(--text)]">
                    {selectedFile}
                  </h3>
                  <div className="flex items-center gap-2">
                    {saveSuccess && (
                      <span className="flex items-center gap-1 text-xs text-green-600">
                        <Check className="h-3.5 w-3.5" /> Saved
                      </span>
                    )}
                    {editing ? (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setEditing(false);
                            setEditContent(fileContent);
                          }}
                        >
                          <X className="mr-1.5 h-3.5 w-3.5" />
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          onClick={saveFile}
                          disabled={saving}
                        >
                          <Save className="mr-1.5 h-3.5 w-3.5" />
                          {saving ? "Saving..." : "Save"}
                        </Button>
                      </>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditing(true)}
                      >
                        <Edit3 className="mr-1.5 h-3.5 w-3.5" />
                        Edit
                      </Button>
                    )}
                  </div>
                </div>

                {editing ? (
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="h-[600px] w-full resize-none rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-4 font-mono text-sm text-[color:var(--text)] focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    spellCheck={false}
                  />
                ) : (
                  <pre className="max-h-[600px] w-full overflow-auto whitespace-pre-wrap rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-muted)] p-4 font-mono text-sm leading-relaxed text-[color:var(--text)]">
                    {fileContent || "(empty file)"}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Knowledge Base tab */
        <div className="flex flex-col gap-6 md:flex-row">
          {/* Article list by category */}
          <div className="w-full md:w-72 md:shrink-0">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[color:var(--text)]">
                Articles
              </h3>
              <button
                onClick={loadKnowledge}
                className="text-[color:var(--text-quiet)] hover:text-[color:var(--text)]"
              >
                <RefreshCw
                  className={cn("h-3.5 w-3.5", kbLoading && "animate-spin")}
                />
              </button>
            </div>
            {articles.length === 0 && !kbLoading ? (
              <p className="text-sm text-[color:var(--text-quiet)]">
                No knowledge articles yet. Run the knowledge-compile skill to
                build the knowledge base.
              </p>
            ) : (
              <div className="space-y-4">
                {Object.entries(categories)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([cat, items]) => (
                    <div key={cat}>
                      <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
                        <FolderOpen className="h-3 w-3" />
                        {cat.replace(/-/g, " ")}
                      </div>
                      <div className="space-y-0.5">
                        {items.map((a) => (
                          <button
                            key={a.path}
                            onClick={() => openArticle(a.path)}
                            className={cn(
                              "flex w-full items-center gap-1.5 rounded-md px-2.5 py-1.5 text-left text-sm transition",
                              selectedArticle === a.path
                                ? "bg-blue-100 font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                                : "text-[color:var(--text)] hover:bg-[color:var(--surface-muted)]",
                            )}
                          >
                            <ChevronRight className="h-3 w-3 shrink-0 text-[color:var(--text-quiet)]" />
                            <span className="truncate">{a.title}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>

          {/* Article content */}
          <div className="min-w-0 flex-1">
            {!selectedArticle ? (
              <div className="flex flex-col items-center justify-center py-16 text-[color:var(--text-quiet)]">
                <BookOpen className="mb-3 h-10 w-10 opacity-30" />
                <p>Select an article to read</p>
                <p className="mt-1 text-xs">
                  Compiled from cron scan outputs by the knowledge-compile
                  skill.
                </p>
              </div>
            ) : loadingArticle ? (
              <div className="flex items-center justify-center py-16 text-[color:var(--text-quiet)]">
                Loading...
              </div>
            ) : (
              <div>
                <h3 className="mb-3 text-lg font-semibold text-[color:var(--text)]">
                  {articles.find((a) => a.path === selectedArticle)?.title ||
                    selectedArticle}
                </h3>
                <pre className="max-h-[600px] w-full overflow-auto whitespace-pre-wrap rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-muted)] p-4 font-mono text-sm leading-relaxed text-[color:var(--text)]">
                  {articleContent || "(empty article)"}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </DashboardPageLayout>
  );
}
