"use client";
import { Users, Activity, MessageSquare, Clock } from "lucide-react";
import { StatCard } from "../components/stat-card";

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.abs(diff) / 1000;
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

interface Stats {
  total_leads: number; active_leads: number;
  messages_sent_30d: number; messages_received_30d: number;
  team_members: number; last_activity: string | null;
}

export function OverviewView({ stats }: { stats: Stats }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
      <StatCard icon={<Users size={18} />} label="Total Leads" value={stats.total_leads} />
      <StatCard icon={<Activity size={18} />} label="Active Leads (A+B)" value={stats.active_leads} />
      <StatCard icon={<MessageSquare size={18} />} label="Msgs Sent (30d)" value={stats.messages_sent_30d} />
      <StatCard icon={<MessageSquare size={18} />} label="Msgs Received (30d)" value={stats.messages_received_30d} />
      <StatCard icon={<Users size={18} />} label="Team Members" value={stats.team_members} />
      <StatCard icon={<Clock size={18} />} label="Last Activity" value={stats.last_activity ? relTime(stats.last_activity) : "—"} />
    </div>
  );
}
