"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, User } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { useLogout } from "@/hooks/useLogout";

export function ProfileMenu() {
  const { role } = useAuthRole();
  const router = useRouter();
  const [email, setEmail] = useState<string>("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    const loadUser = async () => {
      const { data } = await supabase.auth.getUser();
      setEmail(data.user?.email ?? "");
    };
    loadUser();
  }, []);

  const roleLabel = role === "owner" ? "Admin" : role === "caller" ? "Telecaller" : "";

  const logout = useLogout();

  const initials = email ? email.charAt(0).toUpperCase() : "U";

  return (
    <div className="relative">
      <button onClick={() => setOpen((v) => !v)} className="flex items-center justify-center w-[34px] h-[34px] rounded-full text-white text-[12px] font-bold transition-transform hover:scale-105" style={{ background: "linear-gradient(135deg, #2e1065, #5b21b6)" }}>
        {initials}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 w-56 bg-white border border-[#e8e3db]/80 rounded-2xl shadow-xl z-50 overflow-hidden">
            <div className="px-4 py-3 border-b border-[#f0ece4]">
              <p className="text-xs font-bold text-[#292524] truncate">{email || "Account"}</p>
              <p className="text-[10px] text-[#a8a29e] mt-0.5">{roleLabel}</p>
            </div>
            <button onClick={() => { setOpen(false); router.push("/dashboard/profile"); }} className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-[#44403c] hover:bg-[#faf8f5] text-left"><User size={15} /> Profile</button>
            <button onClick={logout} className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-rose-600 hover:bg-rose-50 text-left"><LogOut size={15} /> Sign out</button>
          </div>
        </>
      )}
    </div>
  );
}
