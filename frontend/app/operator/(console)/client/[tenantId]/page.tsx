"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { 
  ArrowLeft, LayoutDashboard, MessageSquare, Users, Phone, 
  BarChart2, Upload, BookOpen, Layers, FileCheck, Inbox,
  Settings, Save, Activity, Shield, AlertTriangle, CheckCircle,
  XCircle, ChevronDown, ChevronRight, Check
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

type ServiceTier = string;

// Types
type ClientDetail = {
  id: string;
  name: string;
  enabled_features: string[];
  status: string;
  created_at: string;
};

type SettingsSummary = {
  key: string;
  has_value: boolean;
  is_secret: boolean;
};

type DataCounts = {
  leads: number;
  messages: number;
  conversations: number;
  call_logs: number;
  broadcast_recipients: number;
  scheduled_broadcasts: number;
  knowledge_documents: number;
  templates: number;
  bookings: number;
  notes: number;
  todos: number;
  callers: number;
  team_members: number;
};

type TeamMember = {
  user_id: string;
  role: string;
  created_at: string;
};

type Caller = {
  id: string;
  name: string;
  active: boolean;
  overall_score: number;
  created_at: string;
};

type AuditEntry = {
  id: string;
  actor_role: string;
  action: string;
  metadata: any;
  created_at: string;
};

const SERVICE_LABELS: Record<string, string> = {
  whatsapp_only: "WhatsApp Only",
  telecalling_only: "Telecalling Only",
  combined: "WhatsApp + Telecalling",
  whatsapp_instagram: "WhatsApp + Instagram",
  whatsapp_facebook: "WhatsApp + Facebook",
  whatsapp_telegram: "WhatsApp + Telegram",
  omnichannel: "Omnichannel (WA + IG + FB + TG)",
  omnichannel_telecalling: "Omnichannel + Telecalling",
};

