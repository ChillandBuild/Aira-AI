"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Cpu, TrendingUp, TrendingDown } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { operatorFetch } from "@/lib/operator";
import { RateManagementPanel } from "./RateManagementPanel";

interface FleetTotals {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  has_unrated: boolean;
  trend_pct: number | null;
}

interface ProviderUsage {
  provider: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  has_unrated: boolean;
}

interface FeatureUsage {
  purpose: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  has_unrated: boolean;
}

interface DailyUsage {
  date: string;
  [provider: string]: string | number;
}

interface LeaderboardRow {
  tenant_id: string;
  tenant_name: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  has_unrated: boolean;
  share_of_fleet: number;
  trend_pct: number | null;
}

interface FleetData {
  totals: FleetTotals;
  active_clients: number;
  total_clients: number;
  by_provider: ProviderUsage[];
  by_feature: FeatureUsage[];
  daily: DailyUsage[];
  leaderboard: LeaderboardRow[];
}

const PURPOSE_LABELS: Record<string, string> = {
  ai_reply: "AI Replies",
  scoring: "Lead Scoring",
  call_analysis: "Call Analysis",
  coaching_digest: "Coaching Digest",
  coaching: "On-Demand Coaching Tip",
  ai_tune: "AI Tuning",
  pre_call_brief: "Pre-Call Brief",
  conversation_compaction: "Conversation Compaction",
  speech_to_text: "Speech-to-Text",
  doc_digitization: "Knowledge Doc Digitization",
  voice_reply_tts: "Voice Reply (TTS)",
};

// Fixed categorical order — validated for CVD-safe separation and contrast
// against the console's white/cream surface (never reuse success/warning/danger).
const PROVIDER_ORDER = ["groq", "gemini", "openai", "sarvam"] as const;
const PROVIDER_COLORS: Record<string, string> = {
  groq: "#7c3aed",
  gemini: "#0891b2",
  openai: "#c2650a",
  sarvam: "#a1276b",
};
const PROVIDER_LABELS: Record<string, string> = {
  groq: "Groq",
  gemini: "Google",
  openai: "OpenAI",
  sarvam: "Sarvam",
};

type Range = "30" | "90" | "all";

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString("en-IN");
}

