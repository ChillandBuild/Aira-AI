"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ToggleLeft } from "lucide-react";
import { api, CatalogAiRules } from "@/lib/api";
import { cn } from "@/lib/utils";

function RuleCard({
  title,
  description,
  checked,
  disabled = false,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="rounded-card border border-border bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-display text-base font-bold text-ink">{title}</h3>
          <p className="mt-1 text-sm leading-relaxed text-ink-muted">{description}</p>
        </div>
        <button
          type="button"
          onClick={() => onChange(!checked)}
          disabled={disabled}
          className={cn(
            "inline-flex h-8 w-14 shrink-0 items-center rounded-full p-1 transition-colors disabled:cursor-not-allowed disabled:opacity-45",
            checked ? "bg-primary" : "bg-surface-mid"
          )}
          aria-label={`Toggle ${title}`}
        >
          <span className={cn("h-6 w-6 rounded-full bg-white shadow-sm transition-transform", checked && "translate-x-6")} />
        </button>
      </div>
      <div className="mt-5 inline-flex items-center gap-2 rounded-full bg-surface-low px-3 py-1 text-xs font-semibold text-ink-muted">
        {checked ? <CheckCircle2 size={13} className="text-success" /> : <ToggleLeft size={13} />}
        {checked ? "Enabled" : "Disabled"}
      </div>
    </div>
  );
}

export function AiRulesTab({ canManage }: { canManage: boolean }) {
  const [rules, setRules] = useState<CatalogAiRules | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.catalog
      .getAiRules()
      .then(setRules)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load AI rules"));
  }, []);

  async function patch(update: Partial<Pick<CatalogAiRules, "can_recommend" | "can_send_images" | "max_images_per_reply">>) {
    if (!canManage) {
      setError("Read-only role: catalog AI rule changes are disabled.");
      return;
    }
    if (!rules) return;
    const optimistic = { ...rules, ...update };
    setRules(optimistic);
    try {
      const saved = await api.catalog.updateAiRules(update);
      setRules(saved);
    } catch (err) {
      setRules(rules);
      setError(err instanceof Error ? err.message : "Failed to save AI rules");
    }
  }

  if (!rules) {
    return <div className="min-h-[200px] animate-pulse rounded-card bg-surface-low" />;
  }

  const controlsDisabled = !canManage || !rules.feature_enabled;

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-card border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">{error}</div>
      )}
      {!rules.feature_enabled && (
        <div className="rounded-card border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
          Catalog AI recommendations aren&apos;t enabled for your account. Your preferences below are saved but have no effect until support turns this on.
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <RuleCard
          title="AI Recommendations"
          description="Allow Aira to recommend matching catalog items when customers ask for options."
          checked={rules.can_recommend}
          disabled={controlsDisabled}
          onChange={(checked) => patch({ can_recommend: checked })}
        />
        <RuleCard
          title="Send Images"
          description="Allow Aira to send item images with its recommendation when the chat context calls for it."
          checked={rules.can_send_images}
          disabled={controlsDisabled}
          onChange={(checked) => patch({ can_send_images: checked })}
        />
        <div className="rounded-card border border-border bg-white p-5 shadow-sm">
          <h3 className="font-display text-base font-bold text-ink">Reply Limits</h3>
          <p className="mt-1 text-sm text-ink-muted">Default maximum images per AI reply (up to {rules.max_images_ceiling}).</p>
          <div className="mt-5 flex items-center gap-3">
            <button
              type="button"
              onClick={() => patch({ max_images_per_reply: Math.max(0, rules.max_images_per_reply - 1) })}
              disabled={controlsDisabled}
              className="h-9 w-9 rounded-xl border border-border text-lg font-bold text-ink-muted transition-colors hover:bg-surface-low disabled:opacity-40"
            >
              -
            </button>
            <span className="font-mono text-xl font-bold text-ink">{rules.max_images_per_reply}</span>
            <button
              type="button"
              onClick={() => patch({ max_images_per_reply: Math.min(rules.max_images_ceiling, rules.max_images_per_reply + 1) })}
              disabled={controlsDisabled || rules.max_images_per_reply >= rules.max_images_ceiling}
              className="h-9 w-9 rounded-xl border border-border text-lg font-bold text-ink-muted transition-colors hover:bg-surface-low disabled:opacity-40"
            >
              +
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
