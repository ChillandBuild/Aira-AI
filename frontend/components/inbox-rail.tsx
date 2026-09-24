"use client";
import {
  MessageCircle, Archive, Ban, Bell,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type InboxFolder = "chats" | "escalations" | "archived" | "blocked";

interface InboxRailProps {
  folder: InboxFolder;
  onFolderChange: (folder: InboxFolder) => void;
  onOpenFilter?: () => void;
  escalationCount?: number;
}

const FOLDERS: { value: InboxFolder; icon: typeof MessageCircle; label: string }[] = [
  { value: "chats", icon: MessageCircle, label: "Chats" },
  { value: "escalations", icon: Bell, label: "Escalations" },
  { value: "archived", icon: Archive, label: "Archived" },
  { value: "blocked", icon: Ban, label: "Blocked" },
];

export function InboxRail({ folder, onFolderChange, escalationCount }: InboxRailProps) {
  const railBtn = "w-11 h-11 rounded-xl flex items-center justify-center transition-colors";

  return (
    <aside className="fixed left-16 top-0 z-40 h-screen w-16 bg-surface border-r border-surface-mid flex flex-col items-center py-3 gap-1">
      {FOLDERS.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => onFolderChange(value)}
          title={label}
          className={cn(
            railBtn, "relative",
            folder === value
              ? "bg-primary/10 text-primary"
              : "text-on-surface-muted hover:bg-surface-low hover:text-on-surface"
          )}
        >
          <Icon size={19} />
          {value === "escalations" && !!escalationCount && escalationCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 px-1 min-w-[16px] h-4 rounded-full bg-orange-500 text-white text-[9px] font-bold flex items-center justify-center">
              {escalationCount}
            </span>
          )}
        </button>
      ))}
    </aside>
  );
}
