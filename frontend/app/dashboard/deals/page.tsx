"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { NewDealDialog } from "@/components/deals/NewDealDialog";
import { DealDetailDrawer } from "@/components/deals/DealDetailDrawer";
import { BoardTab } from "./BoardTab";
import { ListTab } from "./ListTab";
import { InsightsTab } from "./InsightsTab";
import { FormAnswersTab } from "./FormAnswersTab";

type DealsTab = "board" | "list" | "insights" | "forms";

const TABS: { id: DealsTab; label: string }[] = [
  { id: "board", label: "Board" },
  { id: "list", label: "List" },
  { id: "insights", label: "Insights" },
  { id: "forms", label: "Form answers" },
];

export default function DealsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { role, permissions, loading: roleLoading } = useAuthRole();
  const rawTab = searchParams.get("tab");
  const [intakeEnabled, setIntakeEnabled] = useState(false);
  const [showNewDeal, setShowNewDeal] = useState(false);
  const [openDealId, setOpenDealId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const canManage = role === "owner" || permissions.includes("leads.manage");
  const canView = role === "owner" || permissions.includes("leads.view") || canManage;

  const visibleTabs = TABS.filter((t) => t.id !== "forms" || intakeEnabled);
  const tab = (visibleTabs.some((t) => t.id === rawTab) ? rawTab : "board") as DealsTab;

  function setTab(next: DealsTab) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", next);
    router.replace(`/dashboard/deals?${params.toString()}`, { scroll: false });
  }

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, { headers: auth });
        if (res.ok) {
          const config = await res.json();
          setIntakeEnabled(Boolean(config.enabled));
        }
      } catch {
        setIntakeEnabled(false);
      }
    })();
  }, []);

  function handleCreated() {
    setReloadToken((n) => n + 1);
  }

  function handleDealChanged() {
    setReloadToken((n) => n + 1);
  }

  if (roleLoading) {
    return <div className="min-h-[320px] animate-pulse rounded-2xl bg-border-subtle m-6" />;
  }

  if (!canView) {
    return (
      <div className="py-20 text-center">
        <p className="font-body text-sm text-ink-muted">You do not have access to deals.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
        <div>
          <h1 className="font-display text-lg font-bold text-ink">Deals</h1>
          <p className="font-body text-xs text-ink-muted">Quotes, payments and sales — from chat, calls and walk-ins.</p>
        </div>

        <div className="flex gap-1 rounded-xl border border-border bg-surface-subtle p-1">
          {visibleTabs.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded-lg px-3 py-1.5 font-label text-xs font-bold transition-all ${
                tab === id ? "bg-white text-ink shadow-sm" : "text-ink-muted"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {canManage && (
          <button
            type="button"
            onClick={() => setShowNewDeal(true)}
            className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 font-label text-xs font-bold text-white shadow-sm hover:bg-primary/90"
          >
            <Plus size={14} /> New deal
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {tab === "board" && <BoardTab onOpenDeal={setOpenDealId} reloadToken={reloadToken} />}
        {tab === "list" && <ListTab onOpenDeal={setOpenDealId} reloadToken={reloadToken} />}
        {tab === "insights" && <InsightsTab />}
        {tab === "forms" && intakeEnabled && <FormAnswersTab />}
      </div>

      {showNewDeal && (
        <NewDealDialog
          open={showNewDeal}
          onClose={() => setShowNewDeal(false)}
          onCreated={handleCreated}
        />
      )}

      {openDealId && (
        <DealDetailDrawer
          dealId={openDealId}
          canManage={canManage}
          onClose={() => setOpenDealId(null)}
          onChanged={handleDealChanged}
        />
      )}
    </div>
  );
}
