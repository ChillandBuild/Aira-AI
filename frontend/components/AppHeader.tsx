"use client";
import { useState, useEffect } from "react";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { Clock, RefreshCw, LayoutGrid, List } from "lucide-react";
import { NotificationBell } from "@/components/NotificationBell";
import { ProfileMenu } from "@/components/ProfileMenu";
import { MoreMenu } from "@/components/MoreMenu";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";

import { cn } from "@/lib/utils";

// Define a map of exact path matches and dynamic route prefixes
function getRouteMetadata(pathname: string, searchParams: URLSearchParams) {
  const tab = searchParams.get("tab") || "";

  if (pathname === "/dashboard") {
    return {
      title: "Product Overview",
      description: "Here's what's happening with your leads.",
    };
  }
  if (pathname === "/dashboard/outbound-leads") {
    let desc = "Import a CSV and broadcast a WhatsApp campaign to all eligible leads.";
    if (tab === "history") desc = "Track delivery status, read rates, and failures of sent broadcast campaigns.";
    if (tab === "tags") desc = "Create and manage tags to segment and label leads for outbound campaigns.";
    return {
      title: "Outbound Leads",
      description: desc,
    };
  }
  if (pathname === "/dashboard/telecalling/upload") {
    let desc = "Upload contacts, assign them to queues, and start call campaigns.";
    if (tab === "history") desc = "Review past CSV uploads, processing status, and import summaries.";
    if (tab === "scripts") desc = "Manage call scripts and guidelines for telecallers to follow.";
    return {
      title: "Telecalling Upload",
      description: desc,
    };
  }
  if (pathname === "/dashboard/telecalling") {
    return {
      title: "Telecalling Dashboard",
      description: "Manage calls, callers, and lead queues in real time.",
    };
  }
  if (pathname === "/dashboard/telecalling/scheduled") {
    return {
      title: "Scheduled Calls",
      description: "View and manage upcoming scheduled calls for leads.",
    };
  }
  if (pathname === "/dashboard/team") {
    let tabLabel = "Agent Performance";
    if (tab === "log") tabLabel = "Assignment Log";
    return {
      title: `Team / ${tabLabel}`,
      description: "Add and manage telecallers under your account.",
    };
  }
  if (pathname === "/dashboard/analytics") {
    return {
      title: "Analytics",
      description: "Service metrics across all channels and the lead funnel.",
    };
  }
  if (pathname === "/dashboard/channels") {
    return {
      title: "Connect Channels",
      description: "Configure credentials and view synchronization health across your messaging channels.",
    };
  }
  if (pathname === "/dashboard/inbound-leads") {
    return {
      title: "Inbound Leads",
      description: "All inbound leads — organic and Meta Ad, across messaging channels.",
    };
  }
  if (pathname === "/dashboard/knowledge") {
    let tabLabel = "Documents (RAG)";
    if (tab === "ai-tune") tabLabel = "AI Tune";
    return {
      title: `Knowledge Base / ${tabLabel}`,
      description: "Upload documents and tune AI prompts to answer lead queries accurately.",
    };
  }
  if (pathname === "/dashboard/leads") {
    let tabLabel = "Leads";
    if (tab === "reengagement") tabLabel = "Re-engagement";
    return {
      title: `Segments / ${tabLabel}`,
      description: "Group and manage your leads by attributes and behavior.",
    };
  }
  if (pathname === "/dashboard/numbers") {
    let tabLabel = "Numbers Pool";
    if (tab === "activity") tabLabel = "Incident Log";
    return {
      title: `WhatsApp Numbers / ${tabLabel}`,
      description: "Manage sender numbers and outbound routing.",
    };
  }
  if (pathname === "/dashboard/settings") {
    let tabLabel = "General";
    if (tab === "channels") tabLabel = "Messaging Channels";
    if (tab === "telecalling") tabLabel = "Telecalling Config";
    if (tab === "ai") tabLabel = "AI Settings";
    if (tab === "automations") tabLabel = "Automations";
    return {
      title: `Account Settings / ${tabLabel}`,
      description: "Configure global parameters, voice calling and AI behavior.",
    };
  }
  if (pathname === "/dashboard/templates") {
    return {
      title: "WhatsApp Message Templates",
      description: "Create, sync and manage your WhatsApp message templates.",
    };
  }
  if (pathname === "/dashboard/templates/new") {
    return {
      title: "Create Message Template",
      description: "Design a new WhatsApp message template.",
    };
  }
  if (pathname === "/dashboard/templates/carousel") {
    return {
      title: "New Carousel Template",
      description: "Design a new WhatsApp carousel message template.",
    };
  }
  if (pathname === "/dashboard/onboarding") {
    return {
      title: "Welcome to Aira AI",
      description: "Complete your onboarding setup.",
    };
  }
  if (pathname === "/dashboard/profile") {
    return {
      title: "My Profile",
      description: "View and manage your profile details, passwords and API access.",
    };
  }
  if (pathname === "/dashboard/notes") {
    return {
      title: "Call Notes",
      description: "Browse and manage notes across your leads.",
    };
  }

  // fallback/prefix matches
  if (pathname.startsWith("/dashboard/templates/")) {
    return {
      title: "Template Details",
      description: "View and manage message template configuration.",
    };
  }

  return {
    title: "Aira AI",
    description: "Your autonomous AI calling and messaging assistant.",
  };
}

