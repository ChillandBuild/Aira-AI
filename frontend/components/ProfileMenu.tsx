"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, Settings, Monitor, ChevronRight } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { useLogout } from "@/hooks/useLogout";

export function ProfileMenu() {
  const { role, permissions, tenantName } = useAuthRole();
  const router = useRouter();
  const [email, setEmail] = useState<string>("");
  const [fullName, setFullName] = useState<string>("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    const loadUser = async () => {
      const { data } = await supabase.auth.getUser();
      const userEmail = data.user?.email ?? "";
      setEmail(userEmail);

      const metaName = data.user?.user_metadata?.full_name;
      if (metaName) {
        setFullName(metaName);
      } else {
        const parts = userEmail.split("@")[0].split(/[._-]/);
        const capitalized = parts.map((p: string) => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
        setFullName(capitalized || "User");
      }
    };
    loadUser();
  }, []);

  const logout = useLogout();
  const initials = email ? email.charAt(0).toUpperCase() : "U";
  const canAccessSettings =
    role === "owner" ||
    permissions.includes("settings.view") ||
    permissions.includes("settings.manage");

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-full py-0.5 pl-0.5 pr-1 transition-colors hover:bg-[#f0ece4]"
        title={tenantName ?? undefined}
      >
        <span
          className="flex items-center justify-center w-[34px] h-[34px] shrink-0 rounded-full text-white text-[12px] font-bold"
          style={{ background: "linear-gradient(135deg, #2e1065, #5b21b6)" }}
        >
          {initials}
        </span>
        {tenantName && (
          <span className="hidden max-w-[150px] truncate font-body text-sm font-semibold text-[#1c1917] sm:block">
            {tenantName}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 w-64 bg-white border border-[#e8e3db] rounded-2xl shadow-xl z-50 overflow-hidden py-1">
            <div className="flex items-center gap-3 px-4 py-3 border-b border-[#f0ece4]">
              <div className="flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-full bg-yellow-100 text-yellow-800 font-bold text-sm">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-[#1c1917] truncate">{tenantName || fullName}</p>
                <p className="text-xs text-[#78716c] truncate">{email}</p>
              </div>
            </div>

            <div className="py-1">
              {canAccessSettings && (
                <button
                  onClick={() => {
                    setOpen(false);
                    router.push("/dashboard/settings");
                  }}
                  className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-[#292524] hover:bg-[#faf8f5] transition-colors text-left"
                >
                  <Settings size={16} className="text-[#78716c]" />
                  <span className="flex-1">Settings</span>
                </button>
              )}

              <button
                className="w-full flex items-center justify-between gap-2.5 px-4 py-2.5 text-sm text-[#292524] hover:bg-[#faf8f5] transition-colors text-left"
                onClick={() => {}}
              >
                <div className="flex items-center gap-2.5">
                  <Monitor size={16} className="text-[#78716c]" />
                  <span>Theme</span>
                </div>
                <ChevronRight size={14} className="text-[#a8a29e]" />
              </button>
            </div>

            <div className="border-t border-[#f0ece4] my-1" />

            <div className="py-1">
              <button onClick={logout} className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-[#292524] hover:bg-[#faf8f5] transition-colors text-left">
                <LogOut size={16} className="text-[#78716c]" />
                <span>Sign out</span>
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
