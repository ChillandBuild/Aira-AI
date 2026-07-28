"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Trash2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...auth, ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

export function DeleteClientView({ tenantId, clientName }: { tenantId: string; clientName: string }) {
  const router = useRouter();
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setDeleting(true);
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}`, { method: "DELETE" });
      router.push("/operator");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete client");
      setDeleting(false);
    }
  }

  return (
    <div className="max-w-lg">
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-xs underline ml-2">dismiss</button>
        </div>
      )}

      <div className="bg-white rounded-card border border-danger/30 p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-full bg-danger/10 flex items-center justify-center">
            <AlertTriangle size={24} className="text-danger" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-ink">Delete Client Permanently</h3>
            <p className="text-xs text-ink-muted">This action is irreversible</p>
          </div>
        </div>

        <div className="bg-red-50 rounded-xl p-4 mb-4 text-sm text-danger space-y-1">
          <p className="font-medium">This will permanently destroy:</p>
          <ul className="list-disc list-inside text-xs space-y-0.5 text-danger/80">
            <li>All leads, messages, and conversation history</li>
            <li>All call logs, notes, and recordings metadata</li>
            <li>All broadcasts, templates, and knowledge base</li>
            <li>All scheduled broadcasts and follow-up jobs</li>
            <li>All team members and their Supabase auth accounts</li>
            <li>The tenant record itself and all settings</li>
          </ul>
        </div>

        <p className="text-sm text-ink-secondary mb-2">
          Type <span className="font-mono font-bold text-danger">{clientName}</span> to confirm:
        </p>
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          className="w-full border border-border rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-danger/20 focus:border-danger mb-4 font-mono"
          placeholder={clientName}
        />

        <button
          onClick={handleDelete}
          disabled={typed !== clientName || deleting}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-danger text-white text-sm font-bold rounded-xl hover:bg-danger/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Trash2 size={16} />
          {deleting ? "Deleting..." : "Delete Client Forever"}
        </button>
      </div>
    </div>
  );
}
