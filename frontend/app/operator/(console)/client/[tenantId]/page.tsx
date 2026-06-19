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
  user_id?: string;
};

type AuditEntry = {
  id: string;
  actor_role: string;
  action: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

type ToggleValue = boolean | Record<string, boolean>;
type PageToggles = Record<string, ToggleValue>;

type ClientDetailResponse = {
  tenant: ClientDetail;
  owner_email: string | null;
  settings_summary: SettingsSummary[];
};

type PageTogglesResponse = {
  page_toggles: PageToggles | null;
};

type TeamResponse = {
  users: TeamMember[];
  callers: Caller[];
};

type ActivityResponse = {
  leads_7d: number;
  messages_7d: number;
  calls_7d: number;
  leads_30d: number;
  messages_30d: number;
  calls_30d: number;
  recent_leads: Array<{
    id: string;
    name: string;
    phone: string;
    source: string;
    segment: string;
    score: number;
    created_at: string;
  }>;
};

type AuditLogResponse = {
  entries: AuditEntry[];
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
  const [pageToggles, setPageToggles] = useState<PageToggles | null>(null);
  const [editedToggles, setEditedToggles] = useState<PageToggles | null>(null);
  const [savingToggles, setSavingToggles] = useState(false);
  
  // Expanded sections in toggles
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    knowledge: true, analytics: true, team: true, telecalling: true, settings: true
  });

  // Other tabs data
  const [teamData, setTeamData] = useState<TeamResponse | null>(null);
  const [activityData, setActivityData] = useState<ActivityResponse | null>(null);
  const [auditData, setAuditData] = useState<AuditEntry[]>([]);

  // Danger zone state
  const [wipingSection, setWipingSection] = useState<string | null>(null);

  useEffect(() => {
    async function loadAll() {
      setLoading(true);
      try {
        const [detailRes, countsRes, togglesRes, teamRes, activityRes, auditRes] = await Promise.all([
          apiFetch<ClientDetailResponse>(`/api/v1/operator/clients/${tenantId}/detail`),
          apiFetch<DataCounts>(`/api/v1/operator/clients/${tenantId}/data-counts`),
          apiFetch<PageTogglesResponse>(`/api/v1/operator/clients/${tenantId}/page-toggles`),
          apiFetch<TeamResponse>(`/api/v1/operator/clients/${tenantId}/team`),
          apiFetch<ActivityResponse>(`/api/v1/operator/clients/${tenantId}/activity`),
          apiFetch<AuditLogResponse>(`/api/v1/operator/clients/${tenantId}/audit-log`)
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
    if (!editedToggles) return;
    const newToggles = { ...editedToggles };
    if (path.length === 1) {
      newToggles[path[0]] = value;
    } else {
      const parent = newToggles[path[0]];
      const parentObj = (parent && typeof parent === 'object') ? (parent as Record<string, boolean>) : {};
      newToggles[path[0]] = { ...parentObj, [path[1]]: value };
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
      } ${checked ? 'bg-[#5b21b6]' : 'bg-[#e8e3db]'}`}
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
      const res = await apiFetch<Record<string, unknown>>(`/api/v1/operator/clients/${tenantId}/${endpoint}`, { method: "POST" });
      const deletedCounts = res.deleted as Record<string, number>;
      alert(`Successfully wiped ${sectionName}.\n\nDeleted records:\n${Object.entries(deletedCounts).map(([k,v]) => `${k}: ${v}`).join('\n')}`);
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
        <div className="text-[#5b21b6] flex flex-col items-center">
          <div className="w-8 h-8 border-4 border-[#5b21b6]/20 border-t-[#5b21b6] rounded-full animate-spin mb-4"></div>
          <span className="text-[#a8a29e] font-medium">Loading client details...</span>
        </div>
      </div>
    );
  }

  if (error || !client) {
    return (
      <div className="p-6 bg-rose-50 border border-rose-200 rounded-[1.25rem] text-rose-800 font-manrope shadow-sm">
        <h2 className="text-xl font-bold mb-2">Error Loading Client</h2>
        <p className="text-rose-700">{error || "Client not found."}</p>
        <button 
          onClick={() => router.push('/operator')} 
          className="mt-4 px-4 py-2 bg-rose-600 hover:bg-rose-700 text-sm font-semibold rounded-xl text-white transition-all shadow-sm"
        >
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
    <div className="font-manrope">
      {/* Header */}
      <div className="mb-8">
        <button 
          onClick={() => router.push('/operator')}
          className="flex items-center gap-2 text-sm text-[#a8a29e] hover:text-[#1c1917] transition-colors mb-4"
        >
          <ArrowLeft size={16} /> Back to Clients
        </button>
        
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-[#1c1917] tracking-tight flex items-center gap-3">
              {client.name}
              <span className={`text-xs px-2.5 py-1 rounded-md font-semibold border ${
                client.status === "active" 
                  ? "bg-emerald-55 text-emerald-700 border-emerald-200 bg-emerald-50" 
                  : "bg-rose-50 text-rose-700 border-rose-200"
              }`}>
                {client.status.toUpperCase()}
              </span>
            </h1>
            <div className="flex items-center gap-4 mt-2 text-sm">
              <span className="text-[#78716c] font-mono bg-[#f0ece4]/60 px-2 py-0.5 rounded">ID: {client.id}</span>
              <span className="text-[#78716c]">{ownerEmail || "No owner email"}</span>
              <span className="text-[#78716c]">Created {new Date(client.created_at).toLocaleDateString()}</span>
            </div>
          </div>
          
          <div className="bg-[#f5f3ff] border border-violet-200 px-4 py-2 rounded-xl">
            <p className="text-xs text-[#5b21b6]/70 uppercase tracking-wider font-semibold mb-0.5">Service Package</p>
            <p className="text-sm font-semibold text-[#5b21b6]">{SERVICE_LABELS[featuresToService(client.enabled_features)] ?? "Custom"}</p>
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
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all whitespace-nowrap border
                ${isActive 
                  ? (tab.isDanger ? 'bg-rose-100 text-rose-700 border-rose-200 shadow-sm font-bold' : 'bg-[#5b21b6] text-white border-[#5b21b6] shadow-sm font-bold') 
                  : (tab.isDanger ? 'text-rose-600 border-transparent hover:bg-rose-50' : 'text-[#78716c] border-transparent hover:text-[#1c1917] hover:bg-[#f0ece4]/50')
                }`}
            >
              <Icon size={16} />
              {tab.label}
              {tab.isDanger && <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse ml-1"></span>}
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
              <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
                <p className="text-sm text-[#78716c] font-medium mb-1">Total Leads</p>
                <p className="text-3xl font-bold text-[#1c1917]">{counts.leads.toLocaleString()}</p>
              </div>
              <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
                <p className="text-sm text-[#78716c] font-medium mb-1">Messages</p>
                <p className="text-3xl font-bold text-[#1c1917]">{counts.messages.toLocaleString()}</p>
              </div>
              <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
                <p className="text-sm text-[#78716c] font-medium mb-1">Call Logs</p>
                <p className="text-3xl font-bold text-[#1c1917]">{counts.call_logs.toLocaleString()}</p>
              </div>
              <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
                <p className="text-sm text-[#78716c] font-medium mb-1">Team & Callers</p>
                <p className="text-3xl font-bold text-[#1c1917]">{counts.team_members + counts.callers}</p>
              </div>
            </div>

            <h3 className="text-lg font-bold text-[#1c1917] mt-8 mb-4">Integration Health</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { name: "WhatsApp (Meta)", connected: isSettingSet("meta_phone_number_id") && isSettingSet("meta_access_token") },
                { name: "Telecalling (TeleCMI)", connected: isSettingSet("telecmi_user_id") && isSettingSet("telecmi_secret") },
                { name: "Groq AI", connected: isSettingSet("groq_api_key") },
                { name: "Payments (Razorpay)", connected: isSettingSet("razorpay_key_id") }
              ].map(int => (
                <div key={int.name} className="bg-white border border-[#e8e3db] rounded-xl p-4 flex items-center justify-between shadow-sm">
                  <span className="text-[#1c1917] font-medium">{int.name}</span>
                  {int.connected ? (
                    <span className="flex items-center gap-1.5 text-sm text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200">
                      <CheckCircle size={14} /> Connected
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-sm text-[#a8a29e] bg-[#f0ece4]/30 px-2.5 py-1 rounded-md border border-[#e8e3db]">
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
          <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] overflow-hidden shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
            <div className="p-6 border-b border-[#e8e3db] flex items-center justify-between bg-[#f0ece4]/20">
              <div>
                <h3 className="text-lg font-bold text-[#1c1917]">Feature Toggles</h3>
                <p className="text-sm text-[#78716c]">Control which pages and sections are visible in the client&apos;s sidebar.</p>
              </div>
              <button 
                onClick={handleSaveToggles}
                disabled={!hasTogglesChanged || savingToggles}
                className="flex items-center gap-2 px-4 py-2 bg-[#5b21b6] hover:bg-[#4c1d95] text-white text-sm font-semibold rounded-xl disabled:opacity-50 disabled:grayscale transition-all"
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
                <div key={item.id} className="flex items-center justify-between p-4 hover:bg-[#f0ece4]/20 border-b border-[#e8e3db]/40 last:border-0 rounded-xl transition-colors">
                  <div className="flex items-center gap-3 text-[#1c1917]">
                    <item.icon size={18} className="text-[#a8a29e]" />
                    <span className="font-semibold">{item.label}</span>
                  </div>
                  <CustomToggle 
                    checked={
                      editedToggles 
                        ? (typeof editedToggles[item.id] === 'boolean' ? (editedToggles[item.id] as boolean) : true)
                        : true
                    } 
                    onChange={(v) => updateToggle([item.id], v)} 
                  />
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
                const groupVal = editedToggles?.[group.id];
                const isGroupEnabled = (groupVal && typeof groupVal === 'object' && 'enabled' in groupVal)
                  ? (groupVal.enabled as boolean ?? true)
                  : true;
                const isExpanded = expandedSections[group.id];
                return (
                  <div key={group.id} className="border border-[#e8e3db] rounded-xl overflow-hidden my-2">
                    <div className="flex items-center justify-between p-4 bg-[#f0ece4]/10 hover:bg-[#f0ece4]/30 transition-colors">
                      <div 
                        className="flex items-center gap-3 text-[#1c1917] cursor-pointer flex-1"
                        onClick={() => toggleSection(group.id)}
                      >
                        {isExpanded ? <ChevronDown size={16} className="text-[#a8a29e]" /> : <ChevronRight size={16} className="text-[#a8a29e]" />}
                        <group.icon size={18} className="text-[#a8a29e]" />
                        <span className="font-semibold">{group.label}</span>
                      </div>
                      <CustomToggle checked={isGroupEnabled} onChange={(v) => updateToggle([group.id, 'enabled'], v)} />
                    </div>
                    
                    {isExpanded && (
                      <div className={`p-2 bg-[#f0ece4]/20 ${!isGroupEnabled ? 'opacity-50 grayscale pointer-events-none' : ''}`}>
                        {group.subs.map(sub => {
                          const subVal = (groupVal && typeof groupVal === 'object') ? groupVal[sub.id] : true;
                          const isSubEnabled = typeof subVal === 'boolean' ? subVal : true;
                          return (
                            <div key={sub.id} className="flex items-center justify-between p-3 pl-12 hover:bg-[#f0ece4]/40 border-t border-[#e8e3db]/20 transition-colors">
                              <span className="text-sm text-[#78716c]">{sub.label}</span>
                              <CustomToggle 
                                checked={isSubEnabled} 
                                onChange={(v) => updateToggle([group.id, sub.id], v)} 
                              />
                            </div>
                          );
                        })}
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
            <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
              <h3 className="text-lg font-bold text-[#1c1917] mb-4 border-b border-[#e8e3db] pb-2">WhatsApp / Meta</h3>
              <div className="space-y-3">
                {['meta_phone_number_id', 'meta_waba_id', 'meta_access_token', 'meta_webhook_verify_token'].map(k => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-[#78716c] font-mono">{k}</span>
                    {isSettingSet(k) ? (
                      <span className="text-emerald-700 font-semibold flex items-center gap-1"><Check size={14}/> {getSetting(k)?.is_secret ? "••••••••" : "Set"}</span>
                    ) : (
                      <span className="text-[#a8a29e]">Not set</span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* TeleCMI */}
            <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
              <h3 className="text-lg font-bold text-[#1c1917] mb-4 border-b border-[#e8e3db] pb-2">Telecalling (TeleCMI)</h3>
              <div className="space-y-3">
                {['telecmi_user_id', 'telecmi_callerid', 'telecmi_secret', 'telecmi_recording_base_url'].map(k => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-[#78716c] font-mono">{k}</span>
                    {isSettingSet(k) ? (
                      <span className="text-emerald-700 font-semibold flex items-center gap-1"><Check size={14}/> {getSetting(k)?.is_secret ? "••••••••" : "Set"}</span>
                    ) : (
                      <span className="text-[#a8a29e]">Not set</span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* AI */}
            <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
              <h3 className="text-lg font-bold text-[#1c1917] mb-4 border-b border-[#e8e3db] pb-2">AI Configuration</h3>
              <div className="space-y-3">
                {['groq_api_key', 'ai_auto_reply_enabled'].map(k => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-[#78716c] font-mono">{k}</span>
                    {isSettingSet(k) ? (
                      <span className="text-emerald-700 font-semibold flex items-center gap-1"><Check size={14}/> {getSetting(k)?.is_secret ? "••••••••" : "Set"}</span>
                    ) : (
                      <span className="text-[#a8a29e]">Not set</span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Payments & Bookings */}
            <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
              <h3 className="text-lg font-bold text-[#1c1917] mb-4 border-b border-[#e8e3db] pb-2">Bookings & Payments</h3>
              <div className="space-y-3">
                {['razorpay_key_id', 'razorpay_key_secret', 'razorpay_webhook_secret', 'booking_event_name'].map(k => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-[#78716c] font-mono">{k}</span>
                    {isSettingSet(k) ? (
                      <span className="text-emerald-700 font-semibold flex items-center gap-1"><Check size={14}/> {getSetting(k)?.is_secret ? "••••••••" : "Set"}</span>
                    ) : (
                      <span className="text-[#a8a29e]">Not set</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TEAM TAB */}
        {activeTab === "team" && teamData && (
          <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] overflow-hidden shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[#e8e3db] bg-[#f0ece4]/20">
                  <th className="px-6 py-4 text-left text-xs font-semibold text-[#78716c] uppercase tracking-widest">User / Role</th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-[#78716c] uppercase tracking-widest">Type</th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-[#78716c] uppercase tracking-widest">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#e8e3db]/50">
                {teamData.users.map((u, i) => (
                  <tr key={`u-${i}`} className="hover:bg-[#f0ece4]/10 transition-colors">
                    <td className="px-6 py-4">
                      <p className="text-sm font-semibold text-[#1c1917] font-mono">{u.user_id.slice(0, 8)}...</p>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-xs px-2 py-1 bg-violet-50 text-[#5b21b6] rounded border border-violet-200 uppercase font-semibold">Dashboard {u.role}</span>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#78716c]">{new Date(u.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
                {teamData.callers.map((c, i) => (
                  <tr key={`c-${i}`} className="hover:bg-[#f0ece4]/10 transition-colors">
                    <td className="px-6 py-4">
                      <p className="text-sm font-semibold text-[#1c1917]">{c.name}</p>
                      {c.user_id && <p className="text-xs text-[#a8a29e] font-mono mt-1">User ID: {c.user_id.slice(0, 8)}...</p>}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1 items-start">
                        <span className="text-xs px-2 py-1 bg-blue-50 text-blue-700 rounded border border-blue-200 uppercase font-semibold">Caller</span>
                        {!c.active && <span className="text-[10px] text-rose-600 font-semibold">Inactive</span>}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#78716c]">{new Date(c.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
                {teamData.users.length === 0 && teamData.callers.length === 0 && (
                  <tr><td colSpan={3} className="px-6 py-8 text-center text-[#a8a29e]">No team members found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* ACTIVITY TAB */}
        {activeTab === "activity" && activityData && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-sm font-manrope">
                <h3 className="text-[#78716c] text-sm font-bold mb-4">Last 7 Days</h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center"><span className="text-[#78716c]">New Leads</span><span className="text-[#1c1917] font-bold">{activityData.leads_7d}</span></div>
                  <div className="flex justify-between items-center"><span className="text-[#78716c]">Messages</span><span className="text-[#1c1917] font-bold">{activityData.messages_7d}</span></div>
                  <div className="flex justify-between items-center"><span className="text-[#78716c]">Calls</span><span className="text-[#1c1917] font-bold">{activityData.calls_7d}</span></div>
                </div>
              </div>
              <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] p-5 shadow-sm font-manrope">
                <h3 className="text-[#78716c] text-sm font-bold mb-4">Last 30 Days</h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center"><span className="text-[#78716c]">New Leads</span><span className="text-[#1c1917] font-bold">{activityData.leads_30d}</span></div>
                  <div className="flex justify-between items-center"><span className="text-[#78716c]">Messages</span><span className="text-[#1c1917] font-bold">{activityData.messages_30d}</span></div>
                  <div className="flex justify-between items-center"><span className="text-[#78716c]">Calls</span><span className="text-[#1c1917] font-bold">{activityData.calls_30d}</span></div>
                </div>
              </div>
            </div>
            
            <h3 className="text-lg font-bold text-[#1c1917] mt-4 font-manrope">Recent Leads</h3>
            <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] overflow-hidden shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)]">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-[#78716c] bg-[#f0ece4]/20 uppercase border-b border-[#e8e3db]">
                  <tr>
                    <th className="px-6 py-4">Name</th>
                    <th className="px-6 py-4">Source</th>
                    <th className="px-6 py-4">Segment</th>
                    <th className="px-6 py-4">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#e8e3db]/50">
                  {activityData.recent_leads.map((l) => (
                    <tr key={l.id} className="hover:bg-[#f0ece4]/10 transition-colors">
                      <td className="px-6 py-3 font-semibold text-[#1c1917]">{l.name}</td>
                      <td className="px-6 py-3 text-[#78716c]">{l.source}</td>
                      <td className="px-6 py-3 text-[#78716c]">{l.segment}</td>
                      <td className="px-6 py-3 text-[#a8a29e]">{new Date(l.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                  {activityData.recent_leads.length === 0 && (
                    <tr><td colSpan={4} className="px-6 py-8 text-center text-[#a8a29e]">No recent leads</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* AUDIT LOG TAB */}
        {activeTab === "audit" && (
          <div className="bg-white border border-[#e8e3db] rounded-[1.25rem] overflow-hidden shadow-[0_2px_16px_-2px_rgba(28,25,23,.07),0_1px_4px_-1px_rgba(28,25,23,.04)] font-manrope">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-[#78716c] bg-[#f0ece4]/20 uppercase border-b border-[#e8e3db]">
                <tr>
                  <th className="px-6 py-4">Time</th>
                  <th className="px-6 py-4">Action</th>
                  <th className="px-6 py-4">Actor</th>
                  <th className="px-6 py-4 max-w-[200px]">Metadata</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#e8e3db]/50">
                {auditData.map((log) => (
                  <tr key={log.id} className="hover:bg-[#f0ece4]/10 transition-colors">
                    <td className="px-6 py-4 text-[#a8a29e] whitespace-nowrap">{new Date(log.created_at).toLocaleString()}</td>
                    <td className="px-6 py-4 font-semibold text-[#5b21b6]">{log.action}</td>
                    <td className="px-6 py-4 text-[#78716c]">{log.actor_role}</td>
                    <td className="px-6 py-4 text-xs font-mono text-[#a8a29e] truncate max-w-[200px] hover:whitespace-normal hover:break-all">{JSON.stringify(log.metadata)}</td>
                  </tr>
                ))}
                {auditData.length === 0 && (
                  <tr><td colSpan={4} className="px-6 py-8 text-center text-[#a8a29e]">No audit logs found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* DANGER ZONE TAB */}
        {activeTab === "danger" && counts && (
          <div className="space-y-6">
            <div className="p-6 bg-rose-50 border border-rose-200 rounded-[1.25rem] shadow-sm font-manrope">
              <div className="flex items-start gap-3 mb-4">
                <AlertTriangle className="text-rose-600 shrink-0 mt-1" size={24} />
                <div>
                  <h3 className="text-lg font-bold text-rose-800">Danger Zone</h3>
                  <p className="text-sm text-rose-700 mt-1">Actions here are irreversible. Wiping data permanently deletes it from the database.</p>
                </div>
              </div>

              <div className="space-y-1 mt-6 divide-y divide-rose-200">
                
                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-[#1c1917]">Leads & Conversations</h4>
                    <p className="text-sm text-[#78716c]">Deletes: leads, messages, conversations, follow-ups, handovers</p>
                    <p className="text-xs text-rose-600 font-semibold mt-1">{counts.leads} leads, {counts.messages} messages</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-leads", "Leads & Conversations")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-100 transition-colors whitespace-nowrap text-sm font-semibold"
                  >
                    {wipingSection === "wipe-leads" ? "Wiping..." : "Wipe Leads"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-[#1c1917]">Call Logs</h4>
                    <p className="text-sm text-[#78716c]">Deletes: call logs, call evaluations</p>
                    <p className="text-xs text-rose-600 font-semibold mt-1">{counts.call_logs} call records</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-calls", "Call Logs")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-100 transition-colors whitespace-nowrap text-sm font-semibold"
                  >
                    {wipingSection === "wipe-calls" ? "Wiping..." : "Wipe Call Logs"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-[#1c1917]">Broadcasts</h4>
                    <p className="text-sm text-[#78716c]">Deletes: scheduled broadcasts, recipients, scores, history</p>
                    <p className="text-xs text-rose-600 font-semibold mt-1">{counts.scheduled_broadcasts} broadcasts, {counts.broadcast_recipients} recipients</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-broadcasts", "Broadcasts")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-100 transition-colors whitespace-nowrap text-sm font-semibold"
                  >
                    {wipingSection === "wipe-broadcasts" ? "Wiping..." : "Wipe Broadcasts"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-[#1c1917]">Knowledge Base</h4>
                    <p className="text-sm text-[#78716c]">Deletes: knowledge documents and text chunks</p>
                    <p className="text-xs text-rose-600 font-semibold mt-1">{counts.knowledge_documents} documents</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-knowledge", "Knowledge Base")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-100 transition-colors whitespace-nowrap text-sm font-semibold"
                  >
                    {wipingSection === "wipe-knowledge" ? "Wiping..." : "Wipe Knowledge"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-[#1c1917]">Templates</h4>
                    <p className="text-sm text-[#78716c]">Deletes: message templates</p>
                    <p className="text-xs text-rose-600 font-semibold mt-1">{counts.templates} templates</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-templates", "Templates")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-100 transition-colors whitespace-nowrap text-sm font-semibold"
                  >
                    {wipingSection === "wipe-templates" ? "Wiping..." : "Wipe Templates"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-[#1c1917]">Bookings</h4>
                    <p className="text-sm text-[#78716c]">Deletes: bookings and calendar events</p>
                    <p className="text-xs text-rose-600 font-semibold mt-1">{counts.bookings} bookings</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-bookings", "Bookings")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-100 transition-colors whitespace-nowrap text-sm font-semibold"
                  >
                    {wipingSection === "wipe-bookings" ? "Wiping..." : "Wipe Bookings"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-[#1c1917]">Notes & Todos</h4>
                    <p className="text-sm text-[#78716c]">Deletes: lead notes and employee todos</p>
                    <p className="text-xs text-rose-600 font-semibold mt-1">{counts.notes} notes, {counts.todos} todos</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-notes", "Notes & Todos")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-100 transition-colors whitespace-nowrap text-sm font-semibold"
                  >
                    {wipingSection === "wipe-notes" ? "Wiping..." : "Wipe Notes"}
                  </button>
                </div>

                <div className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-[#1c1917]">Team Members</h4>
                    <p className="text-sm text-[#78716c]">Deletes: callers, caller attendance, non-owner users</p>
                    <p className="text-xs text-rose-600 font-semibold mt-1">{counts.callers} callers, {Math.max(0, counts.team_members - 1)} members (excludes owner)</p>
                  </div>
                  <button 
                    onClick={() => handleWipe("wipe-team", "Team Members")}
                    disabled={!!wipingSection}
                    className="px-4 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-100 transition-colors whitespace-nowrap text-sm font-semibold"
                  >
                    {wipingSection === "wipe-team" ? "Wiping..." : "Wipe Team"}
                  </button>
                </div>

              </div>
            </div>

            <div className="p-6 bg-rose-100 border border-rose-300 rounded-[1.25rem] shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div>
                  <h4 className="text-xl font-bold text-rose-700 mb-1">DELETE EVERYTHING</h4>
                  <p className="text-sm text-[#78716c]">Wipe ALL data for this client across every single section above. The tenant account itself is preserved.</p>
                </div>
                <button 
                  onClick={() => handleWipe("wipe-all", "EVERYTHING")}
                  disabled={!!wipingSection}
                  className="px-6 py-3 bg-rose-600 hover:bg-rose-700 text-white font-bold rounded-xl transition-all whitespace-nowrap flex items-center gap-2 shadow-sm"
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
