"use client";
import { toast } from "sonner";
import { useEffect, useRef, useState, useCallback, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { Plus, X, Pencil, Check, Trash2, PauseCircle, PlayCircle, Star, RefreshCw, Info, ChevronDown, ChevronUp, ChevronRight } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { cn } from "@/lib/utils";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { Loader2 } from "lucide-react";

type PhoneNumber = {
  id: string;
  provider: "meta_cloud";
  number: string;
  display_name: string;
  role: "primary" | "standby" | "archived";
  status: "active" | "warming" | "restricted" | "archived";
  quality_rating: "green" | "yellow" | "red";
  messaging_tier: number;
  daily_send_count: number;
  warm_up_day: number;
  paused_outbound: boolean;
  meta_phone_number_id?: string | null;
  created_at: string;
};

const QUALITY_COLOR: Record<PhoneNumber["quality_rating"], string> = {
  green: "bg-emerald-400",
  yellow: "bg-amber-400",
  red: "bg-red-400",
};

const QUALITY_LABEL: Record<PhoneNumber["quality_rating"], string> = {
  green: "High",
  yellow: "Medium",
  red: "Low",
};

const ROLE_STYLES: Record<PhoneNumber["role"], string> = {
  primary: "bg-blue-100 text-blue-700",
  standby: "bg-surface-mid text-on-surface-muted",
  archived: "bg-surface-low text-on-surface-muted opacity-60",
};

// Messaging tier labels — based on Meta's current (2025/2026) portfolio-level limits
const TIER_LABELS: Record<number, string> = {
  250: "250 / day · Unverified",
  1000: "1,000 / day · Tier 1",
  2000: "2,000 / day · Tier 1",
  10000: "10,000 / day · Tier 2",
  100000: "100,000 / day · Tier 3",
};
function getTierLabel(tier: number): string {
  return TIER_LABELS[tier] ?? `${tier.toLocaleString()} / day`;
}

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders },
    ...opts,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}

