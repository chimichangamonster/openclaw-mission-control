/**
 * GlobalLoader a11y tests (item 117 P3 fix).
 *
 * Test-first per `feedback_test_before_deploy.md`. The bug: a hardcoded
 * `<span class="sr-only">Loading</span>` rendered unconditionally inside
 * a `role="status"` region announces "Loading" to screen readers
 * indefinitely, even when no fetches or mutations are pending. Surfaced
 * 2026-05-06 session #48 grants Phase 2 dogfood via Playwright a11y
 * snapshot — `browser_wait_for textGone="Loading"` timed out at 30s.
 *
 * Fix: conditionally render the sr-only announcement only while
 * `visible` is true, so screen readers receive a finite "Loading" cue
 * that ends when work settles, instead of a perpetual status region.
 */

import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";

import { GlobalLoader } from "./global-loader";

const renderWithClient = (ui: React.ReactElement) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
};

describe("GlobalLoader a11y", () => {
  it("does not announce 'Loading' to screen readers when no queries are pending", () => {
    renderWithClient(<GlobalLoader />);

    expect(screen.queryByText(/loading/i)).toBeNull();
  });

  it("announces 'Loading' while a query is fetching, then removes the announcement once it settles", async () => {
    let resolveQuery: (value: string) => void = () => {};
    const queryPromise = new Promise<string>((resolve) => {
      resolveQuery = resolve;
    });

    function Probe() {
      useQuery({
        queryKey: ["global-loader-probe"],
        queryFn: () => queryPromise,
      });
      return null;
    }

    renderWithClient(
      <>
        <GlobalLoader />
        <Probe />
      </>,
    );

    await waitFor(() => {
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    resolveQuery("done");

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).toBeNull();
    });
  });
});
