"use client";
import { useEffect, useState } from "react";
import { DollarSign, Check } from "lucide-react";
import { operatorFetch } from "@/lib/operator";

interface ConfiguredRate {
  provider: string;
  model: string;
  input_rate_per_1k_inr: number;
  output_rate_per_1k_inr: number;
  updated_at: string;
}

interface MissingRate {
  provider: string;
  model: string;
}

interface RatesData {
  configured: ConfiguredRate[];
  missing: MissingRate[];
}

const PROVIDER_LABELS: Record<string, string> = {
  groq: "Groq",
  gemini: "Google",
  openai: "OpenAI",
  sarvam: "Sarvam",
};

function RateRow({
  provider, model, initialInput, initialOutput, onSaved,
}: {
  provider: string;
  model: string;
  initialInput: number | "";
  initialOutput: number | "";
  onSaved: () => void;
}) {
  const [inputRate, setInputRate] = useState<number | "">(initialInput);
  const [outputRate, setOutputRate] = useState<number | "">(initialOutput);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await operatorFetch("/api/v1/operator/provider-rates", {
        method: "PUT",
        body: JSON.stringify({
          provider, model,
          input_rate_per_1k_inr: Number(inputRate) || 0,
          output_rate_per_1k_inr: Number(outputRate) || 0,
        }),
      });
      setSaved(true);
      onSaved();
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr className="border-t border-border-subtle">
      <td className="py-2 pr-3 font-mono text-xs font-semibold text-ink">{model}</td>
      <td className="py-2 pr-3">
        <span className="rounded-md bg-surface-mid px-1.5 py-0.5 text-[10px] font-semibold text-ink-secondary">
          {PROVIDER_LABELS[provider] || provider}
        </span>
      </td>
      <td className="py-2 pr-2">
        <input
          type="number"
          min={0}
          step="0.01"
          value={inputRate}
          onChange={e => setInputRate(e.target.value === "" ? "" : Number(e.target.value))}
          placeholder="0.00"
          className="w-24 rounded-md border border-border px-2 py-1 text-xs font-mono focus:border-primary focus:outline-none"
        />
      </td>
      <td className="py-2 pr-3">
        <input
          type="number"
          min={0}
          step="0.01"
          value={outputRate}
          onChange={e => setOutputRate(e.target.value === "" ? "" : Number(e.target.value))}
          placeholder="0.00"
          className="w-24 rounded-md border border-border px-2 py-1 text-xs font-mono focus:border-primary focus:outline-none"
        />
      </td>
      <td className="py-2 text-right">
        <button
          onClick={save}
          disabled={saving || inputRate === "" || outputRate === ""}
          className="inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-[11px] font-semibold text-white disabled:opacity-40"
        >
          {saved ? <Check size={12} /> : null}
          {saving ? "Saving…" : saved ? "Saved" : "Save"}
        </button>
        {error && <p className="mt-1 text-[10px] text-danger">{error}</p>}
      </td>
    </tr>
  );
}

export function RateManagementPanel({ onSaved }: { onSaved: () => void }) {
  const [data, setData] = useState<RatesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    operatorFetch<{ data: RatesData }>("/api/v1/operator/provider-rates")
      .then(res => setData(res.data))
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  function handleSaved() {
    load();
    onSaved();
  }

  return (
    <div className="rounded-card border border-border bg-white p-5 shadow-sm">
      <div className="mb-1 flex items-center gap-2">
        <DollarSign size={15} className="text-ink-muted" />
        <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Cost rates</p>
      </div>
      <p className="mb-3 text-xs text-ink-muted">
        Rates you set here — pulled from your own real bills with each provider, not a public price list — drive every estimated-cost figure above.
      </p>

      {error && <p className="rounded-lg bg-red-50 p-3 text-xs text-danger">{error}</p>}
      {!error && loading && <p className="py-4 text-center text-sm text-ink-muted">Loading…</p>}

      {!error && !loading && data && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-[10px] font-bold uppercase tracking-wide text-ink-muted">
                <th className="pb-1.5 pr-3">Model</th>
                <th className="pb-1.5 pr-3">Provider</th>
                <th className="pb-1.5 pr-2">₹ / 1K input</th>
                <th className="pb-1.5 pr-3">₹ / 1K output</th>
                <th className="pb-1.5"></th>
              </tr>
            </thead>
            <tbody>
              {data.missing.map(m => (
                <RateRow key={`${m.provider}:${m.model}`} provider={m.provider} model={m.model} initialInput="" initialOutput="" onSaved={handleSaved} />
              ))}
              {data.configured.map(c => (
                <RateRow
                  key={`${c.provider}:${c.model}`}
                  provider={c.provider}
                  model={c.model}
                  initialInput={c.input_rate_per_1k_inr}
                  initialOutput={c.output_rate_per_1k_inr}
                  onSaved={handleSaved}
                />
              ))}
              {data.missing.length === 0 && data.configured.length === 0 && (
                <tr><td colSpan={5} className="py-4 text-center text-sm text-ink-muted">No models recorded yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
