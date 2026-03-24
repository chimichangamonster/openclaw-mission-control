"use client";

import { AuthMode } from "@/auth/mode";

let wechatToken: string | null = null;
const STORAGE_KEY = "mc_wechat_auth_token";

export function isWeChatAuthMode(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_MODE === AuthMode.WeChat;
}

export function setWeChatAuthToken(token: string): void {
  wechatToken = token;
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Ignore storage failures (private mode / policy).
  }
}

export function getWeChatAuthToken(): string | null {
  if (wechatToken) return wechatToken;
  if (typeof window === "undefined") return null;
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY);
    if (stored) {
      wechatToken = stored;
      return stored;
    }
  } catch {
    // Ignore storage failures (private mode / policy).
  }
  return null;
}

export function clearWeChatAuthToken(): void {
  wechatToken = null;
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore storage failures (private mode / policy).
  }
}