function featuresToService(features: string[]): string {
  const has = (f: string) => features.includes(f);
  const wa = has("whatsapp"), tc = has("telecalling");
  const ig = has("instagram"), fb = has("facebook"), tg = has("telegram");
  if (wa && tc && ig && fb && tg) return "omnichannel_telecalling";
  if (wa && ig && fb && tg) return "omnichannel";
  if (wa && ig) return "whatsapp_instagram";
  if (wa && fb) return "whatsapp_facebook";
  if (wa && tg) return "whatsapp_telegram";
  if (wa && tc) return "combined";
  if (wa) return "whatsapp_only";
  if (tc) return "telecalling_only";
  return "combined";
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...auth, ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

export default function ClientDetailPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;

  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [client, setClient] = useState<ClientDetail | null>(null);
  const [ownerEmail, setOwnerEmail] = useState<string | null>(null);
  const [settings, setSettings] = useState<SettingsSummary[]>([]);
  const [counts, setCounts] = useState<DataCounts | null>(null);
  
  // Feature Toggles state
  const [pageToggles, setPageToggles] = useState<any>(null);
  const [editedToggles, setEditedToggles] = useState<any>(null);
  const [savingToggles, setSavingToggles] = useState(false);
  
  // Expanded sections in toggles
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    knowledge: true, analytics: true, team: true, telecalling: true, settings: true
  });

  // Other tabs data
  const [teamData, setTeamData] = useState<{users: TeamMember[], callers: Caller[]} | null>(null);
  const [activityData, setActivityData] = useState<any>(null);
  const [auditData, setAuditData] = useState<AuditEntry[]>([]);

  // Danger zone state
  const [wipingSection, setWipingSection] = useState<string | null>(null);

  useEffect(() => {
    async function loadAll() {
      setLoading(true);
      try {
        const [detailRes, countsRes, togglesRes, teamRes, activityRes, auditRes] = await Promise.all([
          apiFetch<any>(`/api/v1/operator/clients/${tenantId}/detail`),
          apiFetch<DataCounts>(`/api/v1/operator/clients/${tenantId}/data-counts`),
          apiFetch<any>(`/api/v1/operator/clients/${tenantId}/page-toggles`),
          apiFetch<any>(`/api/v1/operator/clients/${tenantId}/team`),
          apiFetch<any>(`/api/v1/operator/clients/${tenantId}/activity`),
          apiFetch<any>(`/api/v1/operator/clients/${tenantId}/audit-log`)
        ]);

        setClient(detailRes.tenant);
        setOwnerEmail(detailRes.owner_email);
        setSettings(detailRes.settings_summary);
        setCounts(countsRes);
        
        // Initialize toggles (default all to true if null)
        const initialToggles = togglesRes.page_toggles || {
          dashboard: true, inbox: true, conversations: true, segments: true, 
          inbound_leads: true, outbound_leads: true, templates: true, numbers_pool: true, bookings: true,
          knowledge: { enabled: true, documents: true, ai_tune: true },
          analytics: { enabled: true, overview: true, channels: true, inbound: true, templates: true },
          team: { enabled: true, performance: true, attendance: true, assignment_log: true },
          telecalling: { enabled: true, upload: true, dialer: true, scheduled: true, notes: true },
          settings: { enabled: true, general: true, channels: true, telecalling_config: true, inbox_config: true }
        };
        setPageToggles(initialToggles);
        setEditedToggles(JSON.parse(JSON.stringify(initialToggles))); // deep copy

        setTeamData(teamRes);
        setActivityData(activityRes);
        setAuditData(auditRes.entries);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load client data");
      } finally {
        setLoading(false);
      }
    }
    loadAll();
  }, [tenantId]);

  const hasTogglesChanged = JSON.stringify(pageToggles) !== JSON.stringify(editedToggles);

  async function handleSaveToggles() {
    setSavingToggles(true);
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/page-toggles`, {
        method: "PATCH",
        body: JSON.stringify({ page_toggles: editedToggles })
      });
      setPageToggles(JSON.parse(JSON.stringify(editedToggles)));
      alert("Feature toggles saved successfully.");
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to save toggles");
    } finally {
      setSavingToggles(false);
    }
  }

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({...prev, [section]: !prev[section]}));
  };

  const updateToggle = (path: string[], value: boolean) => {
    const newToggles = { ...editedToggles };
    if (path.length === 1) {
      newToggles[path[0]] = value;
    } else {
      newToggles[path[0]] = { ...newToggles[path[0]], [path[1]]: value };
    }
    setEditedToggles(newToggles);
  };

  const CustomToggle = ({ checked, onChange, disabled = false }: { checked: boolean, onChange: (c: boolean) => void, disabled?: boolean }) => (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
        disabled ? 'opacity-50 cursor-not-allowed' : ''
      } ${checked ? 'bg-gradient-to-r from-cyan-500 to-emerald-500' : 'bg-slate-700'}`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  );

  async function handleWipe(endpoint: string, sectionName: string) {
    if (!client) return;
    if (!confirm(`⚠️ WARNING: You are about to permanently delete all ${sectionName} for ${client.name}.\n\nThis cannot be undone. Are you sure?`)) return;
    const confirmName = prompt(`Please type the client name "${client.name}" to confirm:`);
    if (confirmName !== client.name) {
      alert("Name did not match. Aborting.");
      return;
    }

    setWipingSection(endpoint);
    try {
      const res = await apiFetch<any>(`/api/v1/operator/clients/${tenantId}/${endpoint}`, { method: "POST" });
      alert(`Successfully wiped ${sectionName}.\n\nDeleted records:\n${Object.entries(res.deleted).map(([k,v]) => `${k}: ${v}`).join('\n')}`);
      // Refresh counts
      const countsRes = await apiFetch<DataCounts>(`/api/v1/operator/clients/${tenantId}/data-counts`);
      setCounts(countsRes);
    } catch (e) {
      alert(e instanceof Error ? e.message : `Failed to wipe ${sectionName}`);
    } finally {
      setWipingSection(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-cyan-500 flex flex-col items-center">
          <div className="w-8 h-8 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin mb-4"></div>
          <span className="text-slate-400 font-medium">Loading client details...</span>
        </div>
      </div>
    );
  }

  if (error || !client) {
    return (
      <div className="p-6 bg-red-500/[0.06] border border-red-500/20 rounded-2xl text-red-400 backdrop-blur-md">
        <h2 className="text-xl font-bold mb-2">Error Loading Client</h2>
        <p>{error || "Client not found."}</p>
        <button onClick={() => router.push('/operator')} className="mt-4 px-4 py-2 bg-white/[0.05] rounded-xl hover:bg-white/[0.1] transition-colors text-white">
          Return to Clients
        </button>
      </div>
    );
  }

  const tabs = [
    { id: "overview", label: "Overview", icon: LayoutDashboard },
    { id: "toggles", label: "Feature Toggles", icon: Settings },
    { id: "settings", label: "Config", icon: Shield },
    { id: "team", label: "Team", icon: Users },
    { id: "activity", label: "Activity", icon: Activity },
    { id: "audit", label: "Audit Log", icon: FileCheck },
    { id: "danger", label: "Danger Zone", icon: AlertTriangle, isDanger: true }
  ];

  const getSetting = (key: string) => settings?.find(s => s.key === key);
  const isSettingSet = (key: string) => getSetting(key)?.has_value ?? false;

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <button 
          onClick={() => router.push('/operator')}
          className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors mb-4"
        >
          <ArrowLeft size={16} /> Back to Clients
        </button>
        
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
              {client.name}
              <span className={`text-xs px-2.5 py-1 rounded-md font-medium border ${
                client.status === "active" 
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" 
                  : "bg-red-500/10 text-red-400 border-red-500/20"
              }`}>
                {client.status.toUpperCase()}
              </span>
            </h1>
            <div className="flex items-center gap-4 mt-2 text-sm">
              <span className="text-slate-400 font-mono bg-white/[0.05] px-2 py-0.5 rounded">ID: {client.id}</span>
              <span className="text-slate-400">{ownerEmail || "No owner email"}</span>
              <span className="text-slate-400">Created {new Date(client.created_at).toLocaleDateString()}</span>
            </div>
          </div>
          
          <div className="bg-cyan-500/10 border border-cyan-500/20 px-4 py-2 rounded-xl">
            <p className="text-xs text-cyan-500/70 uppercase tracking-wider font-semibold mb-0.5">Service Package</p>
            <p className="text-sm font-medium text-cyan-400">{SERVICE_LABELS[featuresToService(client.enabled_features)] ?? "Custom"}</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex overflow-x-auto gap-2 mb-6 pb-2 scrollbar-none">
        {tabs.map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all whitespace-nowrap
                ${isActive 
                  ? (tab.isDanger ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-gradient-to-r from-cyan-500/20 to-violet-500/20 text-white border border-white/[0.1]') 
                  : (tab.isDanger ? 'text-red-400/70 hover:bg-red-500/10 hover:text-red-400' : 'text-slate-400 hover:text-white hover:bg-white/[0.05]')
                }`}
            >
              <Icon size={16} />
              {tab.label}
              {tab.isDanger && <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse ml-1"></span>}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="min-h-[400px]">
        
        {/* OVERVIEW TAB */}
        {activeTab === "overview" && counts && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-gradient-to-br from-cyan-500/10 to-violet-500/10 backdrop-blur-xl border border-white/[0.08] rounded-2xl p-5">
                <p className="text-sm text-slate-400 mb-1">Total Leads</p>
                <p className="text-3xl font-bold text-white">{counts.leads.toLocaleString()}</p>
              </div>
              <div className="bg-gradient-to-br from-cyan-500/10 to-violet-500/10 backdrop-blur-xl border border-white/[0.08] rounded-2xl p-5">
                <p className="text-sm text-slate-400 mb-1">Messages</p>
                <p className="text-3xl font-bold text-white">{counts.messages.toLocaleString()}</p>
              </div>
              <div className="bg-gradient-to-br from-cyan-500/10 to-violet-500/10 backdrop-blur-xl border border-white/[0.08] rounded-2xl p-5">
                <p className="text-sm text-slate-400 mb-1">Call Logs</p>
                <p className="text-3xl font-bold text-white">{counts.call_logs.toLocaleString()}</p>
              </div>
              <div className="bg-gradient-to-br from-cyan-500/10 to-violet-500/10 backdrop-blur-xl border border-white/[0.08] rounded-2xl p-5">
                <p className="text-sm text-slate-400 mb-1">Team & Callers</p>
                <p className="text-3xl font-bold text-white">{counts.team_members + counts.callers}</p>
              </div>
            </div>

            <h3 className="text-lg font-semibold text-white mt-8 mb-4">Integration Health</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { name: "WhatsApp (Meta)", connected: isSettingSet("meta_phone_number_id") && isSettingSet("meta_access_token") },
                { name: "Telecalling (TeleCMI)", connected: isSettingSet("telecmi_user_id") && isSettingSet("telecmi_secret") },
                { name: "Groq AI", connected: isSettingSet("groq_api_key") },
                { name: "Payments (Razorpay)", connected: isSettingSet("razorpay_key_id") }
              ].map(int => (
                <div key={int.name} className="bg-white/[0.02] border border-white/[0.08] rounded-xl p-4 flex items-center justify-between">
                  <span className="text-slate-300 font-medium">{int.name}</span>
                  {int.connected ? (
                    <span className="flex items-center gap-1.5 text-sm text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-md border border-emerald-500/20">
                      <CheckCircle size={14} /> Connected
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-sm text-slate-500 bg-white/[0.05] px-2.5 py-1 rounded-md border border-white/[0.05]">
                      <XCircle size={14} /> Not Configured
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* FEATURE TOGGLES TAB */}
        {activeTab === "toggles" && editedToggles && (
          <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden backdrop-blur-xl">
            <div className="p-6 border-b border-white/[0.08] flex items-center justify-between bg-black/20">
              <div>
                <h3 className="text-lg font-semibold text-white">Feature Toggles</h3>
                <p className="text-sm text-slate-400">Control which pages and sections are visible in the client's sidebar.</p>
              </div>
              <button 
                onClick={handleSaveToggles}
                disabled={!hasTogglesChanged || savingToggles}
                className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-cyan-500 to-violet-500 text-white text-sm font-semibold rounded-xl disabled:opacity-50 disabled:grayscale transition-all"
              >
                <Save size={16} /> {savingToggles ? "Saving..." : "Save Changes"}
              </button>
            </div>
            
            <div className="p-2 space-y-1">
              {/* Simple toggles */}
              {[
                { id: "dashboard", label: "Dashboard Home", icon: LayoutDashboard },
                { id: "inbox", label: "Inbox (Chat Handovers)", icon: Inbox },
                { id: "conversations", label: "Conversations", icon: MessageSquare },
                { id: "segments", label: "Segments (Lead CRM)", icon: Users },
                { id: "inbound_leads", label: "Inbound Leads", icon: Inbox }, // TODO fix icon
                { id: "outbound_leads", label: "Outbound Leads & Broadcasts", icon: Upload },
                { id: "templates", label: "WhatsApp Templates", icon: FileCheck },
                { id: "numbers_pool", label: "Numbers Pool", icon: Layers },
                { id: "bookings", label: "Bookings", icon: BookOpen }
              ].map(item => (
                <div key={item.id} className="flex items-center justify-between p-4 hover:bg-white/[0.02] rounded-xl transition-colors">
                  <div className="flex items-center gap-3 text-slate-300">
                    <item.icon size={18} className="text-slate-500" />
                    <span className="font-medium">{item.label}</span>
                  </div>
                  <CustomToggle checked={editedToggles[item.id] ?? true} onChange={(v) => updateToggle([item.id], v)} />
                </div>
              ))}

              {/* Nested toggles */}
              {[
                { id: "knowledge", label: "Knowledge Base", icon: BookOpen, subs: [{ id: "documents", label: "Knowledge Documents" }, { id: "ai_tune", label: "AI Tuning & Prompts" }] },
                { id: "analytics", label: "Analytics", icon: BarChart2, subs: [{ id: "overview", label: "Analytics Overview" }, { id: "channels", label: "Channel Analytics" }, { id: "inbound", label: "Inbound Analytics" }, { id: "templates", label: "Template Performance" }] },
                { id: "team", label: "Team", icon: Users, subs: [{ id: "performance", label: "Team Performance" }, { id: "attendance", label: "Attendance Management" }, { id: "assignment_log", label: "Assignment Log" }] },
                { id: "telecalling", label: "Telecalling", icon: Phone, subs: [{ id: "upload", label: "Lead Upload" }, { id: "dialer", label: "Dialer" }, { id: "scheduled", label: "Scheduled Calls" }, { id: "notes", label: "Call Notes" }] },
                { id: "settings", label: "Settings", icon: Settings, subs: [{ id: "general", label: "General Settings" }, { id: "channels", label: "Channel Configuration" }, { id: "telecalling_config", label: "Telecalling Configuration" }, { id: "inbox_config", label: "Inbox Configuration" }] }
              ].map(group => {
                const isGroupEnabled = editedToggles[group.id]?.enabled ?? true;
                const isExpanded = expandedSections[group.id];
                return (
                  <div key={group.id} className="border border-white/[0.04] rounded-xl overflow-hidden my-2">
                    <div className="flex items-center justify-between p-4 bg-white/[0.01] hover:bg-white/[0.03] transition-colors">
                      <div 
                        className="flex items-center gap-3 text-slate-300 cursor-pointer flex-1"
                        onClick={() => toggleSection(group.id)}
                      >
                        {isExpanded ? <ChevronDown size={16} className="text-slate-500" /> : <ChevronRight size={16} className="text-slate-500" />}
                        <group.icon size={18} className="text-slate-500" />
                        <span className="font-medium">{group.label}</span>
                      </div>
                      <CustomToggle checked={isGroupEnabled} onChange={(v) => updateToggle([group.id, 'enabled'], v)} />
                    </div>
                    
                    {isExpanded && (
                      <div className={`p-2 bg-black/20 ${!isGroupEnabled ? 'opacity-50 grayscale pointer-events-none' : ''}`}>
                        {group.subs.map(sub => (
                          <div key={sub.id} className="flex items-center justify-between p-3 pl-12 hover:bg-white/[0.03] rounded-lg transition-colors">
                            <span className="text-sm text-slate-400">{sub.label}</span>
                            <CustomToggle 
                              checked={editedToggles[group.id]?.[sub.id] ?? true} 
                              onChange={(v) => updateToggle([group.id, sub.id], v)} 
                            />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* SETTINGS TAB */}
        {activeTab === "settings" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Meta */}
            <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl p-5">
              <h3 className="text-lg font-semibold text-white mb-4 border-b border-white/[0.08] pb-2">WhatsApp / Meta</h3>
              <div className="space-y-3">
                {['meta_phone_number_id', 'meta_waba_id', 'meta_access_token', 'meta_webhook_verify_token'].map(k => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-slate-400 font-mono">{k}</span>
                    {isSettingSet(k) ? (
                      <span className="text-emerald-400 flex items-center gap-1"><Check size={14}/> {getSetting(k)?.is_secret ? "••••••••" : "Set"}</span>
                    ) : (
                      <span className="text-slate-600">Not set</span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* TeleCMI */}
            <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl p-5">
              <h3 className="text-lg font-semibold text-white mb-4 border-b border-white/[0.08] pb-2">Telecalling (TeleCMI)</h3>
              <div className="space-y-3">
                {['telecmi_user_id', 'telecmi_callerid', 'telecmi_secret', 'telecmi_recording_base_url'].map(k => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-slate-400 font-mono">{k}</span>
                    {isSettingSet(k) ? (
                      <span className="text-emerald-400 flex items-center gap-1"><Check size={14}/> {getSetting(k)?.is_secret ? "••••••••" : "Set"}</span>
                    ) : (
                      <span className="text-slate-600">Not set</span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* AI */}
            <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl p-5">
              <h3 className="text-lg font-semibold text-white mb-4 border-b border-white/[0.08] pb-2">AI Configuration</h3>
              <div className="space-y-3">
                {['groq_api_key', 'ai_auto_reply_enabled'].map(k => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-slate-400 font-mono">{k}</span>
                    {isSettingSet(k) ? (
                      <span className="text-emerald-400 flex items-center gap-1"><Check size={14}/> {getSetting(k)?.is_secret ? "••••••••" : "Set"}</span>
                    ) : (
                      <span className="text-slate-600">Not set</span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Payments & Bookings */}
            <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl p-5">
              <h3 className="text-lg font-semibold text-white mb-4 border-b border-white/[0.08] pb-2">Bookings & Payments</h3>
              <div className="space-y-3">
                {['razorpay_key_id', 'razorpay_key_secret', 'razorpay_webhook_secret', 'booking_event_name'].map(k => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-slate-400 font-mono">{k}</span>
                    {isSettingSet(k) ? (
                      <span className="text-emerald-400 flex items-center gap-1"><Check size={14}/> {getSetting(k)?.is_secret ? "••••••••" : "Set"}</span>
                    ) : (
                      <span className="text-slate-600">Not set</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TEAM TAB */}
        {activeTab === "team" && teamData && (
          <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden backdrop-blur-xl">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/[0.06] bg-black/20">
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-widest">User / Role</th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-widest">Type</th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-widest">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {teamData.users.map((u, i) => (
                  <tr key={`u-${i}`} className="hover:bg-white/[0.02]">
                    <td className="px-6 py-4">
                      <p className="text-sm font-medium text-white font-mono">{u.user_id.slice(0, 8)}...</p>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-xs px-2 py-1 bg-violet-500/10 text-violet-400 rounded border border-violet-500/20 uppercase">Dashboard {u.role}</span>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-400">{new Date(u.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
                {teamData.callers.map((c, i) => (
                  <tr key={`c-${i}`} className="hover:bg-white/[0.02]">
                    <td className="px-6 py-4">
                      <p className="text-sm font-medium text-white">{c.name}</p>
                      {c.user_id && <p className="text-xs text-slate-500 font-mono mt-1">User ID: {c.user_id.slice(0, 8)}...</p>}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1 items-start">
                        <span className="text-xs px-2 py-1 bg-cyan-500/10 text-cyan-400 rounded border border-cyan-500/20 uppercase">Caller</span>
                        {!c.active && <span className="text-[10px] text-red-400">Inactive</span>}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-400">{new Date(c.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
                {teamData.users.length === 0 && teamData.callers.length === 0 && (
                  <tr><td colSpan={3} className="px-6 py-8 text-center text-slate-500">No team members found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* ACTIVITY TAB */}
        {activeTab === "activity" && activityData && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl p-5 backdrop-blur-md">
                <h3 className="text-slate-400 text-sm font-medium mb-4">Last 7 Days</h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center"><span className="text-slate-300">New Leads</span><span className="text-white font-bold">{activityData.leads_7d}</span></div>
                  <div className="flex justify-between items-center"><span className="text-slate-300">Messages</span><span className="text-white font-bold">{activityData.messages_7d}</span></div>
                  <div className="flex justify-between items-center"><span className="text-slate-300">Calls</span><span className="text-white font-bold">{activityData.calls_7d}</span></div>
                </div>
              </div>
              <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl p-5 backdrop-blur-md">
                <h3 className="text-slate-400 text-sm font-medium mb-4">Last 30 Days</h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center"><span className="text-slate-300">New Leads</span><span className="text-white font-bold">{activityData.leads_30d}</span></div>
                  <div className="flex justify-between items-center"><span className="text-slate-300">Messages</span><span className="text-white font-bold">{activityData.messages_30d}</span></div>
                  <div className="flex justify-between items-center"><span className="text-slate-300">Calls</span><span className="text-white font-bold">{activityData.calls_30d}</span></div>
                </div>
              </div>
            </div>
            
            <h3 className="text-lg font-semibold text-white mt-4">Recent Leads</h3>
            <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden backdrop-blur-xl">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-slate-400 bg-black/20 uppercase border-b border-white/[0.06]">
                  <tr>
                    <th className="px-6 py-4">Name</th>
                    <th className="px-6 py-4">Source</th>
                    <th className="px-6 py-4">Segment</th>
                    <th className="px-6 py-4">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {activityData.recent_leads.map((l: any) => (
                    <tr key={l.id} className="hover:bg-white/[0.02]">
                      <td className="px-6 py-3 font-medium text-white">{l.name}</td>
                      <td className="px-6 py-3 text-slate-300">{l.source}</td>
                      <td className="px-6 py-3 text-slate-300">{l.segment}</td>
                      <td className="px-6 py-3 text-slate-400">{new Date(l.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                  {activityData.recent_leads.length === 0 && (
                    <tr><td colSpan={4} className="px-6 py-8 text-center text-slate-500">No recent leads</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* AUDIT LOG TAB */}
        {activeTab === "audit" && (
          <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden backdrop-blur-xl">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-400 bg-black/20 uppercase border-b border-white/[0.06]">
                <tr>
                  <th className="px-6 py-4">Time</th>
                  <th className="px-6 py-4">Action</th>
                  <th className="px-6 py-4">Actor</th>
                  <th className="px-6 py-4 max-w-[200px]">Metadata</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {auditData.map((log) => (
                  <tr key={log.id} className="hover:bg-white/[0.02]">
                    <td className="px-6 py-4 text-slate-400 whitespace-nowrap">{new Date(log.created_at).toLocaleString()}</td>
                    <td className="px-6 py-4 font-medium text-cyan-400">{log.action}</td>
                    <td className="px-6 py-4 text-slate-300">{log.actor_role}</td>
                    <td className="px-6 py-4 text-xs font-mono text-slate-500 truncate max-w-[200px] hover:whitespace-normal hover:break-all">{JSON.stringify(log.metadata)}</td>
                  </tr>
                ))}
                {auditData.length === 0 && (
                  <tr><td colSpan={4} className="px-6 py-8 text-center text-slate-500">No audit logs found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* DANGER ZONE TAB */}
        {activeTab === "danger" && counts && (
          <div className="space-y-6">
            <div className="p-6 bg-red-500/[0.05] border border-red-500/20 rounded-2xl backdrop-blur-md">
              <div className="flex items-start gap-3 mb-4">
                <AlertTriangle className="text-red-500 shrink-0 mt-1" size={24} />
                <div>
                  <h3 className="text-lg font-bold text-red-400">Danger Zone</h3>
                  <p className="text-sm text-red-400/80 mt-1">Actions here are irreversible. Wiping data permanently deletes it from the database.</p>
                </div>
              </div>

              <div className="space-y-1 mt-6 divide-y divide-red-500/10">
                
                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-white">Leads & Conversations</h4>
                    <p className="text-sm text-slate-400">Deletes: leads, messages, conversations, follow-ups, handovers</p>
                    <p className="text-xs text-red-400 mt-1">{counts.leads} leads, {counts.messages} messages</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-leads", "Leads & Conversations")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition-colors whitespace-nowrap text-sm font-medium"
                  >
                    {wipingSection === "wipe-leads" ? "Wiping..." : "Wipe Leads"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-white">Call Logs</h4>
                    <p className="text-sm text-slate-400">Deletes: call logs, call evaluations</p>
                    <p className="text-xs text-red-400 mt-1">{counts.call_logs} call records</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-calls", "Call Logs")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition-colors whitespace-nowrap text-sm font-medium"
                  >
                    {wipingSection === "wipe-calls" ? "Wiping..." : "Wipe Call Logs"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-white">Broadcasts</h4>
                    <p className="text-sm text-slate-400">Deletes: scheduled broadcasts, recipients, scores, history</p>
                    <p className="text-xs text-red-400 mt-1">{counts.scheduled_broadcasts} broadcasts, {counts.broadcast_recipients} recipients</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-broadcasts", "Broadcasts")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition-colors whitespace-nowrap text-sm font-medium"
                  >
                    {wipingSection === "wipe-broadcasts" ? "Wiping..." : "Wipe Broadcasts"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-white">Knowledge Base</h4>
                    <p className="text-sm text-slate-400">Deletes: knowledge documents and text chunks</p>
                    <p className="text-xs text-red-400 mt-1">{counts.knowledge_documents} documents</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-knowledge", "Knowledge Base")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition-colors whitespace-nowrap text-sm font-medium"
                  >
                    {wipingSection === "wipe-knowledge" ? "Wiping..." : "Wipe Knowledge"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-white">Templates</h4>
                    <p className="text-sm text-slate-400">Deletes: message templates</p>
                    <p className="text-xs text-red-400 mt-1">{counts.templates} templates</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-templates", "Templates")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition-colors whitespace-nowrap text-sm font-medium"
                  >
                    {wipingSection === "wipe-templates" ? "Wiping..." : "Wipe Templates"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-white">Bookings</h4>
                    <p className="text-sm text-slate-400">Deletes: bookings and calendar events</p>
                    <p className="text-xs text-red-400 mt-1">{counts.bookings} bookings</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-bookings", "Bookings")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition-colors whitespace-nowrap text-sm font-medium"
                  >
                    {wipingSection === "wipe-bookings" ? "Wiping..." : "Wipe Bookings"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-white">Notes & Todos</h4>
                    <p className="text-sm text-slate-400">Deletes: lead notes and employee todos</p>
                    <p className="text-xs text-red-400 mt-1">{counts.notes} notes, {counts.todos} todos</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-notes", "Notes & Todos")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition-colors whitespace-nowrap text-sm font-medium"
                  >
                    {wipingSection === "wipe-notes" ? "Wiping..." : "Wipe Notes"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-white">Team Members</h4>
                    <p className="text-sm text-slate-400">Deletes: callers, caller attendance, non-owner users</p>
                    <p className="text-xs text-red-400 mt-1">{counts.callers} callers, {Math.max(0, counts.team_members - 1)} members (excludes owner)</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-team", "Team Members")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition-colors whitespace-nowrap text-sm font-medium"
                  >
                    {wipingSection === "wipe-team" ? "Wiping..." : "Wipe Team"}
                  </button>
                </div>

              </div>
            </div>

            <div className="p-6 bg-red-600/[0.1] border border-red-500/30 rounded-2xl backdrop-blur-md shadow-[0_0_30px_rgba(239,68,68,0.1)]">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div>
                  <h4 className="text-xl font-bold text-red-500 mb-1">DELETE EVERYTHING</h4>
                  <p className="text-sm text-slate-300">Wipe ALL data for this client across every single section above. The tenant account itself is preserved.</p>
                </div>
                <button 
                  onClick={() => handleWipe("wipe-all", "EVERYTHING")}
                  disabled={!!wipingSection}
                  className="px-6 py-3 bg-red-500/20 text-red-400 font-bold border-2 border-red-500/40 rounded-xl hover:bg-red-500/30 hover:border-red-500/60 hover:shadow-[0_0_20px_rgba(239,68,68,0.3)] transition-all whitespace-nowrap flex items-center gap-2"
                >
                  <Shield size={18} /> {wipingSection === "wipe-all" ? "WIPING DATA..." : "DELETE ALL CLIENT DATA"}
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
