"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Menu, Users, MessageCircle, Archive, Ban, Settings,
  Filter, Clock, Bell, Moon, UserPlus, Download, LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useLogout } from "@/hooks/useLogout";
import { toast } from "sonner";

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

export function InboxRail({ folder, onFolderChange, onOpenFilter, escalationCount }: InboxRailProps) {
  const router = useRouter();
  const logout = useLogout();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    if (menuOpen) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [menuOpen]);

  function toggleDarkMode() {
    const root = document.documentElement;
    const next = !root.classList.contains("dark");
    root.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
    setMenuOpen(false);
  }

  async function enableNotifications() {
    setMenuOpen(false);
    if (!("Notification" in window)) return toast.error("Notifications not supported");
    const perm = await Notification.requestPermission();
    toast[perm === "granted" ? "success" : "error"](
      perm === "granted" ? "Notifications enabled" : "Notification permission denied"
    );
  }

  const MENU_ITEMS: { icon: typeof Filter; label: string; beta?: boolean; onClick: () => void }[] = [
    { icon: Filter, label: "Filter Channel & Account", onClick: () => { onOpenFilter?.(); setMenuOpen(false); } },
    { icon: Clock, label: "Follow-up List", onClick: () => { setMenuOpen(false); router.push("/dashboard/notes"); } },
    { icon: Bell, label: "Enable Notification", onClick: enableNotifications },
    { icon: Users, label: "Groupchat Settings", beta: true, onClick: () => { setMenuOpen(false); toast("Groupchat settings coming soon"); } },
    { icon: Moon, label: "Dark Mode", onClick: toggleDarkMode },
    { icon: UserPlus, label: "Add WhatsApp Subscriber", onClick: () => { setMenuOpen(false); router.push("/dashboard/upload"); } },
    { icon: Download, label: "Install App", onClick: () => { setMenuOpen(false); toast("Use your browser's Install option"); } },
    { icon: LogOut, label: "Logout", onClick: () => { setMenuOpen(false); logout(); } },
  ];

  const railBtn = "w-11 h-11 rounded-xl flex items-center justify-center transition-colors";

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-16 bg-surface border-r border-surface-mid flex flex-col items-center py-3 gap-1">
      <button
        onClick={() => {
          window.dispatchEvent(new CustomEvent("open-inbox-sidebar"));
        }}
        title="Open menu"
        className={cn(railBtn, "text-on-surface-muted hover:bg-surface-low hover:text-on-surface mb-1")}
      >
        <Menu size={20} />
      </button>

      <button
        onClick={() => router.push("/dashboard/leads")}
        title="Contacts"
        className={cn(railBtn, "text-on-surface-muted hover:bg-surface-low hover:text-on-surface")}
      >
        <Users size={19} />
      </button>

      {FOLDERS.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => onFolderChange(value)}
          title={label}
          className={cn(
            railBtn, "relative",
            folder === value
              ? "bg-tertiary/10 text-tertiary"
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

      <div className="relative mt-auto" ref={menuRef}>
        <button
          onClick={() => setMenuOpen((o) => !o)}
          title="Settings"
          className={cn(railBtn, menuOpen ? "bg-surface-low text-on-surface" : "text-on-surface-muted hover:bg-surface-low hover:text-on-surface")}
        >
          <Settings size={20} />
        </button>

        {menuOpen && (
          <div className="absolute bottom-0 left-full ml-2 w-64 bg-surface border border-surface-mid rounded-2xl shadow-xl py-2 z-50 animate-in fade-in slide-in-from-left-1 duration-150">
            {MENU_ITEMS.map(({ icon: Icon, label, beta, onClick }, i) => (
              <div key={label}>
                {(i === 2 || i === MENU_ITEMS.length - 1) && <div className="my-1.5 border-t border-surface-mid/60" />}
                <button
                  onClick={onClick}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left font-body text-[13.5px] text-on-surface hover:bg-surface-low transition-colors"
                >
                  <Icon size={18} className="text-on-surface-muted shrink-0" />
                  <span>{label}</span>
                  {beta && <span className="font-label text-[11px] font-semibold text-tertiary">(Beta)</span>}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
