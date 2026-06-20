"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { ClientDetailSidebar, type SectionType } from "./sidebar";
import { OverviewView } from "./views/overview";
import { InboxView } from "./views/inbox";
import { LeadsView } from "./views/leads";
import { ContentView } from "./views/content";
import { AnalyticsView } from "./views/analytics";
import { TeamView } from "./views/team";
import { TelecallingView } from "./views/telecalling";
import { ConfigView } from "./views/config";
import { HealthView } from "./views/health";
import { ManagementView } from "./views/management";
import { DataOpsView } from "./views/data-ops";

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

interface OverviewData {
  tenant: { id: string; name: string; status: string; enabled_features: string[]; created_at: string };
  owner: { user_id: string | null; email: string | null };
  stats: { total_leads: number; active_leads: number; messages_sent_30d: number; messages_received_30d: number; team_members: number; last_activity: string | null };
}

export { apiFetch };
export type { OverviewData };

export default function ClientDetailPage() {
  const { id: tenantId } = useParams<{ id: string }>();
  const router = useRouter();
  const [section, setSection] = useState<SectionType>("overview");
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [featureUpdating, setFeatureUpdating] = useState(false);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<OverviewData>(`/api/v1/operator/clients/${tenantId}/overview`);
      setOverview(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  async function handleToggleFeature(feature: string) {
    if (!overview) return;
    setFeatureUpdating(true);
    const current = overview.tenant.enabled_features;
    let updated: string[];

    if (feature === "telecalling") {
      const tcSubs = ["telecalling.dialer", "telecalling.upload", "telecalling.scheduled", "telecalling.notes"];
      if (current.includes("telecalling")) {
        updated = current.filter(f => f !== "telecalling" && !tcSubs.includes(f));
      } else {
        updated = [...current, "telecalling", ...tcSubs];
      }
    } else {
      updated = current.includes(feature)
        ? current.filter(f => f !== feature)
        : [...current, feature];
    }

    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/features`, {
        method: "PATCH",
        body: JSON.stringify({ features: updated }),
      });
      setOverview({ ...overview, tenant: { ...overview.tenant, enabled_features: updated } });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update features");
    } finally {
      setFeatureUpdating(false);
    }
  }

  if (loading && !overview) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-ink-muted text-sm">Loading...</div>
      </div>
    );
  }

  const tenant = overview?.tenant;

  return (
    <div>
      {/* Back */}
      <button onClick={() => router.push("/operator")} className="flex items-center gap-1.5 text-sm text-ink-secondary hover:text-ink transition-colors mb-4">
        <ArrowLeft size={14} /> Back to Clients
      </button>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-xs underline ml-2">dismiss</button>
        </div>
      )}

      {/* Header Card */}
      {tenant && (
        <div className="bg-white rounded-card border border-border p-6 mb-6 shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold text-ink font-display">{tenant.name}</h1>
              <p className="text-xs text-ink-muted font-mono mt-1">
                {tenant.id}
                <button onClick={() => navigator.clipboard.writeText(tenant.id)} className="ml-2 text-ink-muted hover:text-ink transition-colors" title="Copy ID">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                </button>
              </p>
              {overview?.owner?.email && <p className="text-sm text-ink-secondary mt-2">Owner: {overview.owner.email}</p>}
              <p className="text-xs text-ink-muted mt-1">Created {new Date(tenant.created_at).toLocaleDateString("en-IN")}</p>
            </div>
            <div className="flex items-center gap-2 flex-wrap justify-end">
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                tenant.status === "active" ? "bg-green-50 text-success" : "bg-red-50 text-danger"
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${tenant.status === "active" ? "bg-success" : "bg-danger"}`} />
                {tenant.status}
              </span>
              {tenant.enabled_features.filter(f => !f.includes(".")).map(f => (
                <span key={f} className="px-2 py-0.5 rounded-full text-xs font-medium bg-primary-muted text-primary">
                  {{"whatsapp":"WhatsApp","telecalling":"Telecalling","instagram":"Instagram","facebook":"Facebook","telegram":"Telegram"}[f] || f}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Sidebar + Content */}
      <div className="flex gap-6">
        <ClientDetailSidebar
          activeSection={section}
          onSectionChange={setSection}
          enabledFeatures={tenant?.enabled_features || []}
          onToggleFeature={handleToggleFeature}
          featureUpdating={featureUpdating}
        />
        <div className="flex-1 min-w-0">
          <SectionContent section={section} tenantId={tenantId} overview={overview} onReload={loadOverview} setError={setError} />
        </div>
      </div>
    </div>
  );
}

function SectionContent({ section, tenantId, overview, onReload, setError }: {
  section: SectionType; tenantId: string; overview: OverviewData | null;
  onReload: () => void; setError: (e: string | null) => void;
}) {
  switch (section) {
    case "overview":
      return overview ? <OverviewView stats={overview.stats} /> : null;
    case "inbox":
    case "conversations":
      return <InboxView tenantId={tenantId} />;
    case "segments":
      return <LeadsView tenantId={tenantId} subSection="segments" />;
    case "inbound":
      return <LeadsView tenantId={tenantId} subSection="inbound" />;
    case "outbound":
      return <LeadsView tenantId={tenantId} subSection="outbound" />;
    case "templates":
      return <ContentView tenantId={tenantId} subSection="templates" />;
    case "numbers":
      return <ContentView tenantId={tenantId} subSection="numbers" />;
    case "knowledge":
      return <ContentView tenantId={tenantId} subSection="knowledge" />;
    case "analytics":
      return <AnalyticsView tenantId={tenantId} />;
    case "team":
      return <TeamView tenantId={tenantId} />;
    case "tc-upload":
      return <TelecallingView tenantId={tenantId} subSection="upload" />;
    case "tc-dialer":
      return <TelecallingView tenantId={tenantId} subSection="dialer" />;
    case "tc-scheduled":
      return <TelecallingView tenantId={tenantId} subSection="scheduled" />;
    case "tc-notes":
      return <TelecallingView tenantId={tenantId} subSection="notes" />;
    case "config":
      return <ConfigView tenantId={tenantId} />;
    case "health":
      return <HealthView tenantId={tenantId} />;
    case "management":
      return <ManagementView tenantId={tenantId} overview={overview} onReload={onReload} setError={setError} />;
    case "data-ops":
      return <DataOpsView tenantId={tenantId} clientName={overview?.tenant.name || ""} />;
    default:
      return (
        <div className="flex items-center justify-center h-48 text-ink-muted text-sm">
          {section} — coming soon
        </div>
      );
  }
}
