"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { API_URL } from "@/lib/api";

export default function OperatorLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const supabase = createClient();

    try {
      const { data, error: signInError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });

      if (signInError) throw new Error("Invalid email or password");

      const token = data.session?.access_token;
      if (!token) throw new Error("No session returned");

      const res = await fetch(`${API_URL}/api/v1/operator/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        await supabase.auth.signOut();
        setError("Access denied. This console is for Aira AI operators only.");
        return;
      }

      const me = await res.json();

      if (!me.is_system_admin) {
        await supabase.auth.signOut();
        setError("Access denied. This console is for Aira AI operators only.");
        return;
      }

      router.push("/operator");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <p className="text-2xl font-bold text-[#1c1917] font-manrope">
            Aira<span className="text-[#5b21b6]">AI</span>
          </p>
          <p className="text-xs text-[#a8a29e] mt-1.5 uppercase tracking-widest font-semibold font-manrope">
            Operator Console
          </p>
        </div>

        <div className="bg-white rounded-[1.25rem] shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)] border border-[#e8e3db] p-8">
          <form onSubmit={handleLogin} className="space-y-4">
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 font-manrope">
                {error}
              </div>
            )}
            <div>
              <label className="text-sm font-medium text-[#1c1917] block mb-1.5 font-manrope">Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoFocus
                className="input"
                placeholder="you@airaai.com"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-[#1c1917] block mb-1.5 font-manrope">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="input"
                placeholder="••••••••"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full justify-center mt-2 disabled:opacity-50"
            >
              {loading ? "Verifying..." : "Sign in"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-[#a8a29e] mt-6 font-manrope">
          Client dashboard?{" "}
          <a href="/login" className="text-[#5b21b6] hover:underline">Login here</a>
        </p>
      </div>
    </div>
  );
}
