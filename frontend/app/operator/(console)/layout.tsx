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
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold text-gray-900">
            Aira <span className="text-indigo-600">AI</span>
          </span>
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-widest border border-gray-200 rounded px-2 py-0.5">
            Operator Console
          </span>
          <nav className="flex items-center gap-1 ml-4">
            <a href="/operator" className="text-sm text-gray-500 hover:text-gray-900 px-3 py-1.5 rounded-lg hover:bg-gray-100">
              Clients
            </a>
            <a href="/operator/scheduler" className="text-sm text-gray-500 hover:text-gray-900 px-3 py-1.5 rounded-lg hover:bg-gray-100">
              Schedulers
            </a>
          </nav>
        </div>
        <a href="/login" className="text-sm text-gray-500 hover:text-gray-800">
          ← Back to Client Login
        </a>
      </header>
      <main className="max-w-5xl mx-auto px-8 py-8">{children}</main>
    </div>
  );
}