// ── Tier Guide Banner ─────────────────────────────────────────────────────────
function TierGuide() {
  const [open, setOpen] = useState(false);

  const tiers = [
    { limit: "250 / day", label: "Unverified", color: "bg-red-100 text-red-700", trigger: "Default on registration" },
    { limit: "2,000 / day", label: "Tier 1", color: "bg-amber-100 text-amber-700", trigger: "Complete Meta Business Verification" },
    { limit: "10,000 / day", label: "Tier 2", color: "bg-blue-100 text-blue-700", trigger: "Auto-upgrade: ≥50% usage in 7 days + High/Medium quality" },
    { limit: "100,000 / day", label: "Tier 3", color: "bg-violet-100 text-violet-700", trigger: "Auto-upgrade: same criteria" },
    { limit: "Unlimited", label: "Unlimited", color: "bg-emerald-100 text-emerald-700", trigger: "Auto-upgrade: same criteria" },
  ];

  return (
    <div className="mb-6 rounded-xl border border-blue-100 bg-blue-50/60 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-blue-50 transition-colors"
      >
        <span className="flex items-center gap-2">
          <Info size={14} className="text-blue-500 shrink-0" />
          <span className="font-label text-sm font-semibold text-blue-800">
            How WhatsApp messaging limits work
          </span>
          <span className="font-body text-xs text-blue-500">· Updated 2025/2026</span>
        </span>
        {open ? (
          <ChevronUp size={14} className="text-blue-400 shrink-0" />
        ) : (
          <ChevronDown size={14} className="text-blue-400 shrink-0" />
        )}
      </button>

      {open && (
        <div className="px-5 pb-5 border-t border-blue-100">
          <p className="font-body text-xs text-blue-700 mt-3 mb-4 leading-relaxed">
            Meta uses a <strong>portfolio-level</strong> tier system (since Oct 2025). All numbers in your portfolio share the same tier.
            There is <strong>no fixed 14-day period</strong> — upgrades are automatic based on quality + usage.
          </p>

          {/* Tier table */}
          <div className="space-y-2 mb-4">
            {tiers.map((t) => (
              <div key={t.label} className="flex items-center gap-3">
                <span className={`px-2 py-0.5 rounded-full font-label text-[11px] font-semibold whitespace-nowrap ${t.color}`}>
                  {t.label}
                </span>
                <span className="font-label text-xs font-bold text-on-surface whitespace-nowrap">{t.limit}</span>
                <span className="font-body text-xs text-on-surface-muted">{t.trigger}</span>
              </div>
            ))}
          </div>

          {/* Key rules */}
          <div className="grid grid-cols-2 gap-2">
            {[
              { icon: "✅", text: "Submit Meta Business Verification immediately after adding a number" },
              { icon: "✅", text: "Send only to opted-in, warm contacts — avoid cold outreach" },
              { icon: "✅", text: "Use ≥50% of your daily limit each week to trigger auto-upgrades" },
              { icon: "❌", text: "Don't blast cold lists — spam reports drop your quality rating instantly" },
            ].map((r, i) => (
              <div key={i} className="flex items-start gap-1.5 bg-white/70 rounded-lg p-2.5">
                <span className="text-xs shrink-0 mt-0.5">{r.icon}</span>
                <span className="font-body text-[11px] text-on-surface-muted leading-relaxed">{r.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Incidents Types & Components ─────────────────────────────────────────────
type Incident = {
  id: string;
  type: string;
  phone_number_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
};

const TYPE_LABELS: Record<string, string> = {
  quality_yellow: "Number flagged Yellow — outbound volume halved",
  quality_red: "Number flagged Red — failover triggered",
  failover: "Standby promoted to primary",
  migration_sent: "Channel migration notice sent to recent leads",
  appeal_filed: "Meta appeal filed",
  standby_promoted: "Standby number promoted",
  warm_up_complete: "Number warm-up complete — now active",
  quality_snapshot: "Quality synced from Meta",
};

const TYPE_BADGE: Record<string, string> = {
  quality_yellow: "bg-amber-100 text-amber-700",
  quality_red: "bg-red-100 text-red-700",
  failover: "bg-blue-100 text-blue-700",
  migration_sent: "bg-purple-100 text-purple-700",
  appeal_filed: "bg-orange-100 text-orange-700",
  standby_promoted: "bg-blue-100 text-blue-700",
  warm_up_complete: "bg-green-100 text-green-700",
  quality_snapshot: "bg-emerald-100 text-emerald-700",
};

const INCIDENTS_PAGE_SIZE = 50;

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
    ", " +
    d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
}

function DetailExpander({ detail }: { detail: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const keys = Object.keys(detail);
  if (keys.length === 0) return null;
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 font-label text-xs text-on-surface-muted hover:text-on-surface transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {open ? "Hide detail" : "Show detail"}
      </button>
      {open && (
        <pre className="mt-2 p-3 rounded-lg bg-surface-low font-mono text-xs text-on-surface overflow-x-auto">
          {JSON.stringify(detail, null, 2)}
        </pre>
      )}
    </div>
  );
}

const QUALITY_DOT: Record<string, string> = {
  green: "bg-emerald-400",
  yellow: "bg-amber-400",
  red: "bg-red-400",
};

function IncidentRow({ incident }: { incident: Incident }) {
  const badgeClass = TYPE_BADGE[incident.type] ?? "bg-surface-mid text-on-surface-muted";
  const label = TYPE_LABELS[incident.type] ?? incident.type.replace(/_/g, " ");
  const isSnapshot = incident.type === "quality_snapshot";
  const snapQuality = isSnapshot ? (incident.detail.quality_rating as string) : null;

  return (
    <div className="flex gap-4 py-5 border-b border-surface-mid/50 last:border-0">
      <div className="flex flex-col items-center gap-1 pt-0.5">
        <div className="w-2.5 h-2.5 rounded-full bg-tertiary/30 ring-2 ring-tertiary/20 flex-shrink-0" />
        <div className="flex-1 w-px bg-surface-mid" />
      </div>
      <div className="flex-1 min-w-0 pb-1">
        <div className="flex flex-wrap items-center gap-2 mb-1.5">
          <span className="font-label text-xs text-on-surface-muted whitespace-nowrap">
            {formatTimestamp(incident.created_at)}
          </span>
          <span className={`px-2 py-0.5 rounded-full font-label text-xs font-semibold ${badgeClass}`}>
            {incident.type.replace(/_/g, " ")}
          </span>
          {isSnapshot && snapQuality && (
            <span className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${QUALITY_DOT[snapQuality] ?? "bg-surface-mid"}`} />
              <span className="font-label text-xs text-on-surface-muted capitalize">{snapQuality}</span>
              {incident.detail.messaging_tier != null && (
                <span className="font-label text-xs text-on-surface-muted">
                  · {Number(incident.detail.messaging_tier).toLocaleString()} /day
                </span>
              )}
            </span>
          )}
        </div>
        <p className="font-body text-sm text-on-surface">{label}</p>
        {!isSnapshot && <DetailExpander detail={incident.detail} />}
      </div>
    </div>
  );
}

const numbersApi = {
  list: () =>
    apiFetch<{ data: PhoneNumber[] }>("/api/v1/numbers").then((r) => r.data ?? []),
  create: (payload: {
    provider: string;
    number: string;
    display_name: string;
    meta_phone_number_id?: string;
    api_key?: string;
  }) =>
    apiFetch<PhoneNumber>("/api/v1/numbers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  update: (id: string, data: Partial<Pick<PhoneNumber, "role" | "status" | "display_name" | "paused_outbound">>) =>
    apiFetch<PhoneNumber>(`/api/v1/numbers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  remove: (id: string) =>
    apiFetch<{ deleted: boolean }>(`/api/v1/numbers/${id}`, { method: "DELETE" }),
  syncMeta: (id: string) =>
    apiFetch<PhoneNumber>(`/api/v1/numbers/${id}/sync-meta`, { method: "POST" }),
};

function NumbersPageContent() {
  const { role, loading: roleLoading } = useAuthRole();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const tabQuery = searchParams.get("tab");

  const [activeTab, setActiveTab] = useState<"pool" | "activity">("pool");
  const [numbers, setNumbers] = useState<PhoneNumber[]>([]);
  const [loading, setLoading] = useState(true);

  const [showAddModal, setShowAddModal] = useState(false);
  const [addNumber, setAddNumber] = useState("");
  const [addDisplayName, setAddDisplayName] = useState("");
  const [addMetaId, setAddMetaId] = useState("");
  const [adding, setAdding] = useState(false);

  // Inline rename state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [saving, setSaving] = useState(false);
  const editInputRef = useRef<HTMLInputElement>(null);

  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);
  const [pausingId, setPausingId] = useState<string | null>(null);

  // Incidents state
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [incidentOffset, setIncidentOffset] = useState(0);
  const [hasMoreIncidents, setHasMoreIncidents] = useState(true);
  const [incidentsLoading, setIncidentsLoading] = useState(true);
  const [loadingMoreIncidents, setLoadingMoreIncidents] = useState(false);

  useEffect(() => {
    if (tabQuery === "activity") {
      setActiveTab("activity");
    } else {
      setActiveTab("pool");
    }
  }, [tabQuery]);

  const handleTabChange = (tab: "pool" | "activity") => {
    setActiveTab(tab);
    if (tab === "activity") {
      router.push(`${pathname}?tab=activity`);
    } else {
      router.push(pathname);
    }
  };

  async function reload() {
    const rows = await numbersApi.list();
    setNumbers(rows);
  }

  useEffect(() => {
    setLoading(true);
    numbersApi.list().then((rows) => {
      setNumbers(rows);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const fetchIncidents = useCallback(async (currentOffset: number, append: boolean) => {
    try {
      const result = await apiFetch<{ data: Incident[] }>(
        `/api/v1/incidents/?limit=${INCIDENTS_PAGE_SIZE}&offset=${currentOffset}`
      );
      const rows = result.data ?? [];
      setIncidents((prev) => (append ? [...prev, ...rows] : rows));
      setHasMoreIncidents(rows.length === INCIDENTS_PAGE_SIZE);
    } catch {
      // silent — keep stale data visible
    }
  }, []);

  useEffect(() => {
    if (activeTab === "activity") {
      setIncidentsLoading(true);
      fetchIncidents(0, false).finally(() => setIncidentsLoading(false));
    }
  }, [activeTab, fetchIncidents]);

  const refreshIncidents = useCallback(() => {
    if (activeTab === "activity") {
      fetchIncidents(0, false);
    }
  }, [activeTab, fetchIncidents]);

  usePolling(refreshIncidents, 30_000);

  async function handleLoadMoreIncidents() {
    const nextOffset = incidentOffset + INCIDENTS_PAGE_SIZE;
    setLoadingMoreIncidents(true);
    await fetchIncidents(nextOffset, true);
    setIncidentOffset(nextOffset);
    setLoadingMoreIncidents(false);
  }

  // Focus input when entering edit mode
  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  if (roleLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (role !== "owner") {
    return (
      <div className="text-center py-20">
        <p className="text-on-surface-muted font-body">
          This section is only available for owners/admins.
        </p>
      </div>
    );
  }

  function startRename(num: PhoneNumber) {
    setEditingId(num.id);
    setEditName(num.display_name);
  }

  async function saveRename(id: string) {
    if (!editName.trim()) return;
    setSaving(true);
    try {
      await numbersApi.update(id, { display_name: editName.trim() });
      await reload();
      setEditingId(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleAdd() {
    if (!addNumber.trim() || !addDisplayName.trim()) return;
    setAdding(true);
    try {
      await numbersApi.create({
        provider: "meta_cloud",
        number: addNumber.trim(),
        display_name: addDisplayName.trim(),
        ...(addMetaId.trim() ? { meta_phone_number_id: addMetaId.trim() } : {}),
      });
      await reload();
      setShowAddModal(false);
      setAddNumber("");
      setAddDisplayName("");
      setAddMetaId("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add number");
    } finally {
      setAdding(false);
    }
  }

  async function handleSetPrimary(id: string) {
    try {
      await numbersApi.update(id, { role: "primary" });
      await reload();
      toast.success("Set as primary number");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function handleTogglePause(num: PhoneNumber) {
    setPausingId(num.id);
    try {
      await numbersApi.update(num.id, { paused_outbound: !num.paused_outbound });
      await reload();
      toast.success(num.paused_outbound ? "Outbound resumed" : "Outbound paused");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    } finally {
      setPausingId(null);
    }
  }

  async function handleSyncMeta(id: string) {
    setSyncingId(id);
    try {
      await numbersApi.syncMeta(id);
      await reload();
      toast.success("Synced from Meta");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncingId(null);
    }
  }

  async function handleSyncAllMeta() {
    const configuredNumbers = numbers.filter((n) => n.meta_phone_number_id && n.status !== "archived");
    if (configuredNumbers.length === 0) {
      toast.error("No configured numbers to sync");
      return;
    }
    setSyncingAll(true);
    let successCount = 0;
    let failCount = 0;

    await Promise.all(
      configuredNumbers.map(async (num) => {
        try {
          await numbersApi.syncMeta(num.id);
          successCount++;
        } catch (err) {
          console.error(`Failed to sync number ${num.number}:`, err);
          failCount++;
        }
      })
    );

    await reload();
    setSyncingAll(false);

    if (failCount === 0) {
      toast.success(`Successfully synced ${successCount} numbers from Meta`);
    } else if (successCount > 0) {
      toast.success(`Synced ${successCount} numbers, ${failCount} failed`);
    } else {
      toast.error("Failed to sync numbers from Meta");
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this number? It will no longer send or receive messages.")) return;
    try {
      await numbersApi.remove(id);
      await reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const activeCount = numbers.filter((n) => n.status === "active").length;
  const visible = numbers.filter((n) => n.status !== "archived");

  return (
    <div>
      {/* Tab Navigation */}
      <div className="flex items-center gap-1 border-b border-surface-mid mb-6">
        <button
          onClick={() => handleTabChange("pool")}
          className={cn(
            "px-6 py-3 font-label font-semibold text-sm transition-all border-b-2",
            activeTab === "pool" ? "border-tertiary text-tertiary" : "border-transparent text-on-surface-muted hover:text-on-surface"
          )}
        >
          Active Pool
        </button>
        <button
          onClick={() => handleTabChange("activity")}
          className={cn(
            "px-6 py-3 font-label font-semibold text-sm transition-all border-b-2",
            activeTab === "activity" ? "border-tertiary text-tertiary" : "border-transparent text-on-surface-muted hover:text-on-surface"
          )}
        >
          Activity Log
        </button>
      </div>

      {activeTab === "pool" ? (
        <>
          {/* Messaging Tier Guide */}
          <TierGuide />

          <div className="bg-surface rounded-card shadow-card ring-1 ring-[#c4c7c7]/15 p-8">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display text-lg font-bold text-tertiary">Number Pool</h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSyncAllMeta}
                  disabled={syncingAll || numbers.filter(n => n.meta_phone_number_id && n.status !== "archived").length === 0}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-surface-mid text-on-surface hover:text-tertiary hover:border-tertiary/40 rounded-lg font-label text-xs font-semibold transition-colors disabled:opacity-50"
                  title="Sync all configured numbers from Meta"
                >
                  <RefreshCw size={13} className={syncingAll ? "animate-spin" : ""} />
                  {syncingAll ? "Syncing all…" : "Sync from Meta"}
                </button>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-tertiary text-white rounded-lg font-label text-xs font-semibold hover:bg-tertiary/90 transition-colors"
                >
                  <Plus size={13} />
                  Add Number
                </button>
              </div>
            </div>

            {loading ? (
              <p className="font-body text-sm text-on-surface-muted">Loading…</p>
            ) : visible.length === 0 ? (
              <p className="font-body text-sm text-on-surface-muted">
                No numbers yet. Click &quot;Add Number&quot; to get started.
              </p>
            ) : (
              <div className="space-y-3">
                {visible.map((num) => {
                  const isEditing = editingId === num.id;
                  const isSyncing = syncingId === num.id;
                  const isPausing = pausingId === num.id;
                  const sendPct = num.messaging_tier > 0
                    ? Math.min((num.daily_send_count / num.messaging_tier) * 100, 100)
                    : 0;

                  return (
                    <div
                      key={num.id}
                      className="rounded-xl border border-surface-mid bg-surface-low/40 p-4 hover:bg-surface-low transition-colors"
                    >
                      {/* Row 1: name + role + status + quality */}
                      <div className="flex items-center gap-3 mb-3">
                        {/* Inline-editable name */}
                        {isEditing ? (
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            <input
                              ref={editInputRef}
                              type="text"
                              value={editName}
                              onChange={(e) => setEditName(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") saveRename(num.id);
                                if (e.key === "Escape") setEditingId(null);
                              }}
                              className="px-2.5 py-1.5 rounded-lg bg-surface border border-tertiary font-body text-sm focus:outline-none focus:ring-2 focus:ring-tertiary min-w-0 w-48"
                            />
                            <button
                              onClick={() => saveRename(num.id)}
                              disabled={saving}
                              className="p-1.5 rounded-lg bg-tertiary text-white hover:bg-tertiary/90 disabled:opacity-50 transition-colors"
                              title="Save"
                            >
                              <Check size={12} />
                            </button>
                            <button
                              onClick={() => setEditingId(null)}
                              className="p-1.5 rounded-lg hover:bg-surface-mid transition-colors text-on-surface-muted"
                              title="Cancel"
                            >
                              <X size={12} />
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => startRename(num)}
                            className="flex items-center gap-1.5 group min-w-0"
                            title="Click to rename"
                          >
                            <span className="font-body text-sm font-semibold text-on-surface group-hover:text-tertiary transition-colors truncate">
                              {num.display_name}
                            </span>
                            <Pencil size={11} className="text-on-surface-muted opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                          </button>
                        )}

                        <span className="font-label text-xs text-on-surface-muted whitespace-nowrap">{num.number}</span>

                        {/* Role */}
                        <span className={`px-2 py-0.5 rounded-full font-label text-[11px] font-semibold capitalize ${ROLE_STYLES[num.role]}`}>
                          {num.role}
                        </span>

                        {/* Quality */}
                        <span className="flex items-center gap-1">
                          <span className={`w-2 h-2 rounded-full inline-block flex-shrink-0 ${QUALITY_COLOR[num.quality_rating]}`} />
                          <span className="font-label text-[11px] text-on-surface-muted">{QUALITY_LABEL[num.quality_rating]}</span>
                        </span>

                        {/* Paused badge */}
                        {num.paused_outbound && (
                          <span className="px-2 py-0.5 rounded-full font-label text-[11px] bg-amber-100 text-amber-700 font-semibold">
                            Paused
                          </span>
                        )}
                      </div>

                      {/* Row 2: sends bar + warm-up + actions */}
                      <div className="flex items-center gap-4">
                        {/* Daily sends bar */}
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="font-label text-[11px] text-on-surface-muted whitespace-nowrap">
                            {num.daily_send_count.toLocaleString()} / {num.messaging_tier.toLocaleString()} today
                          </span>
                          <div className="w-24 h-1.5 rounded-full bg-surface-mid overflow-hidden flex-shrink-0">
                            <div
                              className={`h-full rounded-full transition-all ${sendPct > 80 ? "bg-red-400" : sendPct > 50 ? "bg-amber-400" : "bg-emerald-400"}`}
                              style={{ width: `${sendPct}%` }}
                            />
                          </div>
                          <span className="font-label text-[11px] text-on-surface-muted">{Math.round(sendPct)}%</span>
                        </div>

                        {/* Tier label */}
                        <span className="font-label text-[11px] text-on-surface-muted whitespace-nowrap">
                          {getTierLabel(num.messaging_tier)}
                        </span>

                        {/* Spacer */}
                        <div className="flex-1" />

                        {/* Action buttons */}

                        {/* Set as Primary */}
                        {num.role !== "primary" && num.role !== "archived" && (
                          <button
                            onClick={() => handleSetPrimary(num.id)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-blue-200 bg-blue-50 hover:bg-blue-100 text-blue-600 font-label text-[11px] font-semibold transition-colors"
                            title="Set as primary number"
                          >
                            <Star size={11} />
                            Set Primary
                          </button>
                        )}

                        {/* Pause / Resume */}
                        <button
                          onClick={() => handleTogglePause(num)}
                          disabled={isPausing}
                          className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg border font-label text-[11px] font-semibold transition-colors disabled:opacity-50 ${
                            num.paused_outbound
                              ? "border-green-200 bg-green-50 hover:bg-green-100 text-green-700"
                              : "border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-700"
                          }`}
                          title={num.paused_outbound ? "Resume outbound messaging" : "Pause outbound messaging"}
                        >
                          {num.paused_outbound
                            ? <><PlayCircle size={12} /> Resume</>
                            : <><PauseCircle size={12} /> Pause</>
                          }
                        </button>

                        {/* Sync from Meta */}
                        <button
                          onClick={() => handleSyncMeta(num.id)}
                          disabled={isSyncing}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-surface-mid bg-surface hover:bg-surface-low text-on-surface-muted hover:text-on-surface font-label text-[11px] font-semibold transition-colors disabled:opacity-50"
                          title="Pull latest quality rating and tier from Meta"
                        >
                          <RefreshCw size={11} className={isSyncing ? "animate-spin" : ""} />
                          {isSyncing ? "Syncing…" : "Sync Meta"}
                        </button>

                        {/* Delete */}
                        <button
                          onClick={() => handleDelete(num.id)}
                          disabled={activeCount === 1 && num.status === "active"}
                          title={activeCount === 1 && num.status === "active" ? "Cannot delete last active number" : "Delete number"}
                          className="p-1.5 rounded-lg hover:bg-red-50 text-on-surface-muted hover:text-red-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Add Number Modal */}
          {showAddModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
              <div className="bg-surface rounded-card p-8 shadow-card w-full max-w-md ring-1 ring-[#c4c7c7]/20">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-display text-lg font-bold text-tertiary">Add Number</h2>
                  <button
                    onClick={() => setShowAddModal(false)}
                    className="p-1.5 rounded-lg hover:bg-surface-low transition-colors text-on-surface-muted"
                  >
                    <X size={16} />
                  </button>
                </div>

                {/* What happens after you add */}
                <div className="mb-5 p-3.5 rounded-xl bg-amber-50 border border-amber-100">
                  <p className="font-label text-xs font-bold text-amber-800 mb-2">⚡ After registering, your number starts at 250 msgs/day</p>
                  <ol className="space-y-1">
                    {[
                      "Complete Meta Business Verification → instantly unlocks 2,000/day",
                      "Send quality messages to warm, opted-in contacts only",
                      "Maintain High/Medium quality rating (avoid spam reports)",
                      "Usage ≥ 50% of limit over 7 days → Meta auto-upgrades to 10,000/day",
                    ].map((step, i) => (
                      <li key={i} className="flex items-start gap-1.5">
                        <span className="font-label text-[10px] font-bold text-amber-600 mt-0.5 shrink-0">{i + 1}.</span>
                        <span className="font-body text-[11px] text-amber-700">{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block font-label text-xs font-semibold text-on-surface-muted mb-1.5">Provider</label>
                    <div className="w-full px-3 py-2 rounded-lg bg-surface-low border border-surface-mid font-body text-sm text-on-surface-muted">
                      Meta Cloud API
                    </div>
                  </div>
                  <div>
                    <label className="block font-label text-xs font-semibold text-on-surface-muted mb-1.5">Phone Number</label>
                    <input
                      type="tel"
                      placeholder="+919876543210"
                      value={addNumber}
                      onChange={(e) => setAddNumber(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg bg-surface-low border border-surface-mid font-body text-sm focus:outline-none focus:ring-2 focus:ring-tertiary"
                    />
                  </div>
                  <div>
                    <label className="block font-label text-xs font-semibold text-on-surface-muted mb-1.5">Display Name</label>
                    <input
                      type="text"
                      placeholder="e.g. Aira Main"
                      value={addDisplayName}
                      onChange={(e) => setAddDisplayName(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg bg-surface-low border border-surface-mid font-body text-sm focus:outline-none focus:ring-2 focus:ring-tertiary"
                    />
                  </div>
                  <div>
                    <label className="block font-label text-xs font-semibold text-on-surface-muted mb-1.5">Meta Phone Number ID</label>
                    <input
                      type="text"
                      placeholder="From Meta Business Manager"
                      value={addMetaId}
                      onChange={(e) => setAddMetaId(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg bg-surface-low border border-surface-mid font-body text-sm focus:outline-none focus:ring-2 focus:ring-tertiary"
                    />
                  </div>
                  <button
                    onClick={handleAdd}
                    disabled={adding || !addNumber.trim() || !addDisplayName.trim()}
                    className="w-full py-2.5 bg-tertiary text-white rounded-lg font-label text-sm font-semibold hover:bg-tertiary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {adding ? "Adding…" : "Add Number"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="bg-surface rounded-card p-8 shadow-card ring-1 ring-[#c4c7c7]/15">
          <div className="flex items-center justify-between mb-6">
            <h2 className="font-display text-lg font-bold text-tertiary">Timeline</h2>
            <div className="flex items-center gap-3">
              <button
                onClick={async () => {
                  await handleSyncAllMeta();
                  setIncidentsLoading(true);
                  await fetchIncidents(0, false);
                  setIncidentOffset(0);
                  setIncidentsLoading(false);
                }}
                disabled={syncingAll || numbers.filter(n => n.meta_phone_number_id && n.status !== "archived").length === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-surface-mid text-on-surface hover:text-tertiary hover:border-tertiary/40 rounded-lg font-label text-xs font-semibold transition-colors disabled:opacity-50"
                title="Sync quality from Meta and log any changes"
              >
                <RefreshCw size={13} className={syncingAll ? "animate-spin" : ""} />
                {syncingAll ? "Syncing…" : "Sync from Meta"}
              </button>
              <span className="font-label text-xs text-on-surface-muted">
                Auto-refreshes every 30 s
              </span>
            </div>
          </div>

          {incidentsLoading ? (
            <p className="font-body text-sm text-on-surface-muted">Loading…</p>
          ) : incidents.length === 0 ? (
            <div className="py-16 text-center">
              <p className="font-body text-sm text-on-surface-muted">
                No incidents yet — your numbers are healthy
              </p>
            </div>
          ) : (
            <div>
              {incidents.map((incident) => (
                <IncidentRow key={incident.id} incident={incident} />
              ))}

              {hasMoreIncidents && (
                <div className="pt-4 text-center">
                  <button
                    onClick={handleLoadMoreIncidents}
                    disabled={loadingMoreIncidents}
                    className="px-4 py-2 bg-surface-low border border-surface-mid rounded-lg font-label text-xs font-semibold text-on-surface hover:bg-surface-mid transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loadingMoreIncidents ? "Loading…" : "Load more"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function NumbersPage() {
  return (
    <Suspense fallback={
      <div>
        <div className="mb-6 flex items-start justify-between animate-pulse">
          <div>
            <div className="h-8 w-48 bg-surface-mid rounded mb-2"></div>
            <div className="h-4 w-72 bg-surface-mid rounded"></div>
          </div>
        </div>
        <div className="h-32 bg-surface-mid rounded animate-pulse"></div>
      </div>
    }>
      <NumbersPageContent />
    </Suspense>
  );
}
