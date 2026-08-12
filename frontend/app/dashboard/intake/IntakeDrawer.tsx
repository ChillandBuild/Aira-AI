"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, Copy, Loader2, Phone, X } from "lucide-react";
import { API_URL, IntakeSession, api, getAuthHeaders } from "@/lib/api";

interface IntakePackageOption {
  key: string;
  name: string;
  amount_paise: number;
}

function labelFor(session: IntakeSession, key: string): string {
  const snapshot = (session.field_schema ?? []).find((f) => f.key === key);
  if (snapshot) return snapshot.label;
  return key.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

interface IntakeDrawerProps {
  session: IntakeSession;
  onClose: () => void;
  onChanged: () => void;
}

export function IntakeDrawer({ session, onClose, onChanged }: IntakeDrawerProps) {
  const [busy, setBusy] = useState(false);
  const [packages, setPackages] = useState<IntakePackageOption[]>([]);
  const entries = Object.entries(session.collected_data ?? {});
  const canChangePackage = session.status === "awaiting_payment";

  useEffect(() => {
    if (!canChangePackage) return;
    (async () => {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, { headers: auth });
      if (res.ok) {
        const config = await res.json();
        setPackages(config.packages ?? []);
      }
    })();
  }, [canChangePackage]);

  async function resolve() {
    setBusy(true);
    try {
      await api.intake.resolveSession(session.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function changePackage(key: string) {
    setBusy(true);
    try {
      await api.intake.changePackage(session.id, key);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/20" onClick={onClose}>
      <aside
        className="h-full w-[420px] overflow-y-auto bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        aria-label="Intake details"
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="font-display text-base font-bold text-ink">
              {session.leads?.name || session.collected_data?.name || "Unknown lead"}
            </h2>
            <div className="mt-0.5 flex items-center gap-1 font-body text-xs text-ink-muted">
              <Phone size={11} />
              {session.leads?.phone || "—"}
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close">
            <X size={16} className="text-ink-muted" />
          </button>
        </div>

        <div className="mb-4 space-y-1 rounded-2xl border border-border p-3">
          <div className="flex justify-between font-body text-sm">
            <span className="text-ink-muted">Package</span>
            <span className="text-ink">{session.package_name || "—"}</span>
          </div>
          <div className="flex justify-between font-body text-sm">
            <span className="text-ink-muted">Amount</span>
            <span className="text-ink">
              {session.amount_paise ? `₹${(session.amount_paise / 100).toFixed(0)}` : "—"}
            </span>
          </div>
          {session.amount_mismatch && (
            <p className="font-body text-xs text-amber-700">
              Paid amount differs from the package price — the lead likely paid a superseded link.
            </p>
          )}
          {session.paid_at && (
            <div className="flex justify-between font-body text-sm">
              <span className="text-ink-muted">Paid at</span>
              <span className="text-ink">{new Date(session.paid_at).toLocaleString()}</span>
            </div>
          )}
          {session.payment_link && (
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(session.payment_link ?? "")}
              className="mt-1 inline-flex items-center gap-1 font-label text-xs font-bold text-primary"
            >
              <Copy size={11} /> Copy payment link
            </button>
          )}
        </div>

        {canChangePackage && packages.length > 1 && (
          <div className="mb-4">
            <label className="mb-1 block font-label text-xs font-bold text-ink-muted" htmlFor="package-select">
              Change package
            </label>
            <select
              id="package-select"
              value={session.package_key ?? ""}
              disabled={busy}
              onChange={(e) => changePackage(e.target.value)}
              className="w-full rounded-xl border border-border px-3 py-2 font-body text-sm"
            >
              {packages.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.name} — ₹{(p.amount_paise / 100).toFixed(0)}
                </option>
              ))}
            </select>
            <p className="mt-1 font-body text-xs text-ink-muted">
              Clears the current link. The lead is sent a new one on their next message.
            </p>
          </div>
        )}

        {entries.length === 0 ? (
          <p className="font-body text-xs italic text-ink-muted">No details collected yet.</p>
        ) : (
          <table className="w-full border-collapse">
            <tbody>
              {entries.map(([key, value]) => (
                <tr key={key} className="border-b border-border-subtle last:border-0">
                  <td className="whitespace-nowrap py-2 pr-4 align-top font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
                    {labelFor(session, key)}
                  </td>
                  <td className="py-2 font-body text-sm text-ink">{value || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {session.status === "paid" && (
          <button
            type="button"
            onClick={resolve}
            disabled={busy}
            className="mt-5 inline-flex w-full items-center justify-center gap-1 rounded-full bg-primary px-4 py-2 font-label text-xs font-bold text-white hover:bg-primary/90 disabled:opacity-60"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
            Mark Resolved
          </button>
        )}
      </aside>
    </div>
  );
}
