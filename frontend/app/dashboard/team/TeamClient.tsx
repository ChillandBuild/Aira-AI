"use client";
import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  UserPlus, Loader2, ClipboardList, TrendingUp,
} from "lucide-react";
import { api, TeamMember, Caller } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { useCallers } from "@/hooks/useApi";

import AssignmentLog from "../telecalling/components/assignment-log";
import PerformanceView from "../telecalling/components/performance-view";
import WinnerBanner from "./WinnerBanner";

/* ──────────────────────────── Main Client Component ──────────────────────────── */
interface TeamClientProps {
  fallbackTeam: { data: TeamMember[] } | null;
  fallbackCallers: Caller[] | null;
}

export function TeamClient({ fallbackTeam, fallbackCallers }: TeamClientProps) {
  const { role, loading: roleLoading } = useAuthRole();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab = (rawTab === "log" ? "log" : "performance") as "performance" | "log";

  const setTab = (val: "performance" | "log") => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", val);
    router.replace(`/dashboard/team?${params.toString()}`, { scroll: false });
  };

  // invite
  const [showInvite, setShowInvite] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [telecmiAgentId, setTelecmiAgentId] = useState("");
  const [telecmiAgentPassword, setTelecmiAgentPassword] = useState("");
  const [callingProvider, setCallingProvider] = useState<"telecmi" | "sim_basic">("telecmi");
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOwner = role === "owner" || fallbackTeam !== null;

  const { data: callersData, mutate: mutateCallers } = useCallers(
    isOwner,
    fallbackCallers ?? undefined
  );

  const callers = callersData?.data ?? [];
  const adminCaller = callersData?.admin_caller ?? null;

  useEffect(() => {
    if (!isOwner) return;
    api.settings.getTelecallingConfig()
      .then((cfg) => setCallingProvider((cfg.calling_provider as "telecmi" | "sim_basic" | undefined) ?? "telecmi"))
      .catch(() => setCallingProvider("telecmi"));
  }, [isOwner]);

  async function load() {
    await mutateCallers();
  }

  if (roleLoading && !fallbackTeam) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (!isOwner) {
    return (
      <div className="text-center py-20">
        <p className="text-ink-muted font-body">This section is only available for owners/admins.</p>
      </div>
    );
  }

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password.trim()) return;
    if (callingProvider === "sim_basic" && !phone.trim()) {
      setError("Phone number is required for SIM Basic telecallers");
      return;
    }
    if (callingProvider === "telecmi" && (!telecmiAgentId.trim() || !telecmiAgentPassword.trim())) {
      setError("TeleCMI agent ID and password are required for TeleCMI telecallers");
      return;
    }
    setInviting(true);
    setError(null);
    try {
      await api.team.invite(
        email.trim(),
        password.trim(),
        name.trim() || undefined,
        phone.trim() || undefined,
        callingProvider === "telecmi" ? telecmiAgentId.trim() : undefined,
        callingProvider === "telecmi" ? telecmiAgentPassword.trim() : undefined,
      );
      setEmail(""); setPassword(""); setName(""); setPhone(""); setTelecmiAgentId(""); setTelecmiAgentPassword("");
      setShowInvite(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create telecaller");
    } finally {
      setInviting(false);
    }
  }

  return (
    <div className="min-w-0">
      {showInvite && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-card-hover w-full max-w-md p-6">
            <h2 className="font-display font-bold text-ink mb-4" style={{ fontSize: "1.05rem" }}>Add Telecaller</h2>
            <div className="mb-4 rounded-2xl border border-primary-muted bg-primary-light/60 px-4 py-3">
              <p className="font-label text-[10px] font-black uppercase tracking-wider text-primary">Calling Provider</p>
              <p className="mt-0.5 font-body text-sm font-semibold text-ink">
                {callingProvider === "sim_basic" ? "SIM Basic" : "TeleCMI"}
              </p>
            </div>
            {error && <div className="mb-4 p-3 rounded-xl bg-red-50 text-red-700 font-body text-sm">{error}</div>}
            <form onSubmit={handleInvite} className="space-y-3">
              <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">Email *</label><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="input" placeholder="telecaller@example.com" /></div>
              <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">Password *</label><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required className="input" placeholder="Set a password for them" /></div>
              <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">Name</label><input type="text" value={name} onChange={(e) => setName(e.target.value)} className="input" placeholder="Ravi Kumar" /></div>
              <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">Phone{callingProvider === "sim_basic" ? " *" : ""}</label><input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} className="input" placeholder="+919876543210" /></div>
              {callingProvider === "telecmi" && (
                <>
                  <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">TeleCMI Agent ID *</label><input type="text" value={telecmiAgentId} onChange={(e) => setTelecmiAgentId(e.target.value)} className="input" placeholder="Agent ID for TeleCMI dialer" /></div>
                  <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">TeleCMI Agent Password *</label><input type="password" value={telecmiAgentPassword} onChange={(e) => setTelecmiAgentPassword(e.target.value)} className="input" placeholder="Agent password" /></div>
                </>
              )}
              <div className="flex gap-3 pt-3">
                <button type="button" onClick={() => { setShowInvite(false); setError(null); }} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" disabled={inviting || !email.trim()} className="btn-primary flex-1">{inviting ? "Adding…" : "Add"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* View tabs and actions in a single line */}
      <div className="mb-5 flex min-w-0 flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="-mx-1 overflow-x-auto px-1 pb-1 sm:mx-0 sm:overflow-visible sm:p-0">
        <div className="flex w-max gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 sm:w-fit">
          <button onClick={() => setTab("performance")}
            className={`flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5 ${
              tab === "performance" ? "bg-white text-primary shadow-sm" : "text-[#78716c] hover:text-[#292524]"
            }`}>
            <TrendingUp size={14} /> Team & Performance
          </button>
          <button onClick={() => setTab("log")}
            className={`flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5 ${
              tab === "log" ? "bg-white text-primary shadow-sm" : "text-[#78716c] hover:text-[#292524]"
            }`}>
            <ClipboardList size={14} /> Assignment Log
          </button>
        </div>
        </div>
        <button onClick={() => setShowInvite(true)} className="btn-primary w-full justify-center sm:w-auto">
          <UserPlus size={14} /> Add Telecaller
        </button>
      </div>

      <WinnerBanner />

      {tab === "log" ? (
        <AssignmentLog callers={callers} />
      ) : (
        <PerformanceView callers={callers} adminCaller={adminCaller} />
      )}
    </div>
  );
}
