"use client";
import { useState } from "react";
import {
  LayoutDashboard, Inbox, MessageSquare, Users, RadioTower, Upload,
  FileCheck, Layers, BookOpen, BarChart2, Phone, Calendar, StickyNote,
  Wrench, Activity, Settings, Database, ChevronDown, ChevronRight,
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
  featureKey?: string;
  alwaysOn?: boolean;
};

const PRODUCT_NAV: NavItem[] = [
  { key: "overview", icon: LayoutDashboard, label: "Overview", alwaysOn: true },
  { key: "inbox", icon: Inbox, label: "Inbox", featureKey: "whatsapp" },
  { key: "conversations", icon: MessageSquare, label: "Conversations", alwaysOn: true },
  { key: "segments", icon: Users, label: "Segments", alwaysOn: true },
  { key: "inbound", icon: RadioTower, label: "Inbound Leads", featureKey: "whatsapp" },
  { key: "outbound", icon: Upload, label: "Outbound Leads", featureKey: "whatsapp" },
  { key: "templates", icon: FileCheck, label: "Templates", featureKey: "whatsapp" },
  { key: "numbers", icon: Layers, label: "Numbers Pool", featureKey: "whatsapp" },
  { key: "knowledge", icon: BookOpen, label: "Knowledge Base", alwaysOn: true },
  { key: "analytics", icon: BarChart2, label: "Analytics", featureKey: "analytics" },
  { key: "team", icon: Users, label: "Team", alwaysOn: true },
];

const TC_SUB_NAV: { key: SectionType; icon: typeof Phone; label: string; featureKey: string }[] = [
  { key: "tc-upload", icon: Upload, label: "Upload", featureKey: "telecalling.upload" },
  { key: "tc-dialer", icon: Phone, label: "Dialer", featureKey: "telecalling.dialer" },
  { key: "tc-scheduled", icon: Calendar, label: "Scheduled Calls", featureKey: "telecalling.scheduled" },
  { key: "tc-notes", icon: StickyNote, label: "Call Notes", featureKey: "telecalling.notes" },
];

const OPERATOR_NAV: NavItem[] = [
  { key: "config", icon: Wrench, label: "Configuration", alwaysOn: true },
  { key: "health", icon: Activity, label: "Health", alwaysOn: true },
  { key: "management", icon: Settings, label: "Management", alwaysOn: true },
  { key: "data-ops", icon: Database, label: "Data Ops", alwaysOn: true },
];

interface SidebarProps {
  activeSection: SectionType;
  onSectionChange: (s: SectionType) => void;
  enabledFeatures: string[];
  onToggleFeature: (feature: string) => void;
  featureUpdating: boolean;
}

export function ClientDetailSidebar({
  activeSection, onSectionChange, enabledFeatures, onToggleFeature, featureUpdating
}: SidebarProps) {
  const [tcExpanded, setTcExpanded] = useState(true);

  const isEnabled = (key: string) => enabledFeatures.includes(key);

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

  function NavItemRow({ item, indent }: { item: NavItem | typeof TC_SUB_NAV[0]; indent?: boolean }) {
    const active = activeSection === item.key;
    const featureKey = "featureKey" in item ? item.featureKey : undefined;
    const disabled = featureKey ? !isEnabled(featureKey) : false;
    const alwaysOn = "alwaysOn" in item && item.alwaysOn;

    return (
      <div
        onClick={() => onSectionChange(item.key)}
        className={`flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer transition-all duration-200 group ${
          indent ? "ml-4" : ""
        } ${active ? "bg-primary-light text-primary" : disabled ? "opacity-40" : "text-ink-secondary hover:bg-surface-mid hover:text-ink"}`}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <item.icon size={16} className="flex-shrink-0" />
          <span className={`text-sm font-medium truncate ${disabled && !active ? "line-through" : ""}`}>{item.label}</span>
        </div>
        {featureKey && !alwaysOn && <FeatureToggle featureKey={featureKey} disabled={featureKey.startsWith("telecalling.") && !isEnabled("telecalling")} />}
      </div>
    );
  }

  return (
    <div className="w-[200px] flex-shrink-0 border-r border-border-subtle pr-2 space-y-1">
      {/* Product sections */}
      {PRODUCT_NAV.map(item => (
        <NavItemRow key={item.key} item={item} />
      ))}

      {/* Telecalling group */}
      <div>
        <div
          onClick={() => setTcExpanded(!tcExpanded)}
          className={`flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer transition-all duration-200 ${
            ["tc-upload", "tc-dialer", "tc-scheduled", "tc-notes"].includes(activeSection)
              ? "bg-primary-light text-primary" : isEnabled("telecalling") ? "text-ink-secondary hover:bg-surface-mid hover:text-ink" : "text-ink-secondary opacity-40"
          }`}
        >
          <div className="flex items-center gap-2.5">
            <Phone size={16} />
            <span className="text-sm font-medium">Telecalling</span>
          </div>
          <div className="flex items-center gap-2">
            <FeatureToggle featureKey="telecalling" />
            {tcExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </div>
        </div>
        {tcExpanded && isEnabled("telecalling") && (
          <div className="mt-1 space-y-0.5">
            {TC_SUB_NAV.map(item => (
              <NavItemRow key={item.key} item={item} indent />
            ))}
          </div>
        )}
      </div>

      {/* Divider + Operator sections */}
      <div className="pt-3 mt-3 border-t border-border-subtle">
        <p className="px-3 py-1 text-[10px] font-semibold text-ink-muted uppercase tracking-widest">Operator</p>
        {OPERATOR_NAV.map(item => (
          <NavItemRow key={item.key} item={item} />
        ))}
      </div>
    </div>
  );
}
