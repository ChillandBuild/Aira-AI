"use client";
import { useCallback, useEffect, useState, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { getAuthHeaders, API_URL, Lead, api } from "@/lib/api";
import { ConversationList } from "@/components/conversation-list";
import { ChatThread } from "@/components/chat-thread";
import { LeadDetailsPanel } from "@/components/lead-details-panel";
import { EscalationPanel } from "@/components/escalation-panel";
import { InboxRail, type InboxFolder } from "@/components/inbox-rail";
import { ChevronLeft } from "lucide-react";
import { usePolling } from "@/hooks/usePolling";
import { toast } from "sonner";
import { createClient } from "@/lib/supabase/client";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";

function getDetailsPanelDefault(): boolean {
  if (typeof window === "undefined") return true;
  const stored = localStorage.getItem("lead_details_open");
  if (stored !== null) return stored === "true";
  return window.innerWidth >= 1280;
}

async function fetchConversations(folder: InboxFolder): Promise<Lead[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/conversations?limit=50&folder=${folder}`, { headers: auth });
  if (!res.ok) throw new Error(`conversations fetch failed: ${res.status}`);
  const data = await res.json();
  return data.leads ?? [];
}

function togglePinInList(leads: Lead[], leadId: string): Lead[] {
  return leads.map((l) =>
    l.id === leadId ? { ...l, pinned_at: l.pinned_at ? null : new Date().toISOString() } : l
  );
}

function SharedInboxEmpty() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-8 text-center select-none">
      <div className="w-[280px] h-[200px] rounded-2xl bg-gradient-to-br from-primary/15 via-primary/5 to-transparent border border-primary/15 p-4 mb-8 shadow-sm">
        <div className="flex gap-1.5 mb-4">
          <span className="w-2 h-2 rounded-full bg-primary/40" />
          <span className="w-2 h-2 rounded-full bg-primary/40" />
          <span className="w-2 h-2 rounded-full bg-primary/40" />
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="h-7 w-32 rounded-lg bg-primary/20" />
            <div className="h-6 w-6 rounded-full bg-primary/30" />
          </div>
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-full bg-primary/40" />
            <div className="h-7 flex-1 rounded-lg bg-primary/15" />
          </div>
          <div className="h-7 w-3/4 rounded-lg bg-primary/10" />
        </div>
      </div>
      <h2 className="font-display text-2xl font-bold text-primary mb-2">Shared Inbox</h2>
      <p className="font-body text-sm font-semibold text-on-surface mb-1">Connect Multiple Platforms &ndash; all in one inbox!</p>
      <p className="font-body text-sm text-on-surface-muted">Easily manage messages from multiple platforms in a single inbox.</p>
    </div>
  );
}

export default function ConversationsPage() {
  const { callerId } = useAuthRole();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [selected, setSelected] = useState<Lead | null>(null);
  const [error, setError] = useState(false);
  const [platform, setPlatform] = useState<string>("all");
  const [folder, setFolder] = useState<InboxFolder>("chats");
  const [detailsOpen, setDetailsOpen] = useState(getDetailsPanelDefault);
  const [escalationCount, setEscalationCount] = useState(0);

  const searchParams = useSearchParams();
  const deepLinkLeadId = searchParams.get("lead");
  const deepLinked = useRef(false);

  const fetchEscalationCount = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/chat-handovers/count`, { headers: auth });
      if (res.ok) setEscalationCount((await res.json()).count ?? 0);
    } catch {}
  }, []);

  useEffect(() => {
    fetchEscalationCount();
    const supabase = createClient();
    const channel = supabase
      .channel("escalation-count-realtime")
      .on("postgres_changes", { event: "*", schema: "public", table: "chat_handovers" }, () => {
        fetchEscalationCount();
      })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [fetchEscalationCount]);

  const load = useCallback(() => {
    if (folder === "escalations") return;
    fetchConversations(folder)
      .then((loadedLeads) => { setLeads(loadedLeads); setError(false); })
      .catch(() => setError(true));
  }, [folder]);

  useEffect(() => { load(); }, [load]);
  usePolling(load, 20000);

  // Auto-select lead from ?lead= query param (e.g. from Inbox Reply button)
  useEffect(() => {
    if (!deepLinkLeadId || deepLinked.current || leads.length === 0) return;
    const match = leads.find((l) => l.id === deepLinkLeadId);
    if (match) {
      setSelected(match);
      deepLinked.current = true;
    }
  }, [deepLinkLeadId, leads]);

  useEffect(() => {
    localStorage.setItem("lead_details_open", String(detailsOpen));
  }, [detailsOpen]);

  function handleFolderChange(next: InboxFolder) {
    setFolder(next);
    setSelected(null);
  }

  function handleSelect(lead: Lead) {
    setSelected(lead);
  }

  function handlePin(id: string) {
    setLeads((prev) => {
      const current = prev.find((l) => l.id === id);
      if (!current) return prev;
      const toggled = togglePinInList(prev, id);
      api.leads.pin(id).catch(() => {
        setLeads((rollback) => togglePinInList(rollback, id));
        toast.error("Failed to pin/unpin contact");
      });
      return toggled;
    });
  }

  function handlePinSelected(ids: string[]) {
    setLeads((prev) => {
      let next = prev;
      for (const id of ids) {
        next = togglePinInList(next, id);
      }
      return next;
    });
    for (const id of ids) {
      api.leads.pin(id).catch(() => {
        setLeads((rollback) => togglePinInList(rollback, id));
        toast.error("Failed to pin/unpin contact");
      });
    }
  }

  // Archiving/blocking changes which folder a lead belongs to, so it leaves the
  // current list. Optimistically remove; reload on failure.
  function handleArchive(id: string) {
    setLeads((prev) => prev.filter((l) => l.id !== id));
    if (selected?.id === id) setSelected(null);
    api.leads.archive(id)
      .then(() => toast.success(folder === "archived" ? "Chat unarchived" : "Chat archived"))
      .catch(() => { toast.error("Failed to archive"); load(); });
  }

  function handleBlock(id: string) {
    setLeads((prev) => prev.filter((l) => l.id !== id));
    if (selected?.id === id) setSelected(null);
    api.leads.block(id)
      .then(() => toast.success(folder === "blocked" ? "Contact unblocked" : "Contact blocked"))
      .catch(() => { toast.error("Failed to block"); load(); });
  }

  const pendingReplyRef = useRef<string | null>(null);

  function handleEscalationReply(leadId: string) {
    pendingReplyRef.current = leadId;
    setFolder("chats");
    setSelected(null);
  }

  useEffect(() => {
    if (!pendingReplyRef.current || leads.length === 0) return;
    const match = leads.find((l) => l.id === pendingReplyRef.current);
    if (match) {
      setSelected(match);
      pendingReplyRef.current = null;
    }
  }, [leads]);

  if (folder === "escalations") {
    return (
      <div className="h-screen flex relative pl-16">
        <InboxRail folder={folder} onFolderChange={handleFolderChange} escalationCount={escalationCount} />
        <EscalationPanel
          onReply={handleEscalationReply}
          onCountChange={setEscalationCount}
          currentCallerId={callerId}
        />
      </div>
    );
  }

  return (
    <div className="h-screen flex relative pl-16">
      <InboxRail folder={folder} onFolderChange={handleFolderChange} escalationCount={escalationCount} />

      {/* ── Conversation list ── */}
      <div className="relative flex-shrink-0 w-[440px] max-w-[42vw]">
        <ConversationList
          leads={leads}
          selectedId={selected?.id ?? null}
          onSelect={handleSelect}
          platform={platform}
          onPlatformChange={setPlatform}
          onRefresh={load}
          onPin={handlePin}
          onPinSelected={handlePinSelected}
          onArchive={handleArchive}
          onBlock={handleBlock}
          folder={folder}
          onDeleted={(deletedIds) => {
            setLeads((prev) => prev.filter((l) => !deletedIds.includes(l.id)));
            if (selected && deletedIds.includes(selected.id)) {
              setSelected(null);
            }
          }}
        />
      </div>

      {/* ── Center: Chat thread / Shared Inbox empty state ── */}
      {selected ? (
        <ChatThread
          lead={selected}
          onDeleted={(id) => {
            setLeads((prev) => prev.filter((l) => l.id !== id));
            setSelected(null);
          }}
          onLeadUpdate={(updated) => setSelected(updated)}
        />
      ) : (
        <SharedInboxEmpty />
      )}
      {error && !selected && (
        <p className="absolute bottom-4 left-1/2 -translate-x-1/2 font-body text-sm text-red-500">Failed to load conversations. Retrying…</p>
      )}

      {/* ── Right: Lead details panel ── */}
      {selected && (
        <>
          {detailsOpen ? (
            <LeadDetailsPanel
              lead={selected}
              onCollapse={() => setDetailsOpen(false)}
              onLeadUpdate={(updated) => setSelected(updated)}
            />
          ) : (
            <button
              onClick={() => setDetailsOpen(true)}
              title="Show contact details"
              className="absolute right-0 top-1/2 -translate-y-1/2 z-30 w-6 h-12 bg-surface border border-surface-mid border-r-0 rounded-l-lg flex items-center justify-center text-on-surface-muted hover:text-primary hover:bg-surface-low transition-colors shadow-md"
            >
              <ChevronLeft size={14} />
            </button>
          )}
        </>
      )}
    </div>
  );
}
