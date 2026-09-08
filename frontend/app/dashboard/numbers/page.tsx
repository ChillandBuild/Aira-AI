"use client";

import { toast } from "sonner";
import { useEffect, useRef, useState, useCallback, Suspense, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  X, Pencil, Check, Trash2, PauseCircle, PlayCircle, Star, RefreshCw,
  Info, ChevronDown, ChevronUp, ChevronRight, Lock, Copy, Phone,
  ShieldCheck, Activity, Smartphone, CheckCircle2,
  Search, ArrowRightLeft, ExternalLink
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { cn } from "@/lib/utils";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { Loader2 } from "lucide-react";

// ── Types ───────────────────────────────────────────────────────────────────

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
  locked: boolean;
};

const QUALITY_COLOR: Record<PhoneNumber["quality_rating"], string> = {
  green: "bg-emerald-500",
  yellow: "bg-amber-500",
  red: "bg-red-500",
};

const QUALITY_LABEL: Record<PhoneNumber["quality_rating"], string> = {
  green: "High",
  yellow: "Medium",
  red: "Low",
};

const QUALITY_BG: Record<PhoneNumber["quality_rating"], string> = {
  green: "bg-emerald-50 text-emerald-700 border-emerald-200",
  yellow: "bg-amber-50 text-amber-700 border-amber-200",
  red: "bg-red-50 text-red-700 border-red-200",
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
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `API error ${res.status}`);
  }
  return res.json();
}

// ── Tier Guide Banner ─────────────────────────────────────────────────────────

