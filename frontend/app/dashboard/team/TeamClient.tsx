"use client";
import { useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  UserPlus, Loader2, ClipboardList, TrendingUp,
} from "lucide-react";
import { api, TeamMember, Caller } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { useCallers } from "@/hooks/useApi";

import AssignmentLog from "../telecalling/components/assignment-log";
import PerformanceView from "../telecalling/components/performance-view";

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
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOwner = role === "owner" || fallbackTeam !== null;

  const { data: callersData, mutate: mutateCallers } = useCallers(
    isOwner,
    fallbackCallers ?? undefined
  );

  const callers = callersData ?? [];

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
    setInviting(true);
    setError(null);
    try {
      await api.team.invite(email.trim(), password.trim(), name.trim() || undefined, phone.trim() || undefined, telecmiAgentId.trim() || undefined);
      setEmail(""); setPassword(""); setName(""); setPhone(""); setTelecmiAgentId("");
      setShowInvite(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create telecaller");
    } finally {
      setInviting(false);
    }
  }

  return (
    <div>
      {showInvite && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-card-hover w-full max-w-md p-6">
            <h2 className="font-display font-bold text-ink mb-4" style={{ fontSize: "1.05rem" }}>Add Telecaller</h2>
            {error && <div className="mb-4 p-3 rounded-xl bg-red-50 text-red-700 font-body text-sm">{error}</div>}
            <form onSubmit={handleInvite} className="space-y-3">
              <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">Email *</label><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="input" placeholder="telecaller@example.com" /></div>
              <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">Password *</label><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required className="input" placeholder="Set a password for them" /></div>
              <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">Name</label><input type="text" value={name} onChange={(e) => setName(e.target.value)} className="input" placeholder="Ravi Kumar" /></div>
              <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">Phone</label><input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} className="input" placeholder="+919876543210" /></div>
              <div><label className="font-body text-sm font-medium text-ink mb-1.5 block">Telecmi Agent ID</label><input type="text" value={telecmiAgentId} onChange={(e) => setTelecmiAgentId(e.target.value)} className="input" placeholder="Agent ID for TeleCMI dialer" /></div>
              <div className="flex gap-3 pt-3">
                <button type="button" onClick={() => { setShowInvite(false); setError(null); }} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" disabled={inviting || !email.trim()} className="btn-primary flex-1">{inviting ? "Adding…" : "Add"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* View tabs and actions in a single line */}
      <div className="mb-6 flex items-center justify-between flex-wrap gap-4">
        <div className="p-1 bg-[#e8e3db]/60 rounded-2xl flex gap-1 self-start w-fit">
          <button onClick={() => setTab("performance")}
            className={`flex items-center gap-1.5 px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all ${
              tab === "performance" ? "bg-white text-indigo-600 shadow-sm" : "text-[#78716c] hover:text-[#292524]"
            }`}>
            <TrendingUp size={14} /> Team & Performance
          </button>
          <button onClick={() => setTab("log")}
            className={`flex items-center gap-1.5 px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all ${
              tab === "log" ? "bg-white text-indigo-600 shadow-sm" : "text-[#78716c] hover:text-[#292524]"
            }`}>
            <ClipboardList size={14} /> Assignment Log
          </button>
        </div>
        <button onClick={() => setShowInvite(true)} className="btn-primary">
          <UserPlus size={14} /> Add Telecaller
        </button>
      </div>

      {tab === "log" ? (
        <AssignmentLog callers={callers} />
      ) : (
        <PerformanceView callers={callers} />
      )}
    </div>
  );
}
