"use client";
import { useEffect, useState } from "react";
import { FileCheck, Layers, BookOpen, Hash, CheckCircle, Clock } from "lucide-react";
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

/* ---------- Templates ---------- */

interface TemplateRow {
  name: string;
  status: string;
  category: string;
  language: string;
  last_synced: string | null;
}

interface TemplatesData {
  total: number;
  approved: number;
  pending: number;
  templates: TemplateRow[];
}

const TEMPLATE_STATUS: Record<string, string> = {
  APPROVED: "bg-green-50 text-success",
  PENDING: "bg-amber-50 text-warning",
  REJECTED: "bg-red-50 text-danger",
};

function TemplatesSection({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<TemplatesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch<TemplatesData>(`/api/v1/operator/clients/${tenantId}/dashboard/templates`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) return <div className="space-y-4"><div className="grid grid-cols-3 gap-4"><SkeletonCard /><SkeletonCard /><SkeletonCard /></div><SkeletonTable /></div>;
  if (error) return <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <StatCard icon={<Hash size={18} />} label="Total" value={data.total} />
        <StatCard icon={<CheckCircle size={18} />} label="Approved" value={data.approved} />
        <StatCard icon={<Clock size={18} />} label="Pending" value={data.pending} />
      </div>
      {data.templates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <FileCheck size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No templates</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Name</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Category</th>
                <th className="text-left px-4 py-3 font-medium">Language</th>
                <th className="text-left px-4 py-3 font-medium">Last Synced</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.templates.map((t) => (
                <tr key={t.name} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink">{t.name}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${TEMPLATE_STATUS[t.status] || "bg-surface-mid text-ink-muted"}`}>
                      {t.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-ink-secondary">{t.category}</td>
                  <td className="px-4 py-3 text-ink-secondary">{t.language}</td>
                  <td className="px-4 py-3 text-ink-muted text-xs">{t.last_synced ? relTime(t.last_synced) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- Numbers ---------- */

interface NumberRow {
  number: string;
  display_name: string | null;
  quality_rating: string | null;
  status: string;
  messaging_limit: string | null;
}

interface NumbersData {
  total: number;
  active: number;
  numbers: NumberRow[];
}

const QUALITY_BADGE: Record<string, string> = {
  GREEN: "bg-green-50 text-success",
  YELLOW: "bg-amber-50 text-warning",
  RED: "bg-red-50 text-danger",
};

function NumbersSection({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<NumbersData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch<NumbersData>(`/api/v1/operator/clients/${tenantId}/dashboard/numbers`)
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
        <StatCard icon={<Hash size={18} />} label="Total Numbers" value={data.total} />
        <StatCard icon={<CheckCircle size={18} />} label="Active" value={data.active} />
      </div>
      {data.numbers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <Layers size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No numbers</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Number</th>
                <th className="text-left px-4 py-3 font-medium">Display Name</th>
                <th className="text-left px-4 py-3 font-medium">Quality</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Messaging Limit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.numbers.map((n) => (
                <tr key={n.number} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink font-mono">{n.number}</td>
                  <td className="px-4 py-3 text-ink-secondary">{n.display_name || "—"}</td>
                  <td className="px-4 py-3">
                    {n.quality_rating ? (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${QUALITY_BADGE[n.quality_rating] || "bg-surface-mid text-ink-muted"}`}>
                        {n.quality_rating}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${n.status === "active" ? "bg-green-50 text-success" : "bg-red-50 text-danger"}`}>
                      {n.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-ink-secondary">{n.messaging_limit || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- Knowledge ---------- */

interface KnowledgeRow {
  id: string;
  title: string;
  chunks: number;
  file_type: string;
  created_at: string;
}

interface KnowledgeData {
  total_docs: number;
  total_chunks: number;
  documents: KnowledgeRow[];
}

function KnowledgeSection({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<KnowledgeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch<KnowledgeData>(`/api/v1/operator/clients/${tenantId}/dashboard/knowledge`)
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
        <StatCard icon={<BookOpen size={18} />} label="Documents" value={data.total_docs} />
        <StatCard icon={<Hash size={18} />} label="Total Chunks" value={data.total_chunks} />
      </div>
      {data.documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <BookOpen size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No knowledge documents</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Title</th>
                <th className="text-left px-4 py-3 font-medium">Chunks</th>
                <th className="text-left px-4 py-3 font-medium">File Type</th>
                <th className="text-left px-4 py-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink">{doc.title}</td>
                  <td className="px-4 py-3 text-ink-secondary">{doc.chunks}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-primary-muted text-primary">
                      {doc.file_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-ink-muted text-xs">{relTime(doc.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- Main ContentView ---------- */

export function ContentView({ tenantId, subSection }: { tenantId: string; subSection: "templates" | "numbers" | "knowledge" }) {
  switch (subSection) {
    case "templates": return <TemplatesSection tenantId={tenantId} />;
    case "numbers": return <NumbersSection tenantId={tenantId} />;
    case "knowledge": return <KnowledgeSection tenantId={tenantId} />;
  }
}
