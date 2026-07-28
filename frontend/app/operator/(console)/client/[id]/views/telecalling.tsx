"use client";
import { useEffect, useState } from "react";
import { Upload, Phone, Calendar, StickyNote, Hash, Clock } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { StatCard } from "../components/stat-card";
import { SkeletonCard, SkeletonTable } from "../components/skeleton";

async function apiFetch<T>(path: string): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...auth },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.abs(diff) / 1000;
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/* ---------- Upload ---------- */

interface UploadBatch {
  id: string;
  file_name: string;
  lead_count: number;
  created_at: string;
  status: string;
}

interface UploadData {
  total_batches: number;
  batches: UploadBatch[];
}

function UploadSection({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<UploadData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch<UploadData>(`/api/v1/operator/clients/${tenantId}/dashboard/telecalling?section=upload`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) return <div className="space-y-4"><div className="grid grid-cols-2 gap-4"><SkeletonCard /><SkeletonCard /></div><SkeletonTable /></div>;
  if (error) return <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <StatCard icon={<Upload size={18} />} label="Total Batches" value={data.total_batches} />
      </div>
      {data.batches.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <Upload size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No upload batches</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Filename</th>
                <th className="text-left px-4 py-3 font-medium">Leads</th>
                <th className="text-left px-4 py-3 font-medium">Date</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.batches.map((b) => (
                <tr key={b.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink">{b.file_name}</td>
                  <td className="px-4 py-3 text-ink-secondary">{b.lead_count}</td>
                  <td className="px-4 py-3 text-ink-muted text-xs">{relTime(b.created_at)}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      b.status === "completed" ? "bg-green-50 text-success" :
                      b.status === "processing" ? "bg-amber-50 text-warning" :
                      "bg-surface-mid text-ink-muted"
                    }`}>{b.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- Dialer ---------- */

interface CallRow {
  id: string;
  lead_id: string | null;
  caller_id: string | null;
  duration_seconds: number | null;
  disposition: string | null;
  manual_status: string | null;
  created_at: string;
}

interface DialerData {
  calls_today: number;
  connect_rate: number;
  recent_calls: CallRow[];
}

const DISPOSITION_BADGE: Record<string, string> = {
  answered: "bg-green-50 text-success",
  no_answer: "bg-amber-50 text-warning",
  busy: "bg-red-50 text-danger",
  switched_off: "bg-stone-100 text-ink-muted",
  followup_required: "bg-blue-50 text-blue-600",
  connected: "bg-green-50 text-success",
  not_picked: "bg-amber-50 text-warning",
  wrong_number: "bg-red-50 text-danger",
  interested: "bg-cyan-50 text-cyan-700",
  not_interested: "bg-rose-50 text-rose-700",
  callback: "bg-blue-50 text-blue-600",
};

function DialerSection({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<DialerData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch<DialerData>(`/api/v1/operator/clients/${tenantId}/dashboard/telecalling?section=dialer`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) return <div className="space-y-4"><SkeletonCard /><SkeletonTable /></div>;
  if (error) return <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>;
  if (!data) return null;

  function fmtDuration(s: number | null) {
    if (s == null) return "—";
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <StatCard icon={<Phone size={18} />} label="Calls Today" value={data.calls_today} />
        <StatCard icon={<Hash size={18} />} label="Connect Rate" value={`${data.connect_rate}%`} />
      </div>
      {data.recent_calls.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <Phone size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No recent calls</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Lead</th>
                <th className="text-left px-4 py-3 font-medium">Caller</th>
                <th className="text-left px-4 py-3 font-medium">Duration</th>
                <th className="text-left px-4 py-3 font-medium">Disposition</th>
                <th className="text-left px-4 py-3 font-medium">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.recent_calls.map((c) => (
                <tr key={c.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink font-mono text-xs">{c.lead_id?.slice(0, 8) || "—"}</td>
                  <td className="px-4 py-3 text-ink-secondary font-mono text-xs">{c.caller_id?.slice(0, 8) || "—"}</td>
                  <td className="px-4 py-3 text-ink-secondary font-mono text-xs">{fmtDuration(c.duration_seconds)}</td>
                  <td className="px-4 py-3">
                    {c.manual_status || c.disposition ? (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${DISPOSITION_BADGE[c.manual_status || c.disposition || ""] || "bg-surface-mid text-ink-muted"}`}>
                        {(c.manual_status || c.disposition || "").replace(/_/g, " ")}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-3 text-ink-muted text-xs">{relTime(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- Scheduled ---------- */

interface ScheduledRow {
  id: string;
  lead_id: string | null;
  scheduled_for: string;
  cadence: string | null;
}

interface ScheduledData {
  pending_count: number;
  scheduled: ScheduledRow[];
}

function ScheduledSection({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<ScheduledData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch<ScheduledData>(`/api/v1/operator/clients/${tenantId}/dashboard/telecalling?section=scheduled`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) return <div className="space-y-4"><SkeletonCard /><SkeletonTable /></div>;
  if (error) return <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <StatCard icon={<Clock size={18} />} label="Pending Callbacks" value={data.pending_count} />
      {data.scheduled.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <Calendar size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No scheduled calls</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Lead</th>
                <th className="text-left px-4 py-3 font-medium">Type</th>
                <th className="text-left px-4 py-3 font-medium">Scheduled For</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.scheduled.map((r) => (
                <tr key={r.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink font-mono text-xs">{r.lead_id?.slice(0, 8) || "—"}</td>
                  <td className="px-4 py-3 text-ink-secondary">{r.cadence || "callback"}</td>
                  <td className="px-4 py-3 text-ink-muted text-xs">
                    {new Date(r.scheduled_for).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- Notes ---------- */

interface NoteRow {
  id: string;
  lead_id: string | null;
  author_name: string | null;
  note: string;
  created_at: string;
}

interface NotesData {
  total_notes: number;
  notes: NoteRow[];
}

function NotesSection({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<NotesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch<NotesData>(`/api/v1/operator/clients/${tenantId}/dashboard/telecalling?section=notes`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) return <div className="space-y-4"><SkeletonCard /><SkeletonTable /></div>;
  if (error) return <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <StatCard icon={<StickyNote size={18} />} label="Total Notes" value={data.total_notes} />
      {data.notes.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <StickyNote size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No call notes</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Lead</th>
                <th className="text-left px-4 py-3 font-medium">Author</th>
                <th className="text-left px-4 py-3 font-medium">Note</th>
                <th className="text-left px-4 py-3 font-medium">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.notes.map((n) => (
                <tr key={n.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink font-mono text-xs">{n.lead_id?.slice(0, 8) || "—"}</td>
                  <td className="px-4 py-3 text-ink-secondary">{n.author_name || "—"}</td>
                  <td className="px-4 py-3 text-ink-secondary truncate max-w-[240px]">
                    {(n.note || "").length > 80 ? n.note.slice(0, 80) + "..." : n.note}
                  </td>
                  <td className="px-4 py-3 text-ink-muted text-xs">{relTime(n.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- Main TelecallingView ---------- */

export function TelecallingView({ tenantId, subSection }: { tenantId: string; subSection: "upload" | "dialer" | "scheduled" | "notes" }) {
  switch (subSection) {
    case "upload": return <UploadSection tenantId={tenantId} />;
    case "dialer": return <DialerSection tenantId={tenantId} />;
    case "scheduled": return <ScheduledSection tenantId={tenantId} />;
    case "notes": return <NotesSection tenantId={tenantId} />;
  }
}
