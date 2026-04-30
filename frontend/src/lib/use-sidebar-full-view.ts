"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "vc_sidebar_full_view";

function read(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) onChange();
  };
  window.addEventListener("storage", handler);
  window.addEventListener("vc_sidebar_full_view_change", onChange);
  return () => {
    window.removeEventListener("storage", handler);
    window.removeEventListener("vc_sidebar_full_view_change", onChange);
  };
}

export function useSidebarFullView(): {
  fullView: boolean;
  toggle: () => void;
} {
  const fullView = useSyncExternalStore(
    subscribe,
    read,
    () => false,
  );

  const toggle = useCallback(() => {
    const next = !read();
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
    } catch {
      // localStorage unavailable — same-tab dispatch still notifies subscribers
    }
    window.dispatchEvent(new Event("vc_sidebar_full_view_change"));
  }, []);

  return { fullView, toggle };
}
