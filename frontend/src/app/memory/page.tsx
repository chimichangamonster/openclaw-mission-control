"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { Brain, Check, Edit3, RefreshCw, Save, X } from "lucide-react";

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

async function fetchMemoryFiles(): Promise<MemoryFile[]> {
  const res: any = await customFetch("/api/v1/memory/files", { method: "GET" });
  const data = res?.data ?? res;
  return Array.isArray(data) ? data : [];
}

async function fetchMemoryFile(name: string): Promise<MemoryFile> {
  const res: any = await customFetch(`/api/v1/memory/files/${encodeURIComponent(name)}`, { method: "GET" });
  return res?.data ?? res;
}

async function updateMemoryFile(name: string, content: string): Promise<MemoryFile> {
  const res: any = await customFetch(`/api/v1/memory/files/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify({ content }),
  });
  return res?.data ?? res;
}

export default function MemoryPage() {
  const { isSignedIn } = useAuth();
  const [files, setFiles] = useState<MemoryFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingFile, setLoadingFile] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

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

  useEffect(() => {
    if (isSignedIn) loadFiles();
  }, [isSignedIn, loadFiles]);

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

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to manage agent memory.",
        forceRedirectUrl: "/memory",
        signUpForceRedirectUrl: "/memory",
      }}
      title="Agent Memory"
      description="View and edit The Claw's memory files. Changes take effect on next session."
    >
      <div className="flex gap-6">
        {/* File list */}
        <div className="w-64 shrink-0">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-700">Memory Files</h3>
            <button onClick={loadFiles} className="text-slate-400 hover:text-slate-600">
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            </button>
          </div>
          <div className="space-y-1">
            {files.map((f) => (
              <button
                key={f.name}
                onClick={() => openFile(f.name)}
                className={cn(
                  "w-full text-left rounded-lg px-3 py-2.5 text-sm transition",
                  selectedFile === f.name
                    ? "bg-blue-100 text-blue-800 font-medium"
                    : "text-slate-700 hover:bg-slate-100",
                )}
              >
                <div className="font-medium">{f.name}</div>
                <div className="text-xs text-slate-500 mt-0.5">{f.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* File content */}
        <div className="flex-1 min-w-0">
          {!selectedFile ? (
            <div className="flex flex-col items-center justify-center py-16 text-slate-500">
              <Brain className="mb-3 h-10 w-10 text-slate-300" />
              <p>Select a memory file to view or edit</p>
              <p className="mt-1 text-xs">
                These files define who The Claw is and what it knows.
              </p>
            </div>
          ) : loadingFile ? (
            <div className="flex items-center justify-center py-16 text-slate-500">
              Loading...
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-semibold text-slate-800">{selectedFile}</h3>
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
                      <Button size="sm" onClick={saveFile} disabled={saving}>
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
                  className="w-full h-[600px] rounded-lg border border-slate-300 bg-white p-4 font-mono text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
                  spellCheck={false}
                />
              ) : (
                <pre className="w-full overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-4 font-mono text-sm text-slate-800 whitespace-pre-wrap leading-relaxed max-h-[600px]">
                  {fileContent || "(empty file)"}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </DashboardPageLayout>
  );
}
