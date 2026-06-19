"use client";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { Clock } from "lucide-react";
import { NotificationBell } from "@/components/NotificationBell";
import { ProfileMenu } from "@/components/ProfileMenu";

// Define a map of exact path matches and dynamic route prefixes
function getRouteMetadata(pathname: string) {
  if (pathname === "/dashboard") {
    return {
      title: "Product Overview",
      description: "Here's what's happening with your leads.",
    };
  }
  if (pathname === "/dashboard/outbound-leads") {
    return {
      title: "Outbound Leads",
      description: "Import a CSV and broadcast a WhatsApp campaign to all eligible leads.",
    };
  }
  if (pathname === "/dashboard/telecalling/upload") {
    return {
      title: "Telecalling Upload",
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
    return {
      title: "Team",
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
    return {
      title: "Knowledge Base",
      description: "Upload documents and tune AI prompts to answer lead queries accurately.",
    };
  }
  if (pathname === "/dashboard/leads") {
    return {
      title: "Segments",
      description: "Group and manage your leads by attributes and behavior.",
    };
  }
  if (pathname === "/dashboard/numbers") {
    return {
      title: "WhatsApp Numbers",
      description: "Manage sender numbers and outbound routing.",
    };
  }
  if (pathname === "/dashboard/settings") {
    return {
      title: "Settings",
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
  const { title, description } = getRouteMetadata(pathname || "");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString("en-US", { hour12: false, hour: '2-digit', minute: '2-digit' }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

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
