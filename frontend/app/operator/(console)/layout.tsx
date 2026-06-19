import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function OperatorLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/operator/login");

  const { data: { session } } = await supabase.auth.getSession();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    const meRes = await fetch(`${apiUrl}/api/v1/operator/me`, {
      headers: { Authorization: `Bearer ${session?.access_token}` },
      cache: "no-store",
    });
    if (meRes.ok) {
      const me = await meRes.json();
      if (!me.is_system_admin) redirect("/dashboard");
    } else {
      redirect("/dashboard");
    }
  } catch {
    redirect("/dashboard");
  }

  return (
    <div
      className="min-h-screen relative"
      style={{
        background: "linear-gradient(135deg, #050816 0%, #0a1628 30%, #0d1f3c 60%, #0a0e27 100%)",
      }}
    >
      {/* Aurora ambient glow */}
      <div
        className="pointer-events-none fixed inset-0 z-0"
        style={{
          background:
            "radial-gradient(ellipse at 20% 0%, rgba(6,182,212,0.10) 0%, transparent 50%)," +
            "radial-gradient(ellipse at 80% 0%, rgba(139,92,246,0.08) 0%, transparent 50%)," +
            "radial-gradient(ellipse at 50% 0%, rgba(16,185,129,0.06) 0%, transparent 40%)",
        }}
      />

      {/* Header */}
      <header className="sticky top-0 z-30 bg-white/[0.03] backdrop-blur-2xl border-b border-white/[0.06] px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold text-white">
            Aira{" "}
            <span className="bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-transparent">
              AI
            </span>
          </span>
          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest border border-white/[0.1] rounded px-2 py-0.5">
            Operator Console
          </span>
          <nav className="flex items-center gap-1 ml-4">
            <a
              href="/operator"
              className="text-sm text-slate-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/[0.06] transition-all duration-200"
            >
              Clients
            </a>
            <a
              href="/operator/scheduler"
              className="text-sm text-slate-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/[0.06] transition-all duration-200"
            >
              Schedulers
            </a>
          </nav>
        </div>
        <a
          href="/login"
          className="text-sm text-slate-500 hover:text-slate-300 transition-colors duration-200"
        >
          ← Back to Client Login
        </a>
      </header>

      <main className="relative z-10 max-w-6xl mx-auto px-8 py-8">{children}</main>
    </div>
  );
}
