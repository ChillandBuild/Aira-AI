"use client";
import { useEffect, useState } from "react";
import { Cpu } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { API_URL, getAuthHeaders } from "@/lib/api";

async function apiFetch<T>(path: string): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, { headers: { "Content-Type": "application/json", ...auth } });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  const json = await res.json();
  return ((json as { data?: T }).data ?? json) as T;
}

interface TokenTotals {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  has_unrated: boolean;
}

interface FeatureUsage extends TokenTotals {
  purpose: string;
}

interface ModelUsage extends TokenTotals {
  provider: string;
  model: string;
}

interface DailyUsage {
  date: string;
  input_tokens: number;
  output_tokens: number;
}

interface UnratedModel {
  provider: string;
  model: string;
}

interface TokenUsageData {
  totals: TokenTotals;
  by_feature: FeatureUsage[];
  by_model: ModelUsage[];
  daily: DailyUsage[];
  unrated_models: UnratedModel[];
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
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function FeatureBar({ item, maxTotal }: { item: FeatureUsage; maxTotal: number }) {
  const total = item.input_tokens + item.output_tokens;
  const pct = maxTotal > 0 ? Math.max(3, Math.round((total / maxTotal) * 100)) : 0;
  return (
    <div className="grid grid-cols-[130px_1fr_84px] items-center gap-3 py-1.5">
      <span className="truncate text-sm font-medium text-ink">{PURPOSE_LABELS[item.purpose] || item.purpose}</span>
      <div className="h-3.5 rounded bg-surface-mid">
        <div className="h-full rounded bg-primary/80" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-right font-mono text-xs text-ink-secondary">{fmt(total)}</span>
    </div>
  );
}

export function TokenUsageCard({ tenantId }: { tenantId: string }) {
  const [range, setRange] = useState<Range>("30");
  const [data, setData] = useState<TokenUsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const query = range === "all" ? "all_time=true" : `range_days=${range}`;
    apiFetch<TokenUsageData>(`/api/v1/operator/clients/${tenantId}/token-usage?${query}`)
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId, range]);

  const totals = data?.totals ?? { calls: 0, input_tokens: 0, output_tokens: 0, estimated_cost: 0, has_unrated: false };
  const totalTokens = totals.input_tokens + totals.output_tokens;
  const avgPerCall = totals.calls > 0 ? Math.round(totalTokens / totals.calls) : 0;
  const maxFeatureTotal = Math.max(0, ...(data?.by_feature ?? []).map(f => f.input_tokens + f.output_tokens));

  return (
    <div className="bg-white rounded-card border border-border p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Cpu size={16} className="text-ink-muted" /> Token Consumption
          </h3>
          <p className="mt-0.5 text-xs text-ink-muted">Provider-reported usage across every AI feature, on this client&apos;s own API keys</p>
        </div>
        <div className="inline-flex rounded-lg bg-surface-mid p-0.5">
          {(["30", "90", "all"] as Range[]).map(r => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                range === r ? "bg-white text-ink shadow-sm" : "text-ink-secondary"
              }`}
            >
              {r === "30" ? "30 days" : r === "90" ? "90 days" : "All time"}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="rounded-lg bg-red-50 p-3 text-xs text-danger">{error}</p>}

      {!error && loading && <p className="py-6 text-center text-sm text-ink-muted">Loading…</p>}

      {!error && !loading && totalTokens === 0 && (
        <p className="py-6 text-center text-sm text-ink-muted">No AI usage recorded in this window.</p>
      )}

      {!error && !loading && !!data && totals.has_unrated && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-warning/25 bg-warning-bg px-3 py-2 text-xs text-ink">
          <span>⚠</span>
          <span>
            <strong className="text-warning">{data.unrated_models.length} model{data.unrated_models.length === 1 ? "" : "s"}</strong> without a configured cost rate — estimated cost below is incomplete.
          </span>
        </div>
      )}

      {!error && !loading && totalTokens > 0 && data && (
        <>
          <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
            <div className="rounded-xl border border-border-subtle bg-background p-3">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Est. cost</p>
              <p className="mt-1 font-mono text-xl font-bold text-ink">
                {fmtCost(totals.estimated_cost)}
                {totals.has_unrated && <span className="ml-1 text-sm font-semibold text-warning">*</span>}
              </p>
            </div>
            <div className="rounded-xl border border-border-subtle bg-background p-3">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Total tokens</p>
              <p className="mt-1 font-mono text-xl font-bold text-ink">{fmt(totalTokens)}</p>
            </div>
            <div className="rounded-xl border border-border-subtle bg-background p-3">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Input / Output</p>
              <p className="mt-1 font-mono text-xl font-bold text-ink">
                {fmt(totals.input_tokens)} <span className="text-sm font-medium text-ink-muted">/</span> {fmt(totals.output_tokens)}
              </p>
            </div>
            <div className="rounded-xl border border-border-subtle bg-background p-3">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">LLM calls</p>
              <p className="mt-1 font-mono text-xl font-bold text-ink">{totals.calls.toLocaleString("en-IN")}</p>
            </div>
            <div className="rounded-xl border border-border-subtle bg-background p-3">
              <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Avg tokens / call</p>
              <p className="mt-1 font-mono text-xl font-bold text-ink">{fmt(avgPerCall)}</p>
            </div>
          </div>

          {data.daily.length > 0 && (
            <div className="mb-5" role="img" aria-label="Daily token consumption">
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-ink-muted">Daily tokens</p>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={data.daily} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: "#a8a29e" }}
                    tickFormatter={(d: string) => new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                  />
                  <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} tickFormatter={fmt} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }}
                    labelFormatter={(d) => new Date(String(d)).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                    formatter={(value, name) => [fmt(Number(value) || 0), name === "input_tokens" ? "Input" : "Output"]}
                  />
                  <Bar dataKey="input_tokens" stackId="tokens" fill="#5b21b6" radius={[0, 0, 0, 0]} name="input_tokens" />
                  <Bar dataKey="output_tokens" stackId="tokens" fill="#a78bfa" radius={[4, 4, 0, 0]} name="output_tokens" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {data.by_feature.length > 0 && (
            <div className="mb-5">
              <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-ink-muted">By feature</p>
              <div className="divide-y divide-border-subtle">
                {data.by_feature.map(f => <FeatureBar key={f.purpose} item={f} maxTotal={maxFeatureTotal} />)}
              </div>
            </div>
          )}

          {data.by_model.length > 0 && (
            <div>
              <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-ink-muted">By model</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[10px] font-bold uppercase tracking-wide text-ink-muted">
                      <th className="pb-1.5 pr-3">Model</th>
                      <th className="pb-1.5 pr-3">Provider</th>
                      <th className="pb-1.5 pr-3 text-right">Calls</th>
                      <th className="pb-1.5 pr-3 text-right">Input</th>
                      <th className="pb-1.5 pr-3 text-right">Output</th>
                      <th className="pb-1.5 text-right">Est. cost</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {data.by_model.map(m => (
                      <tr key={`${m.provider}:${m.model}`} className="border-t border-border-subtle">
                        <td className="py-1.5 pr-3 font-semibold text-ink">{m.model}</td>
                        <td className="py-1.5 pr-3">
                          <span className="rounded-md bg-surface-mid px-1.5 py-0.5 text-[10px] font-semibold text-ink-secondary">
                            {PROVIDER_LABELS[m.provider] || m.provider}
                          </span>
                        </td>
                        <td className="py-1.5 pr-3 text-right text-ink-secondary">{m.calls.toLocaleString("en-IN")}</td>
                        <td className="py-1.5 pr-3 text-right text-ink-secondary">{fmt(m.input_tokens)}</td>
                        <td className="py-1.5 pr-3 text-right text-ink-secondary">{fmt(m.output_tokens)}</td>
                        <td className="py-1.5 text-right text-ink-secondary">
                          {m.has_unrated ? <span className="text-ink-muted">no rate set</span> : fmtCost(m.estimated_cost)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <p className="mt-4 border-t border-border-subtle pt-3 text-[11px] leading-relaxed text-ink-muted">
            Token counts are read from the usage block each provider returns with every response — no estimation.
            Estimated cost is computed from admin-set rates and may not exactly match your provider invoice.
          </p>
        </>
      )}
    </div>
  );
}
