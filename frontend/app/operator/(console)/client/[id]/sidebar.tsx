"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard, MessageSquare, Users, RadioTower, Upload,
  FileCheck, Layers, BookOpen, BarChart2, Phone, Calendar, StickyNote,
  Wrench, Activity, Settings, Database, ChevronDown, ChevronRight,
  ArrowLeft,
} from "lucide-react";

export type SectionType =
  | "overview" | "inbox" | "conversations" | "segments"
  | "inbound" | "outbound" | "templates" | "numbers"
  | "knowledge" | "analytics" | "team"
  | "tc-upload" | "tc-dialer" | "tc-scheduled" | "tc-notes"
  | "config" | "health" | "management" | "data-ops";

type NavItem = {
  key: SectionType;
  icon: typeof LayoutDashboard;
  label: string;
  toggleKey?: string;
  dependsOn?: "outbound" | "messaging";
};

const PRODUCT_NAV: NavItem[] = [
  { key: "overview", icon: LayoutDashboard, label: "Dashboard" },
  { key: "conversations", icon: MessageSquare, label: "Conversations", dependsOn: "messaging" },
  { key: "segments", icon: Users, label: "Segments", dependsOn: "messaging" },
  { key: "inbound", icon: RadioTower, label: "Inbound Leads", toggleKey: "inbound_leads" },
  { key: "outbound", icon: Upload, label: "Outbound Leads", toggleKey: "outbound_leads" },
  { key: "templates", icon: FileCheck, label: "Templates", dependsOn: "outbound" },
  { key: "numbers", icon: Layers, label: "Numbers Pool", dependsOn: "messaging" },
  { key: "knowledge", icon: BookOpen, label: "Knowledge Base", dependsOn: "messaging" },
  { key: "analytics", icon: BarChart2, label: "Analytics", dependsOn: "messaging" },
  { key: "team", icon: Users, label: "Team" },
];

const TC_SUB_NAV: { key: SectionType; icon: typeof Phone; label: string; featureKey: string }[] = [
  { key: "tc-upload", icon: Upload, label: "Upload", featureKey: "telecalling.upload" },
  { key: "tc-dialer", icon: Phone, label: "Dialer", featureKey: "telecalling.dialer" },
  { key: "tc-scheduled", icon: Calendar, label: "Scheduled Calls", featureKey: "telecalling.scheduled" },
  { key: "tc-notes", icon: StickyNote, label: "Call Notes", featureKey: "telecalling.notes" },
];

const OPERATOR_NAV: NavItem[] = [
  { key: "config", icon: Wrench, label: "Configuration" },
  { key: "health", icon: Activity, label: "Health" },
  { key: "management", icon: Settings, label: "Management" },
  { key: "data-ops", icon: Database, label: "Data Ops" },
];

interface SidebarProps {
  activeSection: SectionType;
  onSectionChange: (s: SectionType) => void;
  enabledFeatures: string[];
  onToggleFeature: (feature: string) => void;
  featureUpdating: boolean;
  tenantName: string;
}

