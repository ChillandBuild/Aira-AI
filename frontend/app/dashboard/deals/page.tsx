"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { NewDealDialog } from "@/components/deals/NewDealDialog";
import { DealDetailDrawer } from "@/components/deals/DealDetailDrawer";
import { DealsTab } from "./DealsTab";
import { InsightsTab } from "./InsightsTab";
import { FormAnswersTab } from "./FormAnswersTab";

type PageTab = "deals" | "insights" | "forms";

const TABS: { id: PageTab; label: string }[] = [
  { id: "deals", label: "Deals" },
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

  const canManage = role === "owner" || permissions.includes("deals.manage");
  const canView = role === "owner" || permissions.includes("deals.view") || canManage;

  const visibleTabs = TABS.filter((t) => t.id !== "forms" || intakeEnabled);
  const tab = (visibleTabs.some((t) => t.id === rawTab) ? rawTab : "deals") as PageTab;

  function setTab(next: PageTab) {
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
      {/* Tab navigation with underline style */}
      <div className="flex items-center justify-between gap-4 border-b border-border px-4">
        <div className="flex gap-1">
          {visibleTabs.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`px-3 py-3 font-label text-sm font-bold border-b-2 transition-all ${
                tab === id
                  ? "border-primary text-ink"
                  : "border-transparent text-ink-secondary hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {canManage && tab === "deals" && (
          <button
            type="button"
            onClick={() => setShowNewDeal(true)}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 font-label text-xs font-bold text-white shadow-sm hover:bg-primary/90"
          >
            <Plus size={14} /> New deal
          </button>
        )}
      </div>

      <div className="flex-1 overflow-hidden">
        {tab === "deals" && <DealsTab onOpenDeal={setOpenDealId} reloadToken={reloadToken} />}
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
