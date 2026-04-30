"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { SignOutButton, useUser } from "@/auth/clerk";
import { clearLocalAuthToken, isLocalAuthMode } from "@/auth/localAuth";
import {
  ChevronDown,
  LogOut,
  Settings,
  Sparkles,
  UserCircle,
} from "lucide-react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useAuth } from "@/auth/clerk";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import { usePlatformRole } from "@/lib/use-platform-role";
import { cn } from "@/lib/utils";

type UserMenuProps = {
  className?: string;
  displayName?: string;
  displayEmail?: string;
};

export function UserMenu({
  className,
  displayName: displayNameFromDb,
  displayEmail: displayEmailFromDb,
}: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const { user } = useUser();
  const { isSignedIn } = useAuth();
  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const { isPlatformOwner } = usePlatformRole(isSignedIn);
  const localMode = isLocalAuthMode();
  if (!user && !localMode) return null;

  const avatarUrl = localMode ? null : (user?.imageUrl ?? null);
  const avatarLabelSource =
    displayNameFromDb ?? (localMode ? "Local User" : user?.id) ?? "U";
  const avatarLabel = avatarLabelSource.slice(0, 1).toUpperCase();
  const displayName =
    displayNameFromDb ?? (localMode ? "Local User" : "Account");
  const displayEmail =
    displayEmailFromDb ?? (localMode ? "local@localhost" : "");

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "group inline-flex h-9 items-center gap-2 rounded-[10px] bg-transparent px-1 py-1 transition",
            "hover:bg-[color:var(--surface-muted)]",
            // Avoid the default browser focus outline (often bright blue) on click.
            // Keep a subtle, enterprise-looking focus ring for keyboard navigation.
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--neutral-300,var(--border-strong))] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--surface)]",
            "data-[state=open]:bg-[color:var(--surface-muted)]",
            className,
          )}
          aria-label="Open user menu"
        >
          <span
            className={cn(
              "relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-[10px] text-xs font-semibold text-white shadow-sm",
              avatarUrl
                ? "bg-[color:var(--neutral-200,var(--surface-muted))]"
                : "bg-gradient-to-br from-[color:var(--primary-navy,var(--accent))] to-[color:var(--secondary-navy,var(--accent-strong))]",
            )}
          >
            {avatarUrl ? (
              <Image
                src={avatarUrl}
                alt="User avatar"
                width={36}
                height={36}
                className="h-9 w-9 object-cover"
              />
            ) : (
              avatarLabel
            )}
          </span>
          <ChevronDown className="h-4 w-4 text-[color:var(--neutral-700,var(--text-quiet))] transition group-data-[state=open]:rotate-180" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={12}
        className="w-80 overflow-hidden rounded-2xl border border-[color:var(--neutral-200,var(--border))] bg-[color:var(--surface)] p-0 shadow-[0_8px_32px_rgba(10,22,40,0.08)] backdrop-blur"
      >
        <div className="border-b border-[color:var(--neutral-200,var(--border))] px-4 py-3">
          <div className="flex items-center gap-3">
            <span
              className={cn(
                "flex h-10 w-10 items-center justify-center overflow-hidden rounded-xl text-sm font-semibold text-white",
                avatarUrl
                  ? "bg-[color:var(--neutral-200,var(--surface-muted))]"
                  : "bg-gradient-to-br from-[color:var(--primary-navy,var(--accent))] to-[color:var(--secondary-navy,var(--accent-strong))]",
              )}
            >
              {avatarUrl ? (
                <Image
                  src={avatarUrl}
                  alt="User avatar"
                  width={40}
                  height={40}
                  className="h-10 w-10 object-cover"
                />
              ) : (
                avatarLabel
              )}
            </span>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-[color:var(--primary-navy,var(--text))]">
                {displayName}
              </div>
              {displayEmail ? (
                <div className="truncate text-xs text-[color:var(--neutral-700,var(--text-muted))]">
                  {displayEmail}
                </div>
              ) : null}
            </div>
          </div>
        </div>
        <div className="p-2">
          <Link
            href="/settings"
            className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-[color:var(--neutral-800,var(--text))] transition hover:bg-[color:var(--neutral-100,var(--surface-muted))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent-teal,var(--accent))] focus-visible:ring-offset-2"
            onClick={() => setOpen(false)}
          >
            <UserCircle className="h-4 w-4 text-[color:var(--neutral-700,var(--text-quiet))]" />
            Account settings
          </Link>

          {isAdmin ? (
            <Link
              href="/admin"
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-[color:var(--neutral-800,var(--text))] transition hover:bg-[color:var(--neutral-100,var(--surface-muted))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent-teal,var(--accent))] focus-visible:ring-offset-2"
              onClick={() => setOpen(false)}
            >
              <Settings className="h-4 w-4 text-[color:var(--neutral-700,var(--text-quiet))]" />
              Admin
            </Link>
          ) : null}

          {isPlatformOwner ? (
            <Link
              href="/platform"
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-[color:var(--neutral-800,var(--text))] transition hover:bg-[color:var(--neutral-100,var(--surface-muted))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent-teal,var(--accent))] focus-visible:ring-offset-2"
              onClick={() => setOpen(false)}
            >
              <Sparkles className="h-4 w-4 text-[color:var(--neutral-700,var(--text-quiet))]" />
              Platform Owner
            </Link>
          ) : null}

          <div className="my-2 h-px bg-[color:var(--neutral-200,var(--border))]" />

          {localMode ? (
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-[color:var(--neutral-800,var(--text))] transition hover:bg-[color:var(--neutral-100,var(--surface-muted))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent-teal,var(--accent))] focus-visible:ring-offset-2"
              onClick={() => {
                clearLocalAuthToken();
                setOpen(false);
                window.location.reload();
              }}
            >
              <LogOut className="h-4 w-4 text-[color:var(--neutral-700,var(--text-quiet))]" />
              Sign out
            </button>
          ) : (
            <SignOutButton>
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-[color:var(--neutral-800,var(--text))] transition hover:bg-[color:var(--neutral-100,var(--surface-muted))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent-teal,var(--accent))] focus-visible:ring-offset-2"
                onClick={() => setOpen(false)}
              >
                <LogOut className="h-4 w-4 text-[color:var(--neutral-700,var(--text-quiet))]" />
                Sign out
              </button>
            </SignOutButton>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