function TierGuide({
  isOpen,
  onToggleOpen,
  visible = true,
  onDismiss,
}: {
  isOpen?: boolean;
  onToggleOpen?: () => void;
  visible?: boolean;
  onDismiss?: () => void;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [isFading, setIsFading] = useState(false);

  const open = isOpen !== undefined ? isOpen : internalOpen;
  const toggleOpen = onToggleOpen ?? (() => setInternalOpen((v) => !v));

  useEffect(() => {
    // If the guide is open to read, don't dismiss
    if (open) return;

    // Disappear after 15 seconds
    const timer = setTimeout(() => {
      setIsFading(true);
      const hideTimer = setTimeout(() => {
        onDismiss?.();
      }, 500);
      return () => clearTimeout(hideTimer);
    }, 15000);

    return () => clearTimeout(timer);
  }, [open, onDismiss]);

  const handleManualDismiss = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsFading(true);
    setTimeout(() => {
      onDismiss?.();
    }, 350);
  };

  if (!visible) return null;

  const tiers = [
    { limit: "250 / day", label: "Unverified", color: "bg-red-50 text-red-700 border-red-200", trigger: "Default on registration" },
    { limit: "2,000 / day", label: "Tier 1", color: "bg-amber-50 text-amber-700 border-amber-200", trigger: "Complete Meta Business Verification" },
    { limit: "10,000 / day", label: "Tier 2", color: "bg-blue-50 text-blue-700 border-blue-200", trigger: "Auto-upgrade: ≥50% usage in 7 days + High/Medium quality" },
    { limit: "100,000 / day", label: "Tier 3", color: "bg-purple-50 text-purple-700 border-purple-200", trigger: "Auto-upgrade: same criteria" },
    { limit: "Unlimited", label: "Tier 4", color: "bg-emerald-50 text-emerald-700 border-emerald-200", trigger: "Auto-upgrade: same criteria" },
  ];

  return (
    <div
      className={cn(
        "rounded-2xl border border-purple-200/70 bg-gradient-to-br from-purple-50/40 via-white to-blue-50/30 overflow-hidden shadow-xs transition-all duration-300",
        isFading
          ? "opacity-0 -translate-y-1 max-h-0 pointer-events-none border-transparent py-0"
          : "opacity-100 max-h-[1000px]"
      )}
    >
      <div
        onClick={toggleOpen}
        className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-purple-50/50 transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
            <Info size={15} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-display text-sm font-bold text-on-surface">
              How WhatsApp messaging limits work
            </span>
            <span className="px-2 py-0.5 rounded-full bg-purple-100/80 text-primary font-label text-[10px] font-bold">
              Portfolio-Level · Updated 2025/2026
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 text-primary font-label text-xs font-semibold">
          <span className="hover:underline flex items-center gap-1">
            {open ? "Hide guide" : "View guide"}
            {open ? (
              <ChevronUp size={15} className="text-primary shrink-0" />
            ) : (
              <ChevronDown size={15} className="text-primary shrink-0" />
            )}
          </span>
          <button
            type="button"
            onClick={handleManualDismiss}
            className="p-1 rounded-lg hover:bg-purple-100 text-on-surface-muted hover:text-on-surface transition-colors ml-1"
            title="Dismiss notice"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {open && (
        <div className="px-5 pb-5 pt-1 border-t border-purple-100/80 space-y-4">
          <p className="font-body text-xs text-on-surface-muted leading-relaxed">
            Meta operates on a <strong>portfolio-level</strong> tier system (since Oct 2025). All phone numbers in your Meta Business portfolio share the portfolio tier limit.
            There is <strong>no fixed 14-day evaluation window</strong> — upgrades trigger automatically when you dispatch ≥50% of your current tier limit over any rolling 7-day period while keeping High or Medium quality.
          </p>

          {/* Tier progression cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2.5">
            {tiers.map((t, idx) => (
              <div key={t.label} className="p-3 rounded-xl bg-white border border-border/70 shadow-2xs flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between gap-1 mb-1.5">
                    <span className={`px-2 py-0.5 rounded-md font-label text-[10px] font-bold border ${t.color}`}>
                      {t.label}
                    </span>
                    <span className="font-mono text-[10px] text-on-surface-muted font-bold">#{idx + 1}</span>
                  </div>
                  <p className="font-display text-sm font-bold text-on-surface">{t.limit}</p>
                </div>
                <p className="font-body text-[11px] text-on-surface-muted mt-2 leading-tight">{t.trigger}</p>
              </div>
            ))}
          </div>

          {/* Key rules */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
            {[
              { icon: "✅", title: "Business Verification", text: "Complete Meta Business Verification immediately to unlock Tier 1 (2,000/day)." },
              { icon: "✅", title: "Warm Opt-in Contacts", text: "Only message opted-in leads with relevant templates to protect your quality rating." },
              { icon: "✅", title: "50% Weekly Pacing", text: "Utilize ≥50% of your daily quota across a rolling week to qualify for the next tier." },
              { icon: "❌", title: "Avoid Cold Lists", text: "Recipient spam and block reports drop quality to Medium or Low, capping limits instantly." },
            ].map((r, i) => (
              <div key={i} className="flex items-start gap-2.5 bg-white/90 rounded-xl p-3 border border-border/60">
                <span className="text-sm shrink-0 mt-0.5">{r.icon}</span>
                <div>
                  <p className="font-label text-xs font-bold text-on-surface">{r.title}</p>
                  <p className="font-body text-[11px] text-on-surface-muted leading-relaxed mt-0.5">{r.text}</p>
                </div>
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
  quality_red: "Number flagged Red — automatic failover triggered",
  failover: "Standby promoted to primary sender",
  migration_sent: "Channel migration notice sent to recent leads",
  appeal_filed: "Meta policy appeal filed",
  standby_promoted: "Standby number promoted to primary line",
  warm_up_complete: "Number warm-up completed — now fully active",
  quality_snapshot: "Quality rating & tier synced from Meta",
  whatsapp_alert_failed: "Admin WhatsApp alert failed to send",
};

const TYPE_BADGE: Record<string, string> = {
  quality_yellow: "bg-amber-50 text-amber-700 border-amber-200",
  quality_red: "bg-red-50 text-red-700 border-red-200",
  failover: "bg-blue-50 text-blue-700 border-blue-200",
  migration_sent: "bg-purple-50 text-purple-700 border-purple-200",
  appeal_filed: "bg-orange-50 text-orange-700 border-orange-200",
  standby_promoted: "bg-blue-50 text-blue-700 border-blue-200",
  warm_up_complete: "bg-green-50 text-green-700 border-green-200",
  quality_snapshot: "bg-emerald-50 text-emerald-700 border-emerald-200",
  whatsapp_alert_failed: "bg-red-50 text-red-700 border-red-200",
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
        className="flex items-center gap-1 font-label text-xs text-primary hover:text-primary-dark transition-colors font-semibold"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {open ? "Hide details" : "View payload details"}
      </button>
      {open && (
        <div className="mt-2 p-3.5 rounded-xl bg-surface-low border border-border/80 font-mono text-xs text-on-surface overflow-x-auto">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-2 pb-2 border-b border-border/60">
            {Object.entries(detail).map(([k, v]) => (
              <div key={k} className="flex flex-col">
                <span className="text-[10px] text-on-surface-muted uppercase font-bold">{k}</span>
                <span className="font-semibold text-on-surface truncate">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
              </div>
            ))}
          </div>
          <pre className="text-[11px] text-on-surface-muted">{JSON.stringify(detail, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

const QUALITY_DOT: Record<string, string> = {
  green: "bg-emerald-500",
  yellow: "bg-amber-500",
  red: "bg-red-500",
};

function IncidentRow({ incident }: { incident: Incident }) {
  const badgeClass = TYPE_BADGE[incident.type] ?? "bg-surface-mid text-on-surface-muted border-border";
  const label = TYPE_LABELS[incident.type] ?? incident.type.replace(/_/g, " ");
  const isSnapshot = incident.type === "quality_snapshot";
  const snapQuality = isSnapshot ? (incident.detail.quality_rating as string) : null;

  return (
    <div className="flex gap-4 py-4 border-b border-border/60 last:border-0 hover:bg-surface-low/50 px-3 rounded-xl transition-colors">
      <div className="flex flex-col items-center gap-1 pt-1">
        <div className="w-8 h-8 rounded-xl bg-purple-50 text-primary border border-purple-100 flex items-center justify-center shrink-0">
          {incident.type.includes("quality") ? (
            <ShieldCheck size={16} />
          ) : incident.type.includes("failover") || incident.type.includes("promoted") ? (
            <ArrowRightLeft size={16} />
          ) : (
            <Activity size={16} />
          )}
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <span className="font-label text-xs font-semibold text-on-surface-muted whitespace-nowrap">
            {formatTimestamp(incident.created_at)}
          </span>
          <span className={`px-2.5 py-0.5 rounded-full font-label text-[11px] font-bold border ${badgeClass}`}>
            {incident.type.replace(/_/g, " ")}
          </span>
          {isSnapshot && snapQuality && (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface-low border border-border text-xs font-medium">
              <span className={`w-2 h-2 rounded-full ${QUALITY_DOT[snapQuality] ?? "bg-surface-mid"}`} />
              <span className="font-label text-[11px] text-on-surface capitalize font-semibold">{snapQuality} Quality</span>
              {incident.detail.messaging_tier != null && (
                <span className="font-label text-[11px] text-on-surface-muted">
                  · {Number(incident.detail.messaging_tier).toLocaleString()} /day
                </span>
              )}
            </span>
          )}
        </div>
        <p className="font-body text-sm font-medium text-on-surface">{label}</p>
        {!isSnapshot && <DetailExpander detail={incident.detail} />}
      </div>
    </div>
  );
}

// ── API helpers ─────────────────────────────────────────────────────────────

const numbersApi = {
  list: () =>
    apiFetch<{ data: PhoneNumber[]; numbers_pool?: { limit: number; used: number } }>("/api/v1/numbers"),
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
  syncFromMeta: () =>
    apiFetch<{ data: PhoneNumber[]; numbers_pool?: { limit: number; used: number }; synced: number; failed: number }>(
      "/api/v1/numbers/sync-from-meta",
      { method: "POST" }
    ),
};

// ── Main Page Content ───────────────────────────────────────────────────────

function NumbersPageContent() {
  const { role, permissions, loading: roleLoading } = useAuthRole();
  const canViewNumbers = role === "owner" || permissions.includes("numbers.view") || permissions.includes("numbers.manage");
  const canManageNumbers = role === "owner" || permissions.includes("numbers.manage");
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const activeTab = (rawTab === "activity" ? "activity" : "pool") as "pool" | "activity";

  const [numbers, setNumbers] = useState<PhoneNumber[]>([]);
  const [numbersPool, setNumbersPool] = useState<{ limit: number; used: number } | null>(null);
  const [loading, setLoading] = useState(true);

  // Search and filter state
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | "primary" | "standby" | "paused">("all");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Tier guide banner state (auto-dismisses after 15s)
  const [showTierGuide, setShowTierGuide] = useState(true);
  const [tierGuideOpen, setTierGuideOpen] = useState(false);

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

  const handleTabChange = (val: "pool" | "activity") => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", val);
    router.replace(`/dashboard/numbers?${params.toString()}`, { scroll: false });
  };

  async function reload() {
    const res = await numbersApi.list();
    setNumbers(res.data ?? []);
    setNumbersPool(res.numbers_pool ?? null);
  }

  useEffect(() => {
    setLoading(true);
    numbersApi.list().then((res) => {
      setNumbers(res.data ?? []);
      setNumbersPool(res.numbers_pool ?? null);
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

  const handleCopyNumber = (id: string, phone: string) => {
    navigator.clipboard.writeText(phone);
    setCopiedId(id);
    toast.success("Phone number copied to clipboard");
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Derived metrics
  const activeCount = numbers.filter((n) => n.status === "active").length;
  const visible = useMemo(() => numbers.filter((n) => n.status !== "archived"), [numbers]);

  const totalPoolLimit = numbersPool?.limit ?? 5;
  const totalPoolUsed = numbersPool?.used ?? visible.length;
  const primaryNumber = visible.find((n) => n.role === "primary");
  const standbyCount = visible.filter((n) => n.role === "standby").length;
  const pausedCount = visible.filter((n) => n.paused_outbound).length;
  const totalDailySends = visible.reduce((acc, n) => acc + (n.daily_send_count || 0), 0);
  const totalDailyCapacity = visible.reduce((acc, n) => acc + (n.messaging_tier || 0), 0);
  const totalSendPct = totalDailyCapacity > 0 ? Math.min((totalDailySends / totalDailyCapacity) * 100, 100) : 0;

  // Portfolio overall quality
  const overallQuality: PhoneNumber["quality_rating"] = visible.some((n) => n.quality_rating === "red")
    ? "red"
    : visible.some((n) => n.quality_rating === "yellow")
    ? "yellow"
    : "green";

  // Filtered numbers
  const filteredNumbers = useMemo(() => {
    return visible.filter((num) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchName = num.display_name.toLowerCase().includes(q);
        const matchPhone = num.number.toLowerCase().includes(q);
        if (!matchName && !matchPhone) return false;
      }
      if (roleFilter === "primary") return num.role === "primary";
      if (roleFilter === "standby") return num.role === "standby";
      if (roleFilter === "paused") return num.paused_outbound;
      return true;
    });
  }, [visible, searchQuery, roleFilter]);

  if (roleLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (!canViewNumbers) {
    return (
      <div className="text-center py-20">
        <p className="text-on-surface-muted font-body">
          You do not have access to the numbers pool.
        </p>
      </div>
    );
  }

  function startRename(num: PhoneNumber) {
    if (!canManageNumbers) return;
    setEditingId(num.id);
    setEditName(num.display_name);
  }

  async function saveRename(id: string) {
    if (!canManageNumbers) return;
    if (!editName.trim()) return;
    setSaving(true);
    try {
      await numbersApi.update(id, { display_name: editName.trim() });
      await reload();
      setEditingId(null);
      toast.success("Number renamed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleSetPrimary(id: string) {
    if (!canManageNumbers) return;
    try {
      await numbersApi.update(id, { role: "primary" });
      await reload();
      toast.success("Set as primary number");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function handleTogglePause(num: PhoneNumber) {
    if (!canManageNumbers) return;
    setPausingId(num.id);
    try {
      await numbersApi.update(num.id, { paused_outbound: !num.paused_outbound });
      await reload();
      toast.success(num.paused_outbound ? "Outbound messaging resumed" : "Outbound messaging paused");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    } finally {
      setPausingId(null);
    }
  }

  async function handleSyncMeta(id: string) {
    if (!canManageNumbers) return;
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
    if (!canManageNumbers) return;
    setSyncingAll(true);
    try {
      const res = await numbersApi.syncFromMeta();
      setNumbers(res.data ?? []);
      setNumbersPool(res.numbers_pool ?? null);
      if (res.failed === 0) {
        toast.success(`Synced ${res.synced} number${res.synced === 1 ? "" : "s"} from Meta`);
      } else if (res.synced > 0) {
        toast.success(`Synced ${res.synced} numbers, ${res.failed} failed`);
      } else {
        toast.error("Failed to sync numbers from Meta");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncingAll(false);
    }
  }

  async function handleDelete(id: string) {
    if (!canManageNumbers) return;
    if (!confirm("Delete this number? It will no longer send or receive messages.")) return;
    try {
      await numbersApi.remove(id);
      await reload();
      toast.success("Number removed from pool");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div>
      {/* Mobile Tab Fallback */}
      <div className="p-1 bg-[#e8e3db]/60 rounded-2xl flex gap-1 self-start w-fit md:hidden mb-4">
        <button
          onClick={() => handleTabChange("pool")}
          className={cn(
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
            activeTab === "pool"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Active Pool
        </button>
        <button
          onClick={() => handleTabChange("activity")}
          className={cn(
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
            activeTab === "activity"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Activity Log
        </button>
      </div>

      <div className="space-y-3.5">
        {activeTab === "pool" ? (
          <>
          {/* ── KPI Overview Grid ───────────────────────────────────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* KPI 1: Pool Utilization */}
            <div className="p-5 rounded-2xl bg-white border border-border/80 shadow-xs hover:shadow-card transition-all flex flex-col justify-between">
              <div className="flex items-start justify-between mb-3">
                <div className="w-10 h-10 rounded-xl bg-purple-50 text-primary flex items-center justify-center shrink-0">
                  <Smartphone size={20} />
                </div>
                <span className="font-label text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-purple-100/70 text-primary">
                  {totalPoolUsed >= totalPoolLimit ? "Quota Full" : `${totalPoolLimit - totalPoolUsed} slots free`}
                </span>
              </div>
              <div>
                <p className="font-display text-2xl font-bold text-on-surface">
                  {totalPoolUsed} <span className="text-sm font-semibold text-on-surface-muted">/ {totalPoolLimit} Used</span>
                </p>
                <p className="font-label text-xs text-on-surface-muted mt-0.5">Active Pool Capacity</p>
              </div>
              <div className="mt-3 pt-3 border-t border-border/60 flex items-center justify-between text-[11px] font-body text-on-surface-muted">
                <span>{visible.length} connected</span>
                {totalPoolUsed >= totalPoolLimit && (
                  <a href="/dashboard/subscriptions" className="font-label text-primary font-bold hover:underline inline-flex items-center gap-0.5">
                    Upgrade <ExternalLink size={10} />
                  </a>
                )}
              </div>
            </div>

            {/* KPI 2: Today's Dispatches */}
            <div className="p-5 rounded-2xl bg-white border border-border/80 shadow-xs hover:shadow-card transition-all flex flex-col justify-between">
              <div className="flex items-start justify-between mb-3">
                <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                  <Activity size={20} />
                </div>
                <span className="font-mono text-xs font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-100">
                  {Math.round(totalSendPct)}% used
                </span>
              </div>
              <div>
                <p className="font-display text-2xl font-bold text-on-surface">
                  {totalDailySends.toLocaleString()} <span className="text-sm font-semibold text-on-surface-muted">/ {totalDailyCapacity.toLocaleString()}</span>
                </p>
                <p className="font-label text-xs text-on-surface-muted mt-0.5">Today&apos;s Dispatches</p>
              </div>
              <div className="mt-3 pt-3 border-t border-border/60">
                <div className="w-full h-1.5 rounded-full bg-surface-mid overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-500",
                      totalSendPct > 85 ? "bg-red-500" : totalSendPct > 50 ? "bg-amber-500" : "bg-emerald-500"
                    )}
                    style={{ width: `${Math.max(totalSendPct, 3)}%` }}
                  />
                </div>
              </div>
            </div>

            {/* KPI 3: Portfolio Health */}
            <div className="p-5 rounded-2xl bg-white border border-border/80 shadow-xs hover:shadow-card transition-all flex flex-col justify-between">
              <div className="flex items-start justify-between mb-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
                  <ShieldCheck size={20} />
                </div>
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full font-label text-[11px] font-bold border ${QUALITY_BG[overallQuality]}`}>
                  <span className={`w-2 h-2 rounded-full animate-pulse ${QUALITY_COLOR[overallQuality]}`} />
                  {QUALITY_LABEL[overallQuality]} Quality
                </span>
              </div>
              <div>
                <p className="font-display text-2xl font-bold text-on-surface">
                  {activeCount} <span className="text-sm font-semibold text-on-surface-muted">Healthy</span>
                </p>
                <p className="font-label text-xs text-on-surface-muted mt-0.5">Portfolio Health Status</p>
              </div>
              <div className="mt-3 pt-3 border-t border-border/60 flex items-center justify-between text-[11px] font-body text-on-surface-muted">
                <span>{pausedCount > 0 ? `${pausedCount} paused line${pausedCount > 1 ? "s" : ""}` : "All lines active"}</span>
                <span className="text-emerald-700 font-semibold">Meta synced</span>
              </div>
            </div>

            {/* KPI 4: Primary Sender */}
            <div className="p-5 rounded-2xl bg-white border border-border/80 shadow-xs hover:shadow-card transition-all flex flex-col justify-between">
              <div className="flex items-start justify-between mb-3">
                <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
                  <Star size={20} className="fill-amber-400 text-amber-500" />
                </div>
                <span className="font-label text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-100/70 text-amber-800">
                  Primary Routing
                </span>
              </div>
              <div>
                <p className="font-display text-lg font-bold text-on-surface truncate">
                  {primaryNumber ? primaryNumber.display_name : "None Set"}
                </p>
                <p className="font-mono text-xs text-on-surface-muted mt-0.5 truncate">
                  {primaryNumber ? primaryNumber.number : "No primary selected"}
                </p>
              </div>
              <div className="mt-3 pt-3 border-t border-border/60 flex items-center justify-between text-[11px] font-body text-on-surface-muted">
                <span>{standbyCount} standby failover{standbyCount === 1 ? "" : "s"}</span>
                <span className="text-primary font-semibold">Broadcasting</span>
              </div>
            </div>
          </div>

          {/* ── Messaging Tier Guide Banner ──────────────────────────────────── */}
          {showTierGuide && (
            <TierGuide
              visible={showTierGuide}
              onDismiss={() => setShowTierGuide(false)}
              isOpen={tierGuideOpen}
              onToggleOpen={() => setTierGuideOpen((v) => !v)}
            />
          )}

          {/* ── Main Numbers Card ───────────────────────────────────────────── */}
          <div className="rounded-2xl bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 md:rounded-card md:p-8 space-y-6">
            {/* Control Bar: Title + Search + Filters + Sync */}
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between pb-2 border-b border-border/70">
              <div className="flex items-center gap-3">
                <h2 className="font-display text-xl font-bold text-on-surface">Sender Numbers</h2>
                <span className="font-label text-xs font-bold text-primary bg-primary/10 px-2.5 py-0.5 rounded-full">
                  {visible.length} total
                </span>
                {!showTierGuide && (
                  <button
                    onClick={() => {
                      setShowTierGuide(true);
                      setTierGuideOpen(true);
                    }}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-label font-bold text-primary bg-purple-50 hover:bg-purple-100 border border-purple-200/80 transition-colors"
                    title="Re-open WhatsApp messaging limits and tier guide"
                  >
                    <Info size={12} />
                    <span>Limits Guide</span>
                  </button>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                {/* Search Box */}
                <div className="relative min-w-[220px]">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-muted" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search name or number…"
                    className="w-full pl-9 pr-8 py-2 bg-surface-low border border-border/80 rounded-xl font-body text-xs text-on-surface placeholder:text-on-surface-muted/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-all"
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery("")}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-on-surface-muted hover:text-on-surface text-xs"
                    >
                      <X size={13} />
                    </button>
                  )}
                </div>

                {/* Filter Pills */}
                <div className="flex items-center gap-1 p-1 bg-surface-low rounded-xl border border-border/70">
                  {[
                    { key: "all", label: "All" },
                    { key: "primary", label: "Primary" },
                    { key: "standby", label: "Standby" },
                    { key: "paused", label: "Paused" },
                  ].map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => setRoleFilter(tab.key as typeof roleFilter)}
                      className={cn(
                        "px-3 py-1 rounded-lg font-label text-xs font-bold transition-colors",
                        roleFilter === tab.key
                          ? "bg-white text-primary shadow-2xs"
                          : "text-on-surface-muted hover:text-on-surface"
                      )}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                {/* Sync from Meta CTA */}
                {canManageNumbers && (
                  <button
                    onClick={handleSyncAllMeta}
                    disabled={syncingAll}
                    className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-[#2e1065] via-[#5b21b6] to-[#7c3aed] text-white hover:opacity-95 rounded-xl font-label text-xs font-bold shadow-sm transition-all disabled:opacity-50"
                    title="Discover and sync all numbers from your connected Meta WhatsApp Business account"
                  >
                    <RefreshCw size={13} className={syncingAll ? "animate-spin" : ""} />
                    <span>{syncingAll ? "Syncing Meta…" : "Sync from Meta"}</span>
                  </button>
                )}
              </div>
            </div>

            {/* List / Cards */}
            {loading ? (
              <div className="py-16 text-center space-y-3">
                <Loader2 size={24} className="animate-spin text-primary mx-auto" />
                <p className="font-body text-sm text-on-surface-muted">Loading sender numbers from Meta Cloud…</p>
              </div>
            ) : visible.length === 0 ? (
              <div className="py-16 text-center max-w-md mx-auto space-y-4">
                <div className="w-14 h-14 rounded-2xl bg-purple-50 text-primary border border-purple-100 flex items-center justify-center mx-auto">
                  <Phone size={26} />
                </div>
                <div>
                  <h3 className="font-display text-lg font-bold text-on-surface">No sender numbers configured</h3>
                  <p className="font-body text-xs text-on-surface-muted mt-1 leading-relaxed">
                    Connect your WhatsApp Business Account in Settings, then click &quot;Sync from Meta&quot; to import your registered sender numbers.
                  </p>
                </div>
                {canManageNumbers && (
                  <button
                    onClick={handleSyncAllMeta}
                    disabled={syncingAll}
                    className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary text-white hover:bg-primary/90 rounded-xl font-label text-xs font-bold transition-all shadow-sm"
                  >
                    <RefreshCw size={13} className={syncingAll ? "animate-spin" : ""} />
                    {syncingAll ? "Syncing…" : "Sync numbers from Meta"}
                  </button>
                )}
              </div>
            ) : filteredNumbers.length === 0 ? (
              <div className="py-12 text-center">
                <p className="font-body text-sm text-on-surface-muted">
                  No numbers match your search &quot;{searchQuery}&quot; or filter.
                </p>
                <button
                  onClick={() => { setSearchQuery(""); setRoleFilter("all"); }}
                  className="mt-2 font-label text-xs text-primary font-bold hover:underline"
                >
                  Clear search & filters
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {filteredNumbers.map((num) => {
                  const isEditing = editingId === num.id;
                  const isSyncing = syncingId === num.id;
                  const isPausing = pausingId === num.id;
                  const sendPct = num.messaging_tier > 0
                    ? Math.min((num.daily_send_count / num.messaging_tier) * 100, 100)
                    : 0;

                  return (
                    <div
                      key={num.id}
                      className={cn(
                        "rounded-2xl border bg-white p-5 transition-all shadow-xs hover:shadow-card",
                        num.locked ? "border-amber-300 bg-amber-50/20" : "border-border/80"
                      )}
                    >
                      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
                        {/* Left: Phone Avatar + Details + Badges */}
                        <div className="flex items-start gap-4 min-w-0">
                          {/* WhatsApp Phone Icon */}
                          <div className={cn(
                            "w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 shadow-xs",
                            num.role === "primary"
                              ? "bg-gradient-to-br from-purple-600 to-[#2e1065] text-white ring-2 ring-primary/20"
                              : "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20"
                          )}>
                            <Phone size={22} />
                          </div>

                          <div className="min-w-0 flex-1 space-y-1.5">
                            {/* Line 1: Name + Editable */}
                            <div className="flex flex-wrap items-center gap-2">
                              {isEditing ? (
                                <div className="flex items-center gap-2">
                                  <input
                                    ref={editInputRef}
                                    type="text"
                                    value={editName}
                                    onChange={(e) => setEditName(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") saveRename(num.id);
                                      if (e.key === "Escape") setEditingId(null);
                                    }}
                                    className="px-3 py-1 bg-surface-low rounded-lg border border-primary font-display text-sm font-bold text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 min-w-0 w-52"
                                  />
                                  <button
                                    onClick={() => saveRename(num.id)}
                                    disabled={saving}
                                    className="p-1.5 rounded-lg bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
                                    title="Save name"
                                  >
                                    <Check size={13} />
                                  </button>
                                  <button
                                    onClick={() => setEditingId(null)}
                                    className="p-1.5 rounded-lg bg-surface-low hover:bg-surface-mid text-on-surface-muted transition-colors"
                                    title="Cancel"
                                  >
                                    <X size={13} />
                                  </button>
                                </div>
                              ) : (
                                <div className="flex items-center gap-2 group min-w-0">
                                  <h3 className="font-display text-base font-bold text-on-surface truncate">
                                    {num.display_name}
                                  </h3>
                                  {canManageNumbers && (
                                    <button
                                      onClick={() => startRename(num)}
                                      className="p-1 rounded-md text-on-surface-muted/40 group-hover:text-primary hover:bg-surface-low transition-colors"
                                      title="Rename display name"
                                    >
                                      <Pencil size={12} />
                                    </button>
                                  )}
                                </div>
                              )}

                              {/* Role Badge */}
                              {num.role === "primary" ? (
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full font-label text-[11px] font-bold bg-gradient-to-r from-purple-100 via-purple-50 to-indigo-100 text-[#5b21b6] border border-purple-200/80 shadow-2xs">
                                  <Star size={11} className="fill-[#5b21b6] text-[#5b21b6]" />
                                  Primary Sender
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-label text-[11px] font-semibold bg-surface-mid/80 text-on-surface-muted border border-border">
                                  Standby Failover
                                </span>
                              )}

                              {/* Quality Rating */}
                              <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full font-label text-[11px] font-bold border ${QUALITY_BG[num.quality_rating]}`}>
                                <span className={`w-2 h-2 rounded-full ${QUALITY_COLOR[num.quality_rating]}`} />
                                {QUALITY_LABEL[num.quality_rating]} Quality
                              </span>

                              {/* Paused Badge */}
                              {num.paused_outbound ? (
                                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-label text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                                  <PauseCircle size={11} />
                                  Paused Outbound
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-label text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80">
                                  <CheckCircle2 size={11} />
                                  Active
                                </span>
                              )}
                            </div>

                            {/* Line 2: Phone number with copy button + Provider info */}
                            <div className="flex flex-wrap items-center gap-3 text-xs text-on-surface-muted">
                              <div className="flex items-center gap-1.5">
                                <span className="font-mono font-bold text-on-surface">{num.number}</span>
                                <button
                                  onClick={() => handleCopyNumber(num.id, num.number)}
                                  className="p-1 rounded hover:bg-surface-low text-on-surface-muted hover:text-on-surface transition-colors"
                                  title="Copy phone number"
                                >
                                  {copiedId === num.id ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                                </button>
                              </div>

                              <span className="text-border">•</span>

                              <span className="font-label text-[11px] text-on-surface-muted">
                                {getTierLabel(num.messaging_tier)}
                              </span>

                              {num.meta_phone_number_id && (
                                <>
                                  <span className="text-border">•</span>
                                  <span className="font-mono text-[10px] text-on-surface-muted/80 bg-surface-low px-1.5 py-0.5 rounded border border-border/60">
                                    ID: {num.meta_phone_number_id}
                                  </span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Center/Right: Capacity Meter + Action Toolbar */}
                        <div className="flex flex-col sm:flex-row sm:items-center gap-5 shrink-0 pt-3 lg:pt-0 border-t lg:border-t-0 border-border/60">
                          {/* Send Meter */}
                          <div className="min-w-[170px] space-y-1.5">
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-label text-[11px] font-bold text-on-surface-muted">Daily Limit</span>
                              <span className="font-mono font-bold text-on-surface text-[11px]">
                                {num.daily_send_count.toLocaleString()} / {num.messaging_tier.toLocaleString()}
                              </span>
                            </div>
                            <div className="w-full h-2 rounded-full bg-surface-mid overflow-hidden">
                              <div
                                className={cn(
                                  "h-full rounded-full transition-all duration-500",
                                  sendPct > 80 ? "bg-red-500" : sendPct > 50 ? "bg-amber-500" : "bg-emerald-500"
                                )}
                                style={{ width: `${Math.max(sendPct, 2)}%` }}
                              />
                            </div>
                            <div className="flex items-center justify-between text-[10px] text-on-surface-muted font-label">
                              <span>{Math.round(sendPct)}% sent</span>
                              <span>{num.messaging_tier - num.daily_send_count > 0 ? `${(num.messaging_tier - num.daily_send_count).toLocaleString()} left` : "Limit reached"}</span>
                            </div>
                          </div>

                          {/* Action Buttons */}
                          <div className="flex items-center gap-2">
                            {/* Set as Primary button */}
                            {canManageNumbers && num.role !== "primary" && num.role !== "archived" && (
                              <button
                                onClick={() => handleSetPrimary(num.id)}
                                className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-purple-200 bg-purple-50/70 hover:bg-purple-100 text-[#5b21b6] font-label text-xs font-bold transition-all shadow-2xs"
                                title="Set this line as the active primary sender"
                              >
                                <Star size={12} className="fill-purple-600/30" />
                                <span>Set Primary</span>
                              </button>
                            )}

                            {/* Pause / Resume */}
                            {canManageNumbers && (
                              <button
                                onClick={() => handleTogglePause(num)}
                                disabled={isPausing || (num.locked && num.paused_outbound)}
                                title={
                                  num.locked && num.paused_outbound
                                    ? "Locked by quota — upgrade to resume"
                                    : num.paused_outbound ? "Resume outbound broadcasts" : "Pause outbound broadcasts"
                                }
                                className={cn(
                                  "flex items-center gap-1.5 px-3 py-2 rounded-xl font-label text-xs font-bold transition-all border shadow-2xs disabled:opacity-50",
                                  num.paused_outbound
                                    ? "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                                    : "border-amber-200 bg-amber-50/80 text-amber-800 hover:bg-amber-100"
                                )}
                              >
                                {num.paused_outbound ? (
                                  <>
                                    <PlayCircle size={13} />
                                    <span>Resume</span>
                                  </>
                                ) : (
                                  <>
                                    <PauseCircle size={13} />
                                    <span>Pause</span>
                                  </>
                                )}
                              </button>
                            )}

                            {/* Sync Meta */}
                            {canManageNumbers && (
                              <button
                                onClick={() => handleSyncMeta(num.id)}
                                disabled={isSyncing}
                                className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-border bg-white hover:bg-surface-low text-on-surface font-label text-xs font-semibold transition-all shadow-2xs disabled:opacity-50"
                                title="Pull latest quality rating and tier from Meta"
                              >
                                <RefreshCw size={12} className={isSyncing ? "animate-spin text-primary" : "text-on-surface-muted"} />
                                <span className="hidden sm:inline">Sync</span>
                              </button>
                            )}

                            {/* Delete */}
                            {canManageNumbers && (
                              <button
                                onClick={() => handleDelete(num.id)}
                                disabled={activeCount === 1 && num.status === "active"}
                                title={activeCount === 1 && num.status === "active" ? "Cannot delete the only active number" : "Remove number from pool"}
                                className="p-2 rounded-xl border border-border/80 bg-white hover:border-red-200 hover:bg-red-50 text-on-surface-muted hover:text-red-600 transition-colors disabled:opacity-30 disabled:cursor-not-allowed shadow-2xs"
                              >
                                <Trash2 size={13} />
                              </button>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Locked Over-Quota Notice */}
                      {num.locked && (
                        <div className="mt-4 pt-3.5 border-t border-amber-200/80 flex flex-wrap items-center justify-between gap-3 bg-amber-50/80 -mx-5 -mb-5 px-5 py-3 rounded-b-2xl">
                          <div className="flex items-center gap-2 font-body text-xs text-amber-900">
                            <Lock size={13} className="text-amber-700 shrink-0" />
                            <span>This number exceeds your current pool quota. Set it as primary to activate it, or upgrade your plan for additional slots.</span>
                          </div>
                          <a
                            href="/dashboard/subscriptions"
                            className="inline-flex items-center gap-1 px-3 py-1.5 bg-primary text-white rounded-lg font-label text-xs font-bold hover:bg-primary/90 transition-colors shadow-2xs"
                          >
                            Upgrade Quota <ArrowRightLeft size={11} />
                          </a>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      ) : (
        /* ── Activity Log Tab ──────────────────────────────────────────────── */
        <div className="bg-surface rounded-card p-6 md:p-8 shadow-card ring-1 ring-[#c4c7c7]/15 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-border/70">
            <div>
              <h2 className="font-display text-xl font-bold text-on-surface">Pool Activity & Incidents</h2>
              <p className="font-body text-xs text-on-surface-muted mt-0.5">
                Audit trail of Meta quality adjustments, standby failovers, and tier changes.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 font-label text-xs font-semibold border border-emerald-200/70">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                Live: Polling every 30s
              </span>

              {canManageNumbers && (
                <button
                  onClick={async () => {
                    await handleSyncAllMeta();
                    setIncidentsLoading(true);
                    await fetchIncidents(0, false);
                    setIncidentOffset(0);
                    setIncidentsLoading(false);
                  }}
                  disabled={syncingAll}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-border text-on-surface hover:text-primary hover:border-primary/40 rounded-xl font-label text-xs font-bold transition-all shadow-2xs disabled:opacity-50"
                  title="Discover and sync every number on your connected Meta WhatsApp account"
                >
                  <RefreshCw size={12} className={syncingAll ? "animate-spin" : ""} />
                  {syncingAll ? "Syncing…" : "Sync from Meta"}
                </button>
              )}
            </div>
          </div>

          {incidentsLoading ? (
            <div className="py-16 text-center space-y-3">
              <Loader2 size={24} className="animate-spin text-primary mx-auto" />
              <p className="font-body text-sm text-on-surface-muted">Loading activity log…</p>
            </div>
          ) : incidents.length === 0 ? (
            <div className="py-20 text-center max-w-sm mx-auto space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 text-emerald-600 border border-emerald-100 flex items-center justify-center mx-auto">
                <ShieldCheck size={24} />
              </div>
              <h3 className="font-display text-base font-bold text-on-surface">No incidents recorded</h3>
              <p className="font-body text-xs text-on-surface-muted leading-relaxed">
                All numbers are operating normally with stable Meta quality ratings.
              </p>
            </div>
          ) : (
            <div>
              <div className="divide-y divide-border/60">
                {incidents.map((incident) => (
                  <IncidentRow key={incident.id} incident={incident} />
                ))}
              </div>

              {hasMoreIncidents && (
                <div className="pt-6 text-center">
                  <button
                    onClick={handleLoadMoreIncidents}
                    disabled={loadingMoreIncidents}
                    className="px-5 py-2.5 bg-surface-low border border-border hover:border-border-subtle rounded-xl font-label text-xs font-bold text-on-surface hover:bg-surface-mid transition-all shadow-2xs disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loadingMoreIncidents ? "Loading more incidents…" : "Load older events"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  );
}

export default function NumbersPage() {
  return (
    <Suspense fallback={
      <div className="space-y-3.5">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 bg-surface-mid/60 rounded-2xl"></div>
          ))}
        </div>
        <div className="h-48 bg-surface-mid/60 rounded-2xl animate-pulse"></div>
        <div className="h-64 bg-surface-mid/60 rounded-2xl animate-pulse"></div>
      </div>
    }>
      <NumbersPageContent />
    </Suspense>
  );
}