export function ClientDetailSidebar({
  activeSection, onSectionChange, enabledFeatures, onToggleFeature, featureUpdating, tenantName
}: SidebarProps) {
  const [tcExpanded, setTcExpanded] = useState(true);
  const router = useRouter();

  const isEnabled = (key: string) => enabledFeatures.includes(key);
  const outboundOn = isEnabled("outbound_leads");
  const inboundOn = isEnabled("inbound_leads");
  const messagingOn = outboundOn || inboundOn;

  function isItemEnabled(item: NavItem): boolean {
    if (item.toggleKey) return isEnabled(item.toggleKey);
    if (item.dependsOn === "outbound") return outboundOn;
    if (item.dependsOn === "messaging") return messagingOn;
    return true;
  }

  function FeatureToggle({ featureKey, disabled }: { featureKey: string; disabled?: boolean }) {
    const on = isEnabled(featureKey);
    return (
      <button
        disabled={featureUpdating || disabled}
        onClick={(e) => { e.stopPropagation(); onToggleFeature(featureKey); }}
        className={`relative w-9 h-5 rounded-full transition-all duration-200 flex-shrink-0 ${
          on ? "bg-primary" : "bg-ink-muted/30"
        } ${(featureUpdating || disabled) ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform duration-200 shadow-sm ${on ? "translate-x-4" : ""}`} />
      </button>
    );
  }

  function NavItemRow({ item }: { item: NavItem }) {
    const active = activeSection === item.key;
    const enabled = isItemEnabled(item);

    return (
      <div
        onClick={() => onSectionChange(item.key)}
        className={`flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer transition-all duration-150 group ${
          active ? "bg-[#f5f3ff] text-[#5b21b6]" : !enabled ? "opacity-40" : "text-[#1c1917] hover:bg-[#f0ece4]"
        }`}
      >
        <div className="flex items-center gap-3 min-w-0">
          <item.icon size={16} className={`flex-shrink-0 ${active ? "text-[#5b21b6]" : ""}`} />
          <span className={`text-sm font-semibold truncate ${!enabled && !active ? "line-through" : ""}`}>{item.label}</span>
        </div>
        {item.toggleKey && <FeatureToggle featureKey={item.toggleKey} />}
      </div>
    );
  }

  function TcSubRow({ item, indent }: { item: typeof TC_SUB_NAV[0]; indent?: boolean }) {
    const active = activeSection === item.key;
    const enabled = isEnabled(item.featureKey);

    return (
      <div
        onClick={() => onSectionChange(item.key)}
        className={`flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer transition-all duration-150 group ${
          indent ? "ml-4" : ""
        } ${active ? "bg-[#f5f3ff] text-[#5b21b6]" : !enabled ? "opacity-40" : "text-[#1c1917] hover:bg-[#f0ece4]"}`}
      >
        <div className="flex items-center gap-3 min-w-0">
          <item.icon size={16} className={`flex-shrink-0 ${active ? "text-[#5b21b6]" : ""}`} />
          <span className={`text-sm font-semibold truncate ${!enabled && !active ? "line-through" : ""}`}>{item.label}</span>
        </div>
        <FeatureToggle featureKey={item.featureKey} disabled={!isEnabled("telecalling")} />
      </div>
    );
  }

  return (
    <aside className="fixed left-0 top-16 h-[calc(100vh-4rem)] w-[220px] bg-background border-r border-[#e8e3db] flex flex-col z-30 select-none">
      <div className="px-4 py-4 border-b border-[#e8e3db]">
        <button
          onClick={() => router.push("/operator")}
          className="flex items-center gap-1.5 text-xs text-ink-secondary hover:text-ink transition-colors mb-2"
        >
          <ArrowLeft size={12} /> Back to Clients
        </button>
        <p className="text-sm font-bold text-ink truncate">{tenantName}</p>
      </div>

      <div className="flex-grow overflow-y-auto px-3 py-3 space-y-0.5 scrollbar-thin">
        {PRODUCT_NAV.map(item => (
          <NavItemRow key={item.key} item={item} />
        ))}

        {/* Telecalling group */}
        <div>
          <div
            onClick={() => setTcExpanded(!tcExpanded)}
            className={`flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer transition-all duration-150 ${
              ["tc-upload", "tc-dialer", "tc-scheduled", "tc-notes"].includes(activeSection)
                ? "bg-[#f5f3ff] text-[#5b21b6]" : isEnabled("telecalling") ? "text-[#1c1917] hover:bg-[#f0ece4]" : "text-[#1c1917] opacity-40"
            }`}
          >
            <div className="flex items-center gap-3">
              <Phone size={16} />
              <span className="text-sm font-semibold">Telecalling</span>
            </div>
            <div className="flex items-center gap-2">
              <FeatureToggle featureKey="telecalling" />
              {tcExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </div>
          </div>
          {tcExpanded && isEnabled("telecalling") && (
            <div className="mt-0.5 space-y-0.5">
              {TC_SUB_NAV.map(item => (
                <TcSubRow key={item.key} item={item} indent />
              ))}
            </div>
          )}
        </div>

        <div className="pt-3 mt-3 border-t border-[#e8e3db]">
          <p className="px-3 py-1 text-[10px] font-semibold text-ink-muted uppercase tracking-widest">Operator</p>
          {OPERATOR_NAV.map(item => (
            <NavItemRow key={item.key} item={item} />
          ))}
        </div>
      </div>
    </aside>
  );
}
