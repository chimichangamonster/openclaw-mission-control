"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { setWeChatAuthToken } from "@/auth/wechatAuth";
import { customFetch } from "@/api/mutator";
import { getApiBaseUrl } from "@/lib/api-base";

export default function WeChatCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    if (!code) {
      setError("No authorization code received from WeChat.");
      return;
    }

    const exchange = async () => {
      try {
        const baseUrl = getApiBaseUrl();
        const res = await fetch(
          `${baseUrl}/api/v1/auth/wechat/callback?code=${encodeURIComponent(code)}`,
          { method: "POST" },
        );
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          setError(data.detail || "WeChat authentication failed.");
          return;
        }
        const data = await res.json();
        if (data.token) {
          setWeChatAuthToken(data.token);
          router.replace("/dashboard");
        } else {
          setError("No token received.");
        }
      } catch (err) {
        setError("Failed to exchange WeChat code.");
      }
    };

    exchange();
  }, [searchParams, router]);

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-app p-6">
        <div className="rounded-xl border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950 p-6 max-w-md text-center">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          <button
            onClick={() => router.replace("/sign-in")}
            className="mt-4 text-sm underline text-red-600"
          >
            Back to sign in
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-app p-6">
      <div className="flex flex-col items-center gap-3">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-slate-200 border-t-green-500" />
        <p className="text-sm text-[color:var(--text-muted)]">
          Signing in with WeChat...
        </p>
      </div>
    </main>
  );
}
