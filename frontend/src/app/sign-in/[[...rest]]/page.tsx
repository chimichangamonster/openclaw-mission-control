"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { SignIn } from "@clerk/nextjs";
import { MessageSquare } from "lucide-react";

import { isLocalAuthMode } from "@/auth/localAuth";
import { resolveSignInRedirectUrl } from "@/auth/redirects";
import { LocalAuthLogin } from "@/components/organisms/LocalAuthLogin";
import { getApiBaseUrl } from "@/lib/api-base";

export default function SignInPage() {
  const searchParams = useSearchParams();
  const [wechatEnabled, setWechatEnabled] = useState(false);
  const [wechatLoading, setWechatLoading] = useState(false);

  useEffect(() => {
    const checkProviders = async () => {
      try {
        const baseUrl = getApiBaseUrl();
        const res = await fetch(`${baseUrl}/api/v1/auth/providers`);
        if (res.ok) {
          const data = await res.json();
          setWechatEnabled(data.wechat_login === true);
        }
      } catch {
        // ignore
      }
    };
    checkProviders();
  }, []);

  if (isLocalAuthMode()) {
    return <LocalAuthLogin />;
  }

  const forceRedirectUrl = resolveSignInRedirectUrl(
    searchParams.get("redirect_url"),
  );

  const handleWeChatLogin = async () => {
    setWechatLoading(true);
    try {
      const baseUrl = getApiBaseUrl();
      const callbackUrl = `${window.location.origin}/auth/wechat/callback`;
      const res = await fetch(
        `${baseUrl}/api/v1/auth/wechat/authorize?redirect_uri=${encodeURIComponent(callbackUrl)}`,
      );
      if (res.ok) {
        const data = await res.json();
        if (data.authorize_url) {
          window.location.href = data.authorize_url;
          return;
        }
      }
      setWechatLoading(false);
    } catch {
      setWechatLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-[color:var(--bg)] p-6">
      <div className="flex flex-col items-center gap-6">
        <SignIn
          routing="path"
          path="/sign-in"
          forceRedirectUrl={forceRedirectUrl}
        />

        {wechatEnabled && (
          <>
            <div className="flex items-center gap-3 w-full max-w-sm">
              <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
              <span className="text-xs text-slate-400">or</span>
              <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
            </div>
            <button
              onClick={handleWeChatLogin}
              disabled={wechatLoading}
              className="flex items-center gap-3 rounded-lg border border-green-300 bg-green-500 px-6 py-3 text-sm font-medium text-white shadow-sm hover:bg-green-600 transition disabled:opacity-50"
            >
              <MessageSquare className="h-5 w-5" />
              {wechatLoading ? "Redirecting..." : "Sign in with WeChat"}
            </button>
          </>
        )}
      </div>
    </main>
  );
}
