"use client";
import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

export default function PromptTemplatePage() {
  const [template, setTemplate] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/operator/prompt-template`, { headers: auth });
        if (!res.ok) throw new Error("Load failed");
        const data = (await res.json()) as { template: string };
        setTemplate(data.template || "");
        setSaved(data.template || "");
      } catch {
        setError("Could not load the template.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/operator/prompt-template`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ template }),
      });
      if (!res.ok) throw new Error("Save failed");
      setSaved(template);
    } catch {
      setError("Could not save the template.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-8 text-sm text-ink-muted">
        <Loader2 size={16} className="animate-spin" /> Loading…
      </div>
    );
  }

  return (
    <div className="max-w-4xl space-y-4 p-8">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-ink">
          <Sparkles size={18} className="text-ink-muted" />
          Default Master Prompt
        </h1>
        <p className="mt-2 text-xs leading-relaxed text-ink-muted">
          This template is copied into a new client&apos;s master prompt when the client is
          created. Editing it here does <strong>not</strong> change any existing client — to
          change a live client, edit their master prompt on their Config tab.
        </p>
      </div>

      <textarea
        value={template}
        onChange={(e) => setTemplate(e.target.value)}
        rows={28}
        spellCheck={false}
        className="w-full resize-y rounded-card border border-border bg-white p-4 font-mono text-xs leading-relaxed shadow-sm focus:outline-none focus:ring-1 focus:ring-primary/30"
      />

      {error && <p className="text-xs font-medium text-danger">{error}</p>}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={save}
          disabled={saving || template === saved}
          className="inline-flex items-center gap-2 rounded-card bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-default disabled:opacity-50"
        >
          {saving && <Loader2 size={14} className="animate-spin" />}
          {saving ? "Saving…" : "Save Template"}
        </button>
      </div>
    </div>
  );
}
