"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  HelpCircle,
  MessageSquare,
  Settings,
  Shield,
  Users,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "vantageclaw_welcome_dismissed";

const steps = [
  {
    icon: MessageSquare,
    title: "Chat with your AI assistant",
    description:
      "Go to Chat in the sidebar. Ask anything in plain English — invoices, schedules, reports. Upload documents by pasting or using the paperclip.",
    href: "/chat",
    cta: "Open Chat",
  },
  {
    icon: Settings,
    title: "Configure your workspace",
    description:
      "Set up API keys, enable features, connect email and calendar integrations. Everything is in Org Settings.",
    href: "/org-settings",
    cta: "Org Settings",
  },
  {
    icon: Users,
    title: "Invite your team",
    description:
      "Add team members and assign roles — Owner, Admin, Operator, Member, or Viewer. Each role sees only what they need.",
    href: "/organization",
    cta: "Manage Team",
  },
  {
    icon: Shield,
    title: "Your data is secure",
    description:
      "Every org gets isolated encryption, audit logging, and role-based access. API keys are encrypted at rest with AES-256-GCM.",
    href: "/help",
    cta: "Learn More",
  },
];

export function WelcomeModal() {
  const [visible, setVisible] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const dismissed = localStorage.getItem(STORAGE_KEY);
    if (!dismissed) {
      setVisible(true);
    }
  }, []);

  const dismiss = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, "1");
    setVisible(false);
  }, []);

  if (!visible) return null;

  const step = steps[currentStep];
  const isLast = currentStep === steps.length - 1;
  const Icon = step.icon;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4">
      <div className="relative w-full max-w-lg rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface)] shadow-xl">
        {/* Close button */}
        <button
          onClick={dismiss}
          className="absolute right-4 top-4 rounded-lg p-1.5 text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)] transition"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="p-6 sm:p-8">
          {/* Header */}
          {currentStep === 0 && (
            <div className="mb-6">
              <h2 className="text-xl font-bold text-[color:var(--text)]">
                Welcome to VantageClaw
              </h2>
              <p className="mt-1 text-sm text-[color:var(--text-muted)]">
                Here's a quick tour of what you can do.
              </p>
            </div>
          )}

          {/* Step content */}
          <div className="flex items-start gap-4">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[color:var(--accent-soft)]">
              <Icon className="h-6 w-6 text-[color:var(--accent-strong)]" />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-[color:var(--text)]">
                {step.title}
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-[color:var(--text-muted)]">
                {step.description}
              </p>
              <Link
                href={step.href}
                onClick={dismiss}
                className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-[color:var(--accent-strong)] hover:underline"
              >
                {step.cta} &rarr;
              </Link>
            </div>
          </div>

          {/* Step indicators + navigation */}
          <div className="mt-8 flex items-center justify-between">
            <div className="flex gap-1.5">
              {steps.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setCurrentStep(i)}
                  className={cn(
                    "h-2 rounded-full transition-all",
                    i === currentStep
                      ? "w-6 bg-[color:var(--accent-strong)]"
                      : "w-2 bg-[color:var(--border)] hover:bg-[color:var(--text-quiet)]",
                  )}
                  aria-label={`Step ${i + 1}`}
                />
              ))}
            </div>
            <div className="flex gap-2">
              <button
                onClick={dismiss}
                className="rounded-lg px-4 py-2 text-sm text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)] transition"
              >
                Skip
              </button>
              {isLast ? (
                <button
                  onClick={dismiss}
                  className="rounded-lg bg-[color:var(--accent-strong)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 transition"
                >
                  Get Started
                </button>
              ) : (
                <button
                  onClick={() => setCurrentStep((s) => s + 1)}
                  className="rounded-lg bg-[color:var(--accent-strong)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 transition"
                >
                  Next
                </button>
              )}
            </div>
          </div>

          {/* Help link */}
          <div className="mt-4 flex items-center justify-center gap-1.5 text-xs text-[color:var(--text-quiet)]">
            <HelpCircle className="h-3.5 w-3.5" />
            <span>
              Need help anytime?{" "}
              <Link
                href="/help"
                onClick={dismiss}
                className="font-medium text-[color:var(--accent-strong)] hover:underline"
              >
                Visit Help & Support
              </Link>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
