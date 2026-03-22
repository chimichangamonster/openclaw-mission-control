"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/auth/clerk";
import { customFetch } from "@/api/mutator";

interface TermsStatus {
  terms_accepted: boolean;
  current_version: string;
  accepted_version: string | null;
}

export function TermsGate({ children }: { children: React.ReactNode }) {
  const { isSignedIn } = useAuth();
  const [status, setStatus] = useState<TermsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [showTerms, setShowTerms] = useState(false);
  const [showPrivacy, setShowPrivacy] = useState(false);

  const checkTerms = useCallback(async () => {
    try {
      const raw: any = await customFetch("/api/v1/auth/terms-status", { method: "GET" });
      const data = raw?.data ?? raw;
      setStatus(data as TermsStatus);
    } catch {
      // If the endpoint fails (e.g., not deployed yet), don't block the user
      setStatus({ terms_accepted: true, current_version: "0", accepted_version: "0" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSignedIn) {
      checkTerms();
    } else {
      setLoading(false);
    }
  }, [isSignedIn, checkTerms]);

  const acceptTerms = async () => {
    try {
      setAccepting(true);
      await customFetch("/api/v1/auth/accept-terms", { method: "POST" });
      await checkTerms();
    } finally {
      setAccepting(false);
    }
  };

  // Don't block while loading or if not signed in
  if (loading || !isSignedIn) return <>{children}</>;

  // If terms are accepted, render children normally
  if (status?.terms_accepted) return <>{children}</>;

  // Show terms acceptance modal
  return (
    <>
      {children}
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm">
        <div className="mx-4 w-full max-w-lg rounded-2xl bg-white shadow-2xl">
          <div className="px-6 pt-6 pb-4">
            <h2 className="text-lg font-bold text-slate-900">Terms of Service Update</h2>
            <p className="mt-1 text-sm text-slate-500">
              Please review and accept our updated terms to continue using the platform.
            </p>
          </div>

          <div className="px-6 space-y-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-600 space-y-2">
              <p>By accepting, you agree to:</p>
              <ul className="list-disc ml-4 space-y-1">
                <li>Our <button onClick={() => setShowTerms(true)} className="text-blue-600 hover:underline font-medium">Terms of Service</button> governing platform use</li>
                <li>Our <button onClick={() => setShowPrivacy(true)} className="text-blue-600 hover:underline font-medium">Privacy Policy</button> explaining how data is handled</li>
                <li>Data processing by third-party LLM providers as described in our data flow disclosures</li>
              </ul>
              <p className="text-[10px] text-slate-400 mt-2">Version: {status?.current_version ?? "unknown"}</p>
            </div>
          </div>

          <div className="flex justify-end gap-3 px-6 py-4">
            <button
              onClick={acceptTerms}
              disabled={accepting}
              className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition"
            >
              {accepting ? "Accepting..." : "I Accept"}
            </button>
          </div>
        </div>
      </div>

      {/* Terms of Service viewer */}
      {showTerms && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-3xl max-h-[80vh] rounded-2xl bg-white shadow-2xl flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <h3 className="text-sm font-semibold text-slate-900">Terms of Service</h3>
              <button onClick={() => setShowTerms(false)} className="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
            </div>
            <iframe src="/api/v1/legal/terms" className="flex-1 w-full" title="Terms of Service" />
          </div>
        </div>
      )}

      {/* Privacy Policy viewer */}
      {showPrivacy && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-3xl max-h-[80vh] rounded-2xl bg-white shadow-2xl flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <h3 className="text-sm font-semibold text-slate-900">Privacy Policy</h3>
              <button onClick={() => setShowPrivacy(false)} className="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
            </div>
            <iframe src="/api/v1/legal/privacy" className="flex-1 w-full" title="Privacy Policy" />
          </div>
        </div>
      )}
    </>
  );
}
