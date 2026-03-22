"use client";

import { useFeatureFlags } from "@/lib/use-feature-flags";
import { ShieldOff } from "lucide-react";

interface FeatureGateProps {
  flag: string;
  label?: string;
  children: React.ReactNode;
}

export function FeatureGate({ flag, label, children }: FeatureGateProps) {
  const { isFeatureEnabled, isLoading } = useFeatureFlags();

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  if (!isFeatureEnabled(flag)) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 text-slate-500">
        <ShieldOff className="h-12 w-12 text-slate-300" />
        <p className="text-lg font-medium">Feature not enabled</p>
        <p className="text-sm">
          {label || flag.replace(/_/g, " ")} is disabled for this organization.
          Contact your admin to enable it in Org Settings.
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
