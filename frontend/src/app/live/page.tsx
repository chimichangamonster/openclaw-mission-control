"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { Activity, Radio, Zap } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { customFetch } from "@/api/mutator";
import { cn } from "@/lib/utils";

interface AgentSession {
  agent_id: string;
  channel: string;
  model: string;
  last_active: string;
  seconds_ago: number;
  input_tokens: number;
  output_tokens: number;
  status: "active" | "idle" | "sleeping";
}

interface LiveFeed {
  sessions: AgentSession[];
  timestamp: string;
}

async function fetchLiveFeed(): Promise<LiveFeed> {
  const res: any = await customFetch("/api/v1/gateway/live", { method: "GET" });
  const data = res?.data ?? res;
  return data as LiveFeed;
}

function statusDot(status: string) {
  if (status === "active") return "bg-green-500 animate-pulse";
  if (status === "idle") return "bg-yellow-500";
  return "bg-slate-300";
}

function statusLabel(status: string) {
  if (status === "active") return "Active now";
  if (status === "idle") return "Idle";
  return "Sleeping";
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function formatTokens(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export default function LivePage() {
  const { isSignedIn } = useAuth();
  const [feed, setFeed] = useState<LiveFeed | null>(null);
  const [loading, setLoading] = useState(true);

  const poll = useCallback(async () => {
    try {
      const data = await fetchLiveFeed();
      setFeed(data);
    } catch {
      // silent fail on poll
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isSignedIn) return;
    poll();
    const interval = setInterval(poll, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [isSignedIn, poll]);

  const sessions = feed?.sessions || [];
  const activeCount = sessions.filter((s: AgentSession) => s.status === "active").length;

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view live activity.",
        forceRedirectUrl: "/live",
        signUpForceRedirectUrl: "/live",
      }}
      title="Live Activity"
      description="Real-time agent activity across Discord channels."
    >
      <div className="space-y-6">
        {/* Status bar */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Radio className="h-4 w-4 text-green-500" />
            <span className="text-sm font-medium text-slate-700">
              {activeCount} active {activeCount === 1 ? "session" : "sessions"}
            </span>
          </div>
          <span className="text-xs text-slate-400">
            Polling every 5s
          </span>
        </div>

        {/* Sessions */}
        {loading && sessions.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-slate-500">
            Connecting to gateway...
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-slate-500">
            <Activity className="mb-3 h-10 w-10 text-slate-300" />
            <p>No active agent sessions</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {sessions.map((s: AgentSession, i: number) => (
              <div
                key={`${s.agent_id}-${s.channel}-${i}`}
                className={cn(
                  "rounded-xl border p-4 transition-all",
                  s.status === "active"
                    ? "border-green-200 bg-green-50/50 shadow-sm"
                    : s.status === "idle"
                    ? "border-yellow-200 bg-yellow-50/30"
                    : "border-slate-200 bg-white",
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {/* Status dot */}
                    <div className={cn("h-2.5 w-2.5 rounded-full", statusDot(s.status))} />
                    {/* Channel + agent */}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-800">{s.channel}</span>
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                          {s.agent_id}
                        </span>
                      </div>
                      <div className="mt-0.5 flex items-center gap-3 text-xs text-slate-500">
                        <span>{statusLabel(s.status)}</span>
                        <span>{formatAge(s.seconds_ago)}</span>
                      </div>
                    </div>
                  </div>
                  {/* Right side — model + tokens */}
                  <div className="text-right">
                    <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                      <Zap className="h-3 w-3" />
                      {s.model}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-400">
                      {formatTokens(s.input_tokens)} in / {formatTokens(s.output_tokens)} out
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </DashboardPageLayout>
  );
}
