"use client";
import { useState, useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { Clock, Settings, RefreshCw, LayoutGrid, List } from "lucide-react";
import { NotificationBell } from "@/components/NotificationBell";
import { ProfileMenu } from "@/components/ProfileMenu";
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
    let tabLabel = "Broadcast Message";
    if (tab === "history") tabLabel = "Broadcast History";
    if (tab === "tags") tabLabel = "Tags";
    return {
      title: `Outbound Leads / ${tabLabel}`,
      description: "Import a CSV and broadcast a WhatsApp campaign to all eligible leads.",
    };
  }
  if (pathname === "/dashboard/telecalling/upload") {
    let tabLabel = "Upload Contacts";
    if (tab === "history") tabLabel = "Upload History";
    if (tab === "scripts") tabLabel = "Call Scripts";
    return {
      title: `Telecalling Upload / ${tabLabel}`,
      description: "Upload contacts, view history, and manage call scripts.",
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
    if (tab === "ai") tabLabel = "AI & Automations";
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
  if (pathname === "/dashboard/inbox") {
    return {
      title: "Chat Inbox",
      description: "Conversations where AI couldn't answer — needs your reply.",
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
  const { role } = useAuthRole();
  const { title, description } = getRouteMetadata(pathname || "", searchParams);
  const tab = searchParams.get("tab") || "";

  // Action states for conditional header buttons
  const [escalationOpen, setEscalationOpen] = useState(false);
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

  // Listen to Escalation Rules state from Inbox page
  useEffect(() => {
    const handleEscalationState = (e: Event) => {
      const customEvent = e as CustomEvent<{ open: boolean }>;
      setEscalationOpen(customEvent.detail.open);
    };
    window.addEventListener("escalation-rules-state", handleEscalationState);
    return () => {
      window.removeEventListener("escalation-rules-state", handleEscalationState);
    };
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

  const onToggleEscalation = () => {
    window.dispatchEvent(new CustomEvent("toggle-escalation-rules"));
  };

  const onRefreshHealth = () => {
    window.dispatchEvent(new CustomEvent("refresh-channels-health"));
  };

  return (
    <header className="sticky top-0 z-40 h-20 flex items-center justify-between gap-4 px-7 bg-[#faf8f5] border-b border-[#e8e3db]">
      {/* Left side: title and description */}
      <div className="flex flex-col justify-center select-none">
        <h1 className="font-display text-lg font-bold text-on-surface leading-tight">
          {title}
        </h1>
        {description && (
          <p className="font-body text-xs text-on-surface-muted mt-0.5 max-w-[650px] truncate">
            {description}
          </p>
        )}
      </div>

      {/* Right side actions */}
      <div className="flex items-center gap-2.5">
        {pathname === "/dashboard/notes" && (
          <>
            <div className="flex gap-1 p-1 bg-[#e8e3db]/60 rounded-2xl">
              <button
                onClick={() => changeNotesPageMode("by_lead")}
                className={cn(
                  "px-3 py-1.5 rounded-xl font-label text-xs font-bold transition-all",
                  notesPageMode === "by_lead"
                    ? "bg-white text-indigo-600 shadow-sm"
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
                    ? "bg-white text-indigo-600 shadow-sm"
                    : "text-[#78716c] hover:text-[#292524]"
                )}
              >
                All Notes
              </button>
            </div>
            <div className="flex gap-1 p-1 bg-[#e8e3db]/60 rounded-2xl mr-2">
              <button
                onClick={() => changeNotesViewMode("grid")}
                className={cn(
                  "p-1.5 rounded-xl transition-all",
                  notesViewMode === "grid"
                    ? "bg-white text-indigo-600 shadow-sm"
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
                    ? "bg-white text-indigo-600 shadow-sm"
                    : "text-[#a8a29e] hover:text-[#44403c]"
                )}
                title="List view"
              >
                <List size={14} />
              </button>
            </div>
          </>
        )}

        {pathname === "/dashboard/inbox" && role === "owner" && (
          <button
            onClick={onToggleEscalation}
            className={cn(
              "flex items-center gap-2 h-[34px] px-3.5 rounded-lg font-label text-xs font-semibold transition-colors border shadow-sm",
              escalationOpen
                ? "bg-violet-50 border-violet-200 text-violet-700 hover:bg-violet-100"
                : "bg-white border-[#e8e3db] text-[#1c1917] hover:text-violet-600 hover:border-violet-300"
            )}
          >
            <Settings size={13} />
            <span>Escalation Rules</span>
          </button>
        )}

        {(pathname === "/dashboard/channels" || (pathname === "/dashboard/settings" && tab === "channels")) && (
          <button
            onClick={onRefreshHealth}
            disabled={channelsLoading}
            className="flex items-center gap-2 h-[34px] px-3.5 rounded-lg font-label text-xs font-semibold border border-[#e8e3db] text-[#78716c] hover:text-[#292524] transition-all bg-white disabled:opacity-40 shadow-sm"
          >
            <RefreshCw size={13} className={channelsLoading ? "animate-spin" : ""} />
            <span>Refresh Health</span>
          </button>
        )}

        <button
          onClick={onOpenCalendar}
          className="flex items-center gap-1.5 h-[34px] px-3 transition-all text-[#1c1917] font-mono text-[13px] font-semibold tracking-wide hover:bg-[#f0ece4] bg-transparent border border-[#e8e3db] rounded-lg"
          title="Schedule & Notes"
        >
          <Clock size={13} className="opacity-50" />
          <span>{time || "00:00"}</span>
          <span className="sr-only">Schedule & Notes</span>
        </button>
        <NotificationBell />
        <ProfileMenu />
      </div>
    </header>
  );
}
