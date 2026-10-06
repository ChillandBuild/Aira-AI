"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { MessagesTab } from "./MessagesTab";
import { ConnectTab } from "./ConnectTab";
import { CounterTab } from "./CounterTab";
import { ActivityTab } from "./ActivityTab";

type Tab = "messages" | "connect" | "counter" | "activity";

const TABS: { id: Tab; label: string; needs: "settings" | "counter" }[] = [
  { id: "messages", label: "Messages", needs: "settings" },
  { id: "connect", label: "Website & apps", needs: "settings" },
  { id: "counter", label: "Shop counter", needs: "counter" },
  { id: "activity", label: "Activity", needs: "settings" },
];

export default function AutoMessagesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { role, permissions, loading } = useAuthRole();

  const isOwner = role === "owner";
  const has = (p: string) => isOwner || permissions.includes(p);
  const canManage = has("settings.manage");
  const canView = canManage || has("settings.view");
  const canCounter = has("leads.manage");

  const visible = TABS.filter((t) => (t.needs === "settings" ? canView : canCounter));
  const raw = searchParams.get("tab");
  const tab = (visible.some((t) => t.id === raw) ? raw : visible[0]?.id) as Tab | undefined;

  function setTab(next: Tab) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", next);
    router.replace(`/dashboard/auto-messages?${params.toString()}`, { scroll: false });
  }

  if (loading) return <div className="m-6 min-h-[320px] animate-pulse rounded-2xl bg-border-subtle" />;

  if (!tab) {
    return (
      <div className="py-20 text-center">
        <p className="font-body text-sm text-ink-muted">You do not have access to Auto-Messages.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5 px-4 py-6 sm:px-6">
      <nav className="grid w-full grid-cols-2 gap-1 rounded-xl border border-border bg-surface-subtle p-1 sm:flex sm:w-fit">
        {visible.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`shrink-0 rounded-lg px-3.5 py-1.5 font-label text-xs font-bold transition-all ${
              tab === id ? "bg-white text-ink shadow-sm" : "text-ink-muted hover:text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "messages" && <MessagesTab canManage={canManage} />}
      {tab === "connect" && <ConnectTab canManage={canManage} />}
      {tab === "counter" && <CounterTab />}
      {tab === "activity" && <ActivityTab />}
    </div>
  );
}
