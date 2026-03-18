"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Key, Shield, Trash2, Wallet } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import {
  type PolymarketWallet,
  type RiskConfig,
  connectWallet,
  disconnectWallet,
  fetchRiskConfig,
  fetchWallet,
  updateRiskConfig,
} from "@/lib/polymarket-api";

export default function TradingSettingsPage() {
  const { isSignedIn } = useAuth();

  const [wallet, setWallet] = useState<PolymarketWallet | null>(null);
  const [risk, setRisk] = useState<RiskConfig | null>(null);
  const [loading, setLoading] = useState(true);

  // Wallet form
  const [privateKey, setPrivateKey] = useState("");
  const [label, setLabel] = useState("Main Trading Wallet");
  const [connecting, setConnecting] = useState(false);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  // Risk form
  const [maxTradeSize, setMaxTradeSize] = useState("100");
  const [dailyLimit, setDailyLimit] = useState("");
  const [weeklyLimit, setWeeklyLimit] = useState("");
  const [riskSaving, setRiskSaving] = useState(false);
  const [riskSuccess, setRiskSuccess] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [w, r] = await Promise.all([fetchWallet(), fetchRiskConfig()]);
      setWallet(w);
      setRisk(r);
      if (r) {
        setMaxTradeSize(String(r.max_trade_size_usdc));
        setDailyLimit(r.daily_loss_limit_usdc != null ? String(r.daily_loss_limit_usdc) : "");
        setWeeklyLimit(r.weekly_loss_limit_usdc != null ? String(r.weekly_loss_limit_usdc) : "");
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSignedIn) load();
  }, [isSignedIn, load]);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!privateKey.trim()) return;
    try {
      setConnecting(true);
      setWalletError(null);
      const w = await connectWallet(privateKey.trim(), label.trim());
      setWallet(w);
      setPrivateKey("");
    } catch (err: unknown) {
      setWalletError(err instanceof Error ? err.message : "Failed to connect wallet.");
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      setDisconnecting(true);
      await disconnectWallet();
      setWallet(null);
      setDisconnectOpen(false);
    } catch {
      // silent
    } finally {
      setDisconnecting(false);
    }
  };

  const handleSaveRisk = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setRiskSaving(true);
      setRiskSuccess(false);
      const updated = await updateRiskConfig({
        max_trade_size_usdc: parseFloat(maxTradeSize) || 100,
        daily_loss_limit_usdc: dailyLimit ? parseFloat(dailyLimit) : null,
        weekly_loss_limit_usdc: weeklyLimit ? parseFloat(weeklyLimit) : null,
      });
      setRisk(updated);
      setRiskSuccess(true);
    } catch {
      // silent
    } finally {
      setRiskSaving(false);
    }
  };

  return (
    <DashboardPageLayout
      signedOut={{ message: "Sign in to manage trading settings.", forceRedirectUrl: "/trading/settings", signUpForceRedirectUrl: "/trading/settings" }}
      title="Trading Settings"
      description="Configure your Polymarket wallet and risk controls."
    >
      <div className="space-y-4">
        <div className="flex gap-2 border-b border-slate-200 pb-3">
          <Link href="/trading" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">Markets</Link>
          <Link href="/trading/proposals" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">Trade Proposals</Link>
          <Link href="/trading/positions" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">Positions</Link>
          <Link href="/trading/history" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">History</Link>
          <Link href="/trading/settings" className="rounded-lg bg-blue-100 px-3 py-1.5 text-sm font-medium text-blue-800">Settings</Link>
        </div>

        <div className="space-y-6">
          {/* Wallet */}
          <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
              <Wallet className="h-5 w-5" /> Polymarket Wallet
            </h2>

            {wallet ? (
              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between rounded-lg border border-slate-200 p-4">
                  <div>
                    <p className="text-sm font-medium text-slate-900">{wallet.label}</p>
                    <p className="mt-1 font-mono text-xs text-slate-500">{wallet.wallet_address}</p>
                    {wallet.api_credentials_derived_at ? (
                      <p className="mt-1 text-xs text-emerald-600">
                        API credentials derived {new Date(wallet.api_credentials_derived_at).toLocaleString()}
                      </p>
                    ) : (
                      <p className="mt-1 text-xs text-amber-600">API credentials not yet derived</p>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-rose-600 hover:bg-rose-50"
                    onClick={() => setDisconnectOpen(true)}
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Disconnect
                  </Button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleConnect} className="mt-4 space-y-3">
                <p className="text-sm text-slate-500">
                  Paste your Polygon wallet private key. It will be encrypted at rest.
                </p>
                <Input
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="Wallet label"
                />
                <Input
                  type="password"
                  value={privateKey}
                  onChange={(e) => setPrivateKey(e.target.value)}
                  placeholder="Private key (0x...)"
                />
                {walletError ? (
                  <p className="text-sm text-rose-600">{walletError}</p>
                ) : null}
                <Button type="submit" disabled={connecting || !privateKey.trim()}>
                  <Key className="h-4 w-4" />
                  {connecting ? "Connecting..." : "Connect Wallet"}
                </Button>
              </form>
            )}
          </section>

          {/* Risk Controls */}
          <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
              <Shield className="h-5 w-5" /> Risk Controls
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              All trades require human approval. These limits add additional safeguards.
            </p>

            <form onSubmit={handleSaveRisk} className="mt-4 space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-700">Max trade size (USDC)</label>
                  <Input value={maxTradeSize} onChange={(e) => setMaxTradeSize(e.target.value)} type="number" step="0.01" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-700">Daily loss limit (USDC)</label>
                  <Input value={dailyLimit} onChange={(e) => setDailyLimit(e.target.value)} type="number" step="0.01" placeholder="No limit" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-700">Weekly loss limit (USDC)</label>
                  <Input value={weeklyLimit} onChange={(e) => setWeeklyLimit(e.target.value)} type="number" step="0.01" placeholder="No limit" />
                </div>
              </div>

              <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
                Human approval is <strong>always required</strong> for every trade. This cannot be disabled.
              </div>

              {riskSuccess ? (
                <p className="text-sm text-emerald-600">Risk controls saved.</p>
              ) : null}

              <Button type="submit" disabled={riskSaving}>
                {riskSaving ? "Saving..." : "Save Risk Controls"}
              </Button>
            </form>
          </section>
        </div>
      </div>

      <ConfirmActionDialog
        open={disconnectOpen}
        onOpenChange={setDisconnectOpen}
        title="Disconnect wallet?"
        description="This removes the encrypted private key and API credentials."
        onConfirm={handleDisconnect}
        isConfirming={disconnecting}
        confirmLabel="Disconnect"
        confirmingLabel="Disconnecting..."
        ariaLabel="Disconnect wallet confirmation"
      />
    </DashboardPageLayout>
  );
}
