/**
 * Polymarket trading API helpers.
 * Replace with Orval-generated hooks after running `npx orval`.
 */

import { customFetch } from "@/api/mutator";

const V1 = "/api/v1";

// --- Types ---

export interface PolymarketWallet {
  id: string;
  organization_id: string;
  label: string;
  wallet_address: string;
  is_active: boolean;
  api_credentials_derived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RiskConfig {
  id: string;
  organization_id: string;
  max_trade_size_usdc: number;
  daily_loss_limit_usdc: number | null;
  weekly_loss_limit_usdc: number | null;
  max_open_positions: number | null;
  market_whitelist: string[] | null;
  market_blacklist: string[] | null;
  require_approval: boolean;
  auto_execute_max_size_usdc: number;
  auto_execute_min_confidence: number;
  created_at: string;
  updated_at: string;
}

export interface MarketSearchResult {
  condition_id: string;
  question: string;
  slug: string;
  outcomes: string[];
  end_date: string | null;
  volume: number;
  liquidity: number;
  yes_price: number | null;
  no_price: number | null;
  active: boolean;
}

export interface MarketDetail extends MarketSearchResult {
  description: string;
  tokens: { token_id: string; outcome: string; price: string }[];
}

export interface TradeProposal {
  id: string;
  organization_id: string;
  board_id: string;
  agent_id: string | null;
  approval_id: string | null;
  condition_id: string;
  token_id: string;
  market_slug: string;
  market_question: string;
  outcome_label: string;
  side: string;
  size_usdc: number;
  price: number;
  order_type: string;
  reasoning: string;
  confidence: number;
  status: string;
  execution_error: string | null;
  polymarket_order_id: string | null;
  executed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Position {
  id: string;
  condition_id: string;
  market_question: string;
  outcome_label: string;
  size: number;
  avg_price: number;
  current_price: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
}

export interface TradeHistoryEntry {
  id: string;
  market_question: string;
  outcome_label: string;
  side: string;
  size_usdc: number;
  price: number;
  filled_price: number | null;
  status: string;
  executed_at: string;
}

// --- Wallet ---

export async function fetchWallet(): Promise<PolymarketWallet | null> {
  const res = await customFetch<{ data: PolymarketWallet | null }>(
    `${V1}/polymarket/wallet`,
    { method: "GET" },
  );
  return res.data;
}

export async function connectWallet(
  privateKey: string,
  label: string,
): Promise<PolymarketWallet> {
  const res = await customFetch<{ data: PolymarketWallet }>(
    `${V1}/polymarket/wallet`,
    {
      method: "POST",
      body: JSON.stringify({ private_key: privateKey, label }),
    },
  );
  return res.data;
}

export async function disconnectWallet(): Promise<void> {
  await customFetch(`${V1}/polymarket/wallet`, { method: "DELETE" });
}

// --- Risk Config ---

export async function fetchRiskConfig(): Promise<RiskConfig | null> {
  const res = await customFetch<{ data: RiskConfig | null }>(
    `${V1}/polymarket/risk-config`,
    { method: "GET" },
  );
  return res.data;
}

export async function updateRiskConfig(
  data: Partial<RiskConfig>,
): Promise<RiskConfig> {
  const res = await customFetch<{ data: RiskConfig }>(
    `${V1}/polymarket/risk-config`,
    { method: "PUT", body: JSON.stringify(data) },
  );
  return res.data;
}

// --- Markets ---

export async function searchMarkets(
  q: string = "",
  limit: number = 20,
): Promise<MarketSearchResult[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  params.set("limit", String(limit));
  const qs = params.toString();
  const res = await customFetch<{ data: MarketSearchResult[] }>(
    `${V1}/polymarket/markets?${qs}`,
    { method: "GET" },
  );
  return res.data;
}

export async function getMarketDetail(
  conditionId: string,
): Promise<MarketDetail> {
  const res = await customFetch<{ data: MarketDetail }>(
    `${V1}/polymarket/markets/${conditionId}`,
    { method: "GET" },
  );
  return res.data;
}

// --- Trade Proposals ---

export async function fetchTradeProposals(
  status?: string,
): Promise<TradeProposal[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const qs = params.toString();
  const res = await customFetch<{ data: TradeProposal[] }>(
    `${V1}/polymarket/trades${qs ? `?${qs}` : ""}`,
    { method: "GET" },
  );
  return res.data;
}

// --- Positions ---

export async function fetchPositions(): Promise<Position[]> {
  const res = await customFetch<{ data: Position[] }>(
    `${V1}/polymarket/positions`,
    { method: "GET" },
  );
  return res.data;
}

// --- History ---

export async function fetchTradeHistory(): Promise<TradeHistoryEntry[]> {
  const res = await customFetch<{ data: TradeHistoryEntry[] }>(
    `${V1}/polymarket/history`,
    { method: "GET" },
  );
  return res.data;
}
