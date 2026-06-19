import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function OperatorLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/operator/login");

  const { data: { session } } = await supabase.auth.getSession();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  let isSystemAdmin = false;
  try {
    const meRes = await fetch(`${apiUrl}/api/v1/operator/me`, {
      headers: { Authorization: `Bearer ${session?.access_token}` },
      cache: "no-store",
    });
    if (meRes.ok) {
      const me = await meRes.json();
      isSystemAdmin = !!me.is_system_admin;
    }
  } catch (e) {
    console.error("Failed to verify system admin status:", e);
  }

  if (!isSystemAdmin) {
    redirect("/dashboard");
  }

  return (
    <div className="min-h-screen bg-[#faf8f5] relative font-manrope">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-[#e8e3db] px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold text-[#1c1917]">
            Aira{" "}
            <span className="text-[#5b21b6]">
              AI
            </span>
          </span>
          <span className="text-[10px] font-semibold text-[#78716c] uppercase tracking-widest border border-[#e8e3db] bg-[#f0ece4]/40 rounded px-2 py-0.5">
            Operator Console
          </span>
          <nav className="flex items-center gap-1 ml-4">
            <a
              href="/operator"
              className="text-sm text-[#78716c] hover:text-[#1c1917] px-3 py-1.5 rounded-lg hover:bg-[#f0ece4]/50 transition-all duration-200"
            >
              Clients
            </a>
            <a
              href="/operator/scheduler"
              className="text-sm text-[#78716c] hover:text-[#1c1917] px-3 py-1.5 rounded-lg hover:bg-[#f0ece4]/50 transition-all duration-200"
            >
              Schedulers
            </a>
          </nav>
        </div>
        <a
          href="/login"
          className="text-sm text-[#a8a29e] hover:text-[#78716c] transition-colors duration-200"
        >
          ← Back to Client Login
        </a>
      </header>

      <main className="relative z-10 max-w-6xl mx-auto px-8 py-8">{children}</main>
    </div>
  );
}
