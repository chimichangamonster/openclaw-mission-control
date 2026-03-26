"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import {
  SignInButton,
  SignedIn,
  SignedOut,
  isClerkEnabled,
} from "@/auth/clerk";

import { UserMenu } from "@/components/organisms/UserMenu";

export function LandingShell({ children }: { children: ReactNode }) {
  const clerkEnabled = isClerkEnabled();

  return (
    <div className="landing-enterprise">
      <nav className="landing-nav" aria-label="Primary navigation">
        <div className="nav-container">
          <Link href="/" className="logo-section" aria-label="VantageClaw home">
            <div className="logo-icon" aria-hidden="true">
              VC
            </div>
            <div className="logo-text">
              <div className="logo-name">VantageClaw</div>
              <div className="logo-tagline">AI Operations</div>
            </div>
          </Link>

          <div className="nav-links">
            <Link href="#capabilities">Capabilities</Link>
            <Link href="#use-cases">Industries</Link>
            <Link href="#pricing">Pricing</Link>
          </div>

          <div className="nav-cta">
            <SignedOut>
              {clerkEnabled ? (
                <SignInButton
                  mode="modal"
                  forceRedirectUrl="/onboarding"
                  signUpForceRedirectUrl="/onboarding"
                >
                  <button type="button" className="btn-primary">
                    Sign In
                  </button>
                </SignInButton>
              ) : (
                <Link href="/boards" className="btn-primary">
                  Get started
                </Link>
              )}
            </SignedOut>

            <SignedIn>
              <Link href="/dashboard" className="btn-secondary">
                Dashboard
              </Link>
              <UserMenu />
            </SignedIn>
          </div>
        </div>
      </nav>

      <main>{children}</main>

      <footer className="landing-footer">
        <div className="footer-content">
          <div className="footer-brand">
            <h3>VantageClaw</h3>
            <p>AI operations for Canadian small businesses. Built by Vantage Solutions, Edmonton AB.</p>
            <div className="footer-tagline">henry@vantagesolutions.ca</div>
          </div>

          <div className="footer-column">
            <h4>Platform</h4>
            <div className="footer-links">
              <Link href="#capabilities">Capabilities</Link>
              <Link href="#use-cases">Industries</Link>
              <Link href="#pricing">Pricing</Link>
            </div>
          </div>

          <div className="footer-column">
            <h4>Platform</h4>
            <div className="footer-links">
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/chat">Chat</Link>
              <Link href="/activity">Activity</Link>
            </div>
          </div>

          <div className="footer-column">
            <h4>Access</h4>
            <div className="footer-links">
              <SignedOut>
                {clerkEnabled ? (
                  <SignInButton
                    mode="modal"
                    forceRedirectUrl="/onboarding"
                    signUpForceRedirectUrl="/onboarding"
                  >
                    <button type="button">Sign In</button>
                  </SignInButton>
                ) : (
                  <Link href="/boards">Boards</Link>
                )}
              </SignedOut>
              <SignedIn>
                <Link href="/dashboard">Dashboard</Link>
                <Link href="/chat">Chat</Link>
              </SignedIn>
            </div>
          </div>
        </div>

        <div className="footer-bottom">
          <div className="footer-copyright">
            &copy; {new Date().getFullYear()} VantageClaw. Built by Vantage Solutions.
          </div>
          <div className="footer-bottom-links">
            <Link href="#capabilities">Capabilities</Link>
            <Link href="#use-cases">Industries</Link>
            <Link href="#pricing">Pricing</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