function fmtCost(n: number): string {
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(2)}L`;
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function TrendBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-ink-muted">—</span>;
  const up = pct >= 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span className={`inline-flex items-center gap-1 font-semibold ${up ? "text-danger" : "text-success"}`}>
      <Icon size={12} /> {Math.abs(pct)}%
    </span>
  );
}

export default function AiSpendPage() {
  const [range, setRange] = useState<Range>("90");
  const [data, setData] = useState<FleetData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ratesVersion, setRatesVersion] = useState(0);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const query = range === "all" ? "all_time=true" : `range_days=${range}`;
    operatorFetch<{ data: FleetData }>(`/api/v1/operator/token-usage/fleet?${query}`)
      .then(res => setData(res.data))
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [range]);

  useEffect(() => { load(); }, [load, ratesVersion]);

  const totals = data?.totals ?? { calls: 0, input_tokens: 0, output_tokens: 0, estimated_cost: 0, has_unrated: false, trend_pct: null };
  const totalTokens = totals.input_tokens + totals.output_tokens;
  const providersPresent = PROVIDER_ORDER.filter(p => (data?.by_provider ?? []).some(row => row.provider === p));
  const maxFeatureTotal = Math.max(0, ...(data?.by_feature ?? []).map(f => f.input_tokens + f.output_tokens));

  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-ink">
            <Cpu size={20} className="text-ink-muted" /> AI Spend
          </h1>
          <p className="mt-1 max-w-xl text-sm text-ink-muted">
            Fleet-wide token consumption and estimated cost across every client — you fund every provider account, so this is where you see who&apos;s costing you the most.
          </p>
        </div>
        <div className="inline-flex rounded-lg bg-surface-mid p-0.5">
          {(["30", "90", "all"] as Range[]).map(r => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                range === r ? "bg-white text-ink shadow-sm" : "text-ink-secondary"
              }`}
            >
              {r === "30" ? "30 days" : r === "90" ? "90 days" : "All time"}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-danger">{error}</p>}
      {!error && loading && <p className="py-10 text-center text-sm text-ink-muted">Loading…</p>}

      {!error && !loading && data && (
        <>
          {totals.has_unrated && (
            <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-warning/25 bg-warning-bg px-3.5 py-2.5 text-xs text-ink">
              <span>⚠</span>
              <span>
                Some models don&apos;t have a cost rate configured yet — estimated cost below may be incomplete.
              </span>
              <a href="#rates" className="ml-auto font-semibold text-primary">Set rates →</a>
            </div>
          )}

          <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-xl border border-border bg-white p-3.5 shadow-sm">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Est. total cost</p>
              <p className="mt-1 font-mono text-2xl font-bold text-ink">
                {fmtCost(totals.estimated_cost)}{totals.has_unrated && <span className="ml-1 text-base font-semibold text-warning">*</span>}
              </p>
              <p className="mt-0.5 text-xs text-ink-muted"><TrendBadge pct={totals.trend_pct} /> vs prior period</p>
            </div>
            <div className="rounded-xl border border-border bg-white p-3.5 shadow-sm">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Total tokens</p>
              <p className="mt-1 font-mono text-2xl font-bold text-ink">{fmt(totalTokens)}</p>
              <p className="mt-0.5 text-xs text-ink-muted">across {providersPresent.length} provider{providersPresent.length === 1 ? "" : "s"}</p>
            </div>
            <div className="rounded-xl border border-border bg-white p-3.5 shadow-sm">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Total LLM calls</p>
              <p className="mt-1 font-mono text-2xl font-bold text-ink">{totals.calls.toLocaleString("en-IN")}</p>
            </div>
            <div className="rounded-xl border border-border bg-white p-3.5 shadow-sm">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Active clients</p>
              <p className="mt-1 font-mono text-2xl font-bold text-ink">
                {data.active_clients}<span className="text-base font-semibold text-ink-muted"> / {data.total_clients}</span>
              </p>
              <p className="mt-0.5 text-xs text-ink-muted">used any AI feature this window</p>
            </div>
          </div>

          <div className="mb-5 grid grid-cols-1 gap-5 lg:grid-cols-[1.6fr_1fr]">
            <div className="rounded-card border border-border bg-white p-5 shadow-sm">
              <p className="mb-3 text-[11px] font-bold uppercase tracking-wide text-ink-muted">Fleet tokens by day, by provider</p>
              {data.daily.length > 0 ? (
                <>
                  <div role="img" aria-label="Daily fleet-wide token consumption stacked by provider">
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={data.daily} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 10, fill: "#a8a29e" }}
                          tickFormatter={(d) => new Date(String(d)).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                        />
                        <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} tickFormatter={fmt} allowDecimals={false} />
                        <Tooltip
                          contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }}
                          labelFormatter={(d) => new Date(String(d)).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                          formatter={(value, name) => [fmt(Number(value) || 0), PROVIDER_LABELS[String(name)] || String(name)]}
                        />
                        {providersPresent.map(p => (
                          <Bar key={p} dataKey={p} stackId="tokens" fill={PROVIDER_COLORS[p]} name={p} radius={p === providersPresent[providersPresent.length - 1] ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
                        ))}
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-4">
                    {providersPresent.map(p => (
                      <span key={p} className="flex items-center gap-1.5 text-xs font-semibold text-ink-secondary">
                        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: PROVIDER_COLORS[p] }} />
                        {PROVIDER_LABELS[p]}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <p className="py-10 text-center text-sm text-ink-muted">No usage recorded in this window.</p>
              )}
            </div>

            <div className="rounded-card border border-border bg-white p-5 shadow-sm">
              <p className="mb-3 text-[11px] font-bold uppercase tracking-wide text-ink-muted">Spend by provider</p>
              {data.by_provider.length > 0 ? (
                <div className="space-y-2.5">
                  {data.by_provider.map(p => {
                    const providerTokens = p.input_tokens + p.output_tokens;
                    const pct = totalTokens > 0 ? Math.round((providerTokens / totalTokens) * 100) : 0;
                    return (
                      <div key={p.provider} className="grid grid-cols-[84px_1fr_40px] items-center gap-2.5">
                        <span className="flex items-center gap-1.5 text-xs font-bold text-ink">
                          <span className="inline-block h-2 w-2 rounded-full" style={{ background: PROVIDER_COLORS[p.provider] }} />
                          {PROVIDER_LABELS[p.provider] || p.provider}
                        </span>
                        <div className="h-2.5 rounded-full bg-surface-mid">
                          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: PROVIDER_COLORS[p.provider] }} />
                        </div>
                        <span className="text-right font-mono text-xs text-ink-secondary">{pct}%</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="py-6 text-center text-sm text-ink-muted">No usage recorded.</p>
              )}
            </div>
          </div>

          <div className="mb-5 rounded-card border border-border bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Clients by spend</p>
              <span className="text-xs text-ink-muted">{data.leaderboard.length} of {data.total_clients} shown</span>
            </div>
            {data.leaderboard.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[10px] font-bold uppercase tracking-wide text-ink-muted">
                      <th className="w-8 pb-2"></th>
                      <th className="pb-2">Client</th>
                      <th className="pb-2 text-right">Tokens</th>
                      <th className="pb-2 text-right">Est. cost</th>
                      <th className="pb-2 pl-3">Share</th>
                      <th className="pb-2 text-right">Trend</th>
                      <th className="pb-2"></th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {data.leaderboard.map((row, i) => (
                      <tr key={row.tenant_id} className="border-t border-border-subtle hover:bg-background">
                        <td className="py-2">
                          <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-surface-mid text-[11px] font-bold text-ink-secondary">{i + 1}</span>
                        </td>
                        <td className="py-2 pr-3 font-sans font-semibold text-ink">{row.tenant_name}</td>
                        <td className="py-2 text-right text-ink-secondary">{fmt(row.input_tokens + row.output_tokens)}</td>
                        <td className="py-2 text-right text-ink-secondary">
                          {row.has_unrated ? <span className="text-ink-muted">partial</span> : fmtCost(row.estimated_cost)}
                        </td>
                        <td className="py-2 pl-3">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-16 rounded-full bg-surface-mid">
                              <div className="h-full rounded-full bg-primary" style={{ width: `${Math.round(row.share_of_fleet * 100)}%` }} />
                            </div>
                            <span className="text-ink-secondary">{Math.round(row.share_of_fleet * 100)}%</span>
                          </div>
                        </td>
                        <td className="py-2 text-right"><TrendBadge pct={row.trend_pct} /></td>
                        <td className="py-2 text-right">
                          <Link href={`/operator/client/${row.tenant_id}?section=entitlements`} className="font-sans font-semibold text-primary hover:text-primary-dark">
                            View →
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="py-6 text-center text-sm text-ink-muted">No client usage recorded in this window.</p>
            )}
          </div>

          <div className="mb-5 rounded-card border border-border bg-white p-5 shadow-sm">
            <p className="mb-3 text-[11px] font-bold uppercase tracking-wide text-ink-muted">Tokens by feature, fleet-wide</p>
            {data.by_feature.length > 0 ? (
              <div className="divide-y divide-border-subtle">
                {data.by_feature.map(f => {
                  const total = f.input_tokens + f.output_tokens;
                  const pct = maxFeatureTotal > 0 ? Math.max(3, Math.round((total / maxFeatureTotal) * 100)) : 0;
                  return (
                    <div key={f.purpose} className="grid grid-cols-[160px_1fr_70px] items-center gap-3 py-1.5">
                      <span className="truncate text-sm font-medium text-ink">{PURPOSE_LABELS[f.purpose] || f.purpose}</span>
                      <div className="h-3 rounded bg-surface-mid"><div className="h-full rounded bg-primary/80" style={{ width: `${pct}%` }} /></div>
                      <span className="text-right font-mono text-xs text-ink-secondary">{fmt(total)}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="py-4 text-center text-sm text-ink-muted">No usage recorded.</p>
            )}
            <p className="mt-3 border-t border-border-subtle pt-2.5 text-[11px] text-ink-muted">
              Where your fleet&apos;s tokens actually go — independent of any one client, useful for deciding what to optimize product-wide.
            </p>
          </div>

          <div id="rates">
            <RateManagementPanel onSaved={() => setRatesVersion(v => v + 1)} />
          </div>
        </>
      )}
    </div>
  );
}