export function AppHeader({ onOpenCalendar }: { onOpenCalendar: () => void }) {
  const [time, setTime] = useState<string>("");
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { role } = useAuthRole();

  let { title, description } = getRouteMetadata(pathname || "", searchParams);

  if (pathname === "/dashboard/profile" && role !== "owner") {
    title = "Overview";
    description = "Your performance at a glance";
  }

  const tab = searchParams.get("tab") || "";

  // Action states for conditional header buttons
  const [channelsLoading, setChannelsLoading] = useState(false);

  // Notes switcher states
  const [notesPageMode, setNotesPageMode] = useState<"by_lead" | "all_notes">("by_lead");
  const [notesViewMode, setNotesViewMode] = useState<"grid" | "list">("grid");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString("en-US", { hour12: false, hour: '2-digit', minute: '2-digit' }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);



  // Listen to Channels loading state from Channels page
  useEffect(() => {
    const handleLoadingStart = () => setChannelsLoading(true);
    const handleLoadingEnd = () => setChannelsLoading(false);
    window.addEventListener("channels-health-loading-start", handleLoadingStart);
    window.addEventListener("channels-health-loading-end", handleLoadingEnd);
    return () => {
      window.removeEventListener("channels-health-loading-start", handleLoadingStart);
      window.removeEventListener("channels-health-loading-end", handleLoadingEnd);
    };
  }, []);

  // Listen to NotesClient page mode and view mode states
  useEffect(() => {
    const handlePageModeState = (e: Event) => {
      const customEvent = e as CustomEvent<"by_lead" | "all_notes">;
      setNotesPageMode(customEvent.detail);
    };
    const handleViewModeState = (e: Event) => {
      const customEvent = e as CustomEvent<"grid" | "list">;
      setNotesViewMode(customEvent.detail);
    };
    window.addEventListener("notes-page-mode-state", handlePageModeState);
    window.addEventListener("notes-view-mode-state", handleViewModeState);
    return () => {
      window.removeEventListener("notes-page-mode-state", handlePageModeState);
      window.removeEventListener("notes-view-mode-state", handleViewModeState);
    };
  }, []);

  const changeNotesPageMode = (mode: "by_lead" | "all_notes") => {
    setNotesPageMode(mode);
    window.dispatchEvent(new CustomEvent("change-notes-page-mode", { detail: mode }));
  };

  const changeNotesViewMode = (mode: "grid" | "list") => {
    setNotesViewMode(mode);
    window.dispatchEvent(new CustomEvent("change-notes-view-mode", { detail: mode }));
  };



  const onRefreshHealth = () => {
    window.dispatchEvent(new CustomEvent("refresh-channels-health"));
  };

  return (
    <header className="sticky top-0 z-40 flex h-16 items-center justify-between gap-3 border-b border-[#e8e3db] bg-[#faf8f5] px-4 md:h-20 md:gap-4 md:px-7">
      {/* Left side: title and description */}
      <div className="flex flex-col justify-center select-none">
        <h1 className="font-display text-base font-bold leading-tight text-on-surface md:text-lg">
          {title}
        </h1>
        {description && (
          <p className="mt-0.5 hidden max-w-[650px] truncate font-body text-xs text-on-surface-muted sm:block">
            {description}
          </p>
        )}
      </div>

      {/* Right side actions */}
      <div className="flex shrink-0 items-center gap-2 md:gap-2.5">
        {pathname === "/dashboard/outbound-leads" && (
          <div className="mr-2 hidden gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 md:flex">
            {(["upload", "history", "tags"] as const).map((t) => (
              <button
                key={t}
                onClick={() => {
                  const params = new URLSearchParams(searchParams.toString());
                  params.set("tab", t);
                  router.replace(`/dashboard/outbound-leads?${params.toString()}`, { scroll: false });
                }}
                className={cn(
                  "px-3 py-1.5 rounded-xl font-label text-xs font-bold transition-all",
                  (tab === t || (t === "upload" && !tab))
                    ? "bg-white text-primary shadow-sm"
                    : "text-[#78716c] hover:text-[#292524]"
                )}
              >
                {t === "upload" ? "Broadcast Message" : t === "history" ? "Broadcast History" : "Tags"}
              </button>
            ))}
          </div>
        )}

        {pathname === "/dashboard/telecalling/upload" && (
          <div className="mr-2 hidden gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 md:flex">
            {(["upload", "history", "scripts"] as const).map((t) => (
              <button
                key={t}
                onClick={() => {
                  const params = new URLSearchParams(searchParams.toString());
                  params.set("tab", t);
                  router.replace(`/dashboard/telecalling/upload?${params.toString()}`, { scroll: false });
                }}
                className={cn(
                  "px-3 py-1.5 rounded-xl font-label text-xs font-bold transition-all",
                  (tab === t || (t === "upload" && !tab))
                    ? "bg-white text-primary shadow-sm"
                    : "text-[#78716c] hover:text-[#292524]"
                )}
              >
                {t === "upload" ? "Upload Contacts" : t === "history" ? "Upload History" : "Scripts"}
              </button>
            ))}
          </div>
        )}

        {pathname === "/dashboard/notes" && (
          <>
            <div className="hidden gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 md:flex">
              <button
                onClick={() => changeNotesPageMode("by_lead")}
                className={cn(
                  "px-3 py-1.5 rounded-xl font-label text-xs font-bold transition-all",
                  notesPageMode === "by_lead"
                    ? "bg-white text-primary shadow-sm"
                    : "text-[#78716c] hover:text-[#292524]"
                )}
              >
                By Lead
              </button>
              <button
                onClick={() => changeNotesPageMode("all_notes")}
                className={cn(
                  "px-3 py-1.5 rounded-xl font-label text-xs font-bold transition-all",
                  notesPageMode === "all_notes"
                    ? "bg-white text-primary shadow-sm"
                    : "text-[#78716c] hover:text-[#292524]"
                )}
              >
                All Notes
              </button>
            </div>
            <div className="mr-2 hidden gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 md:flex">
              <button
                onClick={() => changeNotesViewMode("grid")}
                className={cn(
                  "p-1.5 rounded-xl transition-all",
                  notesViewMode === "grid"
                    ? "bg-white text-primary shadow-sm"
                    : "text-[#a8a29e] hover:text-[#44403c]"
                )}
                title="Grid view"
              >
                <LayoutGrid size={14} />
              </button>
              <button
                onClick={() => changeNotesViewMode("list")}
                className={cn(
                  "p-1.5 rounded-xl transition-all",
                  notesViewMode === "list"
                    ? "bg-white text-primary shadow-sm"
                    : "text-[#a8a29e] hover:text-[#44403c]"
                )}
                title="List view"
              >
                <List size={14} />
              </button>
            </div>
          </>
        )}



        {(pathname === "/dashboard/channels" || (pathname === "/dashboard/settings" && tab === "channels")) && (
          <button
            onClick={onRefreshHealth}
            disabled={channelsLoading}
            className="hidden h-[34px] items-center gap-2 rounded-lg border border-[#e8e3db] bg-white px-3.5 font-label text-xs font-semibold text-[#78716c] shadow-sm transition-all hover:text-[#292524] disabled:opacity-40 md:flex"
          >
            <RefreshCw size={13} className={channelsLoading ? "animate-spin" : ""} />
            <span>Refresh Health</span>
          </button>
        )}

        <button
          onClick={onOpenCalendar}
          className="hidden h-[34px] items-center gap-1.5 rounded-lg border border-[#e8e3db] bg-transparent px-3 font-mono text-[13px] font-semibold tracking-wide text-[#1c1917] transition-all hover:bg-[#f0ece4] sm:flex"
          title="Schedule & Notes"
        >
          <Clock size={13} className="opacity-50" />
          <span>{time || "00:00"}</span>
          <span className="sr-only">Schedule & Notes</span>
        </button>
        <MoreMenu />
        <NotificationBell />
        <ProfileMenu />
      </div>
    </header>
  );
}
