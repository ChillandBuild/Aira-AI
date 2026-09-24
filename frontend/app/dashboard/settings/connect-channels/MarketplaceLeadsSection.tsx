"use client";
import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { CopyButton } from "./ui";

const PROVIDERS = [
  { id: "indiamart", label: "IndiaMART" },
  { id: "justdial", label: "JustDial" },
] as const;

type ProviderId = (typeof PROVIDERS)[number]["id"];

function ProviderCard({ id, label, canManage }: { id: ProviderId; label: string; canManage: boolean }) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/marketplace/${id}/token`, { headers: auth });
        if (!mounted) return;
        if (res.ok) {
          const data = await res.json();
          setUrl(data.ingest_url);
        }
      } catch {
        // Silent -- an empty state (no URL yet) is the correct default,
        // not an error worth surfacing on first load.
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [id]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/marketplace/${id}/token`, {
        method: "POST",
        headers: { ...auth, "Content-Type": "application/json" },
      });
      if (!res.ok) throw new Error("Failed to generate URL");
      const data = await res.json();
      setUrl(data.ingest_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate URL");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle space-y-3">
      <div className="flex items-center justify-between">
        <p className="font-semibold text-ink text-sm">{label}</p>
        {url && (
          <span className="font-label text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
            Active
          </span>
        )}
      </div>
      <p className="font-body text-xs text-ink-secondary">
        Paste this URL into your {label} account&apos;s webhook / lead-notification settings —
        new enquiries land as leads here automatically.
      </p>

      {loading ? (
        <div className="h-10 rounded-xl bg-border-subtle animate-pulse" />
      ) : url ? (
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-[11px] select-all break-all text-primary font-medium">
            {url}
          </div>
          <CopyButton text={url} />
        </div>
      ) : (
        <p className="font-body text-xs text-ink-muted">No URL generated yet.</p>
      )}

      {error && <p className="font-body text-xs text-red-600">{error}</p>}

      {canManage && (
        <button
          type="button"
          onClick={handleGenerate}
          disabled={generating}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-label font-semibold border border-border bg-white text-ink-secondary hover:text-primary hover:border-primary/40 disabled:opacity-40 transition-all"
        >
          <RefreshCw size={12} className={generating ? "animate-spin" : ""} />
          {url ? "Regenerate URL" : "Generate URL"}
        </button>
      )}
      {url && (
        <p className="font-body text-[10px] text-ink-muted">
          Regenerating invalidates the URL above immediately — update {label} with the new one.
        </p>
      )}
    </div>
  );
}

export default function MarketplaceLeadsSection({ canManage = true }: { canManage?: boolean }) {
  return (
    <div className="rounded-[28px] border border-border-subtle bg-white p-6 space-y-4">
      <div>
        <p className="font-display font-bold text-ink text-base">Marketplace Leads</p>
        <p className="font-body text-xs text-ink-secondary mt-0.5">
          Bring in enquiries from Indian B2B marketplaces — each one gets its own private URL.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {PROVIDERS.map((p) => (
          <ProviderCard key={p.id} id={p.id} label={p.label} canManage={canManage} />
        ))}
      </div>
    </div>
  );
}
