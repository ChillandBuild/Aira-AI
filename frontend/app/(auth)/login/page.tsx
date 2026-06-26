"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Eye, EyeOff, Bot, Target, TrendingUp } from "lucide-react";
import { AiraLogo } from "@/components/logo";
import BackgroundAnimation from "@/components/BackgroundAnimation";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setError(error.message);
      setLoading(false);
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <div className="min-h-screen w-full flex flex-col lg:flex-row bg-[#faf8f5] relative overflow-hidden">
      {/* Left Column: Visual/Branding panel (visible on desktop) */}
      <div className="hidden lg:flex lg:w-1/2 lg:h-screen lg:sticky lg:top-0 bg-gradient-to-br from-[#2e1065] to-[#5b21b6] p-10 lg:pt-12 lg:pb-8 lg:px-16 flex-col justify-between text-white relative z-10 overflow-hidden select-none">
        {/* Subtle background glow decorative elements */}
        <div className="absolute -top-40 -left-40 w-96 h-96 rounded-full bg-[#7c3aed] opacity-20 blur-[120px] pointer-events-none"></div>
        <div className="absolute -bottom-40 -right-20 w-96 h-96 rounded-full bg-[#c084fc] opacity-20 blur-[100px] pointer-events-none"></div>

        <div>
          <AiraLogo className="text-white h-7 w-auto" />
        </div>

        <div className="space-y-6 lg:space-y-8 my-auto">
          <div className="space-y-4">
            <h2 className="text-5xl font-bold tracking-tight text-white leading-tight font-display">
              Automate.<br />
              <span className="text-[#a78bfa] bg-clip-text">Convert.</span><br />
              Grow.
            </h2>
            <p className="text-white/80 text-sm max-w-sm leading-relaxed font-body">
              The ultimate AI revenue acceleration engine. Capture every enquiry, qualify prospects instantly, and optimize telecaller performance automatically.
            </p>
          </div>

          {/* Bento-style feature cards */}
          <div className="grid gap-4 max-w-md">
            <div className="flex items-start gap-4 p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm transition-all hover:bg-white/10 hover:border-white/20 group">
              <div className="p-2.5 rounded-xl bg-white/10 text-white group-hover:scale-105 transition-transform">
                <Bot size={20} />
              </div>
              <div>
                <h4 className="font-semibold text-white text-sm font-label">Automate Conversations</h4>
                <p className="text-white/60 text-xs mt-0.5 font-body">Capture WhatsApp and web enquiries instantly, 24/7 without delays.</p>
              </div>
            </div>

            <div className="flex items-start gap-4 p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm transition-all hover:bg-white/10 hover:border-white/20 group">
              <div className="p-2.5 rounded-xl bg-white/10 text-[#a78bfa] group-hover:scale-105 transition-transform">
                <Target size={20} />
              </div>
              <div>
                <h4 className="font-semibold text-[#a78bfa] text-sm font-label font-bold">Convert Hot Leads</h4>
                <p className="text-white/60 text-xs mt-0.5 font-body">Verify signatures, score intent, and route qualified leads instantly.</p>
              </div>
            </div>

            <div className="flex items-start gap-4 p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm transition-all hover:bg-white/10 hover:border-white/20 group">
              <div className="p-2.5 rounded-xl bg-white/10 text-white group-hover:scale-105 transition-transform">
                <TrendingUp size={20} />
              </div>
              <div>
                <h4 className="font-semibold text-white text-sm font-label">Grow Revenue Pipeline</h4>
                <p className="text-white/60 text-xs mt-0.5 font-body">Monitor voice logs, evaluate telecallers, and drive business growth.</p>
              </div>
            </div>
          </div>
        </div>

        <div className="text-white/40 text-xs font-body flex items-center justify-between">
          <span>© {new Date().getFullYear()} Aira AI. All rights reserved.</span>
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            Platform Operational
          </span>
        </div>
      </div>

      {/* Right Column: Centered Login Form with canvas animation */}
      <div className="flex-1 flex flex-col justify-center items-center p-6 sm:p-12 relative min-h-screen">
        <BackgroundAnimation />

        <div className="w-full max-w-sm relative z-10">
          {/* Mobile logo header (hidden on desktop) */}
          <div className="lg:hidden flex flex-col items-center mb-8">
            <AiraLogo className="h-7 w-auto text-ink mb-2" />
            <p className="text-[10px] tracking-[0.15em] font-semibold text-ink-muted uppercase flex items-center gap-1.5 font-label">
              Automate <span className="w-1 h-1 rounded-full bg-stone-300"></span> <span className="text-primary">Convert</span> <span className="w-1 h-1 rounded-full bg-stone-300"></span> Grow
            </p>
          </div>

          {/* Login Card */}
          <div className="card rounded-3xl p-8 backdrop-blur-sm bg-white/90 shadow-2xl border border-stone-200/50">
            <div className="mb-6">
              <h3 className="font-display text-2xl font-bold text-ink">Welcome back</h3>
              <p className="font-body text-sm text-ink-muted mt-1">Sign in to your account</p>
            </div>

            {error && (
              <div className="mb-4 p-3 rounded-xl bg-red-50 text-red-700 font-body text-sm border border-red-100">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="font-body text-sm font-medium text-ink mb-1.5 block">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="input"
                  placeholder="you@example.com"
                />
              </div>
              <div>
                <label className="font-body text-sm font-medium text-ink mb-1.5 block">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="input pr-10"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink transition-colors"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>
              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full justify-center"
              >
                {loading ? "Signing in…" : "Sign in"}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
