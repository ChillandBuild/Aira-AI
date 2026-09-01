import { useState, useRef, useEffect, useMemo } from "react";
import { api, Lead } from "@/lib/api";
import { SegmentBadge } from "./segment-badge";
import { ChannelAvatar, getChannel } from "./channel-avatar";
import { formatConvoTime, formatPhone, cn } from "@/lib/utils";
import { MessageCircle, Trash2, MoreVertical, MoreHorizontal, Search, X, SearchX, ChevronLeft, Pin, Filter, RefreshCw, Archive, Ban, Check, CheckCheck, Inbox } from "lucide-react";
import { toast } from "sonner";
import { CheckTick } from "@/components/ui/controls";

type ConversationLead = Lead & { last_reply_at?: string };

function IgIcon({ size = 12, className = "" }: { size?: number | string; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  );
}

function TgIcon({ size = 12, className = "" }: { size?: number | string; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function FbIcon({ size = 12, className = "" }: { size?: number | string; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
    </svg>
  );
}

type PlatformFilter = "whatsapp" | "instagram" | "facebook" | "telegram" | "all";

interface PlatformIconProps {
  size?: number | string;
  className?: string;
}

const PLATFORMS: { value: PlatformFilter; label: string; short: string; icon: React.FC<PlatformIconProps> }[] = [
  { value: "all", label: "All channels", short: "All", icon: Inbox },
  { value: "whatsapp", label: "WhatsApp", short: "WA", icon: MessageCircle },
  { value: "instagram", label: "Instagram", short: "IG", icon: IgIcon },
  { value: "facebook", label: "Facebook", short: "FB", icon: FbIcon },
  { value: "telegram", label: "Telegram", short: "TG", icon: TgIcon },
];

const SEGMENTS = [
  { label: "Hot", value: "A", bg: "bg-segment-a-bg", text: "text-segment-a-text", border: "border-segment-a-border" },
  { label: "Warm", value: "B", bg: "bg-segment-b-bg", text: "text-segment-b-text", border: "border-segment-b-border" },
  { label: "Cold", value: "C", bg: "bg-segment-c-bg", text: "text-segment-c-text", border: "border-segment-c-border" },
  { label: "DQ", value: "D", bg: "bg-segment-d-bg", text: "text-segment-d-text", border: "border-segment-d-border" },
] as const;

interface Props {
  leads: Lead[];
  selectedId: string | null;
  onSelect: (lead: Lead) => void;
  onDeleted?: (ids: string[]) => void;
  platform: string;
  onPlatformChange: (platform: string) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onCollapse?: () => void;
  onPin?: (id: string) => void;
  onPinSelected?: (ids: string[]) => void;
  onRefresh?: () => void;
  onArchive?: (id: string) => void;
  canArchive?: boolean;
  onBlock?: (id: string) => void;
  folder?: "chats" | "archived" | "blocked";
  hasMore?: boolean;
  loadingMore?: boolean;
  onLoadMore?: () => void;
}

export function ConversationList({ leads, selectedId, onSelect, onDeleted, platform, onPlatformChange, searchQuery, onSearchChange, onCollapse, onPin, onPinSelected, onRefresh, onArchive, canArchive = false, onBlock, folder = "chats", hasMore = false, loadingMore = false, onLoadMore }: Props) {
  const [segment, setSegment] = useState<"A" | "B" | "C" | "D" | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [cardMenuId, setCardMenuId] = useState<string | null>(null);

  const menuRef = useRef<HTMLDivElement>(null);
  const filterRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
      // The toggle button lives inside filterRef, so its own click is never
      // treated as "outside" — it keeps toggling instead of double-firing.
      if (filterRef.current && !filterRef.current.contains(event.target as Node)) {
        setFiltersOpen(false);
      }
      if (!(event.target as HTMLElement).closest?.("[data-card-menu]")) {
        setCardMenuId(null);
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setFiltersOpen(false);
        setMenuOpen(false);
        setCardMenuId(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  function accountLabel(lead: Lead): string {
    return (lead.tag_name || lead.ad_campaign_name || lead.source || "whatsapp").toUpperCase();
  }

  async function handleDeleteOne(id: string) {
    setCardMenuId(null);
    try {
      await api.leads.delete(id);
      onDeleted?.([id]);
    } catch {
      toast.error("Failed to delete chat");
    }
  }

  const getLeadPlatform = (lead: Lead) => getChannel(lead.source);

  const visible = useMemo(() => {
    const q = searchQuery.toLowerCase();
    const base = platform === "all" ? leads : leads.filter((l) => getLeadPlatform(l) === platform);
    return (segment ? base.filter((l) => l.segment === segment) : base)
      .filter((l) => {
        if (!q) return true;
        const name = l.name?.toLowerCase() || "";
        const phone = l.phone?.toLowerCase() || "";
        if (name.includes(q) || phone.includes(q)) return true;
        // Phone numbers render space-formatted (formatPhone) but are stored
        // digits-only — fall back to a digits-only comparison so a search
        // copied from the UI still matches the raw stored value.
        const qDigits = q.replace(/\D/g, "");
        return qDigits.length > 0 && phone.replace(/\D/g, "").includes(qDigits);
      })
      .sort((a, b) => {
        const aPinned = a.pinned_at ? 1 : 0;
        const bPinned = b.pinned_at ? 1 : 0;
        if (aPinned !== bPinned) return bPinned - aPinned;
        if (aPinned && bPinned) {
          return new Date(b.pinned_at!).getTime() - new Date(a.pinned_at!).getTime();
        }
        if (a.needs_human_intervention && !b.needs_human_intervention) return -1;
        if (!a.needs_human_intervention && b.needs_human_intervention) return 1;
        const aTime = (a as ConversationLead).last_reply_at || a.created_at;
        const bTime = (b as ConversationLead).last_reply_at || b.created_at;
        return new Date(bTime).getTime() - new Date(aTime).getTime();
      });
  }, [leads, platform, segment, searchQuery]);

  const activeFilterCount = (platform !== "all" ? 1 : 0) + (segment ? 1 : 0);

  const platformCounts = useMemo(() => {
    const counts: Record<string, number> = { whatsapp: 0, instagram: 0, facebook: 0, telegram: 0, all: leads.length };
    for (const l of leads) {
      const plat = getLeadPlatform(l);
      if (plat in counts) counts[plat]++;
    }
    return counts;
  }, [leads]);

  async function handleDeleteSelected() {
    if (!confirm(`Delete ${selectedIds.size} conversations?`)) return;
    setIsDeleting(true);
    try {
      await Promise.all(Array.from(selectedIds).map((id) => api.leads.delete(id)));
      onDeleted?.(Array.from(selectedIds));
      setSelectedIds(new Set());
      setSelectionMode(false);
      toast.success("Conversations deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete some conversations");
    } finally {
      setIsDeleting(false);
    }
  }

  function toggleSelect(id: string, e?: React.MouseEvent) {
    e?.stopPropagation();
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  }

  function cancelSelection() {
    setSelectionMode(false);
    setSelectedIds(new Set());
  }

  function handleRefresh() {
    if (!onRefresh || isRefreshing) return;
    setIsRefreshing(true);
    onRefresh();
    setTimeout(() => setIsRefreshing(false), 900);
  }

  function getPlatformColor(source: string): string {
    switch (source) {
      case "whatsapp": return "text-green-500";
      case "instagram": return "text-pink-500";
      case "facebook": return "text-blue-600";
      case "telegram": return "text-sky-500";
      case "all": return "text-primary";
      default: return "text-green-500";
    }
  }

  function getPlatformBg(selected: boolean, source: string): string {
    if (!selected) return "bg-surface-low text-on-surface-muted hover:bg-surface-mid hover:text-on-surface";
    switch (source) {
      case "whatsapp": return "bg-green-500 text-white shadow-sm";
      case "instagram": return "bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-sm";
      case "facebook": return "bg-blue-600 text-white shadow-sm";
      case "telegram": return "bg-sky-500 text-white shadow-sm";
      case "all": return "bg-primary text-white shadow-sm";
      default: return "bg-primary text-white shadow-sm";
    }
  }

  return (
    <div className="w-full flex-shrink-0 bg-surface border-r border-surface-mid flex flex-col h-full shadow-[2px_0_10px_rgba(0,0,0,0.02)] z-10 relative">
      <div className="px-4 py-3 border-b border-surface-mid bg-surface relative z-10">
        {selectionMode ? (
          /* ── Selection mode bar ── */
          <div className="flex items-center justify-between py-1">
            <span className="font-display text-sm font-semibold text-primary">{selectedIds.size} selected</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSelectedIds(selectedIds.size === visible.length && visible.length > 0 ? new Set() : new Set(visible.map(l => l.id)))}
                className="text-[11px] font-semibold text-primary hover:text-primary/80 transition-colors"
              >
                {selectedIds.size === visible.length && visible.length > 0 ? "Deselect All" : "Select All"}
              </button>
              <button onClick={cancelSelection} className="text-[11px] font-semibold text-on-surface-muted hover:text-on-surface transition-colors ml-1">
                Cancel
              </button>
              {selectedIds.size > 0 && onPinSelected && (
                <button onClick={() => onPinSelected(Array.from(selectedIds))} className="flex items-center gap-1.5 text-amber-600 bg-amber-50 hover:bg-amber-100 text-[11px] font-semibold ml-2 px-2 py-1 rounded-md transition-colors">
                  <Pin size={12} /> Pin
                </button>
              )}
              {selectedIds.size > 0 && (
                <button onClick={handleDeleteSelected} disabled={isDeleting} className="flex items-center gap-1.5 text-red-600 bg-red-50 hover:bg-red-100 disabled:opacity-50 text-[11px] font-semibold ml-2 px-2 py-1 rounded-md transition-colors">
                  <Trash2 size={12} /> {isDeleting ? "..." : "Delete"}
                </button>
              )}
            </div>
          </div>
        ) : (
          <>
            {/* ── Title row ── */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-1.5">
                <h2 className="font-display text-base font-bold text-on-surface tracking-tight capitalize">
                  {folder === "chats" ? "Shared Inbox" : folder}
                </h2>
                {onCollapse && (
                  <button onClick={onCollapse} className="p-1 rounded-md hover:bg-surface-low text-on-surface-muted hover:text-on-surface transition-colors">
                    <ChevronLeft size={15} />
                  </button>
                )}
              </div>
              <div className="relative" ref={menuRef}>
                <button onClick={() => setMenuOpen(!menuOpen)} className="p-1.5 rounded-md hover:bg-surface-low text-on-surface-muted hover:text-on-surface transition-colors">
                  <MoreVertical size={15} />
                </button>
                {menuOpen && (
                  <div className="absolute right-0 top-full mt-1 w-36 bg-surface border border-surface-mid rounded-xl shadow-xl overflow-hidden z-20 py-1.5">
                    <button onClick={() => { setSelectionMode(true); setMenuOpen(false); }} className="w-full text-left px-4 py-2 text-[13px] font-medium text-on-surface hover:bg-surface-low transition-colors">
                      Select chats
                    </button>
                    <button onClick={() => { setSelectionMode(true); setSelectedIds(new Set(visible.map(l => l.id))); setMenuOpen(false); }} className="w-full text-left px-4 py-2 text-[13px] font-medium text-on-surface hover:bg-surface-low transition-colors">
                      Select all
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* ── Search + Filter + Refresh row ── */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1 group">
                <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-muted group-focus-within:text-primary transition-colors" />
                <input
                  type="text"
                  placeholder="Type and submit to search"
                  value={searchQuery}
                  onChange={(e) => onSearchChange(e.target.value)}
                  className="w-full pl-8 pr-7 py-2 bg-surface-low border border-surface-mid rounded-xl text-[13px] text-on-surface placeholder:text-on-surface-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                />
                {searchQuery && (
                  <button onClick={() => onSearchChange("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-on-surface-muted hover:text-on-surface p-0.5 rounded-full hover:bg-surface-mid transition-colors">
                    <X size={11} />
                  </button>
                )}
              </div>
              {/* ── Filters: anchored popover, floats over the list ── */}
              <div className="relative shrink-0" ref={filterRef}>
                <button
                  onClick={() => setFiltersOpen((v) => !v)}
                  title="Filters"
                  aria-haspopup="dialog"
                  aria-expanded={filtersOpen}
                  className={cn(
                    "w-9 h-9 rounded-xl flex items-center justify-center transition-colors relative",
                    filtersOpen
                      ? "bg-primary text-white shadow-sm"
                      : "bg-surface-low border border-surface-mid text-on-surface-muted hover:bg-surface-mid"
                  )}
                >
                  <Filter size={14} />
                  {activeFilterCount > 0 && !filtersOpen && (
                    <span className="absolute -top-1 -right-1 h-[15px] min-w-[15px] px-1 rounded-full bg-primary ring-2 ring-surface flex items-center justify-center font-label text-[9px] font-bold text-white tabular-nums">
                      {activeFilterCount}
                    </span>
                  )}
                </button>

                {filtersOpen && (
                  <div
                    role="dialog"
                    aria-label="Filters"
                    className="absolute right-0 top-[calc(100%+8px)] z-30 w-[264px] rounded-2xl border border-surface-mid bg-surface p-2.5 shadow-[0_16px_40px_-8px_rgba(24,16,48,0.22)] animate-popover-in"
                  >
                    {/* Channel */}
                    <div className="flex items-center justify-between px-0.5 pb-1.5">
                      <span className="font-label text-[9.5px] font-bold uppercase tracking-[0.08em] text-on-surface-muted">Channel</span>
                      {activeFilterCount > 0 && (
                        <button
                          onClick={() => { onPlatformChange("all"); setSegment(null); }}
                          className="font-label text-[10px] font-semibold text-primary hover:underline"
                        >
                          Reset
                        </button>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {PLATFORMS.map((p) => {
                        const count = p.value === "all" ? platformCounts.all : (platformCounts[p.value] ?? 0);
                        const Icon = p.icon;
                        const active = platform === p.value;
                        return (
                          <button
                            key={p.value}
                            onClick={() => onPlatformChange(p.value)}
                            title={p.label}
                            aria-pressed={active}
                            className={cn(
                              "h-7 pl-2 pr-1.5 rounded-lg font-label text-[11px] font-semibold flex items-center gap-1.5 transition-all duration-150",
                              getPlatformBg(active, p.value)
                            )}
                          >
                            <Icon size={11} className={active ? "text-white" : getPlatformColor(p.value)} />
                            {p.short}
                            <span className={cn(
                              "min-w-[16px] px-1 rounded-md text-[9px] font-bold leading-[14px] text-center tabular-nums",
                              active ? "bg-white/25 text-white" : "bg-surface-mid text-on-surface-muted"
                            )}>
                              {count}
                            </span>
                          </button>
                        );
                      })}
                    </div>

                    {/* Stage */}
                    <div className="mt-2.5 px-0.5 pb-1.5">
                      <span className="font-label text-[9.5px] font-bold uppercase tracking-[0.08em] text-on-surface-muted">Stage</span>
                    </div>
                    <div className="grid grid-cols-4 gap-1">
                      {SEGMENTS.map((f) => {
                        const count = leads.filter((l) => l.segment === f.value && (platform === "all" || getLeadPlatform(l) === platform)).length;
                        const active = segment === f.value;
                        return (
                          <button
                            key={f.value}
                            onClick={() => setSegment(active ? null : f.value)}
                            aria-pressed={active}
                            className={cn(
                              "h-[38px] rounded-lg border flex flex-col items-center justify-center gap-px transition-all duration-150",
                              active
                                ? cn(f.bg, f.border, "shadow-sm")
                                : "bg-surface-low border-transparent hover:bg-surface-mid"
                            )}
                          >
                            <span className={cn("font-label text-[9px] font-bold uppercase tracking-[0.06em]", active ? f.text : "text-on-surface-muted")}>
                              {f.label}
                            </span>
                            <span className={cn("font-label text-[12px] font-bold leading-none tabular-nums", active ? f.text : "text-on-surface")}>
                              {count}
                            </span>
                          </button>
                        );
                      })}
                    </div>

                    <p className="mt-2.5 border-t border-surface-mid pt-2 px-0.5 font-label text-[10.5px] text-on-surface-muted">
                      <span className="font-bold text-on-surface tabular-nums">{visible.length}</span> conversations
                    </p>
                  </div>
                )}
              </div>
              <button
                onClick={handleRefresh}
                title="Refresh"
                disabled={isRefreshing}
                className="w-9 h-9 rounded-xl bg-surface-low border border-surface-mid flex items-center justify-center text-on-surface-muted hover:bg-surface-mid transition-colors shrink-0 disabled:opacity-60"
              >
                <RefreshCw size={14} className={isRefreshing ? "animate-spin" : ""} />
              </button>
            </div>
          </>
        )}
      </div>
      <div className="flex-1 overflow-y-auto bg-surface-low/30">
        {visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6 py-10 text-on-surface-muted space-y-3 animate-in fade-in duration-300">
            <div className="w-14 h-14 rounded-2xl bg-surface-low border border-surface-mid flex items-center justify-center shadow-sm">
              <SearchX size={24} className="text-on-surface-muted opacity-60" />
            </div>
            <div>
              <p className="font-display font-semibold text-[15px] text-on-surface">No conversations found</p>
              <p className="text-[13px] mt-1.5 leading-relaxed">Try adjusting your search query or switching filters to find what you&apos;re looking for.</p>
            </div>
            {(searchQuery || segment || platform !== "all") && (
              <button
                onClick={() => {
                  onSearchChange("");
                  setSegment(null);
                  onPlatformChange("all");
                }}
                className="mt-3 text-[13px] font-semibold text-primary hover:underline"
              >
                Clear all filters
              </button>
            )}
          </div>
        ) : (
          visible.map((lead) => {
            const isBot = lead.ai_enabled !== false;
            const preview = lead.last_message_content || (lead.phone ? formatPhone(lead.phone) : "No messages yet");
            const isLink = /^https?:\/\//i.test(preview.trim());
            const needsAction = lead.needs_human_intervention || lead.needs_human_attention;
            return (
            <div
              key={lead.id}
              onClick={() => onSelect(lead)}
              role="button"
              tabIndex={0}
              className={cn(
                "w-full text-left px-4 py-3.5 border-b border-surface-mid/40 transition-all duration-150 group flex items-start gap-3 relative cursor-pointer",
                selectedId === lead.id
                  ? "bg-surface before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[3px] before:bg-primary"
                  : "hover:bg-surface"
              )}
            >
              {selectionMode && (
                <div className="pt-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                  <CheckTick
                    checked={selectedIds.has(lead.id)}
                    onChange={() => toggleSelect(lead.id)}
                    size="sm"
                    aria-label="Select conversation"
                  />
                </div>
              )}

              {/* Channel avatar — the logo of the channel the chat arrived on */}
              <ChannelAvatar source={lead.source} size={44} className="mt-0.5" />

              {/* Content */}
              <div className="flex-1 min-w-0">
                {/* Row 1: name + unread/time */}
                <div className="flex items-center justify-between gap-2 mb-0.5">
                  <div className="flex items-center gap-1 min-w-0">
                    <span className={cn(
                      "font-display text-[13.5px] font-semibold truncate",
                      selectedId === lead.id ? "text-primary" : "text-on-surface"
                    )}>
                      {lead.name || formatPhone(lead.phone) || "Unknown"}
                    </span>
                    {onPin ? (
                      <button
                        onClick={(e) => { e.stopPropagation(); onPin(lead.id); }}
                        className={cn(
                          "shrink-0 p-0.5 rounded transition-all",
                          lead.pinned_at
                            ? "text-amber-500 opacity-100 hover:text-amber-700"
                            : "opacity-0 group-hover:opacity-100 text-on-surface-muted hover:text-amber-500"
                        )}
                      >
                        <Pin size={10} className={lead.pinned_at ? "fill-current" : ""} />
                      </button>
                    ) : lead.pinned_at ? (
                      <Pin size={10} className="text-amber-500 fill-current shrink-0" />
                    ) : null}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {needsAction && (
                      <span className="w-[18px] h-[18px] rounded-full bg-primary flex items-center justify-center font-label text-[10px] font-bold text-white">!</span>
                    )}
                    <span className="font-label text-[10px] text-on-surface-muted whitespace-nowrap">
                      {formatConvoTime((lead as ConversationLead).last_reply_at || lead.created_at)}
                    </span>
                  </div>
                </div>

                {/* Row 2: preview + sender indicator */}
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <p className={cn(
                    "font-body text-[12px] truncate leading-snug min-w-0",
                    isLink ? "text-primary" : "text-on-surface-muted"
                  )}>
                    {preview}
                  </p>
                  <span className={cn(
                    "flex items-center gap-0.5 font-label text-[10px] font-semibold shrink-0",
                    isBot ? "text-emerald-600" : "text-on-surface-muted"
                  )}>
                    {isBot ? "Bot" : "You"}
                    {isBot ? <CheckCheck size={12} /> : <Check size={12} />}
                  </span>
                </div>

                {/* Row 3: account label + badges + per-item menu */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                    <span className="font-label text-[10px] font-bold text-on-surface-muted/70 tracking-wide truncate">
                      {accountLabel(lead)}
                    </span>
                    <SegmentBadge segment={lead.segment} />
                    {lead.opted_out && (
                      <span className="font-label text-[9px] font-bold text-red-500 bg-red-50 border border-red-100 px-1.5 py-0.5 rounded-full">STOP</span>
                    )}
                    {lead.blocked_at && (
                      <span className="font-label text-[9px] font-bold text-red-600 bg-red-50 border border-red-100 px-1.5 py-0.5 rounded-full">BLOCKED</span>
                    )}
                  </div>

                  <div className="relative shrink-0" data-card-menu onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => setCardMenuId(cardMenuId === lead.id ? null : lead.id)}
                      className="rounded-md p-1 text-on-surface-muted transition-all hover:bg-surface-mid md:opacity-0 md:group-hover:opacity-100"
                    >
                      <MoreHorizontal size={15} />
                    </button>
                    {cardMenuId === lead.id && (
                      <div className="absolute right-0 top-full mt-1 w-40 bg-surface border border-surface-mid rounded-xl shadow-xl overflow-hidden z-50 py-1">
                        {onArchive && (
                          <button
                            onClick={() => { setCardMenuId(null); onArchive(lead.id); }}
                            disabled={!canArchive}
                            title={canArchive ? undefined : "You have read-only access to conversations"}
                            className="w-full flex items-center gap-2 px-3 py-2 text-left font-body text-[12.5px] text-on-surface hover:bg-surface-low transition-colors disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
                          >
                            <Archive size={14} className="text-on-surface-muted" />
                            {folder === "archived" ? "Unarchive" : "Archive"}
                          </button>
                        )}
                        {onBlock && (
                          <button onClick={() => { setCardMenuId(null); onBlock(lead.id); }} className="w-full flex items-center gap-2 px-3 py-2 text-left font-body text-[12.5px] text-on-surface hover:bg-surface-low transition-colors">
                            <Ban size={14} className="text-on-surface-muted" />
                            {folder === "blocked" ? "Unblock" : "Block"}
                          </button>
                        )}
                        <button onClick={() => handleDeleteOne(lead.id)} className="w-full flex items-center gap-2 px-3 py-2 text-left font-body text-[12.5px] text-red-600 hover:bg-red-50 transition-colors">
                          <Trash2 size={14} /> Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
            );
          })
        )}
        {!searchQuery && !segment && hasMore && (
          <div className="p-3">
            <button
              onClick={onLoadMore}
              disabled={loadingMore}
              className="w-full rounded-xl border border-surface-mid py-2.5 text-center font-label text-xs font-bold text-primary hover:bg-surface-low transition-colors disabled:opacity-50"
            >
              {loadingMore ? "Loading…" : "Load more conversations"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
